#!/usr/bin/env bash
set -euo pipefail

# Build a macOS .app bundle for albikirc using PyInstaller,
# clean duplicates so only the .app remains, and create a zip.

APP_NAME="Albikirc"
ENTRYPOINT="albikirc/app.py"
SOUNDS_DIR="Sounds"
# Virtualenv selection happens dynamically below; default if none found
DEFAULT_VENV_DIR=".venv-build"
VENV_DIR=""

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --clean                 Remove build artifacts and exit
  --python PATH           Use a specific Python 3.x interpreter
  --icon PATH             Optional .icns icon to include
  --no-zip                Skip creating the .zip archive
  -h, --help              Show this help

Notes:
  - Architecture is determined by the Python you use (arm64 vs x86_64).
    For Intel builds on Apple Silicon, run with an x86_64 Python under Rosetta,
    e.g. 'arch -x86_64 ./build-macos.sh --python /usr/local/bin/python3'.
USAGE
}

ICON_PATH=""
MAKE_ZIP=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)
      echo "[clean] Removing build artifacts"
      rm -rf build dist "${APP_NAME}.spec"
      exit 0
      ;;
    --python)
      shift
      PYTHON_BIN="${1:-}"
      [[ -n "${PYTHON_BIN}" ]] || { echo "--python requires a path" >&2; exit 2; }
      ;;
    --icon)
      shift
      ICON_PATH="${1:-}"
      [[ -n "${ICON_PATH}" && -f "${ICON_PATH}" ]] || { echo "--icon requires an existing .icns path" >&2; exit 2; }
      ;;
    --no-zip)
      MAKE_ZIP=0
      ;;
    -h|--help)
      usage; exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 2
      ;;
  esac
  shift
done

# Resolve Python 3.x (>=3.10). Prefer active or local venvs if present.
PYTHON_BIN="${PYTHON_BIN:-}"
USING_EXISTING_VENV=0
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    VENV_DIR="${VIRTUAL_ENV}"
    PYTHON_BIN="${VENV_DIR}/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Reusing active virtualenv at ${VENV_DIR}"
  elif [[ -x ".venv/bin/python" ]]; then
    VENV_DIR=".venv"
    PYTHON_BIN="${PWD}/.venv/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Reusing virtualenv at .venv"
  elif [[ -x ".venv310/bin/python" ]]; then
    VENV_DIR=".venv310"
    PYTHON_BIN="${PWD}/.venv310/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Reusing virtualenv at .venv310"
  else
    if command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v python)"
    else
      echo "Error: No python3 found on PATH. Install Python 3.10+ and retry." >&2
      exit 1
    fi
    VENV_DIR="${DEFAULT_VENV_DIR}"
  fi
fi

# Verify version >= 3.10
PY_VER_OUT="$("${PYTHON_BIN}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ -z "${PY_VER_OUT}" ]]; then
  echo "Error: Unable to determine Python version from ${PYTHON_BIN}" >&2
  exit 1
