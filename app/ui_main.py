from pathlib import Path
import json
import re
from typing import List, Optional, Tuple

from PySide6.QtCore import (
    Qt,
    QEvent,
    QTimer,
    QRectF,
    QSize,
    QRect,
)

from PySide6.QtGui import (
    QAction, QKeySequence,
    QShortcut,
    QGuiApplication,
    QCursor,
    QTextCursor,
)

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
    QLabel,
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGraphicsView,
    QComboBox,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
)

from .config import load_or_create_config, resolve_songs_path
from .playlist import list_song_files_alpha_from_roots
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
from .paths import overrides_dir
from .libraries.model import load_libraries_config
from .ui_preferences import PreferencesDialog, _load_theme_colors
from .ui_song_utils import (
    read_song_text_for_edit,
    is_under_dir,
    library_published_root_for,
    make_unique_local_name,
)
from .ui_song_editor import build_song_editor_dialog
from .ui_maintenance import (
    refresh_playlist_selector,
    selected_path_for_preview,
    sync_active_song_to_path,
)
from .ui_input import (
    exit_combo_active,
    start_or_stop_exit_timer,
    exit_if_still_held,
    maybe_handle_onstage_toggle_combo,
)
from .ui_rendering import (
    resize_viewer_to_viewport,
    fit_view_to_content,
    apply_orientation_transform,
)
from .ui_playback import (
    available_doc_size,
    repaginate_and_render,
    render_page,
    next_page as playback_next_page,
    prev_page as playback_prev_page,
    next_song as playback_next_song,
    prev_song as playback_prev_song,
)
from .ui_playlist_ops import (
    move_selected_item,
    persist_current_playlist_order,
    add_filename_to_active_playlist,
    add_selected_library_to_playlist,
    remove_selected_from_playlist,
    on_playlist_changed,
    pl_new,
    pl_rename,
    pl_duplicate,
    pl_delete,
    save_setlist_from_ui,
)
from .ui_imports import (
    on_import_clicked,
    on_mb_autofill_clicked,
)

