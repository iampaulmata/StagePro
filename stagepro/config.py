import json
import os
import sys
from pathlib import Path
from typing import Tuple
from PySide6.QtCore import QStandardPaths

APP_NAME = "StagePro"
CONFIG_FILE_NAME = "stagepro_config.json"

def _app_base_dir() -> Path:
    """
    Returns the directory that should be treated as the 'portable root'.

    Priority:
    1) If running as an AppImage, use the directory containing the AppImage.
       (APPIMAGE env var is set by AppImage runtime.)
    2) If frozen (PyInstaller), use the directory containing the executable.
    3) Otherwise (dev mode), use the project root (directory containing stagepro.py).
    """
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return Path(appimage_path).resolve().parent

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # dev mode: stagepro.py is in repo root; config.py is in stagepro/
    return Path(__file__).resolve().parents[1]

def resolve_songs_path(config_songs_path: str | None = None) -> str:
    """
    Resolve songs path with portable preference.

    Order:
    1) If config explicitly sets songs_path, use that (relative paths resolve from portable root).
    2) If ./songs exists next to the AppImage/exe, use it (portable mode).
    3) Else use per-user data dir and create it.
    """
    base = _app_base_dir()

    # 1) Config override
    if config_songs_path:
        p = Path(config_songs_path).expanduser()
        if not p.is_absolute():
            p = (base / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    # 2) Portable folder next to app
    portable = base / "songs"
    if portable.exists() and portable.is_dir():
        return str(portable)

    # 3) Per-user fallback
    user_root = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    fallback = user_root / "songs"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)

def get_user_config_dir() -> Path:
    home = Path.home()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return home / ".config" / APP_NAME

def default_config() -> dict:
    return {
        "orientation": "portrait",
        "rotation_deg": 90,
        "portrait_rotation": 90, # deprecated; use rotation_deg
        "font": {
            "family": "DejaVu Sans",
            "size_px": 34,
            "line_height": 1.15,
            "chord_size_factor": 0.70,
            "chord_pad_em": 0.95
        },
        "colors": {
            "background": "#000000",
            "text": "#FFFFFF",
            "chords": "#FFD966",
            "chorus_border": "#FFFFFF",
            "comment": "#FFFFFF",
            "footer": "#FFFFFF",
            "hint": "#FFFFFF",
        },
        "ui": {
            "padding_x": 36,
            "padding_y": 24,
            "fit_mode": "fill",      # "fit" or "fill"
            "fit_margin_px": 8,
            "page_bottom_reserve_px": 64  # keep content above fixed hint/footer
        },
        "setlist": {
            "filename": "setlist.txt",
            "append_unlisted": True
        },
        "shortcuts": {
            "exit_hold_ms": 1500
        }
    }

def merge_defaults(d: dict, u: dict) -> dict:
    out = dict(d)
    for k, v in (u or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_defaults(out[k], v)
        else:
            out[k] = v
    return out

def load_or_create_config(base_dir: Path) -> Tuple[Path, dict]:
    local_path = base_dir / CONFIG_FILE_NAME
    user_path = get_user_config_dir() / CONFIG_FILE_NAME

    for p in (local_path, user_path):
        if p.exists():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
                return p, merge_defaults(default_config(), cfg)
            except Exception:
                return p, default_config()

    cfg = default_config()
    try:
        local_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return local_path, cfg
    except Exception:
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        cfg["songs_path"] = resolve_songs_path(cfg.get("songs_path"))
        return user_path, cfg
