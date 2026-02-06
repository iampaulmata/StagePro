from pathlib import Path
from typing import List, Optional, Sequence

SUPPORTED_EXTS = {".cho", ".pro", ".chopro", ".txt"}

def list_song_files_alpha_from_roots(roots: Sequence[Path], cfg: dict) -> List[Path]:
    setlist_name = (cfg.get("setlist", {}) or {}).get("filename", "setlist.txt").lower()
    files_by_name: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for p in root.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in SUPPORTED_EXTS:
                continue
            if p.name.lower() == setlist_name:  # ignore setlist file as a song
                continue
            key = p.name.lower()
            if key not in files_by_name:
                files_by_name[key] = p
    files = sorted(files_by_name.values(), key=lambda x: x.name.lower())
    return files


def list_song_files_alpha(songs_dir: Path, cfg: dict) -> List[Path]:
    return list_song_files_alpha_from_roots([songs_dir], cfg)

def read_setlist(songs_dir: Path, setlist_filename: str) -> Optional[List[str]]:
    p = songs_dir / setlist_filename
    if not p.exists():
        return None

    lines: List[str] = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines

def order_songs(songs_dir: Path, cfg: dict) -> List[Path]:
    alpha = list_song_files_alpha(songs_dir, cfg)

    setlist_cfg = cfg.get("setlist", {}) or {}
    setlist_name = setlist_cfg.get("filename", "setlist.txt")
    append_unlisted = bool(setlist_cfg.get("append_unlisted", True))

    order = read_setlist(songs_dir, setlist_name)
    if order is None:
        return alpha

    by_name = {p.name.lower(): p for p in alpha}
    ordered: List[Path] = []
    seen = set()

    for item in order:
        key = item.lower()
        if key in by_name:
            ordered.append(by_name[key])
            seen.add(key)
        else:
            cand = (songs_dir / item)
            if cand.exists() and cand.is_file() and cand.suffix.lower() in SUPPORTED_EXTS:
                if cand.name.lower() != setlist_name.lower():
                    ordered.append(cand)
                    seen.add(cand.name.lower())

    if append_unlisted:
        for p in alpha:
            if p.name.lower() not in seen:
                ordered.append(p)

    return ordered if ordered else alpha
