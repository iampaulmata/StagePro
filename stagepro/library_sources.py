from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List

from .paths import (
    libraries_config_path,
    libraries_published_dir,
    overrides_dir,
    resolve_library_path,
)


DEFAULT_VERSION = 1


def default_libraries_config() -> Dict[str, Any]:
    return {
        "version": DEFAULT_VERSION,
        "library_sources": [],
    }


@dataclass
class LibrarySource:
    source_id: str
    source_type: str = "github"
    name: str = ""
    enabled: bool = True
    include_globs: List[str] = field(default_factory=list)
    exclude_globs: List[str] = field(default_factory=list)
    local: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LibrarySource":
        source_id = str(data.get("id") or "").strip()
        local = dict(data.get("local", {}) or {})
        if source_id:
            local = _ensure_local_defaults(source_id, local)
        return cls(
            source_id=source_id,
            source_type=str(data.get("type") or "github"),
            name=str(data.get("name") or source_id),
            enabled=bool(data.get("enabled", True)),
            include_globs=list(data.get("include_globs") or []),
            exclude_globs=list(data.get("exclude_globs") or []),
            local=local,
            raw=dict(data),
        )

    def published_dir(self) -> Path:
        local_path = self.local.get("published_dir")
        if local_path:
            return resolve_library_path(str(local_path))
        return libraries_published_dir() / self.source_id

    def overrides_dir(self) -> Path:
        local_path = self.local.get("overrides_dir")
        if local_path:
            return resolve_library_path(str(local_path))
        return overrides_dir() / self.source_id


def _ensure_local_defaults(source_id: str, local: Dict[str, Any]) -> Dict[str, Any]:
    base = f"libraries/sources/{source_id}"
    defaults = {
        "source_root": base,
        "mirror_dir": f"{base}/mirror",
        "published_dir": f"libraries/published/{source_id}",
        "overrides_dir": f"songs/overrides/{source_id}",
    }
    out = dict(local)
    for key, value in defaults.items():
        out.setdefault(key, value)
    return out


def load_libraries_config() -> Dict[str, Any]:
    path = libraries_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default_libraries_config()

    cfg = default_libraries_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def save_libraries_config(cfg: Dict[str, Any]) -> None:
    path = libraries_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def parse_library_sources(cfg: Dict[str, Any]) -> List[LibrarySource]:
    sources = []
    for entry in cfg.get("library_sources", []) or []:
        source = LibrarySource.from_dict(entry)
        if source.source_id:
            sources.append(source)
    return sources
