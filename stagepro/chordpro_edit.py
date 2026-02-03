"""Small utilities for editing ChordPro files as text.

The renderer/parser in stagepro.chordpro is intentionally simple. For editing
metadata during import/maintenance we operate on raw text to avoid changing
user formatting more than necessary.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple


_KV_RE = re.compile(r"^\s*\{\s*([^}:]+)\s*:\s*([^}]*)\}\s*$", re.IGNORECASE)


def upsert_directives(text: str, updates: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Upsert key:value directives.

    - If a directive exists for a key (case-insensitive), update its value.
    - Otherwise insert new directives near the top (after leading blank lines
      and after any existing directives).

    Returns: (new_text, final_meta_map)
    """
    if not updates:
        return text, {}

    lines = text.splitlines()
    # keep original newline style (we'll re-join with \n and add trailing \n)
    existing = {}
    key_to_index = {}

    for i, ln in enumerate(lines):
        m = _KV_RE.match(ln)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        existing[key] = val
        if key not in key_to_index:
            key_to_index[key] = i

    # Apply updates to existing lines
    for k, v in updates.items():
        k2 = k.strip().lower()
        v2 = (v or "").strip()
        if not v2:
            continue
        if k2 in key_to_index:
            lines[key_to_index[k2]] = f"{{{k2}: {v2}}}"
            existing[k2] = v2

    # Insert missing keys
    missing = []
    for k, v in updates.items():
        k2 = k.strip().lower()
        v2 = (v or "").strip()
        if not v2:
            continue
        if k2 not in existing:
            missing.append((k2, v2))

    if missing:
        # Find insertion point: after leading blanks and existing directives
        insert_at = 0
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        while insert_at < len(lines):
            if _KV_RE.match(lines[insert_at]):
                insert_at += 1
                continue
            break

        directive_lines = [f"{{{k}: {v}}}" for k, v in missing]
        lines[insert_at:insert_at] = directive_lines
        for k, v in missing:
            existing[k] = v

    out = "\n".join(lines).rstrip() + "\n"
    return out, dict(existing)
