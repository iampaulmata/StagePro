"""
StagePro Theme Support (HTML-based)

Loads a JSON theme file and provides helpers for generating
HTML <span> wrappers with colors and styles for ChordPro tags.

This module is intentionally Qt-agnostic.
"""

import json
import html
from pathlib import Path


# Hard fallbacks if theme is missing or incomplete
DEFAULT_COLORS = {
    "background": "#000000",
    "lyrics": "#FFFFFF",
    "chords": "#FFD166",

    "section.verse": "#FFFFFF",
    "section.chorus": "#FFFFFF",
    "section.comment": "#AAAAAA",

    "directive.title": "#FFFFFF",
    "directive.subtitle": "#BBBBBB",
    "directive.meta": "#888888",
}


class Theme:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.name = data.get("name", "Default")
        self.colors = data.get("colors", {})
        self.styles = data.get("styles", {})

    # ---------- Loading ----------

    @classmethod
    def load(cls, base_dir=None, path: str | Path | None = None):
        """
        Load a theme from a JSON file.

        Supports two calling styles:
        - Theme.load("themes/foo.json")
        - Theme.load(base_dir, "themes/foo.json")

        If path is relative and base_dir is provided, it is resolved against base_dir.
        If path is None/empty/invalid, returns a default theme.
        """
        # Allow Theme.load("path") style
        if path is None and base_dir is not None:
            path = base_dir
            base_dir = None

        if not path:
            return cls()

        try:
            p = Path(path)

            # Resolve relative theme path against base_dir if given
            if not p.is_absolute() and base_dir:
                p = Path(base_dir) / p

            if not p.exists():
                return cls()

            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(data)
        except Exception:
            # Theme errors should never crash StagePro
            return cls()


    # ---------- Lookup helpers ----------

    def color_for(self, key: str) -> str:
        """
        Resolve a color for a semantic key with fallbacks.
        """
        return (
            self.colors.get(key)
            or self.colors.get(key.split(".")[0])
            or DEFAULT_COLORS.get(key)
            or DEFAULT_COLORS.get(key.split(".")[0])
            or DEFAULT_COLORS["lyrics"]
        )

    def style_for(self, key: str) -> str:
        """
        Resolve font styles (bold, italic) for a semantic key.
        """
        styles = self.styles.get(key, [])
        css = []

        if "bold" in styles:
            css.append("font-weight:600")
        if "italic" in styles:
            css.append("font-style:italic")

        return "; ".join(css)

    # ---------- HTML helpers ----------

    def span(self, key: str, text: str) -> str:
        """
        Wrap text in a themed HTML <span>.
        """
        text = html.escape(text)
        color = self.color_for(key)
        style = self.style_for(key)

        css_parts = [f"color:{color}"]
        if style:
            css_parts.append(style)

        css = "; ".join(css_parts)
        return f'<span style="{css}">{text}</span>'

    def background_color(self) -> str:
        """
        Background color for the page/window.
        """
        return self.color_for("background")
