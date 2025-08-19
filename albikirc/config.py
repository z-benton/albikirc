from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(os.path.expanduser("~")) / ".albikirc"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS: Dict[str, Any] = {
    "nick": "guest",
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
        "enabled": False,
        "message": "",
        "message_channel": "",
        "message_private": "",
        "message_sent": "",
        "mention": "",
        "notice": "",
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
