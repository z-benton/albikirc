# Changes

## Version 0.2.0

### New Features

*   Added support for joining channels with keys.

### Refactoring

*   Refactored the `_handle_line` method in `irc_client.py` to be more modular and maintainable.
*   Decoupled the UI and IRC client using an event bus.
*   Refactored the slash command handling in `main_frame.py` to be more organized and extensible.
*   Refactored the sound and TTS handling in `main_frame.py` to be cleaner and more maintainable.