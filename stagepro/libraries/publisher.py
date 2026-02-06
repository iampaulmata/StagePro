from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List
import fnmatch

from ..importers import ImportErrorWithHint, normalize_song_file

SUPPORTED_EXTS = {".cho", ".chopro", ".pro", ".txt"}


@dataclass
class PublishResult:
    files_written: int = 0
    files_deleted: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


def is_supported_song_path(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTS


def _matches_globs(rel_path: str, globs: list[str]) -> bool:
    if not globs:
        return True

    for pat in globs:
        # Normal match
        if fnmatch.fnmatch(rel_path, pat):
            return True

        # fnmatch does NOT treat ** specially; "**/*.ext" won't match "file.ext" at root.
        # So if pattern starts with "**/", also try it without that prefix.
        if pat.startswith("**/") and fnmatch.fnmatch(rel_path, pat[3:]):
            return True

    return False

def scan_files(mirror_dir: Path, include_globs: list[str], exclude_globs: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in mirror_dir.rglob("*"):
        if not path.is_file():
            continue
        if not is_supported_song_path(path):
            continue
        rel = path.relative_to(mirror_dir).as_posix()
        if exclude_globs and _matches_globs(rel, exclude_globs):
            continue
        if include_globs and not _matches_globs(rel, include_globs):
            continue
        files.append(path)
    return files


def _write_normalized(src: Path, dest: Path) -> None:
    imported = normalize_song_file(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(imported.chordpro_text, encoding="utf-8")


def publish_full(source_id: str, mirror_dir: Path, published_dir: Path, files: Iterable[Path]) -> PublishResult:
    result = PublishResult()
    tmp_dir = published_dir.parent / f"{source_id}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        rel = path.relative_to(mirror_dir)
        dest = tmp_dir / rel
        try:
            _write_normalized(path, dest)
            result.files_written += 1
        except ImportErrorWithHint as exc:
            result.errors.append(f"{rel.as_posix()}: {exc}")
        except Exception as exc:
            result.errors.append(f"{rel.as_posix()}: {exc}")

    if result.errors:
        return result

    if published_dir.exists():
        shutil.rmtree(published_dir)
    tmp_dir.rename(published_dir)
    return result


def publish_incremental(
    mirror_dir: Path,
    published_dir: Path,
    changed: Iterable[Path],
    deleted: Iterable[Path],
) -> PublishResult:
    result = PublishResult()
    for path in changed:
        rel = path.relative_to(mirror_dir)
        dest = published_dir / rel
        try:
            _write_normalized(path, dest)
            result.files_written += 1
        except ImportErrorWithHint as exc:
            result.errors.append(f"{rel.as_posix()}: {exc}")
        except Exception as exc:
            result.errors.append(f"{rel.as_posix()}: {exc}")

    for path in deleted:
        rel = path.relative_to(mirror_dir)
        dest = published_dir / rel
        if dest.exists():
            dest.unlink()
            result.files_deleted += 1
            _prune_empty_dirs(dest.parent, published_dir)
    return result


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    cur = start
    while cur != stop and stop in cur.parents:
        if any(cur.iterdir()):
            break
        cur.rmdir()
        cur = cur.parent


def write_publish_manifest(source_id: str, published_dir: Path, head_commit: str, files_written: int) -> None:
    manifest = {
        "source_id": source_id,
        "head_commit": head_commit,
        "files_written": files_written,
    }
    path = published_dir / "publish_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
