# albikirc

A minimal, accessible IRC client using wxPython. Focused on VoiceOver (macOS) and cross‑platform compatibility.

## Features
- wxPython app with menu bar and keyboard shortcuts
- Accessible control names for screen readers
- Chat panel with transcript, input box, user list
- Timestamps and minimal theme (system/light/dark)
- IRC client with basic IRCv3 tag parsing, CTCP handling, JOIN/PART/NICK/QUIT events, and user list updates
- Connect dialog with labeled fields (host, port, nick, TLS, optional SASL and client cert)
- Slash commands: /join, /part, /nick, /me, /msg, /query, /quit, /notice, /topic, /whois, /raw

## Requirements
- Python 3.10 or newer
- `pip` and a working C/C++ toolchain as required by wxPython on your OS
  - macOS: Xcode Command Line Tools installed (`xcode-select --install`)
  - Linux: GTK3 and development headers installed (see your distro docs)
  - Windows: Recent CPython + pip; wheels are usually available

## Quickstart (virtual environment)
The following creates an isolated virtual environment, installs dependencies, and runs the app from source.

1) Create a virtual environment

   - macOS/Linux:
     - `python3 -m venv .venv`
     - `source .venv/bin/activate`

   - Windows (PowerShell):
     - `py -3 -m venv .venv`
     - `.venv\Scripts\Activate.ps1`

2) Upgrade tooling and install dependencies

   - `python -m pip install --upgrade pip wheel`
   - macOS/Linux: `pip install -r requirements.txt`
   - Windows (PowerShell): `pip install -r requirements.txt`

   Notes:
   - If installation fails, try `pip install wxPython` directly and review platform notes. Prebuilt wheels vary by OS and Python release.

3) Run the app

   - `python -m albikirc.app`

4) Deactivate the environment when finished

   - `deactivate`

## Build macOS App (.app)
- Script: `./build-macos.sh` builds a double‑clickable `dist/Albikirc.app` and a zip.
- Cleanup: the script removes duplicates so only the `.app` remains (the extra `dist/Albikirc` folder is deleted). Use `--clean` to remove all build artifacts.

### Basic Usage
- Build: `./build-macos.sh`
- Run: `open dist/Albikirc.app`
- Zip output: `dist/Albikirc-macOS-<arch>.zip`

### Options
- `--clean`: remove `build/`, `dist/`, and the generated spec; then exit.
- `--no-zip`: skip creating the zip; only produce the `.app`.
- `--icon path.icns`: include a custom `.icns` as the app icon.
- `--python /path/to/python3`: use a specific Python 3 interpreter.

### Virtualenv Behavior
- If an active virtualenv is detected, the script reuses it.
- Otherwise, it looks for `.venv/` or `.venv310/` and reuses them if present.
- If none are found, it creates and uses `.venv-build/` automatically.

### Architecture Notes
- The app architecture follows the Python interpreter used (arm64 vs x86_64).
  - Apple Silicon (arm64): run normally with an arm64 Python 3.x (default).
  - Intel (x86_64): either build on an Intel Mac, or on Apple Silicon using Rosetta with an x86_64 Python 3.x.
    - Example on Apple Silicon (Rosetta): `arch -x86_64 ./build-macos.sh --python /usr/local/bin/python3`
    - Ensure the specified Python is x86_64 and has compatible `wxPython`/`PyInstaller` wheels.

### Gatekeeper
- Since the app is not code‑signed, macOS may warn on first launch. Bypass by right‑click → Open → Open, or remove quarantine: `xattr -dr com.apple.quarantine dist/Albikirc.app`.

## Shortcuts
- Connect: Cmd/Ctrl+N
- Join Channel: Cmd/Ctrl+J
- Close Tab: Cmd/Ctrl+W
- Preferences: Cmd/Ctrl+,
- Focus Message Input: Cmd/Ctrl+Shift+M
- Send Message: Enter (with input focused)
- Read Last Activity Summary: Cmd/Ctrl+Shift+A
- Help: F1
- Start a private message: Double‑click a user in the user list

## Accessibility Notes
- Controls use `SetName(...)` to expose readable names to screen readers.
- Standard wx controls and labeled layouts aid VoiceOver.
- Tab order is arranged to move logically across chat transcript → input → send → users.

