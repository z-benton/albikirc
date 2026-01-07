from __future__ import annotations
import json, os, sys
from pathlib import Path
from typing import Any, Dict

def _default_sound_dir() -> Path | None:
    """Locate the bundled Sounds directory in common layouts."""
    try:
        candidates = [
            Path(__file__).resolve().parent / "Sounds",  # packaged alongside module
            Path(__file__).resolve().parent.parent / "Sounds",  # source checkout
            Path.cwd() / "Sounds",  # frozen/cwd alongside executable
            Path(sys.executable).resolve().parent / "Sounds",  # next to built executable
        ]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "Sounds")  # PyInstaller onefile unpacked dir
        for c in candidates:
            if c.is_dir():
                return c
    except Exception:
        pass
    return None

_DEFAULT_SOUND_DIR = _default_sound_dir()

def _default_sound_path(name: str) -> str:
    try:
        if _DEFAULT_SOUND_DIR:
            p = _DEFAULT_SOUND_DIR / name
            if p.exists():
                return str(p)
    except Exception:
        pass
    return ""

APP_DIR = Path(os.path.expanduser("~")) / ".albikirc"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS: Dict[str, Any] = {
    "nick": "guest",
    "realname": "",
    "appearance": {
        "theme": "system",  # one of: system, light, dark
        "timestamps": True,
    },
    "beeps": {
        "enabled": False,
    },
    "ctcp": {
        "respond_to_ctcp_version": False,
        "ignore_ctcp": True,
        "version_string": "albikirc (wxPython)",
    },
    "notifications": {
        "show_join_part_notices": True,
        "show_quit_nick_notices": True,
        "activity_summaries": True,
        "activity_window_seconds": 10,
        "notices_inline": True,
    },
    "sounds": {
        "enabled": bool(_DEFAULT_SOUND_DIR),
        "message": _default_sound_path("receive.wav"),
        "message_channel": _default_sound_path("receive.wav"),
        "message_private": _default_sound_path("pm.wav"),
        "message_sent": _default_sound_path("send.wav"),
        "mention": _default_sound_path("mention.wav"),
        "notice": _default_sound_path("notice.wav"),
    },
    "servers": []
}

def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = a.copy()
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)  # type: ignore
        else:
            out[k] = v
    return out

def load() -> Dict[str, Any]:
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return merge(DEFAULTS, data)
    except Exception:
        pass
    return DEFAULTS.copy()

def save(cfg: Dict[str, Any]) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass
