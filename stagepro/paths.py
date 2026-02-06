from __future__ import annotations

import os
import sys
from pathlib import Path
from PySide6.QtCore import QStandardPaths

from .config import APP_NAME


def get_app_data_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if base:
        return Path(base)

    home = Path.home()
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / APP_NAME


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def libraries_base_dir() -> Path:
    return ensure_dir(get_app_data_dir() / "libraries")


def libraries_sources_dir() -> Path:
    return ensure_dir(libraries_base_dir() / "sources")


def libraries_published_dir() -> Path:
    return ensure_dir(libraries_base_dir() / "published")


def overrides_dir() -> Path:
    return ensure_dir(get_app_data_dir() / "songs" / "overrides")


def libraries_config_path() -> Path:
    return get_app_data_dir() / "libraries.json"


def resolve_library_path(path_str: str | None) -> Path:
    if not path_str:
        return get_app_data_dir()
    p = Path(path_str).expanduser()
    if p.is_absolute():
        return p
    return get_app_data_dir() / p
