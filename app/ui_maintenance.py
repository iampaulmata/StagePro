from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt


def refresh_playlist_selector(cmb_playlist, playlists) -> None:
    cmb_playlist.blockSignals(True)
    cmb_playlist.clear()

    active_id = playlists.active_playlist_id
    active_index = 0
    for i, pl in enumerate(playlists.list_playlists()):
        cmb_playlist.addItem(pl.name, pl.playlist_id)
        if pl.playlist_id == active_id:
            active_index = i

    cmb_playlist.setCurrentIndex(active_index)
    cmb_playlist.blockSignals(False)


def selected_path_for_preview(maint_playlist_list, maint_library_list) -> Optional[Path]:
    """Return selected song Path from either playlist or library list."""
    pl_items = maint_playlist_list.selectedItems()
    if pl_items:
        return Path(pl_items[0].data(Qt.UserRole))
    lib_items = maint_library_list.selectedItems()
    if lib_items:
        return Path(lib_items[0].data(Qt.UserRole))
    return None


def sync_active_song_to_path(path: Path, refresh_song_list, get_song_files, get_song_idx, load_song_by_index) -> None:
    """Sync the active on-stage song to the given path if it's in the current playable list."""
    refresh_song_list()
    song_files = get_song_files()
    if not song_files:
        return
    try:
        target = path.resolve()
    except Exception:
        target = path
    idx = None
    for i, p in enumerate(song_files):
        try:
            if p.resolve() == target:
                idx = i
                break
        except Exception:
            if p == path:
                idx = i
                break
    if idx is None:
        return
    if idx != get_song_idx():
        load_song_by_index(idx)