## Configuration
- Config is stored at `~/.albikirc/config.json` and is written automatically when preferences change.
- Saved server entries (if any) are kept alongside other settings in this file.

## Next Steps
- Add per‑server and identity preferences
- Theming and message formatting
  
Implemented in this version: window/tab restore, timestamps, minimal theme, and direct messages via /msg, /query, or user list double‑click.

<!-- SwiftUI prototype not included in this repo; section removed to avoid confusion. -->

## Notes
- The client implements a simple threaded IRC engine with optional TLS.
  - Use the Connect dialog to specify host, port, nick, TLS, optional SASL credentials, and optional TLS client certificate.

## License
This project is licensed under the Apache License, Version 2.0. See the `LICENSE` file for details.

## Preferences Overview
- CTCP: Toggle auto‑reply to `CTCP VERSION`, ignore CTCP entirely, and customize the version string.
- Notifications:
  - `Show join/part notices in channels`: when enabled, a short message appears in the channel when users join or part. When disabled, these notices are suppressed. The user list still refreshes.
  - `Show quit/nick notices in Console`: when enabled, QUIT and nickname change events display in the Console tab; disable to hide them.
  - `Compact activity summaries`: batch join/part/kick into a single summary line per interval instead of many lines.
  - `Summary window (seconds)`: how long to batch activity before summarizing (default 10s).
  - `Show NOTICEs inline in tabs`: when enabled, NOTICEs targeting a channel or you (PM) appear inline in that conversation with a `[notice]` label; when disabled, they appear only as Console status lines.
- Sounds: Enable optional sounds and set file paths for message/mention/notice, channel messages, and private/query messages.
  - Experimental: Optional synthesized beep tones (ascending on send, descending on receive).

## Behavior Details
- Message tags: The client strips IRCv3 message tags (lines starting with `@`) for robust parsing, so messages from servers with tags display correctly.
- User list tracking: The client maintains in‑memory channel membership and updates the sidebar immediately on JOIN/PART/KICK/QUIT/NICK without issuing extra `NAMES` calls. Initial membership is populated from `RPL_NAMREPLY` (353) after you join.
- Activity summaries: When enabled, the client emits a single line like `[activity] 3 joined (alice, bob, cara); 1 left (dave)` per channel after the configured summary window. A copy is shown in the status bar for quick review.
- PM/Query routing: If the message target equals your nick, the message is routed to a private tab with the sender’s name. Preferences include a distinct sound for private/query messages.
- ACTION (`/me`): Incoming CTCP ACTION shows as `* nick action`. Outgoing `/me` is echoed as `* <your-nick> action` for consistency.
- Experimental beeps: When enabled in Preferences, the app plays short synthesized tones for send/receive events in addition to any configured sounds.
 - Notices: When “Show NOTICEs inline in tabs” is enabled (default), NOTICEs to a channel or to you (PM) appear inline in that conversation with a `[notice]` label and use the “notice” sound and optional TTS; otherwise they appear only as Console status lines.
 - WHOIS/TOPIC replies: Common numerics are summarized in Console (topic info and whois details) when you use `/whois` or `/topic`.

## Slash Commands

- `/join <#channel>` — Join a channel. Alias: `/j`
- `/part [#channel] [reason]` — Leave the current or given channel. Alias: `/p`
- `/nick <newnick>` — Change your nickname.
- `/me <action>` — Send an action to the current tab (echoed as `* <your-nick> action`).
- `/msg <nick> <text>` — Send a private message. Aliases: `/query`, `/pm`
- `/quit [reason]` — Disconnect and close the app.
- `/notice <target> <text>` — Send a NOTICE to a user or channel.
- `/topic [#chan] [text]` — Show or set the topic for a channel.
- `/whois <nick>` — Query WHOIS information.
- `/raw <line>` — Send a raw IRC command.

## Changelog
- See `CHANGES.md` for a detailed list of updates.

## Troubleshooting
- wxPython install issues: Ensure you are using a Python version with available wheels for your OS. If compilation is required, install platform build tools and GTK3 dev packages (Linux) or Xcode CLT (macOS). Consult https://wxpython.org/pages/downloads/ for guidance.
- GUI backend errors on Linux: Verify the necessary GTK libraries are present and try running from an X11 session if Wayland causes issues.
