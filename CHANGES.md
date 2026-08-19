# Changes

## Version 0.2.0

### New Features

*   Added support for joining channels with keys.
*   Added automatic reconnection after unexpected connection loss with bounded exponential backoff from 2 to 60 seconds.
*   Added automatic channel rejoin after a recovered connection completes IRC registration. Active channel names and optional keys are retained in memory, while channels deliberately parted or left after a kick are excluded.
*   Added accessible `Reconnect automatically` and `Rejoin channels after reconnecting` controls under Edit → Preferences → Connection. Existing configuration files inherit backward-compatible defaults.
*   Added a Text-to-Speech preference to interrupt ongoing speech so incoming messages speak immediately without piling up.
*   Added an experimental macOS option to route app announcements through VoiceOver when VoiceOver AppleScript control is enabled.

### Bug Fixes

*   Fixed SASL capability negotiation so authentication is not ended prematurely on `CAP LS`.
*   Fixed nickname tracking after `/nick` changes so private-message routing keeps working without reconnecting.
*   Fixed reconnect identity tracking so a nickname changed with `/nick` is reused after an unexpected disconnect.
*   Prevented intentional disconnects, `/quit`, application shutdown, and manual server changes from starting a reconnect attempt.
*   Prevented duplicate or unwanted channel rejoins after initial registration, `/part`, or a kick.
*   Fixed `/quit <reason>` so the requested quit message is not overwritten by a second default `QUIT`.
*   Fixed the Console tab to stop sending bogus `PRIVMSG Console` messages when users type regular chat there.
*   Fixed restored window sizes being overwritten by the default window dimensions at startup.
*   Fixed configuration loading to return independent copies instead of mutating shared in-memory defaults.
*   Fixed event-bus subscriptions leaking across frame lifecycles by unsubscribing handlers during teardown.
*   Fixed the macOS TTS voice path so runtime speech and “Test Speech” consistently use the same backend as the voice list shown in the UI.
*   Fixed the Eloquence voice submenu so language groups are built correctly and checked accurately.
*   Reduced macOS speech lag by keeping an Apple `say` helper process alive instead of spawning a fresh speech process for every utterance.
*   Fixed a macOS TTS regression where the new helper process could stay alive without actually speaking queued text because `say -i` was being driven through a plain pipe instead of a pseudo-terminal.
*   Replaced the macOS app TTS path with Apple’s modern `AVSpeechSynthesizer` backend via PyObjC so spoken output uses the platform speech framework instead of the older command-line speech fallback.

### Refactoring

*   Refactored the `_handle_line` method in `irc_client.py` to be more modular and maintainable.
*   Decoupled the UI and IRC client using an event bus.
*   Refactored the slash command handling in `main_frame.py` to be more organized and extensible.
*   Refactored the sound and TTS handling in `main_frame.py` to be cleaner and more maintainable.

### Testing and Build Verification

*   Added focused unit coverage for reconnect scheduling, bounded backoff, cancellation, welcome-time rejoin, channel removal, and nickname retention.
*   Verified the macOS application bundle and ZIP are built from the updated main checkout, pass code-signature and archive-integrity checks, and expose the new controls in the compiled UI.
