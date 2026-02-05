from pathlib import Path
import copy
import json
import re
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QEvent, QTimer, QRectF, QSize
from PySide6.QtGui import QAction, QKeySequence, QFont
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
    QFormLayout,
    QLabel,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QGraphicsScene,
    QGraphicsView,
    QComboBox,
    QSpinBox,
    QInputDialog,
    QLineEdit,
)

from .config import load_or_create_config, resolve_songs_path
from .playlist import order_songs, list_song_files_alpha
from .playlists_store import PlaylistStore
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
        return dict(colors)
    except Exception as e:
        print(f"[theme] failed to load theme {p}: {e}")
        return {}
def _list_theme_files(base_dir: Path) -> list[Path]:
    theme_dirs = [
        base_dir / "themes",
        get_user_config_dir() / "themes",
    ]
    out = []
    seen = set()
    for d in theme_dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            rp = str(p.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
    return out


class PreferencesDialog(QDialog):
    def __init__(self, parent, base_dir: Path, cfg: dict):
        super().__init__(parent)
        self.base_dir = base_dir
        self._initial_cfg = copy.deepcopy(cfg or {})
        self.setWindowTitle("Preferences")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.font_combo = QFontComboBox(self)
        fam = ((cfg.get("font", {}) or {}).get("family")) or ""
        if fam:
            self.font_combo.setCurrentFont(QFont(fam))
        form.addRow("Font:", self.font_combo)

        self.size_spin = QSpinBox(self)
        self.size_spin.setRange(8, 256)
        self.size_spin.setValue(int((cfg.get("font", {}) or {}).get("size_px", 34)))
        form.addRow("Font size (px):", self.size_spin)

        self.theme_combo = QComboBox(self)
        self.theme_combo.addItem("(None)", "")
        cur_theme = (cfg.get("theme") or cfg.get("theme_path") or "").strip()
        for p in _list_theme_files(base_dir):
            label = p.stem
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                label = (data.get("name") or label).strip() or label
            except Exception:
                pass
            try:
                rel = p.resolve().relative_to(base_dir.resolve())
                val = str(rel).replace("\\", "/")
            except Exception:
                val = str(p)
            self.theme_combo.addItem(label, val)
        if cur_theme:
            for i in range(self.theme_combo.count()):
                if self.theme_combo.itemData(i) == cur_theme:
                    self.theme_combo.setCurrentIndex(i)
                    break
        form.addRow("Theme:", self.theme_combo)

        self.orientation_combo = QComboBox(self)
        self.orientation_combo.addItem("Landscape", "landscape")
        self.orientation_combo.addItem("Portrait", "portrait")
        cur_orient = (cfg.get("orientation") or "landscape").lower().strip()
        for i in range(self.orientation_combo.count()):
            if self.orientation_combo.itemData(i) == cur_orient:
                self.orientation_combo.setCurrentIndex(i)
                break
        form.addRow("Orientation:", self.orientation_combo)

        self.rotation_combo = QComboBox(self)
        for d in (90, 180, 270):
            self.rotation_combo.addItem(f"{d}°", d)
        cur_rot = cfg.get("rotation_deg")
        try:
            cur_rot = int(cur_rot)
        except Exception:
            cur_rot = None
        if cur_rot not in (90, 180, 270):
            try:
                cur_rot = int(cfg.get("portrait_rotation", 90))
            except Exception:
                cur_rot = 90
        for i in range(self.rotation_combo.count()):
            if self.rotation_combo.itemData(i) == cur_rot:
                self.rotation_combo.setCurrentIndex(i)
                break
        form.addRow("Rotation:", self.rotation_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updated_config(self) -> dict:
        cfg = copy.deepcopy(self._initial_cfg)

        f = dict(cfg.get("font", {}) or {})
        f["family"] = self.font_combo.currentFont().family()
        f["size_px"] = int(self.size_spin.value())
        cfg["font"] = f

        theme_ref = str(self.theme_combo.currentData() or "").strip()
        if theme_ref:
            cfg["theme"] = theme_ref
            cfg["theme_path"] = theme_ref
        else:
            cfg.pop("theme", None)
            cfg.pop("theme_path", None)

        cfg["orientation"] = str(self.orientation_combo.currentData() or "landscape")
        cfg["rotation_deg"] = int(self.rotation_combo.currentData() or 90)
        return cfg

class StageProWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

        self.config_path, self.cfg = load_or_create_config(base_dir)

        # Ensure songs_path is resolved (portable-aware) even if cfg came from older file
        self.cfg["songs_path"] = resolve_songs_path(self.cfg.get("songs_path"))

        self.songs_dir = Path(self.cfg["songs_path"])
        self.songs_dir.mkdir(parents=True, exist_ok=True)

        # Playlists (multi-setlist)
        self.playlists = PlaylistStore(self.songs_dir, self.cfg)
        self.playlists.load_or_init()

        self.song_files = []  # will be built from active playlist
        self._refresh_song_list()

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

        # Maintenance UI (playlist + library + actions)
        self.maint_root = QWidget(self)

        # Left column: search + playlist + library
        self.maint_left = QWidget(self.maint_root)
        self.maint_left_layout = QVBoxLayout(self.maint_left)
        self.maint_left_layout.setContentsMargins(0, 0, 0, 0)
        self.maint_left_layout.setSpacing(6)

        self.search_box = QLineEdit(self.maint_left)
        self.search_box.setPlaceholderText("Search library")

        self.lbl_playlist = QLabel("Playlist", self.maint_left)
        self.maint_playlist_list = QListWidget(self.maint_left)

        self.lbl_library = QLabel("Library", self.maint_left)
        self.maint_library_list = QListWidget(self.maint_left)

        self.maint_left_layout.addWidget(self.search_box)
        self.maint_left_layout.addWidget(self.lbl_playlist)
        self.maint_left_layout.addWidget(self.maint_playlist_list, 1)
        self.maint_left_layout.addWidget(self.lbl_library)
        self.maint_left_layout.addWidget(self.maint_library_list, 1)

        # Right column: preview
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
        self.cmb_playlist = QComboBox()
        self.btn_pl_new = QPushButton("New")
        self.btn_pl_rename = QPushButton("Rename")
        self.btn_pl_dup = QPushButton("Duplicate")
        self.btn_pl_del = QPushButton("Delete")
        self.btn_add_to_set = QPushButton("Add →")
        self.btn_remove_from_set = QPushButton("Remove")

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

    def _save_config(self) -> None:
        self.config_path.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")

    def open_preferences(self) -> None:
        dlg = PreferencesDialog(self, self.base_dir, self.cfg)
        if dlg.exec() != QDialog.Accepted:
            return

        # Update config + persist
        self.cfg = dlg.updated_config()
        self._save_config()

        # 1) Recompute any cached layout/metrics
        self._apply_orientation_transform()

        # 2) FORCE re-pagination + render of current song
        self.page_index = 0
        self.pages = []

        if self.song:
            self._repaginate_and_render()
        else:
            # Welcome screen also needs to re-render to pick up theme colors
            self.viewer.setHtml(self._welcome_html())

        # 3) Refresh maintenance preview (if visible)
        try:
            self._on_maint_selection_changed()
        except Exception:
            pass

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
            QTimer.singleShot(0, self._repaginate_and_render)
        else:
            self.stack.setCurrentIndex(0)
            self.menuBar().setVisible(True)

            # IMPORTANT: explicitly leave fullscreen before trying to resize/maximize
            self.showNormal()
            self.setWindowState(self.windowState() & ~Qt.WindowFullScreen)

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
        top_row.addWidget(QLabel("Playlist:"))
        top_row.addWidget(self.cmb_playlist)
        top_row.addWidget(self.btn_pl_new)
        top_row.addWidget(self.btn_pl_rename)
        top_row.addWidget(self.btn_pl_dup)
        top_row.addWidget(self.btn_pl_del)

        top_row.addSpacing(12)
        top_row.addWidget(QLabel("Order:"))
        top_row.addWidget(self.btn_move_up)
        top_row.addWidget(self.btn_move_down)
        top_row.addWidget(self.btn_add_to_set)
        top_row.addWidget(self.btn_remove_from_set)

        top_row.addSpacing(12)
        top_row.addWidget(self.btn_save_setlist)  # keep as export-to-setlist.txt for now

        outer.addLayout(top_row)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.maint_left)
        split.addWidget(self.maint_preview)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        outer.addWidget(self.maint_status)

        self.maint_playlist_list.itemSelectionChanged.connect(self._on_maint_selection_changed)
        self.maint_library_list.itemSelectionChanged.connect(self._on_maint_selection_changed)
        self.maint_library_list.itemDoubleClicked.connect(lambda _: self._add_selected_library_to_playlist())
        self.search_box.textChanged.connect(lambda _: self._refresh_maintenance_list(preserve_selection=True))
        self.btn_import.clicked.connect(self._on_import_clicked)
        self.btn_save_setlist.clicked.connect(self._save_setlist_from_ui)
        self.btn_move_up.clicked.connect(lambda: self._move_selected_item(-1))
        self.btn_move_down.clicked.connect(lambda: self._move_selected_item(+1))
        self.btn_add_to_set.clicked.connect(self._add_selected_library_to_playlist)
        self.btn_mb_autofill.clicked.connect(self._on_mb_autofill_clicked)
        self.cmb_playlist.currentIndexChanged.connect(self._on_playlist_changed)
        self.btn_pl_new.clicked.connect(self._pl_new)
        self.btn_pl_rename.clicked.connect(self._pl_rename)
        self.btn_pl_dup.clicked.connect(self._pl_duplicate)
        self.btn_pl_del.clicked.connect(self._pl_delete)

        self.btn_remove_from_set.clicked.connect(self._remove_selected_from_playlist)

        # Tooltips for clarity
        self.btn_mb_autofill.setToolTip("Search MusicBrainz to fill missing metadata for the selected song")
        self.btn_add_to_set.setToolTip("Add selected Library song to the current playlist (does not copy files)")
        self.btn_remove_from_set.setToolTip("Remove selected song from the current playlist (does not delete the file)")
        self.btn_save_setlist.setToolTip("Export current playlist order to setlist.txt (legacy compatibility)")

    def _refresh_playlist_selector(self) -> None:
        self.cmb_playlist.blockSignals(True)
        self.cmb_playlist.clear()

        active_id = self.playlists.active_playlist_id
        active_index = 0
        for i, pl in enumerate(self.playlists.list_playlists()):
            self.cmb_playlist.addItem(pl.name, pl.playlist_id)
            if pl.playlist_id == active_id:
                active_index = i

        self.cmb_playlist.setCurrentIndex(active_index)
        self.cmb_playlist.blockSignals(False)

    def _refresh_maintenance_list(self, preserve_selection: bool = False) -> None:
        """Refresh Maintenance Mode playlist + library lists."""
        self._refresh_playlist_selector()

        # Preserve selection paths if requested
        prev_pl = None
        prev_lib = None
        if preserve_selection:
            pl_items = self.maint_playlist_list.selectedItems()
            lib_items = self.maint_library_list.selectedItems()
            if pl_items:
                prev_pl = pl_items[0].data(Qt.UserRole)
            if lib_items:
                prev_lib = lib_items[0].data(Qt.UserRole)

        pl = self.playlists.get_active()
        playlist_names = list(pl.items)


        # Prune stale playlist entries that no longer exist on disk
        missing_idxs = [i for i, name in enumerate(playlist_names) if not (self.songs_dir / name).exists()]
        if missing_idxs:
            try:
                self.playlists.remove_items_by_index(pl.playlist_id, missing_idxs)
            except Exception:
                pass
            pl = self.playlists.get_active()
            playlist_names = list(pl.items)

        # Library: all files in songs_dir (alpha)
        lib_paths = list_song_files_alpha(self.songs_dir, self.cfg)
        lib_names = [p.name for p in lib_paths]

        # Search filters the library only (keeps playlist operations predictable)
        q = (self.search_box.text() or "").strip().lower()
        if q:
            lib_names = [n for n in lib_names if q in n.lower()]

        # Populate playlist list (playlist-only)
        self.maint_playlist_list.clear()
        for name in playlist_names:
            p = self.songs_dir / name
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, str(p))
            self.maint_playlist_list.addItem(it)

        # Populate library list; disable items already in playlist
        playlist_set = {n.lower() for n in playlist_names}
        self.maint_library_list.clear()
        for name in lib_names:
            p = self.songs_dir / name
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, str(p))
            if name.lower() in playlist_set:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.maint_library_list.addItem(it)

        # Restore selection
        def _restore(lst: QListWidget, target):
            if not target:
                return False
            for i in range(lst.count()):
                if lst.item(i).data(Qt.UserRole) == target:
                    lst.setCurrentRow(i)
                    return True
            return False

        restored = _restore(self.maint_playlist_list, prev_pl) if prev_pl else False
        if not restored and prev_lib:
            _restore(self.maint_library_list, prev_lib)

        # Default selection for preview: playlist selection if available, else library
        if self.maint_playlist_list.count() > 0 and self.maint_playlist_list.currentRow() < 0:
            self.maint_playlist_list.setCurrentRow(0)
        elif self.maint_library_list.count() > 0 and self.maint_library_list.currentRow() < 0:
            self.maint_library_list.setCurrentRow(0)

        # Rebuild runtime play order for on-stage mode
        self._refresh_song_list()

    def _on_maint_selection_changed(self) -> None:
        path = self._selected_path_for_preview()
        if not path:
            self.maint_preview.setPlainText("")
            return

        self._preview_song_in_maintenance(path)

        # If selection is from the playlist list, make it the active on-stage song too.
        if self.maint_playlist_list.selectedItems():
            self._sync_active_song_to_path(path)

    def _selected_path_for_preview(self) -> Optional[Path]:
        """Return selected song Path from either playlist or library list."""
        pl_items = self.maint_playlist_list.selectedItems()
        if pl_items:
            return Path(pl_items[0].data(Qt.UserRole))
        lib_items = self.maint_library_list.selectedItems()
        if lib_items:
            return Path(lib_items[0].data(Qt.UserRole))
        return None

    
    def _sync_active_song_to_path(self, path: Path) -> None:
            """Sync the active on-stage song to the given path if it's in the current playable list."""
            self._refresh_song_list()
            if not self.song_files:
                return
            try:
                target = path.resolve()
            except Exception:
                target = path
            idx = None
            for i, p in enumerate(self.song_files):
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
            if idx != self.song_idx:
                self.load_song_by_index(idx)


    def _preview_song_in_maintenance(self, path: Path) -> None:
        # Guard against stale playlist entries / deleted files
        if not path.exists():
            msg = f"Song file not found:\n{path}"
            self.maint_status.setText(f"Missing: {path.name} (removing stale entry if needed)")
            self.maint_preview.setPlainText(msg)
            QMessageBox.warning(self, "StagePro - Missing song file", msg)

            # If this came from the playlist list, remove it from the active playlist
            pl_items = self.maint_playlist_list.selectedItems()
            if pl_items:
                row = self.maint_playlist_list.currentRow()
                pl = self.playlists.get_active()
                if row >= 0 and pl and pl.playlist_id:
                    try:
                        self.playlists.remove_items_by_index(pl.playlist_id, [row])
                    except Exception:
                        pass
                    self._refresh_maintenance_list(preserve_selection=False)
                    self._load_first_song_or_welcome()
            return

        try:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="latin-1")
        except FileNotFoundError:
            # Race: file removed after exists() check
            msg = f"Song file not found:\n{path}"
            self.maint_status.setText(f"Missing: {path.name} (it may have been moved/deleted)")
            self.maint_preview.setPlainText(msg)
            QMessageBox.warning(self, "StagePro - Missing song file", msg)
            return

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
        row = self.maint_playlist_list.currentRow()
        if row < 0:
            return
        new_row = row + int(delta)
        if new_row < 0 or new_row >= self.maint_playlist_list.count():
            return
        it = self.maint_playlist_list.takeItem(row)
        self.maint_playlist_list.insertItem(new_row, it)
        self.maint_playlist_list.setCurrentRow(new_row)
        self._persist_current_playlist_order()

    def _persist_current_playlist_order(self) -> None:
        pid = self.playlists.active_playlist_id
        if not pid:
            return
        items = []
        for i in range(self.maint_playlist_list.count()):
            it = self.maint_playlist_list.item(i)
            items.append(Path(it.data(Qt.UserRole)).name)
        self.playlists.set_items(pid, items)

    def _add_selected_library_to_playlist(self) -> None:
        item = self.maint_library_list.currentItem()
        if not item:
            return
        filename = Path(item.data(Qt.UserRole)).name
        self._add_filename_to_active_playlist(filename)
        self._refresh_maintenance_list(preserve_selection=False)

    def _add_filename_to_active_playlist(self, filename: str) -> None:
        pl = self.playlists.get_active()
        items = list(pl.items)
        if filename.lower() in {x.lower() for x in items}:
            return
        items.append(filename)
        self.playlists.set_items(pl.playlist_id, items)

    def _remove_selected_from_playlist(self) -> None:
        pid = self.playlists.active_playlist_id
        if not pid:
            return
        row = self.maint_playlist_list.currentRow()
        if row < 0:
            return

        self.playlists.remove_items_by_index(pid, [row])
        self._refresh_maintenance_list(preserve_selection=False)
        self._load_first_song_or_welcome()

    def _on_playlist_changed(self, idx: int) -> None:
        pid = self.cmb_playlist.currentData()
        if not pid:
            return
        self.playlists.set_active(pid)
        self._refresh_maintenance_list(preserve_selection=False)
        self._load_first_song_or_welcome()

    def _pl_new(self) -> None:
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if not ok:
            return
        self.playlists.create_playlist(name=name.strip() or "New Playlist", items=[])
        self._refresh_maintenance_list(preserve_selection=False)

    def _pl_rename(self) -> None:
        pl = self.playlists.get_active()
        name, ok = QInputDialog.getText(self, "Rename Playlist", "New name:", text=pl.name)
        if not ok:
            return
        self.playlists.rename_playlist(pl.playlist_id, name.strip() or pl.name)
        self._refresh_maintenance_list(preserve_selection=True)

    def _pl_duplicate(self) -> None:
        pl = self.playlists.get_active()
        self.playlists.duplicate_playlist(pl.playlist_id)
        self._refresh_maintenance_list(preserve_selection=False)

    def _pl_delete(self) -> None:
        pl = self.playlists.get_active()
        resp = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Delete playlist '{pl.name}'?\n\nThis will NOT delete any song files.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        self.playlists.delete_playlist(pl.playlist_id)
        self._refresh_maintenance_list(preserve_selection=False)
        self._load_first_song_or_welcome()


    def _save_setlist_from_ui(self) -> None:
        setlist_name = (self.cfg.get("setlist", {}) or {}).get("filename", "setlist.txt")
        lines = []
        for i in range(self.maint_playlist_list.count()):
            it = self.maint_playlist_list.item(i)
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

            # If the selected file is already in the songs folder, do NOT import/copy it.
            # Just add it to the active playlist.
            try:
                if src.resolve().parent == self.songs_dir.resolve():
                    if src.exists() and src.is_file():
                        self._add_filename_to_active_playlist(src.name)
                        imported += 1
                        continue
            except Exception:
                pass

            try:

                imp = import_user_file_to_chordpro(src)
                # choose dest
                title = imp.title or src.stem
                artist = imp.artist or "Unknown"
                dest = choose_destination_path(self.songs_dir, title, artist, ext=".pro")
                dest.write_text(imp.chordpro_text, encoding="utf-8")
                imported += 1
                # add to active playlist (at end)
                self._add_filename_to_active_playlist(dest.name)

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
        path = self._selected_path_for_preview()
        if not path:
            QMessageBox.information(self, "MusicBrainz", "Select a song first.")
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

            # Maintenance: remove from playlist
            if self.mode == "maintenance" and k in (Qt.Key_Delete, Qt.Key_Backspace):
                self._remove_selected_from_playlist()
                return True

            # Maintenance: reorder shortcuts
            if self.mode == "maintenance" and (event.modifiers() & Qt.ControlModifier):
                if k == Qt.Key_Up:
                    self._move_selected_item(-1)
                    return True
                if k == Qt.Key_Down:
                    self._move_selected_item(+1)
                    return True

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
                    lst = self.maint_library_list if self.maint_library_list.hasFocus() else self.maint_playlist_list
                    lst.setCurrentRow(min(lst.count() - 1, lst.currentRow() + 1))
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
                    lst = self.maint_library_list if self.maint_library_list.hasFocus() else self.maint_playlist_list
                    lst.setCurrentRow(max(0, lst.currentRow() - 1))
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
        pref_act = QAction("Preferences…", self)
        pref_act.setShortcut("Ctrl+,")
        pref_act.triggered.connect(self.open_preferences)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        menu = self.menuBar()

        tools_menu = menu.addMenu("&Tools")
        tools_menu.addAction(pref_act)
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


    def _refresh_song_list(self) -> None:
        """Rebuild self.song_files from the ACTIVE playlist only (playlist == setlist)."""
        pl = self.playlists.get_active()
        items = list(pl.items or [])

        # Map filenames -> actual Paths (skip missing)
        existing = {p.name.lower(): p for p in list_song_files_alpha(self.songs_dir, self.cfg)}

        ordered = []
        for name in items:
            p = existing.get(str(name).lower())
            if p:
                ordered.append(p)

        self.song_files = ordered

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

    def _layout_doc_size(self) -> tuple[int, int]:
        """
        Returns logical (reading) width/height for pagination.
        This is independent of visual rotation.
        """
        vw = max(200, int(self.view.viewport().width()))
        vh = max(200, int(self.view.viewport().height()))

        margin = self._fit_margin_px()
        vw -= 2 * margin
        vh -= 2 * margin

        if self._is_portrait():
            # Reading is vertical: height is long axis
            return min(vw, vh), max(vw, vh)
        else:
            return max(vw, vh), min(vw, vh)

    def _repaginate_and_render(self):
        if not self.song:
            return
        w, h = self._layout_doc_size()
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