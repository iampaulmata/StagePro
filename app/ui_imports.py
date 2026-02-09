import re
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QFileDialog, QMessageBox


def on_import_clicked(
    parent,
    songs_dir: Path,
    add_filename_to_active_playlist_callback,
    refresh_maintenance_list_callback,
    import_user_file_to_chordpro,
    choose_destination_path,
    import_error_type,
) -> None:
    files, _ = QFileDialog.getOpenFileNames(
        parent,
        "Import songs",
        str(songs_dir),
        "Songs (*.pro *.cho *.chopro *.txt);;All files (*)",
    )
    if not files:
        return

    imported = 0
    warnings: List[str] = []
    for fp in files:
        src = Path(fp)

        # If the selected file is already in the songs folder, do NOT import/copy it.
        # Just add it to the active playlist.
        try:
            if src.resolve().parent == songs_dir.resolve():
                if src.exists() and src.is_file():
                    add_filename_to_active_playlist_callback(src.name)
                    imported += 1
                    continue
        except Exception:
            pass

        try:
            imp = import_user_file_to_chordpro(src)
            title = imp.title or src.stem
            artist = imp.artist or "Unknown"
            dest = choose_destination_path(songs_dir, title, artist, ext=".pro")
            dest.write_text(imp.chordpro_text, encoding="utf-8")
            imported += 1
            add_filename_to_active_playlist_callback(dest.name)

            if not imp.title or not imp.artist:
                warnings.append(
                    f"{src.name}: imported, but title/artist missing in directives (you can autofill from MusicBrainz)"
                )
        except import_error_type as e:
            warnings.append(f"{src.name}: {e}")
        except Exception as e:
            warnings.append(f"{src.name}: import failed ({e})")

    refresh_maintenance_list_callback(preserve_selection=False)
    msg = f"Imported {imported} file(s)."
    if warnings:
        msg += "\n\n" + "\n".join(warnings[:12])
        if len(warnings) > 12:
            msg += f"\n…and {len(warnings) - 12} more."
    QMessageBox.information(parent, "Import", msg)


def on_mb_autofill_clicked(
    parent,
    selected_path_for_preview_callback,
    mb_client,
    pick_musicbrainz_hit_callback,
    upsert_directives,
    maint_status,
    preview_song_in_maintenance_callback,
) -> None:
    path = selected_path_for_preview_callback()
    if not path:
        QMessageBox.information(parent, "MusicBrainz", "Select a song first.")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")

    # Extract title/artist from existing directives if present.
    title = ""
    artist = ""
    for raw in text.splitlines():
        m = re.match(r"^\s*\{\s*([^}:]+)\s*:\s*([^}]*)\}\s*$", raw, flags=re.IGNORECASE)
        if not m:
            continue
        k = m.group(1).strip().lower()
        v = m.group(2).strip()
        if k in {"title", "t"} and not title:
            title = v
        if k in {"artist", "a"} and not artist:
            artist = v

    if not title or not artist:
        QMessageBox.information(
            parent,
            "MusicBrainz",
            "This file is missing a title and/or artist directive.\n\n"
            "StagePro can search MusicBrainz only when it knows the song title and artist.\n"
            "Add {title: ...} and {artist: ...} (or re-import using the fallback header format).",
        )
        return

    try:
        hits = mb_client.search_recordings(title=title, artist=artist, limit=12)
    except Exception as e:
        QMessageBox.critical(parent, "MusicBrainz", f"Search failed: {e}")
        return

    if not hits:
        QMessageBox.information(parent, "MusicBrainz", "No matches found.")
        return

    chosen = pick_musicbrainz_hit_callback(hits)
    if not chosen:
        return

    updates = {}
    updates.setdefault("title", chosen.title)
    updates.setdefault("artist", chosen.artist)
    if chosen.release:
        updates.setdefault("album", chosen.release)
    if chosen.date:
        updates.setdefault("year", chosen.date.split("-")[0])

    current_meta = {}
    for raw in text.splitlines():
        m = re.match(r"^\s*\{\s*([^}:]+)\s*:\s*([^}]*)\}\s*$", raw, flags=re.IGNORECASE)
        if m:
            current_meta[m.group(1).strip().lower()] = m.group(2).strip()

    filtered_updates = {k: v for k, v in updates.items() if not current_meta.get(k)}
    if not filtered_updates:
        QMessageBox.information(parent, "MusicBrainz", "Nothing to autofill — metadata is already present.")
        return

    new_text, _ = upsert_directives(text, filtered_updates)
    try:
        path.write_text(new_text, encoding="utf-8")
    except Exception as e:
        QMessageBox.critical(parent, "MusicBrainz", f"Failed to save updates: {e}")
        return

    maint_status.setText(f"Autofilled metadata from MusicBrainz for: {path.name}")
    preview_song_in_maintenance_callback(path)
