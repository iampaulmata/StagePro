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
        cur_theme_resolved = None
        if cur_theme:
            try:
                cur_theme_resolved = Path(cur_theme)
                if not cur_theme_resolved.is_absolute():
                    cur_theme_resolved = (base_dir / cur_theme_resolved).resolve()
                else:
                    cur_theme_resolved = cur_theme_resolved.resolve()
            except Exception:
                cur_theme_resolved = None
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
            matched = False
            for i in range(self.theme_combo.count()):
                if self.theme_combo.itemData(i) == cur_theme:
                    self.theme_combo.setCurrentIndex(i)
                    matched = True
                    break
            if not matched and cur_theme_resolved is not None:
                for i in range(self.theme_combo.count()):
                    item_val = str(self.theme_combo.itemData(i) or "").strip()
                    if not item_val:
                        continue
                    try:
                        item_path = Path(item_val)
                        if not item_path.is_absolute():
                            item_path = (base_dir / item_path).resolve()
                        else:
                            item_path = item_path.resolve()
                    except Exception:
                        continue
                    if item_path == cur_theme_resolved:
                        self.theme_combo.setCurrentIndex(i)
                        matched = True
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
