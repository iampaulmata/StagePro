from pathlib import Path
import copy
from typing import List, Optional

from PySide6.QtCore import Qt, QEvent, QTimer, QRectF, QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTextBrowser,
    QGraphicsScene,
    QGraphicsView,
)

from .config import load_or_create_config, resolve_songs_path
from .playlist import order_songs
from .chordpro import Song, parse_chordpro
from .render import song_to_chunks
from .paginate import paginate_to_fit
SONGS_DIR_NAME = "songs"

from pathlib import Path
import json

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

        self.setCentralWidget(self.view)

        self.song: Optional[Song] = None
        self.pages: List[str] = []
        self.page_index = 0
        self.blackout = False

        # Exit combo
        self.pressed_keys = set()
        self.exit_hold_ms = int((self.cfg.get("shortcuts", {}) or {}).get("exit_hold_ms", 1500))
        self.exit_timer = QTimer(self)
        self.exit_timer.setSingleShot(True)
        self.exit_timer.timeout.connect(self._exit_if_still_held)

        QApplication.instance().installEventFilter(self)

        self._build_actions()
        self.setWindowTitle("StagePro")
        self.showFullScreen()
        self._load_first_song_or_welcome()

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

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            k = event.key()
            self.pressed_keys.add(k)
            self._start_or_stop_exit_timer()

            # paging keys handled globally
            if k in (Qt.Key_PageDown, Qt.Key_Right):
                if self._exit_combo_active():
                    return True
                if (Qt.Key_Left in self.pressed_keys and Qt.Key_Right in self.pressed_keys) or \
                   (Qt.Key_PageUp in self.pressed_keys and Qt.Key_PageDown in self.pressed_keys):
                    return True
                self.next_page()
                return True

            if k in (Qt.Key_PageUp, Qt.Key_Left):
                if self._exit_combo_active():
                    return True
                if (Qt.Key_Left in self.pressed_keys and Qt.Key_Right in self.pressed_keys) or \
                   (Qt.Key_PageUp in self.pressed_keys and Qt.Key_PageDown in self.pressed_keys):
                    return True
                self.prev_page()
                return True

        if event.type() == QEvent.KeyRelease and not event.isAutoRepeat():
            k = event.key()
            self.pressed_keys.discard(k)
            self._start_or_stop_exit_timer()
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