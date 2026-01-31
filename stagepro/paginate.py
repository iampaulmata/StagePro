from typing import List, Tuple
from PySide6.QtGui import QTextDocument

from .render import render_page_html

def measure_height(html: str, width_px: int) -> float:
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setTextWidth(max(200, width_px))
    return float(doc.size().height())

def paginate_to_fit(
    cfg: dict,
    song,
    song_filename: str,
    chunks: List[str],
    width_px: int,
    height_px: int,
) -> List[str]:
    """
    Builds pages by adding chunks until the rendered QTextDocument would exceed height_px.
    Chunks are already safe breakpoints (line-by-line).
    """
    ui = cfg.get("ui", {}) or {}
    bottom_reserve = int(ui.get("page_bottom_reserve_px", 64))
    usable_h = max(200, height_px - bottom_reserve)

    pages_chunks: List[List[str]] = []
    current: List[str] = []

    def would_fit(test_chunks: List[str]) -> bool:
        # Temporarily render as page 1/1 for measurement. Footer/hint are fixed, so they don't affect flow.
        html = render_page_html(cfg, song, song_filename, 1, 1, test_chunks)
        h = measure_height(html, width_px)
        return h <= usable_h

    for ch in chunks:
        if not current:
            current = [ch]
            continue

        test = current + [ch]
        if would_fit(test):
            current = test
        else:
            pages_chunks.append(current)
            current = [ch]

    if current:
        pages_chunks.append(current)

    if not pages_chunks:
        pages_chunks = [[]]

    # Now render real page numbers
    total = len(pages_chunks)
    pages: List[str] = []
    for i, body in enumerate(pages_chunks, start=1):
        pages.append(render_page_html(cfg, song, song_filename, i, total, body))
    return pages
