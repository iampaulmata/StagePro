import json
import os
import sys
from pathlib import Path
from typing import Tuple

APP_NAME = "StagePro"
CONFIG_FILE_NAME = "stagepro_config.json"

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
        "orientation": "landscape",     # "landscape" or "portrait"
        "portrait_rotation": 90,        # 90 or 270
        "font": {
            "family": "DejaVu Sans",
            "size_px": 34,
            "line_height": 1.15,
            "chord_size_factor": 0.70,  # chord font relative to lyric font
            "chord_pad_em": 0.95        # vertical room reserved above lyrics
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
        return user_path, cfg
