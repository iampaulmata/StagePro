from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import git_client
from .model import LibrarySource, LibrarySyncState, load_libraries_config, load_state, save_state
from .publisher import (
    scan_files,
    publish_full,
    publish_incremental,
    write_publish_manifest,
    is_supported_song_path,
)


@dataclass
class SyncResult:
    success: bool
    message: str
    files_indexed: int = 0
    last_commit: Optional[str] = None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_source(source_id: str, progress_cb: Optional[Callable[[str], None]] = None) -> SyncResult:
    cfg = load_libraries_config()
    source = next((s for s in cfg.library_sources if s.source_id == source_id), None)
    if not source:
        return SyncResult(False, f"Source {source_id} not found")

    state = load_state(source_id)
    state.status = "syncing"
    state.last_sync_at = _timestamp()
    save_state(source_id, state)

    def _progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    if not git_client.is_git_available():
        state.status = "error"
        state.last_error = "Git not found. Install Git to sync GitHub libraries."
        save_state(source_id, state)
        return SyncResult(False, state.last_error)

    mirror_dir = source.mirror_dir()
    published_dir = source.published_dir()

    try:
        if not (mirror_dir / ".git").exists():
            _progress(f"Cloning {source.repo_url}")
            git_client.clone(source.repo_url, source.default_branch, mirror_dir)
        _progress("Fetching updates")
        git_client.fetch(mirror_dir)
        _progress(f"Checking out {source.default_branch}")
        git_client.checkout_branch(mirror_dir, source.default_branch)

        head_before = state.last_commit
        head_remote = git_client.head_commit(mirror_dir, f"origin/{source.default_branch}")

        _progress("Resetting to remote")
        git_client.hard_reset_to_origin(mirror_dir, source.default_branch)
        head_after = git_client.head_commit(mirror_dir)

        if head_before and head_before == head_after and published_dir.exists():
            state.status = "idle"
            state.last_success_at = _timestamp()
            state.last_commit = head_after
            save_state(source_id, state)
            return SyncResult(True, "No updates", state.files_indexed, head_after)

        include_globs = source.include_globs or ["**/*.cho", "**/*.chopro", "**/*.pro", "**/*.txt"]
        exclude_globs = source.exclude_globs or ["**/.git/**"]

        if head_before and head_before != head_after and published_dir.exists():
            _progress("Calculating changes")
            diff = git_client.diff_name_status(mirror_dir, head_before, head_remote)
            changed = []
            deleted = []
            for status, rel_path in diff:
                path = mirror_dir / rel_path
                if status.startswith("D"):
                    deleted.append(path)
                else:
                    if path.exists() and path.is_file() and is_supported_song_path(path):
                        changed.append(path)
            _progress(f"Publishing {len(changed)} updated files")
            result = publish_incremental(mirror_dir, published_dir, changed, deleted)
        else:
            _progress("Scanning files")
            files = scan_files(mirror_dir, include_globs, exclude_globs)
            _progress(f"Publishing {len(files)} files")
            result = publish_full(source.source_id, mirror_dir, published_dir, files)

        if not result.success:
            state.status = "error"
            state.last_error = "\n".join(result.errors)
            save_state(source_id, state)
            return SyncResult(False, state.last_error or "Publish failed")

        state.status = "idle"
        state.last_success_at = _timestamp()
        state.last_commit = head_after
        state.files_indexed = _count_published_files(published_dir)
        save_state(source_id, state)
        _progress("Writing publish manifest")
        write_publish_manifest(source.source_id, published_dir, head_after, result.files_written)

        return SyncResult(True, "Sync complete", state.files_indexed, head_after)
    except Exception as exc:
        state.status = "error"
        state.last_error = str(exc)
        save_state(source_id, state)
        return SyncResult(False, str(exc))


def _count_published_files(published_dir: Path) -> int:
    if not published_dir.exists():
        return 0
    count = 0
    for path in published_dir.rglob("*"):
        if path.is_file() and is_supported_song_path(path):
            count += 1
    return count
