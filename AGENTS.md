# Repository Guidelines

## Project Structure & Module Organization
- Core package in `albikirc/`: `app.py` (entrypoint), `irc_client.py` (socket + protocol), `event_bus.py` (pub/sub), `config.py` (settings file helpers).
- UI layer in `albikirc/ui/`: dialogs (connect, saved servers, preferences, help) and `main_frame.py` with chat panel composition.
- Assets live in `albikirc/Sounds/` and are bundled via `package-data`; macOS build artifacts land in `build/` and `dist/` (generated).

## Build, Test, and Development Commands
- Create venv (recommended): `python3 -m venv .venv && source .venv/bin/activate`.
- Install deps: `pip install -r requirements.txt` (wxPython).
- Run app from source: `python -m albikirc.app`.
- macOS app bundle: `./build-macos.sh` (use `--clean` to remove `build/` and `dist/`).
- Optional lint (config present): `python -m ruff .` if `ruff` is installed.

## Coding Style & Naming Conventions
- Python 3.10+; prefer 4-space indents and keep lines ≤100 chars (`[tool.ruff]` line-length).
- Follow existing patterns: imperative function names (`connect`, `send_message`), PascalCase wx classes (`MainFrame`, `ConnectDialog`), snake_case module files.
- Keep UI text accessible; set control names for screen readers (see `connect_dialog.py` and `main_frame.py`).

## Testing Guidelines
- No automated test suite yet; do manual verification by running `python -m albikirc.app` and walking through connect/join/send flows.
- When adding tests, colocate under `tests/` with `test_<module>.py` naming; prefer pytest-style functions and fixtures.
- For behavior changes around IRC parsing or event bus routing, include reproducible scenarios or scripts in PR notes.

## Commit & Pull Request Guidelines
- Write imperative, concise commit messages; prefix with scope when helpful (e.g., `feat:`, `fix:`, `docs:`), mirroring current history.
- PRs should include: summary of changes, user-visible impact, manual test notes (platform, commands run), and any screenshots for UI tweaks.
- Link issues when applicable; keep diffs focused and avoid bundling unrelated refactors.

## Configuration & Safety Notes
- User config persists at `~/.albikirc/config.json`; avoid committing personal configs or generated app bundles.
- Network code runs in threads; guard shared state mutations and keep UI updates on the main wx thread to prevent freezes.
