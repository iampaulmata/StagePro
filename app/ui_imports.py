import re
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


_CHORD_BRACKET_RE = re.compile(r"\[[^\]\r\n]+\]")
_CHORD_TOKEN_RE = re.compile(
    r"^(?:[A-G](?:#|b)?(?:maj|min|m|dim|aug|sus|add)?\d*(?:\([^)]*\))?(?:/[A-G](?:#|b)?)?|N\.?C\.?)$",
    flags=re.IGNORECASE,
)


def strip_chord_annotations(chordpro_text: str) -> str:
    """Return lyric-first text by removing chord annotations and chord-only rows."""
    normalized = (chordpro_text or "").replace("\r\n", "\n").replace("\r", "\n")
    out_lines: List[str] = []

    for line in normalized.split("\n"):
        if not line.strip():
            out_lines.append("")
            continue

        if re.match(r"^\s*\{\s*[^}:]+\s*:\s*[^}]*\}\s*$", line):
            out_lines.append(line.strip())
            continue

        de_chorded = _CHORD_BRACKET_RE.sub("", line)
        de_chorded = re.sub(r"\s{2,}", " ", de_chorded).strip()
        if not de_chorded:
            continue

        tokens = de_chorded.split()
        if tokens and all(_CHORD_TOKEN_RE.match(tok) for tok in tokens):
            continue

        out_lines.append(de_chorded)

    return "\n".join(out_lines)


