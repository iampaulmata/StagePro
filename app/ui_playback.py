from .render import song_to_chunks
from .paginate import paginate_to_fit


def available_doc_size(viewer) -> tuple[int, int]:
    # The QTextBrowser is explicitly sized to the viewport (swapped in portrait), so use that.
    w = max(200, int(viewer.width()))
    h = max(200, int(viewer.height()))
    return w, h


def inject_pinned_footer(html: str, page_num: int, page_total: int, height_px: int) -> str:
    if "</body>" not in html:
        return html

    h = max(200, int(height_px))
    bottom_pad = 8
    footer_block_h = 58
    top_px = max(0, h - footer_block_h - bottom_pad)

    if "<body>" in html:
        html = html.replace(
            "<body>",
            f"<body style='position:relative;height:{h}px;overflow:hidden;'>",
            1,
        )

    pin = (
        f"<div style='position:absolute;left:24px;right:24px;top:{top_px}px;"
        "display:flex;justify-content:space-between;align-items:flex-end;"
        "font-family:inherit;pointer-events:none;'>"
        f"<div style='opacity:0.75'>Page {page_num} / {page_total}</div>"
        "<div style='opacity:0.55'>PgUp/PgDn • Hold PgUp+PgDn OR ←+→ to exit</div>"
        "</div>"
    )
    return html.replace("</body>", pin + "</body>")


def repaginate_and_render(
    song,
    song_files,
    song_idx: int,
    page_index: int,
    effective_cfg,
    viewer,
) -> tuple[list[str], int]:
    if not song:
        return [], page_index
    w, h = available_doc_size(viewer)
    filename = song_files[song_idx].name if song_files else "Untitled"
    chunks = song_to_chunks(song)
    eff_cfg = effective_cfg()
    pages = paginate_to_fit(eff_cfg, song, filename, chunks, w, h)
    page_index = max(0, min(page_index, len(pages) - 1))
    return pages, page_index


def render_page(
    blackout: bool,
    song,
    pages: list[str],
    page_index: int,
    effective_cfg,
    welcome_html,
    viewer,
) -> bool:
    if blackout:
        eff = effective_cfg()
        colors = eff.get("colors", {}) or {}
        bg = colors.get("background") or colors.get("bg") or "#000000"
        viewer.setHtml(f"<html><body style='background:{bg};'></body></html>")
        return True
    if not song:
        viewer.setHtml(welcome_html())
        return True
    if not pages:
        return False
    html = pages[page_index]
    _, h = available_doc_size(viewer)
    html = inject_pinned_footer(html, page_index + 1, len(pages), h)
    viewer.setHtml(html)
    return True


def next_page(pages: list[str], page_index: int, render_callback, next_song_callback) -> int:
    if not pages:
        return page_index
    if page_index < len(pages) - 1:
        page_index += 1
        render_callback()
    else:
        next_song_callback()
    return page_index


def prev_page(pages: list[str], page_index: int, render_callback, prev_song_callback) -> int:
    if not pages:
        return page_index
    if page_index > 0:
        page_index -= 1
        render_callback()
    else:
        prev_song_callback(go_to_last_page=True)
    return page_index


def next_song(song_files, song_idx: int, load_song_by_index_callback, render_callback) -> None:
    if not song_files:
        return
    if song_idx < len(song_files) - 1:
        load_song_by_index_callback(song_idx + 1)
    else:
        render_callback()


def prev_song(song_files, song_idx: int, pages: list[str], load_song_by_index_callback, render_callback, go_to_last_page: bool = False):
    if not song_files:
        return None
    if song_idx > 0:
        load_song_by_index_callback(song_idx - 1)
        if go_to_last_page and pages:
            new_page_index = max(0, len(pages) - 1)
            render_callback()
            return new_page_index
    else:
        render_callback()
    return None
