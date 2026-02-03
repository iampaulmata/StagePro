"""MusicBrainz metadata search and simple caching.

This module intentionally handles *metadata only* (no lyrics).

We use the public MusicBrainz web service (ws/2) endpoints with a required
User-Agent, and a small on-disk cache to keep the UI snappy and usable when
offline.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


MB_BASE = "https://musicbrainz.org/ws/2"


@dataclass
class MBRecordingHit:
    title: str
    artist: str
    recording_id: str
    release: Optional[str] = None
    date: Optional[str] = None
    score: Optional[int] = None


class MusicBrainzClient:
    def __init__(
        self,
        cache_path: Path,
        user_agent: str = "StagePro/0.1 (https://github.com/; contact: you@example.com)",
        min_interval_s: float = 1.0,
    ):
        self.cache_path = cache_path
        self.user_agent = user_agent
        self.min_interval_s = float(min_interval_s)
        self._last_request_at = 0.0
        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            if self.cache_path.exists():
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
        except Exception:
            # Cache failure should never break the app.
            pass

    def _throttle(self) -> None:
        now = time.time()
        dt = now - self._last_request_at
        if dt < self.min_interval_s:
            time.sleep(self.min_interval_s - dt)
        self._last_request_at = time.time()

    def _get_json(self, url: str) -> Dict[str, Any]:
        self._throttle()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    def search_recordings(self, title: str, artist: str, limit: int = 10) -> List[MBRecordingHit]:
        """Search recordings by title + artist.

        Returns a list of hits suitable for user selection.
        """
        title = (title or "").strip()
        artist = (artist or "").strip()
        if not title or not artist:
            return []

        key = f"rec::{title.lower()}::{artist.lower()}::{int(limit)}"
        cached = self._cache.get(key)
        if cached and isinstance(cached, dict) and "hits" in cached:
            return [MBRecordingHit(**h) for h in cached.get("hits") or []]

        # Query syntax: recording:"..." AND artist:"..."
        q = f'recording:"{title}" AND artist:"{artist}"'
        params = {
            "query": q,
            "fmt": "json",
            "limit": str(int(limit)),
        }
        url = f"{MB_BASE}/recording/?{urllib.parse.urlencode(params)}"
        data = self._get_json(url)

        hits: List[MBRecordingHit] = []
        for rec in data.get("recordings") or []:
            rid = rec.get("id") or ""
            rtitle = rec.get("title") or ""
            score = rec.get("score")

            # artist-credit can be a list of dicts
            ac = rec.get("artist-credit") or []
            aname = ""
            if ac:
                # Build the display name with joinphrases
                parts = []
                for part in ac:
                    name = (part.get("name") or (part.get("artist") or {}).get("name") or "")
                    join = part.get("joinphrase") or ""
                    if name:
                        parts.append(name + join)
                aname = "".join(parts).strip()

            release = None
            date = None
            rels = rec.get("releases") or []
            if rels:
                release = rels[0].get("title") or None
                date = rels[0].get("date") or None

            if rid and rtitle and aname:
                hits.append(
                    MBRecordingHit(
                        title=rtitle,
                        artist=aname,
                        recording_id=rid,
                        release=release,
                        date=date,
                        score=int(score) if score is not None else None,
                    )
                )

        self._cache[key] = {"cached_at": time.time(), "hits": [h.__dict__ for h in hits]}
        self._save_cache()
        return hits
