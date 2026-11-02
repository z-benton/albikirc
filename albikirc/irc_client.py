from __future__ import annotations

import socket
import ssl
import threading
from dataclasses import dataclass, field
from typing import Optional
import base64
import time

from .event_bus import event_bus


@dataclass
class IRCClient:
    """Simple threaded IRC client with optional TLS.

    Callbacks are invoked from the network thread; the UI layer should marshal
    updates to the main thread (e.g., via wx.CallAfter).
    """

    connected: bool = field(default=False, init=False)
    nick: str | None = field(default=None, init=False)
    real_name: str | None = field(default=None, init=False)
    # Auth / TLS extras
    sasl_enabled: bool = field(default=False)
    sasl_username: str | None = field(default=None)
    sasl_password: str | None = field(default=None)
    tls_client_certfile: str | None = field(default=None)
    tls_client_keyfile: str | None = field(default=None)
    _reg_sent: bool = field(default=False, init=False)
    _cap_in_progress: bool = field(default=False, init=False)
    _awaiting_auth_plus: bool = field(default=False, init=False)
    _quit_sent: bool = field(default=False, init=False)

    # CTCP preferences
    respond_to_ctcp_version: bool = field(default=True)
    ignore_ctcp: bool = field(default=False)
    version_string: str = field(default="albikirc (wxPython)")
    # Notifications
    show_join_part_notices: bool = field(default=True)
    show_quit_nick_notices: bool = field(default=True)
    activity_summaries: bool = field(default=True)
    activity_window_seconds: int = field(default=10)
    # Routing
    route_notices_inline: bool = field(default=True)

    # TCP keepalive options
    enable_tcp_keepalive: bool = field(default=False)
    tcp_keepalive_idle: int = field(default=120)      # seconds before starting probes
    tcp_keepalive_interval: int = field(default=30)   # seconds between probes
    tcp_keepalive_count: int = field(default=4)       # number of failed probes before drop

    # Recovery options
    auto_reconnect: bool = field(default=True)
    auto_rejoin: bool = field(default=True)
    reconnect_initial_delay: float = field(default=2.0)
    reconnect_max_delay: float = field(default=60.0)

    # Optional server password (PASS). Not persisted here.
    server_password: str | None = field(default=None)

    _sock: Optional[socket.socket] = field(default=None, init=False)
    _rx_thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _connection_args: tuple[str, int, str, str | None, bool] | None = field(
        default=None, init=False
    )
    _desired_channels: dict[str, tuple[str, str | None]] = field(default_factory=dict, init=False)
    _reconnect_timer: threading.Timer | None = field(default=None, init=False)
    _reconnect_attempt: int = field(default=0, init=False)
    _rejoining_after_reconnect: bool = field(default=False, init=False)
    _intentional_disconnect: bool = field(default=True, init=False)
    connecting: bool = field(default=False, init=False)
    _connect_thread: Optional[threading.Thread] = field(default=None, init=False)
    _state_lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _connection_serial: int = field(default=0, init=False)
    _names_pending: dict[str, set[str]] = field(default_factory=dict, init=False)
    _names_changes: dict[str, list[tuple[str | None, str | None]]] = field(
        default_factory=dict, init=False
    )
    _case_mapping: str = field(default="rfc1459", init=False)
    _prefix_symbols: str = field(default="~&@%+", init=False)
    # In-memory channel membership tracking (lower-cased channel keys)
    _chan_users: dict[str, set[str]] = field(default_factory=dict, init=False)
    _chan_display: dict[str, str] = field(default_factory=dict, init=False)
    # Activity summaries batching
    _activity: dict[str, dict[str, set[str]]] = field(default_factory=dict, init=False)  # keys: 'join','part','kick'
    _activity_timers: dict[str, threading.Timer] = field(default_factory=dict, init=False)
    _activity_lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _max_irc_line_bytes: int = field(default=510, init=False)

    def _queue_activity(self, channel: str, *, joined: list[str] | None = None, parted: list[str] | None = None, kicked: list[str] | None = None):
        key = self._casefold(channel)
        with self._activity_lock:
            rec = self._activity.setdefault(key, {"join": set(), "part": set(), "kick": set()})
            if joined:
                rec["join"].update(joined)
            if parted:
                rec["part"].update(parted)
            if kicked:
                rec["kick"].update(kicked)
            if key not in self._activity_timers:
                delay = max(1, int(self.activity_window_seconds or 10))
                t = threading.Timer(delay, self._flush_activity, args=(key,))
                t.daemon = True
                self._activity_timers[key] = t
                try:
                    t.start()
                except Exception:
                    # Fallback: flush immediately on failure to start timer
                    self._flush_activity(key)

    def _flush_activity(self, key: str):
        with self._state_lock:
            self._flush_activity_locked(key)

    def _flush_activity_locked(self, key: str):
        with self._activity_lock:
            rec = self._activity.pop(key, None)
            t = self._activity_timers.pop(key, None)
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
        if not rec:
            return
        joined = sorted(rec.get("join", set()))
        parted = sorted(rec.get("part", set()))
        kicked = sorted(rec.get("kick", set()))
        parts: list[str] = []
        if joined:
            parts.append(f"{len(joined)} joined ({', '.join(joined)})")
        if parted:
            parts.append(f"{len(parted)} left ({', '.join(parted)})")
        if kicked:
            parts.append(f"{len(kicked)} kicked ({', '.join(kicked)})")
        if not parts:
            return
        chan = self._chan_display.get(key, key)
        text = "[activity] " + "; ".join(parts)
        # Post as a channel message from '*'
        self._emit_message(chan, "*", text)

    def _emit_status(self, text: str):
        event_bus.publish("irc.status", text=text)

    def _emit_message(self, target: str, sender: str, text: str):
        event_bus.publish("irc.message", target=target, sender=sender, text=text)

    def _emit_users(self, target: str, users: list[str]):
        event_bus.publish("irc.users", target=target, users=users)

    def _emit_channel_list_start(self):
        event_bus.publish("irc.channel_list_start")

    def _emit_channel_list_item(self, channel: str, users: int | None, topic: str):
        event_bus.publish("irc.channel_list_item", channel=channel, users=users, topic=topic)

    def _emit_channel_list_end(self):
        event_bus.publish("irc.channel_list_end")

    # Networking helpers
    def _send_raw(self, line: str):
        sock = self._sock
        if not sock:
            return
        data = (line + "\r\n").encode("utf-8", errors="ignore")
        try:
            sock.sendall(data)
        except Exception as e:
            self._emit_status(f"Send error: {e}")


    def _is_ctcp(self, text: str) -> bool:
        return len(text) >= 2 and text.startswith("\x01") and text.endswith("\x01")

    def _parse_ctcp(self, text: str) -> tuple[str, str]:
        inner = text[1:-1]
        if not inner:
            return "", ""
        parts = inner.split(" ", 1)
        cmd = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""
        return cmd, args

    def _send_ctcp_reply(self, nick: str, cmd: str, args: str = ""):
        payload = f"\x01{cmd}{(' ' + args) if args else ''}\x01"
        self._send_raw(f"NOTICE {nick} :{payload}")

    def _registration_realname(self) -> str:
        real_name = (self.real_name or "").strip()
        return real_name or "albikirc"

    def _send_registration(self):
        if not self._reg_sent and self.nick:
            self._send_raw(f"NICK {self.nick}")
            self._send_raw(f"USER {self.nick} 0 * :{self._registration_realname()}")
            self._reg_sent = True

    def _reader_loop(self, sock, stop_event, generation):
        buf = b""
        try:
            while not stop_event.is_set():
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    with self._state_lock:
                        if generation != self._connection_serial or stop_event.is_set():
                            return
                        try:
                            self._handle_line(line.decode("utf-8", errors="ignore"))
                        except Exception as e:
                            self._emit_status(f"Parse error: {e}")
        except Exception as e:
            with self._state_lock:
                if generation == self._connection_serial and not stop_event.is_set():
                    self._emit_status(f"Connection error: {e}")
        finally:
            sock.close()
            with self._state_lock:
                if generation == self._connection_serial:
                    self._sock = None
                    self.connected = False
                    self._clear_channels()
                    self._emit_status("Disconnected")
                    self._schedule_reconnect(generation)

    def _cancel_reconnect(self):
        with self._state_lock:
            timer = self._reconnect_timer
            self._reconnect_timer = None
        if timer:
            try:
                timer.cancel()
            except Exception:
                pass

    def _schedule_reconnect(self, serial: int):
        with self._state_lock:
            if (
                not self.auto_reconnect
                or self._intentional_disconnect
                or not self._connection_args
                or serial != self._connection_serial
                or self._reconnect_timer is not None
            ):
                return
            delay = min(
                max(0.0, float(self.reconnect_initial_delay))
                * (2 ** min(self._reconnect_attempt, 30)),
                max(0.0, float(self.reconnect_max_delay)),
            )
            self._reconnect_attempt += 1
            self._emit_status(f"Reconnecting in {delay:g} seconds...")
            timer = threading.Timer(delay, self._reconnect, args=(serial,))
            timer.daemon = True
            self._reconnect_timer = timer
            timer.start()

    def _reconnect(self, serial: int):
        with self._state_lock:
            if serial != self._connection_serial:
                return
            self._reconnect_timer = None
            if (self._intentional_disconnect or not self.auto_reconnect
                    or not self._connection_args):
                return
            self._emit_status(f"Reconnect attempt {self._reconnect_attempt}...")
            self._connection_serial += 1
            self._start_connection(*self._connection_args, reconnecting=True)

    def _parse_prefix(self, prefix: str) -> tuple[str, Optional[str]]:
        # returns (nick_or_server, userhost)
        if "!" in prefix:
            nick, rest = prefix.split("!", 1)
            return nick, rest
        return prefix, None

    def _handle_line(self, line: str):
        self._emit_status(f"<- {line}")
        prefix = None
        trailing = None
        # IRCv3 message tags (ignore for now, but strip so parsing works)
        if line.startswith("@"):
            try:
                _tags, line = line[1:].split(" ", 1)
            except ValueError:
                # Malformed line; drop
                return
        if line.startswith(":"):
            prefix, line = line[1:].split(" ", 1)
        if " :" in line:
            line, trailing = line.split(" :", 1)
        parts = line.split()
        if not parts:
            return
        cmd = parts[0]
        params = parts[1:]

        handler = getattr(self, f"_handle_{cmd.lower()}", None)
        if handler:
            handler(prefix, params, trailing)

    def _handle_ping(self, prefix, params, trailing):
        self._send_raw(f"PONG :{trailing or 'ping'}")

    def _handle_001(self, prefix, params, trailing):  # RPL_WELCOME
        self._reconnect_attempt = 0
        should_rejoin = self._rejoining_after_reconnect
        self._rejoining_after_reconnect = False
        if should_rejoin and self.auto_rejoin and self._desired_channels:
            channels = list(self._desired_channels.values())
            self._emit_status(f"Rejoining {len(channels)} channel(s)...")
            for channel, key in channels:
                self._send_join(channel, key)

    def _handle_notice(self, prefix, params, trailing):
        if trailing is None:
            return
        target = params[0] if params else ""
        sender, _ = self._parse_prefix(prefix or "")
        if self._is_ctcp(trailing):
            # Suppress CTCP reply notices unless explicitly not ignored
            if not self.ignore_ctcp:
                ctcp_cmd, ctcp_args = self._parse_ctcp(trailing)
                if ctcp_cmd:
                    self._emit_status(f"CTCP {ctcp_cmd} reply from {sender}: {ctcp_args}")
            return
        # Route notices to the relevant tab when possible; otherwise, Console status
        is_channel = target.startswith("#") or target.startswith("&")
        is_pm = False
        try:
            me = (self.nick or "").lower()
            is_pm = bool(me and target.lower() == me)
        except Exception:
            pass
        if self.route_notices_inline and (is_channel or is_pm):
            # Annotate notice in-line for clarity
            self._emit_message(target, sender, f"[notice] {trailing}")
        else:
            self._emit_status(f"NOTICE from {sender}: {trailing}")

    def _handle_cap(self, prefix, params, trailing):
        if len(params) < 2:
            return
        subcmd = params[1].upper()
        if subcmd == "ACK" and trailing and "sasl" in trailing.lower():
            self._send_raw("AUTHENTICATE PLAIN")
            self._awaiting_auth_plus = True
            return
        if subcmd == "NAK":
            if not self._awaiting_auth_plus and self._cap_in_progress:
                self._send_raw("CAP END")
                self._cap_in_progress = False
                self._send_registration()
            return

    def _handle_authenticate(self, prefix, params, trailing):
        arg = (params[0] if params else "").strip()
        if arg == "+" and self._awaiting_auth_plus:
            u = self.sasl_username or (self.nick or "")
            p = self.sasl_password or ""
            token = ("\0" + u + "\0" + p).encode("utf-8")
            b64 = base64.b64encode(token).decode("ascii")
            self._send_raw("AUTHENTICATE " + b64)
            return

    def _handle_903(self, prefix, params, trailing):
        self._emit_status("SASL authentication successful")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_904(self, prefix, params, trailing):
        self._emit_status("SASL authentication failed (904). Continuing without SASL.")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_905(self, prefix, params, trailing):
        self._emit_status("SASL authentication failed (905). Continuing without SASL.")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_906(self, prefix, params, trailing):
        self._emit_status("SASL authentication failed (906). Continuing without SASL.")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_privmsg(self, prefix, params, trailing):
        if trailing is None:
            return
        target = params[0]
        sender, _ = self._parse_prefix(prefix or "")

        # CTCP requests arrive via PRIVMSG
        if self._is_ctcp(trailing):
            # Special-case ACTION to show as an emote even if CTCP is ignored
            ctcp_cmd, ctcp_args = self._parse_ctcp(trailing)
            if ctcp_cmd == "ACTION":
                # Emit as "* sender action" to the channel/pm target
                action_text = ctcp_args or ""
                self._emit_message(target, "*", f"{sender} {action_text}")
                return
            if self.ignore_ctcp:
                return
            if ctcp_cmd:
                # Only emit when not ignoring CTCP
                self._emit_status(f"CTCP {ctcp_cmd} from {sender} (target {target})")
                if ctcp_cmd == "VERSION" and self.respond_to_ctcp_version:
                    self._send_ctcp_reply(sender, "VERSION", self.version_string)
                elif ctcp_cmd == "PING" and ctcp_args:
                    self._send_ctcp_reply(sender, "PING", ctcp_args)
            return

        # Not CTCP → normal chat message
        self._emit_message(target, sender, trailing)

    def _handle_331(self, prefix, params, trailing):  # RPL_NOTOPIC
        if len(params) < 2:
            return
        channel = params[1]
        self._emit_status(f"No topic set for {channel}")

    def _handle_332(self, prefix, params, trailing):  # RPL_TOPIC
        if len(params) < 2 or trailing is None:
            return
        channel = params[1]
        topic = trailing
        self._emit_status(f"Topic for {channel}: {topic}")

    def _handle_333(self, prefix, params, trailing):  # RPL_TOPICWHOTIME
        if len(params) < 4:
            return
        channel = params[1]
        set_by = params[2]
        try:
            ts = int(params[3])
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            when = params[3]
        self._emit_status(f"Topic for {channel} set by {set_by} at {when}")

    def _handle_311(self, prefix, params, trailing):  # RPL_WHOISUSER
        if len(params) < 5 or trailing is None:
            return
        nick = params[1]
        user = params[2]
        host = params[3]
        real = trailing
        self._emit_status(f"WHOIS {nick}: {user}@{host} — {real}")

    def _handle_312(self, prefix, params, trailing):  # RPL_WHOISSERVER
        if len(params) < 3 or trailing is None:
            return
        nick = params[1]
        server = params[2]
        info = trailing
        self._emit_status(f"WHOIS {nick}: on {server} — {info}")

    def _handle_317(self, prefix, params, trailing):  # RPL_WHOISIDLE
        if len(params) < 3:
            return
        nick = params[1]
        try:
            idle = int(params[2])
        except Exception:
            idle = params[2]
        signon = None
        if len(params) >= 4:
            try:
                signon_ts = int(params[3])
                signon = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(signon_ts))
            except Exception:
                signon = params[3]
        msg = f"WHOIS {nick}: idle {idle}s"
        if signon:
            msg += f"; signon {signon}"
        self._emit_status(msg)

    def _handle_319(self, prefix, params, trailing):  # RPL_WHOISCHANNELS
        if len(params) < 2 or trailing is None:
            return
        nick = params[1]
        chans = trailing
        self._emit_status(f"WHOIS {nick}: channels: {chans}")

    def _handle_318(self, prefix, params, trailing):  # RPL_ENDOFWHOIS
        if len(params) < 2 or trailing is None:
            return
        nick = params[1]
        self._emit_status(f"WHOIS {nick}: {trailing}")

    def _casefold(self, value: str) -> str:
        value = value.lower()
        if self._case_mapping == "ascii":
            return value
        value = value.translate(str.maketrans("[]\\", "{}|"))
        return value.replace("^", "~") if self._case_mapping == "rfc1459" else value

    def _handle_005(self, prefix, params, trailing):
        for token in params[1:]:
            if token.startswith("CASEMAPPING="):
                mapping = token.split("=", 1)[1]
                if mapping in ("ascii", "strict-rfc1459", "rfc1459"):
                    self._case_mapping = mapping
            elif token.startswith("PREFIX=(") and ")" in token:
                self._prefix_symbols = token.split(")", 1)[1]

    def _update_member(self, key: str, nick: str, present: bool):
        users = self._chan_users.setdefault(key, set())
        folded = self._casefold(nick)
        users.difference_update({n for n in users if self._casefold(n) == folded})
        if present:
            users.add(nick)
        if key in self._names_pending:
            self._names_changes[key].append((None, nick) if present else (nick, None))

    def _publish_members(self, key: str):
        self._emit_users(self._chan_display.get(key, key),
                         sorted(self._chan_users.get(key, set()), key=self._casefold))

    def _forget_channel(self, key: str):
        self._emit_users(self._chan_display.get(key, key), [])
        self._chan_users.pop(key, None)
        self._chan_display.pop(key, None)
        self._names_pending.pop(key, None)
        self._names_changes.pop(key, None)
        with self._activity_lock:
            timer = self._activity_timers.pop(key, None)
            if timer:
                timer.cancel()
            self._activity.pop(key, None)

    def _clear_channels(self):
        for key in list(self._chan_users):
            self._forget_channel(key)
        self._names_pending.clear()
        self._names_changes.clear()

    def _handle_join(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        chan = (params[0] if params else trailing) or ""
        if not chan:
            return
        key = self._casefold(chan)
        if self._casefold(sender) == self._casefold(self.nick or ""):
            self._desired_channels.setdefault(key, (chan, None))
            if key in self._chan_users:
                self._forget_channel(key)
            self._names_pending[key] = set()
            self._names_changes[key] = []
        self._chan_display[key] = chan
        self._update_member(key, sender, True)
        self._publish_members(key)
        if self.activity_summaries:
            self._queue_activity(chan, joined=[sender])
        elif self.show_join_part_notices:
            self._emit_message(chan, "*", f"{sender} joined {chan}")

    def _handle_part(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        chan = params[0] if params else ""
        if not chan:
            return
        key = self._casefold(chan)
        if self._casefold(sender) == self._casefold(self.nick or ""):
            self._desired_channels.pop(key, None)
            self._forget_channel(key)
            return
        self._update_member(key, sender, False)
        self._publish_members(key)
        if self.activity_summaries:
            self._queue_activity(chan, parted=[sender])
        elif self.show_join_part_notices:
            reason = f" ({trailing})" if trailing else ""
            self._emit_message(chan, "*", f"{sender} left {chan}{reason}")

    def _handle_kick(self, prefix, params, trailing):
        if len(params) < 2:
            return
        chan, victim = params[:2]
        key = self._casefold(chan)
        if self._casefold(victim) == self._casefold(self.nick or ""):
            self._desired_channels.pop(key, None)
            self._forget_channel(key)
            kicker, _ = self._parse_prefix(prefix or "")
            self._emit_message(chan, "*", f"You were kicked by {kicker}: {trailing or ''}")
            return
        self._update_member(key, victim, False)
        self._publish_members(key)
        if self.activity_summaries:
            self._queue_activity(chan, kicked=[victim])
        elif self.show_join_part_notices:
            kicker, _ = self._parse_prefix(prefix or "")
            reason = f" ({trailing})" if trailing else ""
            self._emit_message(chan, "*", f"{victim} was kicked from {chan} by {kicker}{reason}")

    def _handle_quit(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        if self.show_quit_nick_notices:
            reason = f" ({trailing})" if trailing else ""
            self._emit_status(f"{sender} quit IRC{reason}")
        for key in list(self._chan_users):
            self._update_member(key, sender, False)
            self._publish_members(key)

    def _handle_nick(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        new_nick = trailing or (params[0] if params else "")
        if not new_nick:
            return
        if self._casefold(sender) == self._casefold(self.nick or ""):
            self.nick = new_nick
            if self._connection_args:
                host, port, _nick, real_name, use_tls = self._connection_args
                self._connection_args = (host, port, new_nick, real_name, use_tls)
        if self.show_quit_nick_notices:
            self._emit_status(f"{sender} is now known as {new_nick}")
        for key, users in list(self._chan_users.items()):
            present = any(self._casefold(n) == self._casefold(sender) for n in users)
            users.difference_update({n for n in users if self._casefold(n) == self._casefold(sender)})
            if present:
                users.add(new_nick)
            if key in self._names_pending:
                self._names_changes[key].append((sender, new_nick))
            self._publish_members(key)

    def _handle_353(self, prefix, params, trailing):
        if len(params) < 3 or trailing is None:
            return
        channel = params[2]
        key = self._casefold(channel)
        self._chan_display[key] = channel
        if key not in self._names_pending:
            self._names_pending[key] = set()
            self._names_changes[key] = []
        names = self._names_pending[key]
        names.update(n.lstrip(self._prefix_symbols).split("!", 1)[0] for n in trailing.split())
        # Live JOIN/PART/NICK/QUIT events take precedence over later snapshot chunks.
        merged = {self._casefold(n): n for n in names}
        for old, new in self._names_changes[key]:
            if old is None:
                merged[self._casefold(new)] = new
            else:
                removed = merged.pop(self._casefold(old), None)
                if new is not None and removed is not None:
                    merged[self._casefold(new)] = new
        self._chan_users[key] = set(merged.values())
        self._publish_members(key)

    def _handle_366(self, prefix, params, trailing):
        if len(params) < 2:
            return
        key = self._casefold(params[1])
        self._names_pending.pop(key, None)
        self._names_changes.pop(key, None)
        self._publish_members(key)

    def _handle_321(self, prefix, params, trailing):  # RPL_LISTSTART
        self._emit_channel_list_start()

    def _handle_322(self, prefix, params, trailing):  # RPL_LIST
        if len(params) < 3:
            return
        channel = params[1]
        try:
            users = int(params[2])
        except Exception:
            users = None
        self._emit_channel_list_item(channel, users, trailing or "")

    def _handle_323(self, prefix, params, trailing):  # RPL_LISTEND
        self._emit_channel_list_end()

    # Public API
    def connect(self, host: str, port: int, nick: str, *,
                real_name: str | None = None, use_tls: bool = True):
        """Start connection setup in a worker; return without waiting for the network."""
        with self._state_lock:
            self.disconnect()
            self._desired_channels.clear()
            self._connection_args = (host, port, nick, real_name, use_tls)
            self._intentional_disconnect = False
            self._reconnect_attempt = 0
            self._rejoining_after_reconnect = False
            self._start_connection(host, port, nick, real_name, use_tls)

    def _start_connection(self, host, port, nick, real_name, use_tls, reconnecting=False):
        """Launch an attempt while the caller holds the state lock."""
        self.nick = nick
        self.real_name = (real_name or "").strip() or None
        self._reg_sent = False
        self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._quit_sent = False
        self._case_mapping = "rfc1459"
        self._prefix_symbols = "~&@%+"
        self._stop_event = threading.Event()
        self.connecting = True
        generation = self._connection_serial
        certfile, keyfile = self.tls_client_certfile, self.tls_client_keyfile
        registration = []
        if (self.server_password or "").strip():
            registration.append(f"PASS {self.server_password}")
        if self.sasl_enabled:
            registration.extend(["CAP LS 302", "CAP REQ :sasl"])
        else:
            registration.extend([f"NICK {nick}",
                                 f"USER {nick} 0 * :{self._registration_realname()}"])
        keepalive = (self.enable_tcp_keepalive, self.tcp_keepalive_idle,
                     self.tcp_keepalive_interval, self.tcp_keepalive_count)
        self._emit_status(f"Connecting to {host}:{port} as {nick}")
        self._connect_thread = threading.Thread(
            target=self._connect_worker,
            args=(host, port, use_tls, certfile, keyfile, generation, self._stop_event,
                  registration, self.sasl_enabled, keepalive, reconnecting),
            name="irc-connect", daemon=True,
        )
        self._connect_thread.start()

    def _connect_worker(self, host, port, use_tls, certfile, keyfile, generation, stop_event,
                        registration, sasl_enabled, keepalive, reconnecting):
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=15)
            if stop_event.is_set():
                return
            if use_tls:
                ctx = ssl.create_default_context()
                if certfile:
                    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile or None)
                sock = ctx.wrap_socket(sock, server_hostname=host)
            # Bound writes and let the reader periodically observe cancellation.
            sock.settimeout(1)
            keepalive_enabled = self._configure_keepalive(sock, keepalive)
            for line in registration:
                if stop_event.is_set():
                    return
                sock.sendall((line + "\r\n").encode("utf-8", errors="ignore"))
            with self._state_lock:
                if generation != self._connection_serial or stop_event.is_set():
                    return
                self._sock = sock
                self._reg_sent = not sasl_enabled
                self._cap_in_progress = sasl_enabled
                self._rejoining_after_reconnect = reconnecting
                self.connecting = False
                self.connected = True
                if keepalive_enabled:
                    self._emit_status("TCP keepalive enabled")
                self._emit_status(f"Connected to {host}:{port}{' (TLS)' if use_tls else ''}")
                self._rx_thread = threading.Thread(
                    target=self._reader_loop, args=(sock, stop_event, generation),
                    name="irc-reader", daemon=True,
                )
                self._rx_thread.start()
                sock = None  # The reader owns the socket now.
        except Exception as e:
            with self._state_lock:
                if generation == self._connection_serial and not stop_event.is_set():
                    self.connected = False
                    self.connecting = False
                    self._sock = None
                    self._emit_status(f"Connect failed: {e}")
                    if reconnecting:
                        self._schedule_reconnect(generation)
        finally:
            if sock is not None:
                sock.close()

    @staticmethod
    def _configure_keepalive(sock, options) -> bool:
        enabled, idle, interval, count = options
        if not enabled:
            return False
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            for option, value in (("TCP_KEEPIDLE", idle), ("TCP_KEEPALIVE", idle),
                                  ("TCP_KEEPINTVL", interval), ("TCP_KEEPCNT", count)):
                if hasattr(socket, option):
                    sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), int(value))
            return True
        except (OSError, TypeError, ValueError):
            return False

    def join_channel(self, channel: str, key: str | None = None):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        if not channel.startswith("#") and not channel.startswith("&"):
            channel = f"#{channel}"
        self._desired_channels[self._casefold(channel)] = (channel, key)
        self._send_join(channel, key)

    def _send_join(self, channel: str, key: str | None = None):
        if key:
            self._send_raw(f"JOIN {channel} {key}")
        else:
            self._send_raw(f"JOIN {channel}")

    def part_channel(self, channel: str, reason: str = ""):
        if not channel.startswith("#") and not channel.startswith("&"):
            channel = f"#{channel}"
        self._desired_channels.pop(self._casefold(channel), None)
        if not self.connected:
            self._emit_status("Not connected.")
            return
        self._send_raw(f"PART {channel}{(' :' + reason) if reason else ''}")

    def split_message_text(self, target: str, text: str, command: str = "PRIVMSG") -> list[str]:
        text = str(text or "")
        if not text:
            return []

        prefix = f"{command} {target} :"
        max_text_bytes = self._max_irc_line_bytes - len(prefix.encode("utf-8", errors="ignore"))
        max_text_bytes = max(1, max_text_bytes)

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining.encode("utf-8", errors="ignore")) <= max_text_bytes:
                chunks.append(remaining)
                break

            split_at = self._find_split_index(remaining, max_text_bytes)
            chunk = remaining[:split_at].rstrip()
            if not chunk:
                chunk = remaining[:split_at]
            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()

        return chunks

    def _find_split_index(self, text: str, max_bytes: int) -> int:
        used = 0
        last_space = -1
        for idx, char in enumerate(text):
            char_len = len(char.encode("utf-8", errors="ignore"))
            if used + char_len > max_bytes:
                return last_space + 1 if last_space > 0 else max(1, idx)
            used += char_len
            if char.isspace():
                last_space = idx
        return len(text)

    def send_message(self, target: str, text: str):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        for chunk in self.split_message_text(target, text, "PRIVMSG"):
            self._send_raw(f"PRIVMSG {target} :{chunk}")

    def send_action(self, target: str, action: str):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        payload = f"\x01ACTION {action}\x01"
        self._send_raw(f"PRIVMSG {target} :{payload}")

    def send_notice(self, target: str, text: str):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        for chunk in self.split_message_text(target, text, "NOTICE"):
            self._send_raw(f"NOTICE {target} :{chunk}")

    def set_topic(self, channel: str, topic: str | None = None):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        if not channel.startswith("#") and not channel.startswith("&"):
            channel = f"#{channel}"
        if topic is None:
            self._send_raw(f"TOPIC {channel}")
        else:
            self._send_raw(f"TOPIC {channel} :{topic}")

    def whois(self, nick: str):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        self._send_raw(f"WHOIS {nick}")

    def list_channels(self, mask: str | None = None):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        mask = (mask or "").strip()
        if mask:
            self._send_raw(f"LIST {mask}")
        else:
            self._send_raw("LIST")

    def send_raw(self, line: str):
        self._send_raw(line)

    def quit(self, reason: str = "Bye"):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        try:
            self._intentional_disconnect = True
            self._cancel_reconnect()
            self._send_raw(f"QUIT :{reason}")
            self._quit_sent = True
        except Exception as e:
            self._emit_status(f"Send error: {e}")

    @staticmethod
    def _close_socket(sock, send_quit):
        try:
            if send_quit:
                sock.sendall(b"QUIT :Bye\r\n")
        except OSError:
            pass
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def disconnect(self):
        """Invalidate pending work immediately; close the old socket off the UI thread."""
        with self._state_lock:
            self._intentional_disconnect = True
            self._cancel_reconnect()
            was_active = self.connected or self.connecting
            self._connection_serial += 1
            self._stop_event.set()
            sock, self._sock = self._sock, None
            send_quit = not self._quit_sent
            self.connected = False
            self.connecting = False
            self._rx_thread = None
            self._clear_channels()
            self._quit_sent = False
            if was_active:
                self._emit_status("Disconnected")
            if sock is not None:
                threading.Thread(target=self._close_socket, args=(sock, send_quit),
                                 name="irc-disconnect", daemon=True).start()
