# albikirc v0.1.0

Minimal, accessible IRC client using wxPython. Focused on VoiceOver (macOS) and cross‑platform accessibility.

## Highlights
- Accessible UI with labeled controls (screen‑reader friendly) and logical tab order.
- IRC engine: TLS, PASS, SASL (PLAIN), CTCP handling (ACTION, VERSION, PING), JOIN/PART/NICK/QUIT, user list tracking.
- Inline NOTICE routing (optional) and compact activity summaries.
- Slash commands: `/join`, `/part`, `/nick`, `/me`, `/msg` (aliases: `/query`, `/pm`), `/quit`, `/notice`, `/topic`, `/whois`, `/raw`.
- WHOIS and TOPIC replies summarized in Console.
- Preferences: timestamps/theme, CTCP behavior, notifications (join/part, quit/nick, notices inline), sounds, TCP keepalive, TTS options.

## Downloads (macOS)
- Apple Silicon (arm64) ZIP: `Albikirc-macOS-arm64.zip`
- Apple Silicon (arm64) DMG: `Albikirc-macOS-arm64.dmg`

Checksums (SHA‑256):

```
e7e6d13c9a0dbf4343df283e2a18ffa451454c5cad928938498131cd627bbc40  Albikirc-macOS-arm64.zip
ee0c0c9ffb1d86d0bdb40c8c0066d8e5889c9975d1c62117861c2cb95ac0450d  Albikirc-macOS-arm64.dmg
```

Note: An Intel (x86_64) build can be produced on an Intel Mac or on Apple Silicon using Rosetta with an x86_64 Python. If needed, we’ll add it to this release.

## Install
1) Download the ZIP or DMG for your Mac architecture.
2) ZIP: unzip and drag `Albikirc.app` to `Applications`. DMG: open and drag the app to `Applications`.
3) First launch on macOS may show a Gatekeeper warning (unsigned app). Bypass by right‑click → Open → Open; or remove quarantine:

```
xattr -dr com.apple.quarantine /Applications/Albikirc.app
```

## Notes
- Defaults: Connect dialog uses port 6667 with TLS off by default.
- Passwords (PASS/SASL) are not saved; fields and tooltips indicate “not saved”.
- User list is maintained from JOIN/PART/KICK/QUIT/NICK and initial 353 NAMES.

## Credits
Licensed under Apache‑2.0. See `LICENSE`.

