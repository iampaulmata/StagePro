from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..paths import libraries_config_path, libraries_sources_dir, resolve_library_path


DEFAULT_VERSION = 1


@dataclass
class LibrarySource:
    source_id: str
    source_type: str = "github"
    name: str = ""
    enabled: bool = True
    repo_url: str = ""
    default_branch: str = "main"
    include_globs: List[str] = field(default_factory=list)
    exclude_globs: List[str] = field(default_factory=list)
    sync: Dict[str, Any] = field(default_factory=dict)
    auth: Dict[str, Any] = field(default_factory=dict)
    local: Dict[str, Any] = field(default_factory=dict)

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
            repo_url=str(data.get("repo_url") or ""),
            default_branch=str(data.get("default_branch") or "main"),
            include_globs=list(data.get("include_globs") or []),
            exclude_globs=list(data.get("exclude_globs") or []),
            sync=dict(data.get("sync", {}) or {}),
            auth=dict(data.get("auth", {}) or {}),
            local=local,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.source_id,
            "type": self.source_type,
            "name": self.name,
            "enabled": self.enabled,
            "repo_url": self.repo_url,
            "default_branch": self.default_branch,
            "include_globs": list(self.include_globs),
            "exclude_globs": list(self.exclude_globs),
            "sync": dict(self.sync),
            "auth": dict(self.auth),
            "local": dict(self.local),
        }

    def mirror_dir(self) -> Path:
        return resolve_library_path(str(self.local.get("mirror_dir", "")))

    def published_dir(self) -> Path:
        return resolve_library_path(str(self.local.get("published_dir", "")))

    def overrides_dir(self) -> Path:
        return resolve_library_path(str(self.local.get("overrides_dir", "")))


@dataclass
class LibrariesConfig:
    version: int = DEFAULT_VERSION
    library_sources: List[LibrarySource] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LibrariesConfig":
        sources = [LibrarySource.from_dict(entry) for entry in data.get("library_sources", []) or []]
        sources = [s for s in sources if s.source_id]
        version = int(data.get("version") or DEFAULT_VERSION)
        return cls(version=version, library_sources=sources)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "library_sources": [s.to_dict() for s in self.library_sources],
        }


@dataclass
class LibrarySyncState:
    status: str = "idle"
    last_sync_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    last_commit: Optional[str] = None
    files_indexed: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LibrarySyncState":
        return cls(
            status=str(data.get("status") or "idle"),
            last_sync_at=data.get("last_sync_at"),
            last_success_at=data.get("last_success_at"),
            last_error=data.get("last_error"),
            last_commit=data.get("last_commit"),
            files_indexed=int(data.get("files_indexed") or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "last_sync_at": self.last_sync_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "last_commit": self.last_commit,
            "files_indexed": self.files_indexed,
        }


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


def load_libraries_config(path: Optional[Path] = None) -> LibrariesConfig:
    cfg_path = path or libraries_config_path()
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return LibrariesConfig.from_dict(data)
        except Exception:
            return LibrariesConfig()
    cfg = LibrariesConfig()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    return cfg


def save_libraries_config(cfg: LibrariesConfig, path: Optional[Path] = None) -> None:
    cfg_path = path or libraries_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")


def load_state(source_id: str) -> LibrarySyncState:
    state_path = libraries_sources_dir() / source_id / "state.json"
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return LibrarySyncState.from_dict(data)
        except Exception:
            return LibrarySyncState(status="error", last_error="Failed to read state.json")
    return LibrarySyncState()


def save_state(source_id: str, state: LibrarySyncState) -> None:
    state_path = libraries_sources_dir() / source_id / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