class StageProWindow(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir

        self.config_path, self.cfg = load_or_create_config(base_dir)

        # Ensure songs_path is resolved (portable-aware) even if cfg came from older file
        self.cfg["songs_path"] = resolve_songs_path(self.cfg.get("songs_path"))

        self.songs_dir = Path(self.cfg["songs_path"])
        self.songs_dir.mkdir(parents=True, exist_ok=True)

        self._load_library_sources()

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
        self.btn_edit_song = QPushButton("Edit…")
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
        resize_viewer_to_viewport(
            view=self.view,
            viewer=self.viewer,
            fit_margin_px=self._fit_margin_px(),
            is_portrait=self._is_portrait(),
        )

    def _apply_orientation_transform(self):
        apply_orientation_transform(
            proxy=self.proxy,
            is_portrait=self._is_portrait(),
            portrait_rotation_deg=self._portrait_rotation_deg(),
            fit_view_to_content_callback=self._fit_view_to_content,
        )

    def _fit_view_to_content(self):
        fit_view_to_content(
            view=self.view,
            proxy=self.proxy,
            resize_viewer_to_viewport_callback=self._resize_viewer_to_viewport,
            fit_mode=self._fit_mode(),
        )

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

                # Make the top controls portrait-friendly by using two rows instead of one long horizontal bar.
        # (A single wide row can force an oversized minimum window width on rotated/portrait displays.)
        self.cmb_playlist.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_playlist.setMinimumContentsLength(8)
        try:
            self.cmb_playlist.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        except Exception:
            # Older Qt builds may not expose this enum; it's safe to ignore.
            pass

        row1 = QHBoxLayout()
        row1.addWidget(self.btn_import)
        row1.addSpacing(6)
        row1.addWidget(self.btn_mb_autofill)
        row1.addStretch(1)
        row1.addWidget(QLabel("Playlist:"))
        row1.addWidget(self.cmb_playlist, 1)
        row1.addWidget(self.btn_pl_new)
        row1.addWidget(self.btn_pl_rename)
        row1.addWidget(self.btn_pl_dup)
        row1.addWidget(self.btn_pl_del)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Order:"))
        row2.addWidget(self.btn_move_up)
        row2.addWidget(self.btn_move_down)
        row2.addWidget(self.btn_add_to_set)
        row2.addSpacing(12)
        row2.addWidget(self.btn_edit_song)

        row2.addWidget(self.btn_remove_from_set)
        row2.addStretch(1)
        row2.addWidget(self.btn_save_setlist)  # export-to-setlist.txt (legacy compatibility)

        outer.addLayout(row1)
        outer.addLayout(row2)

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
        self.btn_edit_song.clicked.connect(self._on_edit_song_clicked)
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
        self.btn_edit_song.setToolTip("Edit the selected song (library songs will be copied locally first)")
        self.btn_mb_autofill.setToolTip("Search MusicBrainz to fill missing metadata for the selected song")
        self.btn_add_to_set.setToolTip("Add selected Library song to the current playlist (does not copy files)")
        self.btn_remove_from_set.setToolTip("Remove selected song from the current playlist (does not delete the file)")
        self.btn_save_setlist.setToolTip("Export current playlist order to setlist.txt (legacy compatibility)")

    def _refresh_playlist_selector(self) -> None:
        refresh_playlist_selector(self.cmb_playlist, self.playlists)

    def _load_library_sources(self) -> None:
        self.libraries_cfg = load_libraries_config()
        self.library_sources = list(self.libraries_cfg.library_sources)
        self.library_published_dirs = []
        self.library_override_dirs = []
        for source in self.library_sources:
            if not source.enabled:
                continue
            pub_dir = source.published_dir()
            self.library_published_dirs.append(pub_dir)
            override_dir = source.overrides_dir()
            override_dir.mkdir(parents=True, exist_ok=True)
            self.library_override_dirs.append(override_dir)
        if not self.library_override_dirs:
            overrides_dir().mkdir(parents=True, exist_ok=True)

    def _song_roots(self) -> List[Path]:
        roots: List[Path] = []
        if self.library_override_dirs:
            roots.extend(self.library_override_dirs)
        else:
            roots.append(overrides_dir())
        roots.append(self.songs_dir)
        roots.extend(self.library_published_dirs)
        return roots

    def _resolve_song_path(self, name: str) -> Optional[Path]:
        for root in self._song_roots():
            candidate = root / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

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
        missing_idxs = [i for i, name in enumerate(playlist_names) if not self._resolve_song_path(name)]
        if missing_idxs:
            try:
                self.playlists.remove_items_by_index(pl.playlist_id, missing_idxs)
            except Exception:
                pass
            pl = self.playlists.get_active()
            playlist_names = list(pl.items)

        # Library: merged roots (overrides, user songs, published sources)
        lib_paths = list_song_files_alpha_from_roots(self._song_roots(), self.cfg)
        lib_names = [p.name for p in lib_paths]

        # Search filters the library only (keeps playlist operations predictable)
        q = (self.search_box.text() or "").strip().lower()
        if q:
            lib_names = [n for n in lib_names if q in n.lower()]

        # Populate playlist list (playlist-only)
        self.maint_playlist_list.clear()
        for name in playlist_names:
            p = self._resolve_song_path(name) or (self.songs_dir / name)
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, str(p))
            self.maint_playlist_list.addItem(it)

        # Populate library list; disable items already in playlist
        playlist_set = {n.lower() for n in playlist_names}
        self.maint_library_list.clear()
        for name in lib_names:
            p = next((lp for lp in lib_paths if lp.name == name), self.songs_dir / name)
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
        return selected_path_for_preview(self.maint_playlist_list, self.maint_library_list)

    
    def _sync_active_song_to_path(self, path: Path) -> None:
            sync_active_song_to_path(
                path=path,
                refresh_song_list=self._refresh_song_list,
                get_song_files=lambda: self.song_files,
                get_song_idx=lambda: self.song_idx,
                load_song_by_index=self.load_song_by_index,
            )


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

        # ---------- Local editing in Maintenance ----------

    def _read_song_text_for_edit(self, path: Path) -> str:
        return read_song_text_for_edit(path)

    def _is_under_dir(self, path: Path, root: Path) -> bool:
        return is_under_dir(path, root)

    def _library_published_root_for(self, path: Path) -> Optional[Path]:
        return library_published_root_for(path, self.library_published_dirs)

    def _make_unique_local_name(self, preferred_name: str) -> str:
        return make_unique_local_name(self.songs_dir, preferred_name)

    def _on_edit_song_clicked(self) -> None:
        # Enable local editing from Maintenance mode.
        if getattr(self, "mode", None) != "maintenance":
            return

        path = self._selected_path_for_preview()
        if not path:
            QMessageBox.information(self, "Edit Song", "Select a song first.")
            return
        if not path.exists():
            QMessageBox.warning(self, "Edit Song", f"Song file not found:\n{path}")
            return

        try:
            text = self._read_song_text_for_edit(path)
        except Exception as e:
            QMessageBox.critical(self, "Edit Song", f"Failed to read file:\n{path}\n\n{e}")
            return

        published_root = self._library_published_root_for(path)
        is_user_song = self._is_under_dir(path, self.songs_dir)

        # Rule (compatible with today's playlist model, which stores filenames only):
        # - User songs: edit in place
        # - Published library songs: save as a LOCAL copy in songs_dir root (library version unchanged)
        if published_root and not is_user_song:
            source_id = published_root.name  # published/<source_id>/...
            msg = (
                "This song comes from a synced Library.\n\n"
                "Edits are saved as a LOCAL copy in your Songs folder "
                "(the library version is not modified).\n\n"
                f"Library source: {source_id}\n"
                f"File: {path.name}\n\n"
                "Continue?"
            )
            if QMessageBox.question(self, "Edit Library Song", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

            local_name = self._make_unique_local_name(path.name)
            edit_target = self.songs_dir / local_name
        else:
            edit_target = path

        dlg = self._song_editor_dialog(
            title=f"Edit: {edit_target.name}",
            initial_text=text,
            info_path=edit_target,
            is_copy=(edit_target != path),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_text = dlg._editor.toPlainText()

        try:
            edit_target.parent.mkdir(parents=True, exist_ok=True)
            edit_target.write_text(new_text, encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Edit Song", f"Failed to save:\n{edit_target}\n\n{e}")
            return

        # If we created a local copy while a playlist item is selected, swap that playlist row to the new local filename.
        if edit_target != path and self.maint_playlist_list.selectedItems():
            row = self.maint_playlist_list.currentRow()
            if row >= 0:
                pid = self.playlists.active_playlist_id
                if pid:
                    pl = self.playlists.get_active()
                    items = list(pl.items or [])
                    if 0 <= row < len(items):
                        items[row] = edit_target.name
                        self.playlists.set_items(pid, items)

        self.maint_status.setText(f"Saved: {edit_target.name}")
        self._refresh_maintenance_list(preserve_selection=False)
        self._preview_song_in_maintenance(edit_target)

    def _song_editor_dialog(self, title: str, initial_text: str, info_path: Path, is_copy: bool) -> QDialog:
        return build_song_editor_dialog(
            parent=self,
            title=title,
            initial_text=initial_text,
            info_path=info_path,
            is_copy=is_copy,
        )

    def _move_selected_item(self, delta: int) -> None:
        move_selected_item(self.maint_playlist_list, delta, self._persist_current_playlist_order)

    def _persist_current_playlist_order(self) -> None:
        persist_current_playlist_order(self.maint_playlist_list, self.playlists.active_playlist_id, self.playlists.set_items)

    def _add_selected_library_to_playlist(self) -> None:
        add_selected_library_to_playlist(
            self.maint_library_list,
            self._add_filename_to_active_playlist,
            self._refresh_maintenance_list,
        )

    def _add_filename_to_active_playlist(self, filename: str) -> None:
        add_filename_to_active_playlist(filename, self.playlists.get_active, self.playlists.set_items)

    def _remove_selected_from_playlist(self) -> None:
        remove_selected_from_playlist(
            self.playlists.active_playlist_id,
            self.maint_playlist_list,
            self.playlists.remove_items_by_index,
            self._refresh_maintenance_list,
            self._load_first_song_or_welcome,
        )

    def _on_playlist_changed(self, idx: int) -> None:
        on_playlist_changed(
            self.cmb_playlist,
            self.playlists.set_active,
            self._refresh_maintenance_list,
            self._load_first_song_or_welcome,
        )

    def _pl_new(self) -> None:
        pl_new(self, self.playlists.create_playlist, self._refresh_maintenance_list)

    def _pl_rename(self) -> None:
        pl_rename(self, self.playlists.get_active, self.playlists.rename_playlist, self._refresh_maintenance_list)

    def _pl_duplicate(self) -> None:
        pl_duplicate(self.playlists.get_active, self.playlists.duplicate_playlist, self._refresh_maintenance_list)

    def _pl_delete(self) -> None:
        pl_delete(
            self,
            self.playlists.get_active,
            self.playlists.delete_playlist,
            self._refresh_maintenance_list,
            self._load_first_song_or_welcome,
        )


    def _save_setlist_from_ui(self) -> None:
        save_setlist_from_ui(
            self.cfg,
            self.maint_playlist_list,
            self.songs_dir,
            self.maint_status,
            self._refresh_song_list,
        )

    def _on_import_clicked(self) -> None:
        on_import_clicked(
            parent=self,
            songs_dir=self.songs_dir,
            add_filename_to_active_playlist_callback=self._add_filename_to_active_playlist,
            refresh_maintenance_list_callback=self._refresh_maintenance_list,
            import_user_file_to_chordpro=import_user_file_to_chordpro,
            choose_destination_path=choose_destination_path,
            import_error_type=ImportErrorWithHint,
        )

    def _on_mb_autofill_clicked(self) -> None:
        on_mb_autofill_clicked(
            parent=self,
            selected_path_for_preview_callback=self._selected_path_for_preview,
            mb_client=self.mb,
            pick_musicbrainz_hit_callback=self._pick_musicbrainz_hit,
            upsert_directives=upsert_directives,
            maint_status=self.maint_status,
            preview_song_in_maintenance_callback=self._preview_song_in_maintenance,
        )

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
        return exit_combo_active(self.pressed_keys)

    def _start_or_stop_exit_timer(self):
        start_or_stop_exit_timer(self.exit_timer, self.exit_hold_ms, self.pressed_keys)

    def _exit_if_still_held(self):
        exit_if_still_held(self.pressed_keys, self.close)

    def _maybe_handle_onstage_toggle_combo(self, key: int) -> bool:
        handled = maybe_handle_onstage_toggle_combo(
            key=key,
            combo_latched=self._combo_latched,
            last_pedal_down=self._last_pedal_down,
            combo_window_ms=self._combo_window_ms,
            toggle_mode_callback=self._toggle_mode,
        )
        if handled:
            self._combo_latched = True
        return handled

    def eventFilter(self, obj, event):
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return False
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

        libraries_act = QAction("Libraries…", self)
        libraries_act.triggered.connect(self.open_libraries_manager)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        menu = self.menuBar()

        tools_menu = menu.addMenu("&Tools")
        tools_menu.addAction(pref_act)
        tools_menu.addAction(libraries_act)
        tools_menu.addSeparator()
        tools_menu.addAction(quit_act)

    def open_libraries_manager(self) -> None:
        if getattr(self, "_libraries_dialog", None) is None:
            from .ui_libraries import LibrariesManagerDialog
            dialog = LibrariesManagerDialog(self, on_sync_complete=self._on_libraries_sync_complete)
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.finished.connect(self._on_libraries_dialog_closed)
            self._libraries_dialog = dialog
        self._libraries_dialog.show()
        self._libraries_dialog.raise_()
        self._libraries_dialog.activateWindow()

    def _on_libraries_dialog_closed(self) -> None:
        self._libraries_dialog = None

    def _on_libraries_sync_complete(self) -> None:
        self._load_library_sources()
        self._refresh_maintenance_list(preserve_selection=True)
        self._load_first_song_or_welcome()

    # ---------- Song loading / rendering ----------

    def _welcome_html(self) -> str:
        eff = self._effective_cfg()
        colors = eff.get("colors", {}) or {}
        bg = colors.get("background") or colors.get("bg") or "#000000"
        fg = colors.get("text") or colors.get("lyrics") or "#FFFFFF"
        return (
            f"<html><body style='background:{bg};color:{fg};"
            f"font-family:sans-serif;padding:24px;'>"
            f"<h1>StagePro</h1><p>No songs found in your libraries</p>"
            f"</body></html>"
        )


    def _refresh_song_list(self) -> None:
        """Rebuild self.song_files from the ACTIVE playlist only (playlist == setlist)."""
        pl = self.playlists.get_active()
        items = list(pl.items or [])

        # Map filenames -> actual Paths (skip missing)
        existing = {
            p.name.lower(): p for p in list_song_files_alpha_from_roots(self._song_roots(), self.cfg)
        }

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
        return available_doc_size(self.viewer)

    def _repaginate_and_render(self):
        pages, page_index = repaginate_and_render(
            song=self.song,
            song_files=self.song_files,
            song_idx=self.song_idx,
            page_index=self.page_index,
            effective_cfg=self._effective_cfg,
            viewer=self.viewer,
        )
        if self.song:
            self.pages = pages
            self.page_index = page_index
            self.render()

    def render(self):
        rendered = render_page(
            blackout=self.blackout,
            song=self.song,
            pages=self.pages,
            page_index=self.page_index,
            effective_cfg=self._effective_cfg,
            welcome_html=self._welcome_html,
            viewer=self.viewer,
        )
        if not rendered:
            self._repaginate_and_render()
            if not self.pages:
                self.viewer.setHtml(self._welcome_html())
                return
            self.viewer.setHtml(self.pages[self.page_index])

    # ---------- Controls ----------

    def next_page(self):
        self.page_index = playback_next_page(self.pages, self.page_index, self.render, self.next_song)

    def prev_page(self):
        self.page_index = playback_prev_page(self.pages, self.page_index, self.render, self.prev_song)

    def next_song(self):
        playback_next_song(self.song_files, self.song_idx, self.load_song_by_index, self.render)

    def prev_song(self, go_to_last_page: bool = False):
        new_page_index = playback_prev_song(
            self.song_files,
            self.song_idx,
            self.pages,
            self.load_song_by_index,
            self.render,
            go_to_last_page=go_to_last_page,
        )
        if new_page_index is not None:
            self.page_index = new_page_index

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
