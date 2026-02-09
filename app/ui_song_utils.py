from pathlib import Path
from typing import Iterable, Optional


def read_song_text_for_edit(path: Path) -> str:
    """Read song text using UTF-8, falling back to latin-1 if needed."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def is_under_dir(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def library_published_root_for(path: Path, published_dirs: Iterable[Path]) -> Optional[Path]:
    """Return the published root dir (published/<source_id>) that contains path."""
    for pub in (published_dirs or []):
        if is_under_dir(path, pub):
            return pub
    return None


def make_unique_local_name(songs_dir: Path, preferred_name: str) -> str:
    """Make a unique filename in songs_dir root."""
    preferred = Path(preferred_name).name
    stem = Path(preferred).stem
    ext = "".join(Path(preferred).suffixes) or ""
    cand = songs_dir / (stem + ext)
    if not cand.exists():
        return cand.name

    for i in range(1, 10_000):
        cand = songs_dir / f"{stem} ({i}){ext}"
        if not cand.exists():
            return cand.name
    raise RuntimeError("Could not generate a unique filename for local copy")
