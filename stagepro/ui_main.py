from pathlib import Path
import copy
import json
import re
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QEvent, QTimer, QRectF, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTextBrowser,
    QWidget,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFileDialog,
    QLabel,
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGraphicsView,
)

from .config import load_or_create_config, resolve_songs_path
from .playlist import order_songs
from .chordpro import Song, parse_chordpro
from .chordpro_edit import upsert_directives
from .importers import (
    ImportErrorWithHint,
    import_user_file_to_chordpro,
    choose_destination_path,
)
from .musicbrainz import MusicBrainzClient, MBRecordingHit
from .config import get_user_config_dir
from .render import song_to_chunks
from .paginate import paginate_to_fit
SONGS_DIR_NAME = "songs"

def _load_theme_colors(base_dir: str, cfg: dict) -> dict:
    """
    Loads theme JSON from cfg['theme'] or cfg['theme_path'].
    Returns a dict of color overrides (possibly empty).
    """
    theme_ref = (cfg.get("theme") or cfg.get("theme_path") or "").strip()
    if not theme_ref:
        print("[theme] no theme configured")
        return {}

    p = Path(theme_ref)
    if not p.is_absolute():
        p = Path(base_dir) / p

    if not p.exists():
        print(f"[theme] theme file not found: {p}")
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        colors = (data.get("colors") or {})
        print(f"[theme] loaded: {data.get('name','(unnamed)')} from {p}")
        print(f"[theme] keys: {list(colors.keys())[:12]}")
        return dict(colors)
    except Exception as e:
        print(f"[theme] failed to load theme {p}: {e}")
        return {}

class StageProWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

        self.config_path, self.cfg = load_or_create_config(base_dir)

        # Ensure songs_path is resolved (portable-aware) even if cfg came from older file
        self.cfg["songs_path"] = resolve_songs_path(self.cfg.get("songs_path"))

        self.songs_dir = Path(self.cfg["songs_path"])
        self.songs_dir.mkdir(parents=True, exist_ok=True)

        self.song_files = order_songs(self.songs_dir, self.cfg)

        self.song_idx = 0

        # ---------------- Modes ----------------
        # Maintenance mode is the "setup" experience (keyboard/mouse, import, setlist).
        # On-stage mode is the fullscreen, footswitch-friendly prompter.
        self.mode = "maintenance"  # or "onstage"

        # On-stage viewer (existing rendering pipeline)
        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setStyleSheet("QTextBrowser { border: none; }")

        self.scene = QGraphicsScene(self)
        self.proxy = self.scene.addWidget(self.viewer)

        self.view = QGraphicsView(self.scene)
        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setAlignment(Qt.AlignCenter)

        # Maintenance UI (list + actions)
        self.maint_root = QWidget(self)
        self.maint_song_list = QListWidget(self.maint_root)
        self.maint_preview = QTextBrowser(self.maint_root)
        self.maint_preview.setOpenExternalLinks(False)
        self.maint_preview.setStyleSheet("QTextBrowser { border: 1px solid #333; }")

        self.btn_import = QPushButton("Import Songs…")
        self.btn_save_setlist = QPushButton("Save Setlist")
        self.btn_move_up = QPushButton("▲")
        self.btn_move_down = QPushButton("▼")
        self.btn_mb_autofill = QPushButton("Autofill from MusicBrainz…")
        self.maint_status = QLabel("")
        self.maint_status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._build_maintenance_ui()

        # Stack: maintenance vs on-stage
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.maint_root)  # index 0
        self.stack.addWidget(self.view)        # index 1
        self.setCentralWidget(self.stack)

        self.song: Optional[Song] = None
        self.pages: List[str] = []
        self.page_index = 0
        self.blackout = False

        # Exit combo (hold both pedal buttons)
        self.pressed_keys = set()
        self.exit_hold_ms = int((self.cfg.get("shortcuts", {}) or {}).get("exit_hold_ms", 1500))
        self.exit_timer = QTimer(self)
        self.exit_timer.setSingleShot(True)
        self.exit_timer.timeout.connect(self._exit_if_still_held)

        QApplication.instance().installEventFilter(self)

        # On-stage toggle combo: quick press of both footswitches.
        self._combo_window_ms = int((self.cfg.get("shortcuts", {}) or {}).get("toggle_onstage_combo_ms", 180))
        self._last_pedal_down: dict[int, int] = {}  # key -> ms timestamp
        self._combo_latched = False

        # MusicBrainz client (metadata-only)
        cache_path = get_user_config_dir() / "musicbrainz_cache.json"
        self.mb = MusicBrainzClient(cache_path=cache_path)

        self._build_actions()
        self.setWindowTitle("StagePro")
        self._load_first_song_or_welcome()
        self._refresh_maintenance_list()
        self._set_mode("maintenance")

    # ---------- Config helpers ----------

    def _theme_path(self) -> str:
        """
        Returns the configured theme file path (relative to base_dir or absolute).
        Supports both 'theme' and legacy 'theme_path' config keys.
        """
        cfg = getattr(self, "cfg", {}) or {}
        return (cfg.get("theme") or cfg.get("theme_path") or "").strip()

    def _effective_cfg(self) -> dict:
        cfg = dict(self.cfg)
        colors = dict(cfg.get("colors", {}) or {})

        theme_colors = _load_theme_colors(self.base_dir, cfg)
        # Theme wins over base colors:
        colors.update(theme_colors)

        cfg["colors"] = colors
        return cfg

    def _is_portrait(self) -> bool:
        return (self.cfg.get("orientation") or "landscape").lower() == "portrait"

    def _portrait_rotation_deg(self) -> int:
        try:
            deg = int(self.cfg.get("portrait_rotation", 90))
        except Exception:
            deg = 90
        return 270 if deg == 270 else 90

    def _fit_mode(self) -> str:
        ui = self.cfg.get("ui", {}) or {}
        v = str(ui.get("fit_mode", "fit")).lower().strip()
        return "fill" if v == "fill" else "fit"

    def _fit_margin_px(self) -> int:
        ui = self.cfg.get("ui", {}) or {}
        try:
            return max(0, int(ui.get("fit_margin_px", 8)))
        except Exception:
            return 8

    # ---------- Orientation / Fit ----------

    def _resize_viewer_to_viewport(self):
        margin = self._fit_margin_px()
        vp = self.view.viewport().size()
        w = max(200, vp.width() - 2 * margin)
        h = max(200, vp.height() - 2 * margin)

        # swap size in portrait so the *rotated* content fills
        if self._is_portrait():
            self.viewer.setFixedSize(QSize(h, w))
        else:
            self.viewer.setFixedSize(QSize(w, h))

    def _apply_orientation_transform(self):
        if self._is_portrait():
            self.proxy.setRotation(self._portrait_rotation_deg())
        else:
            self.proxy.setRotation(0)
        self._fit_view_to_content()

    def _fit_view_to_content(self):
        self._resize_viewer_to_viewport()
        rect: QRectF = self.proxy.sceneBoundingRect()
        if rect.isNull():
            return
        self.view.setSceneRect(rect)
        if self._fit_mode() == "fill":
            self.view.fitInView(rect, Qt.KeepAspectRatioByExpanding)
        else:
            self.view.fitInView(rect, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_view_to_content()
        # Re-paginate on resize because wrapping changes height
        self._repaginate_and_render()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_orientation_transform()
        self._repaginate_and_render()

    # ---------- Mode management ----------

    def _set_mode(self, mode: str) -> None:
        mode = (mode or "").strip().lower()
        if mode not in {"maintenance", "onstage"}:
            mode = "maintenance"
        self.mode = mode

        if self.mode == "onstage":
            self.stack.setCurrentIndex(1)
            self.menuBar().setVisible(False)
            self.showFullScreen()
            self._apply_orientation_transform()
            self._repaginate_and_render()
        else:
            self.stack.setCurrentIndex(0)
            self.menuBar().setVisible(True)
            self.showMaximized()
            self._refresh_maintenance_list(preserve_selection=True)

    def _toggle_mode(self) -> None:
        self._set_mode("onstage" if self.mode != "onstage" else "maintenance")

    # ---------- Maintenance UI ----------

    def _build_maintenance_ui(self) -> None:
        """Builds the maintenance-mode UI (library + setlist + import tools)."""
        root = self.maint_root
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.addWidget(self.btn_import)
        top_row.addSpacing(6)
        top_row.addWidget(self.btn_mb_autofill)
        top_row.addStretch(1)
        top_row.addWidget(QLabel("Setlist:"))
        top_row.addWidget(self.btn_move_up)
        top_row.addWidget(self.btn_move_down)
        top_row.addWidget(self.btn_save_setlist)
        outer.addLayout(top_row)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.maint_song_list)
        split.addWidget(self.maint_preview)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        outer.addWidget(self.maint_status)

        self.maint_song_list.itemSelectionChanged.connect(self._on_maint_selection_changed)
        self.btn_import.clicked.connect(self._on_import_clicked)
        self.btn_save_setlist.clicked.connect(self._save_setlist_from_ui)
        self.btn_move_up.clicked.connect(lambda: self._move_selected_item(-1))
        self.btn_move_down.clicked.connect(lambda: self._move_selected_item(+1))
        self.btn_mb_autofill.clicked.connect(self._on_mb_autofill_clicked)

        # Tooltips for clarity
        self.btn_mb_autofill.setToolTip("Search MusicBrainz to fill missing metadata for the selected song")
        self.btn_save_setlist.setToolTip("Write the setlist order to setlist.txt in your songs folder")

    def _refresh_maintenance_list(self, preserve_selection: bool = False) -> None:
        prev = None
        if preserve_selection:
            items = self.maint_song_list.selectedItems()
            if items:
                prev = items[0].data(Qt.UserRole)

        self._refresh_song_list()
        self.maint_song_list.clear()
        for p in self.song_files:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, str(p))
            self.maint_song_list.addItem(it)

        # restore selection
        if prev:
            for i in range(self.maint_song_list.count()):
                if self.maint_song_list.item(i).data(Qt.UserRole) == prev:
                    self.maint_song_list.setCurrentRow(i)
                    break
        elif self.maint_song_list.count() > 0:
            self.maint_song_list.setCurrentRow(max(0, min(self.song_idx, self.maint_song_list.count() - 1)))

    def _on_maint_selection_changed(self) -> None:
        items = self.maint_song_list.selectedItems()
        if not items:
            self.maint_preview.setPlainText("")
            return
        path = Path(items[0].data(Qt.UserRole))
        self._preview_song_in_maintenance(path)

    def _preview_song_in_maintenance(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")

        try:
            song = parse_chordpro(text)
            chunks = song_to_chunks(song)
            # Use a lightweight preview size (avoid needing the onstage graphics view)
            w = 900
            h = 1200
            eff_cfg = self._effective_cfg()
            pages = paginate_to_fit(eff_cfg, song, path.name, chunks, w, h)
            self.maint_preview.setHtml(pages[0] if pages else self._welcome_html())
            missing = []
            if not song.meta.get("title") and not song.meta.get("t"):
                missing.append("title")
            if not song.meta.get("artist") and not song.meta.get("a"):
                missing.append("artist")
            if missing:
                self.maint_status.setText(f"Selected: {path.name} (missing: {', '.join(missing)})")
            else:
                self.maint_status.setText(f"Selected: {path.name}")
        except Exception as e:
            self.maint_preview.setPlainText(text)
            self.maint_status.setText(f"Selected: {path.name} (parse error: {e})")

    def _move_selected_item(self, delta: int) -> None:
        row = self.maint_song_list.currentRow()
        if row < 0:
            return
        new_row = row + int(delta)
        if new_row < 0 or new_row >= self.maint_song_list.count():
            return
        it = self.maint_song_list.takeItem(row)
        self.maint_song_list.insertItem(new_row, it)
        self.maint_song_list.setCurrentRow(new_row)

    def _save_setlist_from_ui(self) -> None:
        setlist_name = (self.cfg.get("setlist", {}) or {}).get("filename", "setlist.txt")
        lines = []
        for i in range(self.maint_song_list.count()):
            it = self.maint_song_list.item(i)
            # store filenames (not absolute paths)
            lines.append(Path(it.data(Qt.UserRole)).name)
        p = self.songs_dir / setlist_name
        p.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.maint_status.setText(f"Saved setlist: {p}")
        self._refresh_song_list()

    def _on_import_clicked(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import songs",
            str(self.songs_dir),
            "Songs (*.pro *.cho *.chopro *.txt);;All files (*)",
        )
        if not files:
            return

        imported = 0
        warnings: List[str] = []
        for fp in files:
            src = Path(fp)
            try:
                imp = import_user_file_to_chordpro(src)
                # choose dest
                title = imp.title or src.stem
                artist = imp.artist or "Unknown"
                dest = choose_destination_path(self.songs_dir, title, artist, ext=".pro")
                dest.write_text(imp.chordpro_text, encoding="utf-8")
                imported += 1
                if not imp.title or not imp.artist:
                    warnings.append(f"{src.name}: imported, but title/artist missing in directives (you can autofill from MusicBrainz)")
            except ImportErrorWithHint as e:
                warnings.append(f"{src.name}: {e}")
            except Exception as e:
                warnings.append(f"{src.name}: import failed ({e})")

        self._refresh_maintenance_list(preserve_selection=False)
        msg = f"Imported {imported} file(s)."
        if warnings:
            msg += "\n\n" + "\n".join(warnings[:12])
            if len(warnings) > 12:
                msg += f"\n…and {len(warnings) - 12} more."
        QMessageBox.information(self, "Import", msg)

    def _on_mb_autofill_clicked(self) -> None:
        items = self.maint_song_list.selectedItems()
        if not items:
            QMessageBox.information(self, "MusicBrainz", "Select a song first.")
            return
        path = Path(items[0].data(Qt.UserRole))
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
                self,
                "MusicBrainz",
                "This file is missing a title and/or artist directive.\n\n"
                "StagePro can search MusicBrainz only when it knows the song title and artist.\n"
                "Add {title: ...} and {artist: ...} (or re-import using the fallback header format).",
            )
            return

        try:
            hits = self.mb.search_recordings(title=title, artist=artist, limit=12)
        except Exception as e:
            QMessageBox.critical(self, "MusicBrainz", f"Search failed: {e}")
            return

        if not hits:
            QMessageBox.information(self, "MusicBrainz", "No matches found.")
            return

        chosen = self._pick_musicbrainz_hit(hits)
        if not chosen:
            return

        updates = {}
        # Fill missing basics (do not overwrite user-specified values)
        updates.setdefault("title", chosen.title)
        updates.setdefault("artist", chosen.artist)
        if chosen.release:
            updates.setdefault("album", chosen.release)
        if chosen.date:
            updates.setdefault("year", chosen.date.split("-")[0])

        # Only apply updates for keys that are currently missing
        current_meta = {}
        for raw in text.splitlines():
            m = re.match(r"^\s*\{\s*([^}:]+)\s*:\s*([^}]*)\}\s*$", raw, flags=re.IGNORECASE)
            if m:
                current_meta[m.group(1).strip().lower()] = m.group(2).strip()

        filtered_updates = {k: v for k, v in updates.items() if not current_meta.get(k)}
        if not filtered_updates:
            QMessageBox.information(self, "MusicBrainz", "Nothing to autofill — metadata is already present.")
            return

        new_text, _ = upsert_directives(text, filtered_updates)
        try:
            path.write_text(new_text, encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "MusicBrainz", f"Failed to save updates: {e}")
            return

        self.maint_status.setText(f"Autofilled metadata from MusicBrainz for: {path.name}")
        self._preview_song_in_maintenance(path)

    def _pick_musicbrainz_hit(self, hits: List[MBRecordingHit]) -> Optional[MBRecordingHit]:
        dlg = QDialog(self)
        dlg.setWindowTitle("Select a match")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Pick the best MusicBrainz match:"))

        lst = QListWidget(dlg)
        for h in hits:
            year = (h.date or "").split("-")[0] if h.date else ""
            extra = ""
            if h.release:
                extra = f" — {h.release}"
            if year:
                extra += f" ({year})"
            it = QListWidgetItem(f"{h.title} — {h.artist}{extra}")
            it.setData(Qt.UserRole, h)
            lst.addItem(it)
        lst.setCurrentRow(0)
        layout.addWidget(lst, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return None
        sel = lst.selectedItems()
        return sel[0].data(Qt.UserRole) if sel else None

    # ---------- Exit combo + paging ----------

    def _exit_combo_active(self) -> bool:
        pg_pair = (Qt.Key_PageUp in self.pressed_keys) and (Qt.Key_PageDown in self.pressed_keys)
        lr_pair = (Qt.Key_Left in self.pressed_keys) and (Qt.Key_Right in self.pressed_keys)
        return pg_pair or lr_pair

    def _start_or_stop_exit_timer(self):
        if self._exit_combo_active():
            if not self.exit_timer.isActive():
                self.exit_timer.start(self.exit_hold_ms)
        else:
            if self.exit_timer.isActive():
                self.exit_timer.stop()

    def _exit_if_still_held(self):
        if self._exit_combo_active():
            self.close()

    def _maybe_handle_onstage_toggle_combo(self, key: int) -> bool:
        """Detect a quick 'both footswitch buttons' press.

        Many pedals are configured to emit PageUp/PageDown. We detect a combo
        when both keys are pressed within a short window.
        """
        if key not in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Left, Qt.Key_Right):
            return False

        # Don't retrigger until both keys are released.
        if self._combo_latched:
            return False

        # Use monotonic time for stable key timing.
        import time
        now_ms = int(time.monotonic() * 1000)
        self._last_pedal_down[key] = now_ms

        # Determine pair
        if key in (Qt.Key_PageUp, Qt.Key_PageDown):
            other = Qt.Key_PageDown if key == Qt.Key_PageUp else Qt.Key_PageUp
        else:
            other = Qt.Key_Right if key == Qt.Key_Left else Qt.Key_Left

        other_ts = self._last_pedal_down.get(other)
        if other_ts is None:
            return False

        if abs(now_ms - other_ts) <= self._combo_window_ms:
            self._combo_latched = True
            self._toggle_mode()
            return True

        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            k = event.key()
            # Ctrl+F toggles maintenance <-> on-stage
            if k == Qt.Key_F and (event.modifiers() & Qt.ControlModifier):
                self._toggle_mode()
                return True

            # Quick "both footswitch buttons" toggle (usually PageUp/PageDown)
            if self._maybe_handle_onstage_toggle_combo(k):
                return True

            self.pressed_keys.add(k)
            self._start_or_stop_exit_timer()

            # navigation
            if k in (Qt.Key_PageDown, Qt.Key_Right):
                if self._exit_combo_active():
                    return True
                if (Qt.Key_Left in self.pressed_keys and Qt.Key_Right in self.pressed_keys) or \
                   (Qt.Key_PageUp in self.pressed_keys and Qt.Key_PageDown in self.pressed_keys):
                    return True
                if self.mode == "onstage":
                    self.next_page()
                else:
                    self.maint_song_list.setCurrentRow(min(self.maint_song_list.count() - 1, self.maint_song_list.currentRow() + 1))
                return True

            if k in (Qt.Key_PageUp, Qt.Key_Left):
                if self._exit_combo_active():
                    return True
                if (Qt.Key_Left in self.pressed_keys and Qt.Key_Right in self.pressed_keys) or \
                   (Qt.Key_PageUp in self.pressed_keys and Qt.Key_PageDown in self.pressed_keys):
                    return True
                if self.mode == "onstage":
                    self.prev_page()
                else:
                    self.maint_song_list.setCurrentRow(max(0, self.maint_song_list.currentRow() - 1))
                return True

        if event.type() == QEvent.KeyRelease and not event.isAutoRepeat():
            k = event.key()
            self.pressed_keys.discard(k)
            self._start_or_stop_exit_timer()

            # Unlatch combo when all relevant keys are released
            if k in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Left, Qt.Key_Right):
                if not any(x in self.pressed_keys for x in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Left, Qt.Key_Right)):
                    self._combo_latched = False
            if k in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Left, Qt.Key_Right):
                return True

        return super().eventFilter(obj, event)

    # ---------- UI actions (non-nav) ----------

    def _build_actions(self):
        reload_cfg_act = QAction("Reload Config", self)
        reload_cfg_act.setShortcut("R")
        reload_cfg_act.triggered.connect(self.reload_config)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        menu = self.menuBar()
        tools_menu = menu.addMenu("&Tools")
        tools_menu.addAction(reload_cfg_act)
        tools_menu.addSeparator()
        tools_menu.addAction(quit_act)

    # ---------- Song loading / rendering ----------

    def _welcome_html(self) -> str:
        eff = self._effective_cfg()
        colors = eff.get("colors", {}) or {}
        bg = colors.get("background") or colors.get("bg") or "#000000"
        fg = colors.get("text") or colors.get("lyrics") or "#FFFFFF"
        return (
            f"<html><body style='background:{bg};color:{fg};"
            f"font-family:sans-serif;padding:24px;'>"
            f"<h1>StagePro</h1><p>No songs found in ./songs</p>"
            f"</body></html>"
        )


    def _refresh_song_list(self):
        self.song_files = order_songs(self.songs_dir, self.cfg)

    def _load_first_song_or_welcome(self):
        self._refresh_song_list()
        self.song_idx = 0
        if not self.song_files:
            self.song = None
            self.pages = []
            self.page_index = 0
            self.viewer.setHtml(self._welcome_html())
            return
        self.load_song_by_index(0)

    def load_song_by_index(self, idx: int):
        self._refresh_song_list()
        if not self.song_files:
            self.song = None
            self.pages = []
            self.page_index = 0
            self.viewer.setHtml(self._welcome_html())
            return

        self.song_idx = max(0, min(idx, len(self.song_files) - 1))
        path = self.song_files[self.song_idx]

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")

        try:
            self.song = parse_chordpro(text)
            self.blackout = False
            self.page_index = 0
            self._repaginate_and_render()
        except Exception as e:
            QMessageBox.critical(self, "StagePro Error", f"Failed to open/parse:\n{path}\n\n{e}")

    def _available_doc_size(self) -> tuple[int, int]:
        # The QTextBrowser is explicitly sized to the viewport (swapped in portrait), so use that.
        w = max(200, int(self.viewer.width()))
        h = max(200, int(self.viewer.height()))
        return w, h

    def _repaginate_and_render(self):
        if not self.song:
            return
        w, h = self._available_doc_size()
        filename = self.song_files[self.song_idx].name if self.song_files else "Untitled"
        chunks = song_to_chunks(self.song)
        #cfg = self.effective_cfg()
        eff_cfg = self._effective_cfg()
        self.pages = paginate_to_fit(eff_cfg, self.song, filename, chunks, w, h)
        self.page_index = max(0, min(self.page_index, len(self.pages) - 1))
        self.render()

    def render(self):
        if self.blackout:
            eff = self._effective_cfg()
            colors = eff.get("colors", {}) or {}
            bg = colors.get("background") or colors.get("bg") or "#000000"
            self.viewer.setHtml(f"<html><body style='background:{bg};'></body></html>")
            return
        if not self.song:
            self.viewer.setHtml(self._welcome_html())
            return
        if not self.pages:
            self._repaginate_and_render()
            if not self.pages:
                self.viewer.setHtml(self._welcome_html())
                return
        self.viewer.setHtml(self.pages[self.page_index])

    # ---------- Controls ----------

    def next_page(self):
        if not self.pages:
            return
        if self.page_index < len(self.pages) - 1:
            self.page_index += 1
            self.render()
        else:
            self.next_song()

    def prev_page(self):
        if not self.pages:
            return
        if self.page_index > 0:
            self.page_index -= 1
            self.render()
        else:
            self.prev_song(go_to_last_page=True)

    def next_song(self):
        if not self.song_files:
            return
        if self.song_idx < len(self.song_files) - 1:
            self.load_song_by_index(self.song_idx + 1)
        else:
            self.render()

    def prev_song(self, go_to_last_page: bool = False):
        if not self.song_files:
            return
        if self.song_idx > 0:
            self.load_song_by_index(self.song_idx - 1)
            if go_to_last_page and self.pages:
                self.page_index = max(0, len(self.pages) - 1)
                self.render()
        else:
            self.render()

    def reload_config(self):
        try:
            if self.config_path.exists():
                import json
                from .config import merge_defaults, default_config
                cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.cfg = merge_defaults(default_config(), cfg)
            self.exit_hold_ms = int((self.cfg.get("shortcuts", {}) or {}).get("exit_hold_ms", 1500))
            self._apply_orientation_transform()
            self._repaginate_and_render()
        except Exception as e:
            QMessageBox.critical(self, "StagePro Error", f"Failed to reload config:\n{e}")