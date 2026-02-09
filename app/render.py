from typing import List, Tuple, Optional
from .chordpro import Song, Block, Line, Token

# Renderer semantic contract (parser -> renderer):
# - "verse", "chorus", "bridge" are content sections
# - "comment" is rendered separately in song_to_chunks()
SEMANTIC_CONTENT_SECTIONS = {"verse", "chorus", "bridge"}


def normalize_content_section_kind(block_kind: str | None) -> str:
    """
    Normalize parser block kinds into renderer semantic section kinds.

    Unknown kinds gracefully map to "verse" for backward compatibility.
    """
    kind = (block_kind or "verse").strip().lower()
    return kind if kind in SEMANTIC_CONTENT_SECTIONS else "verse"


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
    styles = cfg.get("styles", {}) or {}
    ui = cfg.get("ui", {}) or {}

    def _style_css(*keys: str) -> str:
        vals = []
        for k in keys:
            raw = styles.get(k)
            if raw:
                if isinstance(raw, str):
                    vals.extend([x.strip().lower() for x in raw.split(",") if x.strip()])
                elif isinstance(raw, list):
                    vals.extend([str(x).strip().lower() for x in raw if str(x).strip()])
        vals = list(dict.fromkeys(vals))
        css_bits = []
        if "bold" in vals:
            css_bits.append("font-weight: 600")
        if "italic" in vals:
            css_bits.append("font-style: italic")
        return ("; ".join(css_bits) + ";") if css_bits else ""

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

    verse_style = _style_css("section.verse", "verse", "verse_text")
    chorus_style = _style_css("section.chorus", "chorus", "chorus_text")
    comment_style = _style_css("section.comment", "comment")
    title_style = _style_css("directive.title", "title")
    subtitle_style = _style_css("directive.subtitle", "subtitle")
    meta_style = _style_css("directive.meta", "meta")

    pad_x = int(ui.get("padding_x", 36))
    pad_y = int(ui.get("padding_y", 24))

    return f"""
    html, body {{ height:100%; margin:0; }}
    body {{ background:{bg}; color:{text}; overflow:hidden; }}
    .wrap {{
      position: relative;
      height: 100%;
      padding:{pad_y}px {pad_x}px;
      padding-bottom:{max(48, int(size_px*1.8))}px;
      box-sizing:border-box;
      overflow:hidden;
    }}
    .title {{ color:{title_color}; font-size:{int(size_px*1.15)}px; font-weight:750; margin:0 0 6px 0; {title_style} }}
    .subtitle {{ color:{subtitle_color}; font-size:{int(size_px*0.7)}px; opacity:0.88; margin:0 0 6px 0; {subtitle_style} }}
    .meta {{ color:{meta_color}; font-size:{int(size_px*0.5)}px; opacity:0.75; margin:0 0 18px 0; {meta_style} }}

    .block {{ margin:0 0 14px 0; }}
    .comment {{ font-size:{int(size_px*0.6)}px; opacity:0.92; font-style:italic; margin:0 0 12px 0; color:{comment}; {comment_style} }}

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
      {verse_style}
    }}

    .chorusline {{
      border-left: 4px solid {chorus_border};
      color: {chorus_text};
      padding-left: 14px;
      margin-left: 0;
      {chorus_style}
    }}

    .line.section-verse {{ color: {verse_text}; }}
    .line.section-chorus {{ color: {chorus_text}; }}
    .line.section-bridge {{ color: {verse_text}; }}

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

    .footer {{ color:{footer}; }}
    .hint {{ color:{hint}; }}
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

def render_line_html(line: Line, block_kind: str) -> str:
    segs = tokens_to_segments(line.tokens)

    parts: List[str] = []
    kind = normalize_content_section_kind(block_kind)
    classes = ["line", f"section-{kind}"]
    if kind == "chorus":
        classes.append("chorusline")
    klass = " ".join(classes)
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
    - individual line chunks (semantic content sections)
    """
    chunks: List[str] = []

    for block in song.blocks:
        if block.kind == "comment":
            chunks.append(f"<div class='comment'>{escape_html(block.text or '')}</div>")
            continue
        
        for ln in block.lines:
            chunks.append(render_line_html(ln, block_kind=block.kind))
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

    out.append("</div></body></html>")
    return "".join(out)