fi
PY_MAJ=${PY_VER_OUT%%.*}
PY_MIN=${PY_VER_OUT#*.}
if (( PY_MAJ < 3 || (PY_MAJ == 3 && PY_MIN < 10) )); then
  echo "Error: Python ${PY_VER_OUT} detected; require >= 3.10" >&2
  exit 1
fi

echo "[build] Using Python: ${PYTHON_BIN} (v${PY_VER_OUT})"

# Prefer a venv with required packages if available
check_mods() {
  "${1}" - <<'PY' >/dev/null 2>&1
import sys
try:
    import wx, PyInstaller  # noqa: F401
except Exception:
    sys.exit(1)
else:
    sys.exit(0)
PY
  return $?
}

if ! check_mods "${PYTHON_BIN}"; then
  # Try fallback local venvs in priority order
  if [[ "${PYTHON_BIN}" != "${PWD}/.venv/bin/python" && -x ".venv/bin/python" ]] && check_mods "${PWD}/.venv/bin/python"; then
    VENV_DIR=".venv"
    PYTHON_BIN="${PWD}/.venv/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Switching to .venv (has required modules)"
  elif [[ "${PYTHON_BIN}" != "${PWD}/.venv310/bin/python" && -x ".venv310/bin/python" ]] && check_mods "${PWD}/.venv310/bin/python"; then
    VENV_DIR=".venv310"
    PYTHON_BIN="${PWD}/.venv310/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Switching to .venv310 (has required modules)"
  fi
fi

# Create and/or activate venv if VENV_DIR is set and not active
if [[ -n "${VENV_DIR}" && ! -d "$VENV_DIR" ]]; then
  echo "[build] Creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
# If we have a venv dir, activate it for PATH convenience (not strictly required)
if [[ -n "${VENV_DIR}" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
fi

echo "[build] Ensuring dependencies (offline-friendly)"
# Best-effort tooling upgrade; continue if offline
"${PYTHON_BIN}" -m pip install --upgrade pip wheel >/dev/null 2>&1 || true
if ! "${PYTHON_BIN}" - <<'PY'
import sys
ok = True
try:
    import wx  # noqa: F401
except Exception:
    ok = False
try:
    import PyInstaller  # noqa: F401
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
then
  echo "[deps] Installing wxPython and PyInstaller"
  if ! "${PYTHON_BIN}" -m pip install -q wxPython pyinstaller; then
    echo "[error] Failed to install wxPython/PyInstaller. Ensure network access or preinstall in ${VENV_DIR}." >&2
    exit 1
  fi
else
  echo "[deps] Already satisfied"
fi

echo "[build] Cleaning previous build artifacts"
rm -rf build
mkdir -p dist
rm -rf "dist/${APP_NAME}.app" "dist/${APP_NAME}"

echo "[build] Running PyInstaller"
PI_ARGS=(
  --noconfirm \
  --windowed \
  --name "${APP_NAME}"
)

if [[ -n "$ICON_PATH" ]]; then
  PI_ARGS+=( --icon "$ICON_PATH" )
fi

PI_ARGS+=( --add-data "${SOUNDS_DIR}:${SOUNDS_DIR}" "${ENTRYPOINT}" )

# Constrain PyInstaller cache into workspace (sandbox-safe)
export PYINSTALLER_CACHE_DIR="${PWD}/.pyinstaller-cache"
mkdir -p "${PYINSTALLER_CACHE_DIR}"
# Also sandbox HOME so PyInstaller's macOS cache under ~/Library/... stays inside workspace
export HOME="${PWD}/.home"
mkdir -p "${HOME}"

"${PYTHON_BIN}" -m PyInstaller "${PI_ARGS[@]}"

echo "[build] Removing duplicate onedir folder (keeping only .app)"
rm -rf "dist/${APP_NAME}"

ARCH="$(uname -m)"
if [[ $MAKE_ZIP -eq 1 ]]; then
  ZIP_PATH="dist/${APP_NAME}-macOS-${ARCH}.zip"
  echo "[pack] Creating zip at ${ZIP_PATH}"
  rm -f "$ZIP_PATH"
  (
    cd dist
    # Prefer ditto for better macOS metadata; fallback to zip
    if command -v ditto >/dev/null 2>&1; then
      ditto -ck --keepParent "${APP_NAME}.app" "${APP_NAME}-macOS-${ARCH}.zip" 2>/dev/null || \
        zip -qr "${APP_NAME}-macOS-${ARCH}.zip" "${APP_NAME}.app"
    else
      zip -qr "${APP_NAME}-macOS-${ARCH}.zip" "${APP_NAME}.app"
    fi
  )
  echo "[done] App: dist/${APP_NAME}.app"
  echo "[done] Zip: ${ZIP_PATH}"
else
  echo "[done] App: dist/${APP_NAME}.app (zip disabled)"
fi
