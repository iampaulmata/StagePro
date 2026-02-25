"""Best-effort Ultimate Guitar search + tab import helpers.

This integration intentionally avoids third-party UG wrappers and uses stdlib
HTTP calls only. Ultimate Guitar does not provide a stable public API for this
workflow, so parsing logic is defensive and may need future maintenance.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


UG_SEARCH_URL = "https://www.ultimate-guitar.com/search.php"


class UltimateGuitarError(Exception):
    """User-facing Ultimate Guitar integration error."""


@dataclass
class UGSearchHit:
    title: str
    artist: str
    tab_url: str
    tab_id: Optional[int] = None
    tab_type: Optional[str] = None
    rating: Optional[float] = None


@dataclass
class UGTabDetail:
    title: str
    artist: str
    tab_url: str
    content: str
    tab_id: Optional[int] = None


class UltimateGuitarClient:
    def __init__(
        self,
        timeout_s: float = 8.0,
        user_agent: str = "StagePro/0.1 (+https://github.com/iampaulmata/StagePro)",
    ):
        self.timeout_s = float(timeout_s)
        self.user_agent = user_agent

    def _get_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise UltimateGuitarError(f"Ultimate Guitar request failed (HTTP {e.code}).") from e
        except urllib.error.URLError as e:
            raise UltimateGuitarError(f"Ultimate Guitar request failed: {e.reason}") from e
        except TimeoutError as e:
            raise UltimateGuitarError("Ultimate Guitar request timed out.") from e
        except Exception as e:
            raise UltimateGuitarError(f"Ultimate Guitar request failed: {e}") from e

        return data.decode("utf-8", errors="replace")

    def _extract_page_store(self, html_text: str) -> Optional[Dict[str, Any]]:
        # Legacy payload shape used by older UG pages.
        m = re.search(r"window\\.UGAPP\\.store\\.page\\s*=\\s*(\{.*?\})\\s*;", html_text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

        # Current UG pages often embed app state inside a large HTML data-content
        # attribute where JSON entities are HTML-escaped.
        data = self._extract_data_content_json(html_text)
        if isinstance(data, dict):
            store = data.get("store")
            if isinstance(store, dict):
                page = store.get("page")
                if isinstance(page, dict):
                    return page
                return store
            return data

        return None

    def _extract_data_content_json(self, html_text: str) -> Optional[Dict[str, Any]]:
        m = re.search(r'data-content="([^"]+)"', html_text)
        if not m:
            return None
        raw = html.unescape(m.group(1))
        try:
            data = json.loads(raw)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _iter_dicts(self, obj: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from self._iter_dicts(v)
        elif isinstance(obj, list):
            for it in obj:
                yield from self._iter_dicts(it)

    def _coerce_hit(self, d: Dict[str, Any]) -> Optional[UGSearchHit]:
        url = (d.get("tab_url") or d.get("url") or "").strip()
        if not url.startswith("http"):
            return None

        title = (d.get("song_name") or d.get("songname") or d.get("title") or "").strip()
        artist = (d.get("artist_name") or d.get("artist") or "").strip()
        if not title:
            title = self._title_from_url(url)
        if not artist:
            artist = "Unknown"

        tab_id = None
        raw_id = d.get("id")
        if raw_id is not None:
            try:
                tab_id = int(raw_id)
            except Exception:
                tab_id = None

        rating = None
        raw_rating = d.get("rating")
        if raw_rating is not None:
            try:
                rating = float(raw_rating)
            except Exception:
                rating = None

        tab_type = (d.get("type") or d.get("tab_type") or "").strip() or None
        return UGSearchHit(
            title=title,
            artist=artist,
            tab_url=url,
            tab_id=tab_id,
            tab_type=tab_type,
            rating=rating,
        )

    def _title_from_url(self, url: str) -> str:
        slug = url.rstrip("/").split("/")[-1]
        slug = re.sub(r"-tab-\d+$", "", slug)
        slug = slug.replace("_", " ").replace("-", " ")
        slug = re.sub(r"\s+", " ", slug).strip()
        return slug.title() if slug else "Untitled"

    def search(self, query: str, limit: int = 12) -> List[UGSearchHit]:
        query = (query or "").strip()
        if not query:
            return []
        if len(query) < 2:
            raise UltimateGuitarError("Search query is too short. Enter at least 2 characters.")

        params = {"search_type": "title", "value": query}
        url = f"{UG_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        html_text = self._get_text(url)

        hits: List[UGSearchHit] = []
        seen = set()

        store = self._extract_page_store(html_text)
        if store:
            for d in self._iter_dicts(store):
                hit = self._coerce_hit(d)
                if not hit:
                    continue
                key = (hit.tab_id or 0, hit.tab_url)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
                if len(hits) >= int(limit):
                    return hits

        # Fallback: parse visible tab links from HTML.
        if not hits:
            for m in re.finditer(r'href="([^"]+/tab/[^"]+)"', html_text):
                tab_url = html.unescape(m.group(1).split("?")[0])
                if not tab_url.startswith("http"):
                    continue
                key = (0, tab_url)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(UGSearchHit(title=self._title_from_url(tab_url), artist="Unknown", tab_url=tab_url))
                if len(hits) >= int(limit):
                    break

        # Secondary fallback for JS-hydrated pages where tab links are present
        # only inside escaped JSON blobs and not as rendered <a href="...">.
        if not hits:
            for tab_url in self._extract_tab_urls_from_text(html_text):
                key = (0, tab_url)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(UGSearchHit(title=self._title_from_url(tab_url), artist="Unknown", tab_url=tab_url))
                if len(hits) >= int(limit):
                    break

        return hits

    def _extract_tab_urls_from_text(self, text: str) -> Iterable[str]:
        # Regular URL or JSON-escaped URL (https:\/\/tabs...\/tab\/...).
        patterns = [
            r"https?://[^\"'\s]+/tab/[^\"'\s]+",
            r"https?:\\/\\/[^\"'\s]+\\/tab\\/[^\"'\s]+",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text):
                raw = m.group(0)
                url = raw.replace("\\/", "/")
                url = html.unescape(url).split("?")[0]
                if url.startswith("http"):
                    yield url

    def fetch_tab(self, hit: UGSearchHit) -> UGTabDetail:
        html_text = self._get_text(hit.tab_url)
        store = self._extract_page_store(html_text)

        title = hit.title
        artist = hit.artist
        tab_url = hit.tab_url
        tab_id = hit.tab_id
        content = ""

        if store:
            for d in self._iter_dicts(store):
                if not title:
                    title = (d.get("song_name") or d.get("title") or "").strip() or title
                if not artist or artist == "Unknown":
                    artist = (d.get("artist_name") or d.get("artist") or "").strip() or artist
                if not tab_url:
                    tab_url = (d.get("tab_url") or "").strip() or tab_url
                if tab_id is None and d.get("id") is not None:
                    try:
                        tab_id = int(d.get("id"))
                    except Exception:
                        pass

                wiki = d.get("wiki_tab")
                if isinstance(wiki, dict):
                    raw = wiki.get("content") or wiki.get("text") or ""
                    if isinstance(raw, str) and len(raw) > len(content):
                        content = raw

        if not content:
            content = self._extract_content_fallback(html_text)

        if not content.strip():
            raise UltimateGuitarError(
                "Could not read tab content for this result. "
                "Try another version or import manually."
            )

        return UGTabDetail(
            title=(title or "Untitled").strip(),
            artist=(artist or "Unknown").strip(),
            tab_url=tab_url,
            tab_id=tab_id,
            content=content,
        )

    def _extract_content_fallback(self, html_text: str) -> str:
        best = ""
        for m in re.finditer(r'"content"\s*:\s*"((?:\\\\.|[^"\\])*)"', html_text):
            raw = m.group(1)
            try:
                val = json.loads(f'"{raw}"')
            except Exception:
                continue
            if isinstance(val, str) and len(val) > len(best):
                best = val
        return best

    def to_chordpro(self, detail: UGTabDetail) -> str:
        body = self._ug_markup_to_chordpro_lines(detail.content)
        title = detail.title or "Untitled"
        artist = detail.artist or "Unknown"
        lines = [
            f"{{title: {title}}}",
            f"{{artist: {artist}}}",
            f"{{comment: Source: Ultimate Guitar ({detail.tab_url})}}",
            "",
            body.rstrip("\n"),
            "",
        ]
        return "\n".join(lines)

    def _ug_markup_to_chordpro_lines(self, raw: str) -> str:
        text = html.unescape(raw or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Common UG tags -> ChordPro-ish equivalents.
        text = re.sub(r"\[ch\]([^\[]+?)\[/ch\]", lambda m: f"[{m.group(1).strip()}]", text, flags=re.IGNORECASE)
        text = re.sub(r"\[(verse\s*\d*|chorus\s*\d*|bridge\s*\d*|intro|outro|pre-chorus|pre chorus)\]", self._section_to_comment, text, flags=re.IGNORECASE)
        text = re.sub(r"\[/?(tab|b|i|u|size|font|color)(=[^\]]+)?\]", "", text, flags=re.IGNORECASE)

        out_lines: List[str] = []
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                out_lines.append("")
                continue

            # Remove leftover UG control tags.
            s = re.sub(r"\[[^\]]*?\]", lambda m: m.group(0) if re.match(r"^\[[A-G][^\]]*\]$", m.group(0)) else "", s)
            s = re.sub(r"\s+", " ", s).strip()
            out_lines.append(s)

        return "\n".join(out_lines).strip() + "\n"

    def _section_to_comment(self, m: re.Match[str]) -> str:
        label = (m.group(1) or "Section").strip()
        return f"{{comment: {label.title()}}}"
