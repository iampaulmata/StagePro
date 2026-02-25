"""Import and normalization helpers.

StagePro's canonical on-disk format is ChordPro. When importing user files we:

1) Try to recognize and validate ChordPro-like content.
2) If it isn't valid ChordPro, fall back to a strict header format:
   - first non-empty line: title
   - second non-empty line: artist
   - remaining lines: lyrics (verbatim)

If the fallback header format doesn't match, import fails with a clear,
actionable error message.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


TITLE_KEYS = {"title", "t"}
ARTIST_KEYS = {"artist", "a"}

DIRECTIVE_ANY_RE = re.compile(r"^\s*\{[^}]+\}\s*$")
DIRECTIVE_KV_RE = re.compile(r"^\s*\{\s*([^}:]+)\s*:\s*([^}]*)\}\s*$", re.IGNORECASE)


class ImportErrorWithHint(Exception):
    """A user-facing import error with a clear message."""


@dataclass
class ImportedSong:
    title: str
    artist: str
    chordpro_text: str


def normalize_song_file(src: Path) -> ImportedSong:
    """Normalize a song file into canonical ChordPro text.

    This reuses the same import/validation pipeline used for user imports so
    .txt files and loosely formatted chordpro are handled consistently.
    """
    return import_user_file_to_chordpro(src)


def looks_like_chordpro(text: str) -> bool:
    """Heuristic detection: directives or chord tokens."""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("{") and s.endswith("}"):
            return True
        if "[" in s and "]" in s:
            # could be chords
            return True
    return False


def validate_chordpro_basic(text: str) -> Tuple[bool, Optional[str]]:
    """Basic validation that avoids accepting random text as ChordPro.

    Rules:
    - If a line looks like a directive, it must have a closing brace.
    - Key/value directives must parse.

    This does NOT require title/artist directives (those can be autofilled).
    """
    for i, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("{"):
            if not s.endswith("}"):
                return False, f"Line {i} starts a directive '{{' but is missing a closing '}}'."
            # If it's a key:value directive, ensure it parses
            if ":" in s[1:-1]:
                if not DIRECTIVE_KV_RE.match(s):
                    return False, f"Line {i} looks like a key:value directive but couldn't be parsed: {s!r}"
    return True, None


def fallback_import_from_plain_text(text: str) -> ImportedSong:
    """Strict fallback importer.

    Expects first two *non-empty* lines to be title and artist.
    """
    lines = text.splitlines()

    # find first two non-empty lines
    nonempty = [(idx, ln.strip()) for idx, ln in enumerate(lines) if ln.strip()]
    if len(nonempty) < 2:
        raise ImportErrorWithHint(
            "Import failed: file isn't valid ChordPro and doesn't match the fallback format. "
            "Expected at least 2 non-empty lines: Title then Artist."
        )

    t_idx, title = nonempty[0]
    a_idx, artist = nonempty[1]

    # heuristics to reject obvious non-header content
    def _looks_like_section_header(s: str) -> bool:
        s2 = s.lower().strip(":- ")
        return s2 in {"verse", "verse 1", "verse 2", "chorus", "bridge", "intro", "outro", "pre-chorus"} or s2.startswith("verse ")

    def _looks_like_chorded_lyric(s: str) -> bool:
        return "[" in s and "]" in s and re.search(r"\[[^\]]+\]", s) is not None

    if title.startswith("{") and title.endswith("}"):
        raise ImportErrorWithHint(
            "Import failed: first non-empty line looks like a ChordPro directive, but the file did not validate as ChordPro. "
            "Either fix the directive formatting or use the fallback format with a plain Title line first."
        )
    if _looks_like_section_header(title) or _looks_like_chorded_lyric(title):
        raise ImportErrorWithHint(
            "Import failed: fallback format expects first non-empty line to be the song Title. "
            f"Found: {title!r} (looks like lyrics/section header)."
        )

    if artist.startswith("{") and artist.endswith("}"):
        raise ImportErrorWithHint(
            "Import failed: fallback format expects second non-empty line to be the Artist (plain text). "
            f"Found directive-like line: {artist!r}."
        )
    if _looks_like_section_header(artist) or _looks_like_chorded_lyric(artist):
        raise ImportErrorWithHint(
            "Import failed: fallback format expects second non-empty line to be the Artist. "
            f"Found: {artist!r} (looks like lyrics/section header)."
        )

    lyric_lines = lines[a_idx + 1 :]
    lyric_text = "\n".join(lyric_lines).rstrip() + "\n"

    chordpro = "".join(
        [
            f"{{title: {title}}}\n",
            f"{{artist: {artist}}}\n",
            "\n",
            lyric_text,
        ]
    )
    return ImportedSong(title=title, artist=artist, chordpro_text=chordpro)


def sanitize_filename_component(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[\\/:*?\"<>|]+", "-", s)
    s = re.sub(r"\s+", " ", s)
    return s[:120].strip() or "Untitled"


def choose_destination_path(songs_dir: Path, title: str, artist: str, ext: str = ".pro") -> Path:
    base = f"{sanitize_filename_component(artist)} - {sanitize_filename_component(title)}"
    cand = songs_dir / f"{base}{ext}"
    if not cand.exists():
        return cand
    for i in range(2, 999):
        cand2 = songs_dir / f"{base} ({i}){ext}"
        if not cand2.exists():
            return cand2
    return songs_dir / f"{base} (imported){ext}"


def import_user_file_to_chordpro(src: Path) -> ImportedSong:
    """Read a user-selected file and return canonical ChordPro text + required title/artist.

    - If it validates as ChordPro, we return the content and attempt to discover title/artist
      from directives (if present). If missing, title/artist will be empty strings.
    - Otherwise, we require the strict fallback header format.
    """
    if src.suffix.lower() == ".pdf":
        return _import_pdf_to_chordpro(src)

    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = src.read_text(encoding="latin-1")

    if looks_like_chordpro(text):
        ok, reason = validate_chordpro_basic(text)
        if not ok:
            # fall through to strict fallback
            pass
        else:
            # Extract title/artist if present
            title = ""
            artist = ""
            for raw in text.splitlines():
                m = DIRECTIVE_KV_RE.match(raw.strip())
                if not m:
                    continue
                key = m.group(1).strip().lower()
                val = m.group(2).strip()
                if key in TITLE_KEYS and not title:
                    title = val
                if key in ARTIST_KEYS and not artist:
                    artist = val
            return ImportedSong(title=title, artist=artist, chordpro_text=text if text.endswith("\n") else text + "\n")

    # Not chordpro (or failed chordpro validation) => strict fallback
    return fallback_import_from_plain_text(text)


def _import_pdf_to_chordpro(src: Path) -> ImportedSong:
    """Extract text from a PDF and wrap it as ChordPro content.

    MVP behavior:
    - extract page text in order
    - use PDF metadata title/author when present
    - wrap into canonical ChordPro with title/artist directives
    """
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise ImportErrorWithHint(
            "Import failed: PDF support requires the 'pypdf' package. "
            "Install dependencies and try again."
        ) from e

    try:
        reader = PdfReader(str(src))
    except Exception as e:
        raise ImportErrorWithHint(f"Import failed: unable to read PDF ({e})") from e

    page_texts = []
    for page in reader.pages:
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            page_texts.append("")

    text = "\n\n".join(t.strip("\n") for t in page_texts).strip()
    if not text:
        text = _extract_pdf_text_with_ocr(src)

    if not text:
        raise ImportErrorWithHint(
            "Import failed: no extractable text found in PDF. "
            "OCR fallback also produced no text."
        )

    meta = reader.metadata or {}
    title = (getattr(meta, "title", None) or src.stem or "").strip()
    artist = (getattr(meta, "author", None) or "").strip()

    chordpro = "".join(
        [
            f"{{title: {title}}}\n",
            f"{{artist: {artist}}}\n",
            "\n",
            text if text.endswith("\n") else text + "\n",
        ]
    )
    return ImportedSong(title=title, artist=artist, chordpro_text=chordpro)


def _extract_pdf_text_with_ocr(src: Path) -> str:
    """OCR fallback for scanned/image PDFs.

    Requirements:
    - pytesseract + Pillow + pypdfium2 python packages
    - system Tesseract binary available on PATH
    """
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except Exception as e:
        raise ImportErrorWithHint(
            "Import failed: scanned PDF OCR requires optional dependencies "
            "'pytesseract', 'Pillow', and 'pypdfium2'."
        ) from e

    if shutil.which("tesseract") is None:
        raise ImportErrorWithHint(
            "Import failed: OCR fallback requires the Tesseract binary. "
            "Install 'tesseract-ocr' on your system and try again."
        )

    try:
        pdf = pdfium.PdfDocument(str(src))
    except Exception as e:
        raise ImportErrorWithHint(f"Import failed: OCR could not open PDF ({e})") from e

    pages_text = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            text = pytesseract.image_to_string(pil_image)
            pages_text.append((text or "").strip())
            page.close()
            bitmap.close()
    finally:
        pdf.close()

    return "\n\n".join(t for t in pages_text if t).strip()
