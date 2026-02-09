from pathlib import Path
import copy
import json

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from .config import get_user_config_dir


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
