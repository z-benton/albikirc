from __future__ import annotations

import socket
import ssl
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
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

    # Optional server password (PASS). Not persisted here.
    server_password: str | None = field(default=None)

    _sock: Optional[socket.socket] = field(default=None, init=False)
    _rx_thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    # In-memory channel membership tracking (lower-cased channel keys)
    _chan_users: dict[str, set[str]] = field(default_factory=dict, init=False)
    _chan_display: dict[str, str] = field(default_factory=dict, init=False)
    # Activity summaries batching
    _activity: dict[str, dict[str, set[str]]] = field(default_factory=dict, init=False)  # keys: 'join','part','kick'
    _activity_timers: dict[str, threading.Timer] = field(default_factory=dict, init=False)
    _activity_lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def _queue_activity(self, channel: str, *, joined: list[str] | None = None, parted: list[str] | None = None, kicked: list[str] | None = None):
        key = channel.lower()
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

    # Networking helpers
    def _send_raw(self, line: str):
        if not self._sock:
            return
        data = (line + "\r\n").encode("utf-8", errors="ignore")
        try:
            self._sock.sendall(data)
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

    def _reader_loop(self):
        buf = b""
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = self._sock.recv(4096)
                except socket.timeout:
                    # Ignore periodic read timeouts and continue waiting for data
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    try:
                        self._handle_line(line.decode("utf-8", errors="ignore"))
                    except Exception as e:
                        self._emit_status(f"Parse error: {e}")
        except Exception as e:
            self._emit_status(f"Connection error: {e}")
        finally:
            self.connected = False
            self._emit_status("Disconnected")

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
        if subcmd in ("NAK", "LS"):
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
        self._emit_status(f"SASL authentication failed (904). Continuing without SASL.")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_905(self, prefix, params, trailing):
        self._emit_status(f"SASL authentication failed (905). Continuing without SASL.")
        if self._cap_in_progress:
            self._send_raw("CAP END")
            self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._send_registration()

    def _handle_906(self, prefix, params, trailing):
        self._emit_status(f"SASL authentication failed (906). Continuing without SASL.")
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
        nick = params[1]; user = params[2]; host = params[3]
        real = trailing
        self._emit_status(f"WHOIS {nick}: {user}@{host} — {real}")

    def _handle_312(self, prefix, params, trailing):  # RPL_WHOISSERVER
        if len(params) < 3 or trailing is None:
            return
        nick = params[1]; server = params[2]; info = trailing
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

    def _handle_join(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        chan = (params[0] if params else trailing) or ""
        if chan:
            # Track membership
            key = chan.lower()
            self._chan_display[key] = chan
            users = self._chan_users.setdefault(key, set())
            users.add(sender)
            # Emit updated user list
            self._emit_users(self._chan_display.get(key, chan), sorted(users))
            # Emit notice or queue activity summary
            if self.activity_summaries:
                self._queue_activity(chan, joined=[sender])
            elif self.show_join_part_notices:
                self._emit_message(chan, "*", f"{sender} joined {chan}")

    def _handle_part(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        chan = params[0] if params else ""
        if chan:
            reason = trailing or ""
            if not self.activity_summaries and self.show_join_part_notices:
                self._emit_message(chan, "*", f"{sender} left {chan}{(' (' + reason + ')') if reason else ''}")
            # Update membership
            key = chan.lower()
            users = self._chan_users.setdefault(key, set())
            if sender in users:
                users.remove(sender)
            self._emit_users(self._chan_display.get(key, chan), sorted(users))
            if self.activity_summaries:
                self._queue_activity(chan, parted=[sender])

    def _handle_kick(self, prefix, params, trailing):
        if len(params) < 2:
            return
        chan = params[0]
        victim = params[1]
        kicker, _ = self._parse_prefix(prefix or "")
        reason = trailing or ""
        key = chan.lower()
        users = self._chan_users.setdefault(key, set())
        if victim in users:
            users.remove(victim)
        # Update list regardless of notice preference
        self._emit_users(self._chan_display.get(key, chan), sorted(users))
        # Treat like a PART-style notice (respect preference)
        if self.activity_summaries:
            self._queue_activity(chan, kicked=[victim])
        elif self.show_join_part_notices:
            msg = f"{victim} was kicked from {chan} by {kicker}"
            if reason:
                msg += f" ({reason})"
            self._emit_message(chan, "*", msg)

    def _handle_quit(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        reason = trailing or ""
        # Without tracking channel membership, request NAMES on all known channels would be ideal
        # If we are in any channels, the server will often send PART/QUIT effects; request a global NAMES refresh is not possible
        if self.show_quit_nick_notices:
            self._emit_status(f"{sender} quit IRC{(' (' + reason + ')') if reason else ''}")
        # Remove from all tracked channels and emit user updates
        for key, users in list(self._chan_users.items()):
            if sender in users:
                users.remove(sender)
                self._emit_users(self._chan_display.get(key, key), sorted(users))

    def _handle_nick(self, prefix, params, trailing):
        sender, _ = self._parse_prefix(prefix or "")
        new_nick = trailing or (params[0] if params else "")
        if new_nick:
            if self.show_quit_nick_notices:
                self._emit_status(f"{sender} is now known as {new_nick}")
            # Rename in all tracked channels
            for key, users in list(self._chan_users.items()):
                if sender in users:
                    users.remove(sender)
                    users.add(new_nick)
                    self._emit_users(self._chan_display.get(key, key), sorted(users))

    def _handle_353(self, prefix, params, trailing):  # RPL_NAMREPLY
        if len(params) < 3 or trailing is None:
            return
        channel = params[2]
        names = [n.lstrip("@+") for n in trailing.split()]
        key = channel.lower()
        self._chan_display[key] = channel
        self._chan_users[key] = set(names)
        self._emit_users(channel, sorted(self._chan_users[key]))

    # RPL_ENDOFNAMES (366) could be handled to signal completion

    # Public API
    def connect(self, host: str, port: int, nick: str, *, real_name: str | None = None, use_tls: bool = True):
        self.disconnect()
        self.nick = nick
        self.real_name = (real_name or "").strip() or None
        self._reg_sent = False
        self._cap_in_progress = False
        self._awaiting_auth_plus = False
        self._stop_event.clear()
        try:
            raw_sock = socket.create_connection((host, port), timeout=15)
            if use_tls:
                ctx = ssl.create_default_context()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                try:
                    if self.tls_client_certfile:
                        ctx.load_cert_chain(certfile=self.tls_client_certfile, keyfile=self.tls_client_keyfile or None)
                except Exception as e:
                    self._emit_status(f"TLS client cert load failed: {e}")
                self._sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            else:
                self._sock = raw_sock
            # Clear the connect-time timeout so recv() blocks indefinitely
            try:
                self._sock.settimeout(None)
            except Exception:
                pass

            # Optionally enable TCP keepalive (best-effort; platform specific tuning)
            if self.enable_tcp_keepalive:
                try:
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    # Linux: TCP_KEEPIDLE, TCP_KEEPINTVL, TCP_KEEPCNT
                    if hasattr(socket, 'TCP_KEEPIDLE'):
                        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, int(self.tcp_keepalive_idle))
                    # macOS/BSD: TCP_KEEPALIVE (idle seconds)
                    if hasattr(socket, 'TCP_KEEPALIVE'):
                        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, int(self.tcp_keepalive_idle))
                    if hasattr(socket, 'TCP_KEEPINTVL'):
                        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, int(self.tcp_keepalive_interval))
                    if hasattr(socket, 'TCP_KEEPCNT'):
                        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, int(self.tcp_keepalive_count))
                    self._emit_status("TCP keepalive enabled")
                except Exception:
                    # Non-fatal if keepalive tuning fails
                    pass
            self.connected = True
            self._emit_status(f"Connected to {host}:{port}{' (TLS)' if use_tls else ''}")

            self._rx_thread = threading.Thread(target=self._reader_loop, name="irc-reader", daemon=True)
            self._rx_thread.start()

            # CAP/SASL negotiation (before sending NICK/USER)
            # Send PASS first if provided (must precede NICK/USER)
            if (self.server_password or "").strip():
                self._send_raw(f"PASS {self.server_password}")

            if self.sasl_enabled:
                self._cap_in_progress = True
                self._send_raw("CAP LS 302")
                self._send_raw("CAP REQ :sasl")
            else:
                # No SASL: send registration now
                self._send_raw(f"NICK {nick}")
                self._send_raw(f"USER {nick} 0 * :{self._registration_realname()}")
                self._reg_sent = True
        except Exception as e:
            self.connected = False
            self._sock = None
            self._emit_status(f"Connect failed: {e}")

    def join_channel(self, channel: str, key: str | None = None):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        if not channel.startswith("#") and not channel.startswith("&"):
            channel = f"#{channel}"
        if key:
            self._send_raw(f"JOIN {channel} {key}")
        else:
            self._send_raw(f"JOIN {channel}")

    def send_message(self, target: str, text: str):
        if not self.connected:
            self._emit_status("Not connected.")
            return
        self._send_raw(f"PRIVMSG {target} :{text}")

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
        self._send_raw(f"NOTICE {target} :{text}")

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

    def send_raw(self, line: str):
        self._send_raw(line)

    def disconnect(self):
        try:
            if self._sock:
                try:
                    self._send_raw("QUIT :Bye")
                except Exception:
                    pass
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self._sock.close()
                except Exception:
                    pass
        finally:
            self._sock = None
            self._stop_event.set()
            if self._rx_thread and self._rx_thread.is_alive():
                self._rx_thread.join(timeout=2)
            self._rx_thread = None
            self.connected = False
            # Clear tracked channels on disconnect
            self._chan_users.clear()
            self._chan_display.clear()
            # Cancel and clear activity timers
            try:
                for t in list(self._activity_timers.values()):
                    try:
                        t.cancel()
                    except Exception:
                        pass
            finally:
                self._activity_timers.clear()
                self._activity.clear()
            # Do not clear nick; keep for PM routing until next connect