class UltimateGuitarImportDialog(QDialog):
    def __init__(self, parent, ug_client) -> None:
        super().__init__(parent)
        self.ug_client = ug_client
        self.hits = []
        self.selected_hit = None
        self.selected_detail = None
        self.selected_chordpro_raw = ""
        self.selected_chordpro = ""

        self.setWindowTitle("Ultimate Guitar Import")
        self.resize(980, 640)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Search Ultimate Guitar, click a result to load a ChordPro preview, then import that previewed tab.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        query_row = QHBoxLayout()
        self.query_edit = QLineEdit(self)
        self.query_edit.setPlaceholderText("Song title or artist")
        self.search_btn = QPushButton("Search", self)
        query_row.addWidget(self.query_edit, 1)
        query_row.addWidget(self.search_btn)
        layout.addLayout(query_row)

        body = QHBoxLayout()
        self.results_list = QListWidget(self)
        self.results_list.setMinimumWidth(360)
        body.addWidget(self.results_list, 2)

        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("ChordPro Preview", self))
        self.remove_chords_checkbox = QCheckBox("Remove all chord annotations", self)
        preview_col.addWidget(self.remove_chords_checkbox)
        self.preview_text = QPlainTextEdit(self)
        self.preview_text.setReadOnly(True)
        preview_col.addWidget(self.preview_text, 1)
        body.addLayout(preview_col, 3)
        layout.addLayout(body, 1)

        self.status = QLabel("Enter a search term to begin.", self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self.import_btn = self.buttons.addButton("Import Preview", QDialogButtonBox.AcceptRole)
        self.import_btn.setEnabled(False)
        layout.addWidget(self.buttons)

        self.search_btn.clicked.connect(self._run_search)
        self.query_edit.returnPressed.connect(self._run_search)
        self.results_list.currentItemChanged.connect(self._load_selected_preview)
        self.remove_chords_checkbox.toggled.connect(self._refresh_preview_text)
        self.import_btn.clicked.connect(self._accept_if_ready)
        self.buttons.rejected.connect(self.reject)

    def _run_search(self) -> None:
        query = (self.query_edit.text() or "").strip()
        self.results_list.clear()
        self.preview_text.clear()
        self.import_btn.setEnabled(False)
        self.selected_hit = None
        self.selected_detail = None
        self.selected_chordpro_raw = ""
        self.selected_chordpro = ""

        if not query:
            self.status.setText("Enter a search query.")
            return

        self.status.setText("Searching Ultimate Guitar…")
        QApplication.processEvents()
        try:
            self.hits = self.ug_client.search(query)
        except Exception as e:
            self.status.setText(f"Search failed: {e}")
            return

        if not self.hits:
            self.status.setText("No matches found.")
            return

        for h in self.hits:
            suffix = ""
            if h.tab_type:
                suffix += f" — {h.tab_type}"
            if h.rating is not None:
                suffix += f" (rating {h.rating:.1f})"
            it = QListWidgetItem(f"{h.title} — {h.artist}{suffix}")
            it.setData(Qt.UserRole, h)
            self.results_list.addItem(it)

        self.results_list.setCurrentRow(0)
        self.status.setText(f"Found {len(self.hits)} result(s). Select one to preview.")

    def _load_selected_preview(self) -> None:
        item = self.results_list.currentItem()
        self.import_btn.setEnabled(False)
        self.selected_hit = None
        self.selected_detail = None
        self.selected_chordpro_raw = ""
        self.selected_chordpro = ""

        if item is None:
            self.preview_text.clear()
            self.status.setText("Select a result to load preview.")
            return

        hit = item.data(Qt.UserRole)
        self.status.setText("Loading preview…")
        QApplication.processEvents()
        try:
            detail = self.ug_client.fetch_tab(hit)
            chordpro_text = self.ug_client.to_chordpro(detail)
        except Exception as e:
            self.preview_text.clear()
            self.status.setText(f"Preview failed: {e}")
            return

        self.selected_hit = hit
        self.selected_detail = detail
        self.selected_chordpro_raw = chordpro_text
        self._refresh_preview_text()
        self.import_btn.setEnabled(True)
        self.status.setText("Preview loaded. Click ‘Import Preview’ to import this tab.")

    def _refresh_preview_text(self) -> None:
        if not self.selected_chordpro_raw:
            self.selected_chordpro = ""
            self.preview_text.clear()
            return

        if self.remove_chords_checkbox.isChecked():
            self.selected_chordpro = strip_chord_annotations(self.selected_chordpro_raw)
        else:
            self.selected_chordpro = self.selected_chordpro_raw
        self.preview_text.setPlainText(self.selected_chordpro)

    def _accept_if_ready(self) -> None:
        if not self.selected_chordpro or self.selected_detail is None:
            self.status.setText("Load a preview before importing.")
            return
        self.accept()

    def selected_payload(self) -> Optional[tuple]:
        if not self.selected_hit or not self.selected_detail or not self.selected_chordpro:
            return None
        return (self.selected_hit, self.selected_detail, self.selected_chordpro)


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
        "Songs (*.pro *.cho *.chopro *.txt *.pdf);;All files (*)",
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
            dest_ext = ".chopro" if src.suffix.lower() == ".pdf" else ".pro"
            dest = choose_destination_path(songs_dir, title, artist, ext=dest_ext)
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


def on_ug_search_import_clicked(
    parent,
    songs_dir: Path,
    add_filename_to_active_playlist_callback,
    refresh_maintenance_list_callback,
    choose_destination_path,
    ug_enabled: bool,
    ug_client,
) -> None:
    if not ug_enabled:
        QMessageBox.information(
            parent,
            "Ultimate Guitar",
            "Ultimate Guitar import is disabled in config.",
        )
        return

    dlg = UltimateGuitarImportDialog(parent=parent, ug_client=ug_client)
    if dlg.exec() != QDialog.Accepted:
        return

    payload = dlg.selected_payload()
    if payload is None:
        QMessageBox.information(parent, "Ultimate Guitar", "No preview selected for import.")
        return

    selected_hit, detail, chordpro_text = payload

    try:
        title = detail.title or selected_hit.title or "Untitled"
        artist = detail.artist or selected_hit.artist or "Unknown"
        dest = choose_destination_path(songs_dir, title, artist, ext=".pro")
        dest.write_text(chordpro_text, encoding="utf-8")
    except Exception as e:
        QMessageBox.critical(parent, "Ultimate Guitar", f"Import failed: {e}")
        return

    add_filename_to_active_playlist_callback(dest.name)
    refresh_maintenance_list_callback(preserve_selection=False)
    QMessageBox.information(parent, "Ultimate Guitar", f"Imported: {dest.name}")
