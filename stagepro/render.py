from typing import List, Tuple, Optional
from .chordpro import Song, Block, Line, Token
def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

def song_label_title(song: Song, fallback: str) -> Tuple[str, str, str]:
    title = song.meta.get("title", fallback or "Untitled")
    subtitle = song.meta.get("subtitle", "")
    meta_bits = []
    if song.meta.get("key"):
        meta_bits.append(f"Key: {escape_html(song.meta['key'])}")
    if song.meta.get("tempo"):
        meta_bits.append(f"Tempo: {escape_html(song.meta['tempo'])}")
    return title, subtitle, " • ".join(meta_bits)

def stagepro_css(cfg: dict) -> str:
    font = cfg.get("font", {}) or {}
    colors = cfg.get("colors", {}) or {}
    ui = cfg.get("ui", {}) or {}

    family = font.get("family", "DejaVu Sans")
    size_px = int(font.get("size_px", 34))
    line_height = float(font.get("line_height", 1.15))
    chord_factor = float(font.get("chord_size_factor", 0.70))
    chord_pad_em = float(font.get("chord_pad_em", 0.95))

    # Base colors (support both legacy and semantic keys)
    bg = colors.get("background") or colors.get("bg") or "#000000"
    text = colors.get("text") or colors.get("lyrics") or "#FFFFFF"
    chords = colors.get("chords") or "#FFD966"

    # Section colors (semantic fallbacks)
    verse_text = (
        colors.get("verse_text")
        or colors.get("section.verse")
        or text
    )
    chorus_text = (
        colors.get("chorus_text")
        or colors.get("section.chorus")
        or text
    )
    chorus_border = (
        colors.get("chorus_border")
        or colors.get("section.chorus_border")
        or "#FFFFFF"
    )
    comment = (
        colors.get("comment")
        or colors.get("section.comment")
        or text
    )

    # Directive colors
    title_color = (
        colors.get("title")
        or colors.get("directive.title")
        or text
    )
    subtitle_color = (
        colors.get("subtitle")
        or colors.get("directive.subtitle")
        or text
    )
    meta_color = (
        colors.get("meta")
        or colors.get("directive.meta")
        or text
    )

    footer = colors.get("footer") or colors.get("ui.footer") or text
    hint = colors.get("hint") or colors.get("ui.hint") or text

    pad_x = int(ui.get("padding_x", 36))
    pad_y = int(ui.get("padding_y", 24))

    return f"""
    body {{ background:{bg}; color:{text}; margin:0; }}
    .wrap {{ padding:{pad_y}px {pad_x}px; box-sizing:border-box; }}
    .title {{ color:{title_color}; font-size:{int(size_px*1.15)}px; font-weight:750; margin:0 0 6px 0; }}
    .subtitle {{ color:{subtitle_color}; font-size:{int(size_px*0.7)}px; opacity:0.88; margin:0 0 6px 0; }}
    .meta {{ color:{meta_color}; font-size:{int(size_px*0.5)}px; opacity:0.75; margin:0 0 18px 0; }}

    .block {{ margin:0 0 14px 0; }}
    .comment {{ font-size:{int(size_px*0.6)}px; opacity:0.92; font-style:italic; margin:0 0 12px 0; color:{comment}; }}

    .line {{
      font-family: {family}, DejaVu Sans, Liberation Sans, Noto Sans, Arial, sans-serif;
      font-size:{size_px}px;
      line-height:{line_height};
      margin:0;
      padding:0;
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: normal;
      color: {verse_text};
    }}

    .chorusline {{
      border-left: 4px solid {chorus_border};
      color: {chorus_text};
      padding-left: 14px;
      margin-left: 0;
    }}

    .seg {{
      position: relative;
      display: inline;
      padding-top: {chord_pad_em}em;
      white-space: pre-wrap;
    }}

    .seg[data-chord]::before {{
      content: attr(data-chord);
      position: absolute;
      left: 0;
      top: 0;
      transform: translateY(-100%);
      font-size: {max(10, int(size_px*chord_factor))}px;
      line-height: 1.0;
      color: {chords};
      white-space: nowrap;
    }}

    .spacer {{ height: 10px; }}

    .footer {{
      position: fixed;
      bottom: 18px;
      right: 24px;
      font-size:{int(size_px*0.45)}px;
      opacity:0.75;
      color:{footer};
    }}

    .hint {{
      position: fixed;
      bottom: 18px;
      left: 24px;
      font-size:{int(size_px*0.42)}px;
      opacity:0.55;
      color:{hint};
    }}
    """

def tokens_to_segments(tokens: List[Token]) -> List[Tuple[Optional[str], str]]:
    """
    Convert [chord]/lyric token stream into segments: (chord, lyric_text)
    The chord applies to the next lyric run, like ChordPro.
    """
    segs: List[Tuple[Optional[str], str]] = []
    pending_chord: Optional[str] = None

    for t in tokens:
        if t.kind == "chord":
            pending_chord = t.text.strip()
        else:
            text = t.text
            segs.append((pending_chord, text))
            pending_chord = None

    if pending_chord:
        # chord at end of line: give it a tiny spacer so it still renders
        segs.append((pending_chord, " "))
    return segs

def render_line_html(line: Line, chorus: bool) -> str:
    segs = tokens_to_segments(line.tokens)

    parts: List[str] = []
    klass = "line chorusline" if chorus else "line"
    parts.append(f"<div class='{klass}'>")

    for chord, lyric in segs:
        lyric_html = escape_html(lyric)
        if chord:
            parts.append(f"<span class='seg' data-chord='{escape_html(chord)}'>{lyric_html}</span>")
        else:
            parts.append(f"<span class='seg'>{lyric_html}</span>")

    parts.append("</div>")
    return "".join(parts)

def song_to_chunks(song: Song) -> List[str]:
    """
    Produce a flat list of HTML chunks at safe breakpoints:
    - comment chunks
    - spacer chunks
    - individual line chunks (verse/chorus)
    """
    chunks: List[str] = []

    for block in song.blocks:
        if block.kind == "comment":
            chunks.append(f"<div class='comment'>{escape_html(block.text or '')}</div>")
            continue
        
        chorus = (block.kind == "chorus")
        for ln in block.lines:
            chunks.append(render_line_html(ln, chorus=chorus))
        chunks.append("<div class='spacer'></div>")  # blank line between blocks

    # Trim trailing spacer if present
    while chunks and chunks[-1].strip() == "<div class='spacer'></div>":
        chunks.pop()

    return chunks

def render_page_html(
    cfg: dict,
    song: Song,
    song_filename: str,
    page_num: int,
    page_total: int,
    body_chunks: List[str],
) -> str:
    """
    Render a single page as HTML.

    Theming is handled upstream by merging theme colors into cfg["colors"].
    This function should not load theme files (keeps pagination/render deterministic).
    """
    title, subtitle, meta_line = song_label_title(song, song_filename)

    css = stagepro_css(cfg)
    out: List[str] = []
    out.append(f"<html><head><style>{css}</style></head><body>")
    out.append("<div class='wrap'>")
    out.append(f"<div class='title'>{escape_html(title)}</div>")
    if subtitle:
        out.append(f"<div class='subtitle'>{escape_html(subtitle)}</div>")
    if meta_line:
        out.append(f"<div class='meta'>{meta_line}</div>")

    out.extend(body_chunks)

    out.append(f"<div class='footer'>{escape_html(song_filename)} • Page {page_num} / {page_total}</div>")
    out.append("<div class='hint'>PgUp/PgDn • Hold PgUp+PgDn OR ←+→ to exit</div>")
    out.append("</div></body></html>")
    return "".join(out)
