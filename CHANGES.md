# Changelog

All notable changes to this project are documented here.

## 2025-08-19 (UTC)

- Feature: Extended slash commands and help
  - Added `/notice <target> <text>`, `/topic [#chan] [text]`, `/whois <nick>`, and `/raw <line>`.
  - Help dialog now documents all supported commands.
- Feature: Inline NOTICE routing with preference
  - NOTICEs targeting a channel or you (PM) are shown inline in that tab with a `[notice]` label.
  - New preference: Notifications → “Show NOTICEs inline in tabs (instead of Console)”. When disabled, NOTICEs appear in Console only.
  - Sounds/TTS: NOTICEs use the “notice” sound and are spoken as notices (when enabled), without triggering normal message sounds.
- Feature: WHOIS/TOPIC reply display
  - Parse common numerics and show readable summaries in Console: `331/332/333` (topic), `311/312/317/319/318` (WHOIS).
- UX: Consistent outgoing feedback
  - `/me` now echoes as “* <your-nick> action” (was “* me action”).
  - `/me`, `/msg`, and `/notice` now trigger the “message sent” sound and optional beep, matching the Send button behavior.
  - Message input tooltip mentions slash commands.
- Docs: README updates
  - Slash commands list expanded; Preferences section notes the NOTICE inline routing toggle.
  - License: switched to Apache-2.0; added license metadata and README section.

## 2025-08-16 (UTC)

- Fix: Prevent idle disconnects after ~15s by clearing the connect-time socket timeout and making the reader loop resilient to `socket.timeout`.
- Defaults: Connect dialog now defaults to port `6667` with TLS unchecked.
- Feature: TCP keepalive support.
  - New "Enable TCP keepalive" checkbox in Connect dialog (defaults from Preferences).
  - Preferences > Connection: global keepalive enable, idle/interval/count settings.
  - IRC client enables `SO_KEEPALIVE` and tunes options where supported (Linux/macOS), falls back gracefully otherwise.
  - Saved Servers list shows "KA" badge when keepalive is enabled for an entry.
- Feature: Server password (PASS).
  - New "Server password (optional, not saved)" field in Connect dialog.
  - IRC client sends `PASS` before registration/CAP.
  - Passwords are not persisted in saved servers.
- Accessibility: Clear, screen-reader-friendly labeling for unsaved secrets.
  - SASL password label now reads "(not saved)"; tooltips for both PASS and SASL emphasize not saved.
  - Added a note in Connect: "Passwords are not saved. This may be implemented in the future if a secure method is available."

## 2025-08-15 (UTC)

Note: Date approximated from file modification times.

- Added JOIN/PART/QUIT/NICK handling; channel notices (join/part) and Console status notices (quit/nick).
- Added preferences to toggle join/part notices and quit/nick notices.
- Strips IRCv3 message tags to fix missing messages on tagged servers.
- Tracks user lists in memory for instant updates on channel activity.
