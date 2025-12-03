#!/usr/bin/env bash
set -euo pipefail

# Build a Linux bundle for albikirc using PyInstaller.
# Produces an onedir folder by default and an optional tar.gz artifact.

APP_NAME="Albikirc"
ENTRYPOINT="albikirc/app.py"
SOUNDS_DIR="albikirc/Sounds"
# Virtualenv selection happens dynamically below; default if none found
DEFAULT_VENV_DIR=".venv-build"
VENV_DIR=""

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --clean                 Remove build artifacts and exit
  --python PATH           Use a specific Python 3.x interpreter
  --icon PATH             Optional .png/.ico icon to include
  --onefile               Build a single-file binary instead of onedir
  --no-tar                Skip creating the .tar.gz archive
  -h, --help              Show this help

Notes:
  - Requires GTK3 and related development libraries for wxPython.
  - The output is built for the host architecture (e.g., x86_64, aarch64).
USAGE
}

ICON_PATH=""
MAKE_TAR=1
ONEFILE=0

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
      [[ -n "${ICON_PATH}" && -f "${ICON_PATH}" ]] || { echo "--icon requires an existing icon path" >&2; exit 2; }
      ;;
    --onefile)
      ONEFILE=1
      ;;
    --no-tar)
      MAKE_TAR=0
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

# Resolve Python 3.x (>=3.12). Prefer active or local venvs if present.
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
  elif [[ -x ".venv312/bin/python" ]]; then
    VENV_DIR=".venv312"
    PYTHON_BIN="${PWD}/.venv312/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Reusing virtualenv at .venv312"
  else
    if command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v python)"
    else
      echo "Error: No python3 found on PATH. Install Python 3.12+ and retry." >&2
      exit 1
    fi
    VENV_DIR="${DEFAULT_VENV_DIR}"
  fi
fi

# Verify version >= 3.12
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
if (( PY_MAJ < 3 || (PY_MAJ == 3 && PY_MIN < 12) )); then
  echo "Error: Python ${PY_VER_OUT} detected; require >= 3.12" >&2
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
  elif [[ "${PYTHON_BIN}" != "${PWD}/.venv312/bin/python" && -x ".venv312/bin/python" ]] && check_mods "${PWD}/.venv312/bin/python"; then
    VENV_DIR=".venv312"
    PYTHON_BIN="${PWD}/.venv312/bin/python"
    USING_EXISTING_VENV=1
    echo "[env] Switching to .venv312 (has required modules)"
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
rm -rf "dist/${APP_NAME}" "dist/${APP_NAME}.tar.gz" "${APP_NAME}.spec"

echo "[build] Running PyInstaller"
PI_ARGS=(
  --noconfirm \
  --windowed \
  --name "${APP_NAME}"
)

if [[ -n "$ICON_PATH" ]]; then
  PI_ARGS+=( --icon "$ICON_PATH" )
fi

if [[ $ONEFILE -eq 1 ]]; then
  PI_ARGS+=( --onefile )
fi

PI_ARGS+=( --add-data "${SOUNDS_DIR}:Sounds" "${ENTRYPOINT}" )

# Constrain PyInstaller cache into workspace (sandbox-safe)
export PYINSTALLER_CACHE_DIR="${PWD}/.pyinstaller-cache"
export XDG_CACHE_HOME="${PYINSTALLER_CACHE_DIR}"
mkdir -p "${PYINSTALLER_CACHE_DIR}"
export HOME="${PWD}/.home"
mkdir -p "${HOME}"

"${PYTHON_BIN}" -m PyInstaller "${PI_ARGS[@]}"

ARCH="$(uname -m)"
if [[ $MAKE_TAR -eq 1 ]]; then
  TARBALL="dist/${APP_NAME}-linux-${ARCH}.tar.gz"
  echo "[pack] Creating tarball at ${TARBALL}"
  rm -f "$TARBALL"
  tar -czf "$TARBALL" -C dist "${APP_NAME}"
  echo "[done] Binary: dist/${APP_NAME} (tarball at ${TARBALL})"
else
  echo "[done] Binary: dist/${APP_NAME}"
fi
