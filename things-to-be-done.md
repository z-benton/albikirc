# Things To Be Done

This document captures missing or incomplete features needed to make the IRC
client more feature complete. It is intended as a comprehensive checklist to
guide future work.

## Scope and Goals

- Improve multi-server usability and session handling.
- Expand IRC protocol coverage (core replies and IRCv3 capabilities).
- Provide ergonomics and reliability expected from daily-use IRC clients.
- Keep UI accessible and consistent with existing wxPython patterns.
- Avoid storing secrets unless a secure store is added.

## High Priority

### Multi-server and Session Support

- Support multiple simultaneous server connections.
- Per-server tab grouping or a server selector to prevent tab confusion.
- Connection lifecycle UI: status, reconnect progress, and error details.
- Auto-reconnect with backoff, limits, and manual cancel.
- Auto-join channels on connect (per saved server).
- Session restore: reopen tabs, reconnect optionally, and rejoin channels.
- Persist per-server identity (nick, real name, username, SASL settings).

### Core IRC Protocol Handling

- Nick collision handling (RPL 433) with retries or suffixing.
- Handle RPL_ENDOFNAMES (366) to signal complete user list.
- WHO/WHOX for accurate user list refresh on joins/parts.
- MODE parsing for user and channel modes, including op/voice indicators.
- Track and display channel topics (RPL_TOPIC/332) with edit support.
- More robust handling for QUIT/PART to keep user lists accurate.
- Proper handling of numeric error replies (banned, invite-only, bad key).

### Authentication and Identity

- SASL methods beyond PLAIN (EXTERNAL, SCRAM if supported).
- NickServ identify (optional, per server).
- Real name defaults in Preferences and per-server overrides.
- Optional per-server username/ident field (USER command user field).

## Medium Priority

### IRCv3 Capabilities

- CAP LS/REQ/ACK tracking with a full state machine and resume on reconnect.
- message-tags parsing and storage for downstream usage.
- server-time for accurate timestamps and history alignment.
- account-tag for identifying logged-in users.
- away-notify and chghost; reflect in user list and status lines.
- batch for grouped events (netsplits, history playback).
- echo-message to avoid double-echo confusion when servers support it.
- labeled-response for matching responses to client commands.

### Reliability and Networking

- Keepalive beyond TCP keepalive: periodic PING with timeout handling.
- Graceful handling of server-initiated reconnects or throttling.
- Rate limiting and flood protection on outbound messages.
- Better socket error reporting and retry guidance.
- Encoding/charset handling for non-UTF8 networks (if needed).

### Chat and UI Ergonomics

- Channel list (/list) dialog with filters.
- PM tab management (close prompts, unread indicators).
- Highlight/mention rules (custom words, per-channel settings).
- Simple search in transcript and copy/export options.
- Command history and completion (/join, /msg, nick completion).
- Input handling for long messages (split at 512 bytes as needed).

### Notifications and Logging

- Optional logging to local files (per server or per channel).
- Configurable highlight notifications (sound/tts/badge).
- Dedicated notices tab or filter options.
- Activity indicators on tabs (unread counts).
- Better per-channel notification muting.

## Low Priority

### Extras and Quality of Life

- DCC file transfer (if desired, larger scope).
- URL auto-detection and click-to-open with confirmation.
- Customizable keybindings.
- Scripting hooks or user macros for power users.

## Implementation Notes

- Keep UI updates on the wx main thread; network work stays in background threads.
- Prefer event-driven changes via `event_bus`.
- Use `config.py` defaults and merge patterns for new settings.
- Keep saved server entries backward compatible when new fields are added.
- Document new slash commands in `albikirc/ui/help_dialog.py`.

## Suggested Next Steps

1) Add multi-server connection management and tab grouping.
2) Implement reconnect and auto-join behavior.
3) Expand IRCv3 capability support and user list accuracy.
4) Add UX improvements: notifications, highlights, and logging.
