# Changes

## Version 0.2.0

### New Features

*   Added support for joining channels with keys.
*   Added a Text-to-Speech preference to interrupt ongoing speech so incoming messages speak immediately without piling up.
*   Added an experimental macOS option to route app announcements through VoiceOver when VoiceOver AppleScript control is enabled.

### Bug Fixes

*   Fixed SASL capability negotiation so authentication is not ended prematurely on `CAP LS`.
*   Fixed nickname tracking after `/nick` changes so private-message routing keeps working without reconnecting.
*   Fixed `/quit <reason>` so the requested quit message is not overwritten by a second default `QUIT`.
*   Fixed the Console tab to stop sending bogus `PRIVMSG Console` messages when users type regular chat there.
*   Fixed restored window sizes being overwritten by the default window dimensions at startup.
*   Fixed configuration loading to return independent copies instead of mutating shared in-memory defaults.
*   Fixed event-bus subscriptions leaking across frame lifecycles by unsubscribing handlers during teardown.
*   Fixed the macOS TTS voice path so runtime speech and “Test Speech” consistently use the same backend as the voice list shown in the UI.
*   Fixed the Eloquence voice submenu so language groups are built correctly and checked accurately.
*   Reduced macOS speech lag by keeping an Apple `say` helper process alive instead of spawning a fresh speech process for every utterance.

### Refactoring

*   Refactored the `_handle_line` method in `irc_client.py` to be more modular and maintainable.
*   Decoupled the UI and IRC client using an event bus.
*   Refactored the slash command handling in `main_frame.py` to be more organized and extensible.
*   Refactored the sound and TTS handling in `main_frame.py` to be cleaner and more maintainable.
