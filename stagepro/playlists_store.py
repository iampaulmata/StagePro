from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import get_user_config_dir
from .playlist import SUPPORTED_EXTS, list_song_files_alpha, read_setlist  # existing helpers


PLAYLISTS_FILENAME = "playlists.json"
SCHEMA_VERSION = 1


def _now_iso() -> str:
    # keep tiny + dependency-free; optional
    import datetime as _dt
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class Playlist:
    playlist_id: str
    name: str
    items: List[str]  # filenames relative to songs_dir


class PlaylistStore:
    """Simple JSON-backed store for playlists/setlists.

    - Playlist items reference song *filenames* (not absolute paths).
    - No song files are ever deleted by this store.
    """

    def __init__(self, songs_dir: Path, cfg: dict):
        self.songs_dir = Path(songs_dir)
        self.cfg = cfg or {}
        self.path = get_user_config_dir() / PLAYLISTS_FILENAME

        self.version = SCHEMA_VERSION
        self.active_playlist_id: Optional[str] = None
        self.playlist_order: List[str] = []
        self.playlists: Dict[str, Playlist] = {}

    # ---------- public API ----------

    def load_or_init(self) -> None:
        if self.path.exists():
            self._load()
            # ensure at least one playlist exists
            if not self.playlist_order or not self.playlists:
                self._init_default()
                self.save()
            if not self.active_playlist_id or self.active_playlist_id not in self.playlists:
                self.active_playlist_id = self.playlist_order[0]
                self.save()
            return

        # first-run for playlists => migrate from legacy setlist.txt
        self._init_from_legacy_setlist()
        self.save()

    def save(self) -> None:
        data = {
            "version": SCHEMA_VERSION,
            "active_playlist_id": self.active_playlist_id,
            "playlist_order": self.playlist_order,
            "playlists": {
                pid: {"name": pl.name, "items": list(pl.items)}
                for pid, pl in self.playlists.items()
            },
            "updated_at": _now_iso(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def list_playlists(self) -> List[Playlist]:
        out: List[Playlist] = []
        for pid in self.playlist_order:
            pl = self.playlists.get(pid)
            if pl:
                out.append(pl)
        return out

    def get_active(self) -> Playlist:
        if self.active_playlist_id and self.active_playlist_id in self.playlists:
            return self.playlists[self.active_playlist_id]
        # fallback
        first = self.playlist_order[0]
        self.active_playlist_id = first
        return self.playlists[first]

    def set_active(self, playlist_id: str) -> None:
        if playlist_id in self.playlists:
            self.active_playlist_id = playlist_id
            self.save()

    def create_playlist(self, name: str, items: Optional[List[str]] = None) -> str:
        pid = str(uuid.uuid4())
        self.playlists[pid] = Playlist(playlist_id=pid, name=(name or "New Playlist").strip(), items=list(items or []))
        self.playlist_order.append(pid)
        self.active_playlist_id = pid
        self.save()
        return pid

    def rename_playlist(self, playlist_id: str, new_name: str) -> None:
        pl = self.playlists.get(playlist_id)
        if not pl:
            return
        pl.name = (new_name or pl.name).strip()
        self.save()

    def duplicate_playlist(self, playlist_id: str) -> Optional[str]:
        pl = self.playlists.get(playlist_id)
        if not pl:
            return None
        name = f"{pl.name} (Copy)"
        return self.create_playlist(name=name, items=list(pl.items))

    def delete_playlist(self, playlist_id: str) -> None:
        if playlist_id not in self.playlists:
            return
        # don’t allow deleting the last playlist
        if len(self.playlist_order) <= 1:
            return

        self.playlists.pop(playlist_id, None)
        self.playlist_order = [x for x in self.playlist_order if x != playlist_id]

        if self.active_playlist_id == playlist_id:
            self.active_playlist_id = self.playlist_order[0] if self.playlist_order else None

        self.save()

    def set_items(self, playlist_id: str, items: List[str]) -> None:
        pl = self.playlists.get(playlist_id)
        if not pl:
            return
        pl.items = list(items)
        self.save()

    def remove_items_by_index(self, playlist_id: str, indices: List[int]) -> None:
        pl = self.playlists.get(playlist_id)
        if not pl:
            return
        keep = []
        idx_set = set(indices)
        for i, s in enumerate(pl.items):
            if i not in idx_set:
                keep.append(s)
        pl.items = keep
        self.save()

    # ---------- legacy migration ----------

    def _init_default(self) -> None:
        pid = str(uuid.uuid4())
        self.playlists = {pid: Playlist(pid, "Default Set", [])}
        self.playlist_order = [pid]
        self.active_playlist_id = pid

    def _init_from_legacy_setlist(self) -> None:
        self._init_default()
        setlist_cfg = self.cfg.get("setlist", {}) or {}
        setlist_name = setlist_cfg.get("filename", "setlist.txt")

        # Try legacy order first
        legacy = read_setlist(self.songs_dir, setlist_name)

        if legacy:
            # keep only entries that point to actual files; do NOT create placeholders
            actual = {p.name for p in list_song_files_alpha(self.songs_dir, self.cfg)}
            items = [x for x in legacy if x in actual]
        else:
            # fallback: alphabetical library
            items = [p.name for p in list_song_files_alpha(self.songs_dir, self.cfg)]

        self.playlists[self.active_playlist_id].items = items

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.version = int(raw.get("version") or 1)
        self.active_playlist_id = raw.get("active_playlist_id")
        self.playlist_order = list(raw.get("playlist_order") or [])
        pls = raw.get("playlists") or {}

        self.playlists = {}
        for pid, pdata in pls.items():
            self.playlists[pid] = Playlist(
                playlist_id=pid,
                name=str(pdata.get("name") or "Playlist"),
                items=list(pdata.get("items") or []),
            )

        # repair order if needed
        for pid in list(self.playlists.keys()):
            if pid not in self.playlist_order:
                self.playlist_order.append(pid)
        self.playlist_order = [pid for pid in self.playlist_order if pid in self.playlists]
