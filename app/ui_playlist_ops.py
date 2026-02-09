from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QMessageBox


def move_selected_item(maint_playlist_list, delta: int, persist_current_playlist_order_callback) -> None:
    row = maint_playlist_list.currentRow()
    if row < 0:
        return
    new_row = row + int(delta)
    if new_row < 0 or new_row >= maint_playlist_list.count():
        return
    it = maint_playlist_list.takeItem(row)
    maint_playlist_list.insertItem(new_row, it)
    maint_playlist_list.setCurrentRow(new_row)
    persist_current_playlist_order_callback()


def persist_current_playlist_order(maint_playlist_list, active_playlist_id, playlists_set_items) -> None:
    pid = active_playlist_id
    if not pid:
        return
    items = []
    for i in range(maint_playlist_list.count()):
        it = maint_playlist_list.item(i)
        items.append(Path(it.data(0x0100)).name)  # Qt.UserRole
    playlists_set_items(pid, items)


def add_filename_to_active_playlist(filename: str, playlists_get_active, playlists_set_items) -> None:
    pl = playlists_get_active()
    items = list(pl.items)
    if filename.lower() in {x.lower() for x in items}:
        return
    items.append(filename)
    playlists_set_items(pl.playlist_id, items)


def add_selected_library_to_playlist(maint_library_list, add_filename_to_active_playlist_callback, refresh_maintenance_list_callback) -> None:
    item = maint_library_list.currentItem()
    if not item:
        return
    filename = Path(item.data(0x0100)).name  # Qt.UserRole
    add_filename_to_active_playlist_callback(filename)
    refresh_maintenance_list_callback(preserve_selection=False)


def remove_selected_from_playlist(active_playlist_id, maint_playlist_list, remove_items_by_index_callback, refresh_maintenance_list_callback, load_first_song_or_welcome_callback) -> None:
    pid = active_playlist_id
    if not pid:
        return
    row = maint_playlist_list.currentRow()
    if row < 0:
        return

    remove_items_by_index_callback(pid, [row])
    refresh_maintenance_list_callback(preserve_selection=False)
    load_first_song_or_welcome_callback()


def on_playlist_changed(cmb_playlist, set_active_callback, refresh_maintenance_list_callback, load_first_song_or_welcome_callback) -> None:
    pid = cmb_playlist.currentData()
    if not pid:
        return
    set_active_callback(pid)
    refresh_maintenance_list_callback(preserve_selection=False)
    load_first_song_or_welcome_callback()


def pl_new(parent, create_playlist_callback, refresh_maintenance_list_callback) -> None:
    name, ok = QInputDialog.getText(parent, "New Playlist", "Playlist name:")
    if not ok:
        return
    create_playlist_callback(name=name.strip() or "New Playlist", items=[])
    refresh_maintenance_list_callback(preserve_selection=False)


def pl_rename(parent, playlists_get_active, rename_playlist_callback, refresh_maintenance_list_callback) -> None:
    pl = playlists_get_active()
    name, ok = QInputDialog.getText(parent, "Rename Playlist", "New name:", text=pl.name)
    if not ok:
        return
    rename_playlist_callback(pl.playlist_id, name.strip() or pl.name)
    refresh_maintenance_list_callback(preserve_selection=True)


def pl_duplicate(playlists_get_active, duplicate_playlist_callback, refresh_maintenance_list_callback) -> None:
    pl = playlists_get_active()
    duplicate_playlist_callback(pl.playlist_id)
    refresh_maintenance_list_callback(preserve_selection=False)


def pl_delete(parent, playlists_get_active, delete_playlist_callback, refresh_maintenance_list_callback, load_first_song_or_welcome_callback) -> None:
    pl = playlists_get_active()
    resp = QMessageBox.question(
        parent,
        "Delete Playlist",
        f"Delete playlist '{pl.name}'?\n\nThis will NOT delete any song files.",
        QMessageBox.Yes | QMessageBox.No,
    )
    if resp != QMessageBox.Yes:
        return
    delete_playlist_callback(pl.playlist_id)
    refresh_maintenance_list_callback(preserve_selection=False)
    load_first_song_or_welcome_callback()


def save_setlist_from_ui(cfg, maint_playlist_list, songs_dir: Path, maint_status, refresh_song_list_callback) -> None:
    setlist_name = (cfg.get("setlist", {}) or {}).get("filename", "setlist.txt")
    lines = []
    for i in range(maint_playlist_list.count()):
        it = maint_playlist_list.item(i)
        lines.append(Path(it.data(0x0100)).name)  # Qt.UserRole
    p = songs_dir / setlist_name
    p.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    maint_status.setText(f"Saved setlist: {p}")
    refresh_song_list_callback()
