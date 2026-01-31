import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class Token:
    kind: str  # "lyric" or "chord"
    text: str

@dataclass
class Line:
    tokens: List[Token]

@dataclass
class Block:
    kind: str  # "verse" | "chorus" | "comment"
    lines: List[Line] = field(default_factory=list)
    text: Optional[str] = None

@dataclass
class Song:
    meta: Dict[str, str] = field(default_factory=dict)
    blocks: List[Block] = field(default_factory=list)

DIRECTIVE_RE = re.compile(r"^\s*\{([^}:]+)\s*:\s*([^}]*)\}\s*$", re.IGNORECASE)
SOC_RE = re.compile(r"^\s*\{(soc|start_of_chorus)\}\s*$", re.IGNORECASE)
EOC_RE = re.compile(r"^\s*\{(eoc|end_of_chorus)\}\s*$", re.IGNORECASE)
COMMENT_RE = re.compile(r"^\s*\{(comment|c)\s*:\s*([^}]*)\}\s*$", re.IGNORECASE)
CHORD_TOKEN_RE = re.compile(r"\[([^\]]+)\]")

def parse_chordpro(text: str) -> Song:
    song = Song()
    in_chorus = False
    current_block = Block(kind="verse")

    def flush_block():
        nonlocal current_block
        if current_block.lines:
            song.blocks.append(current_block)
        current_block = Block(kind="chorus" if in_chorus else "verse")

    for raw in text.splitlines():
        line = raw.rstrip("\n")

        if not line.strip():
            flush_block()
            continue

        if SOC_RE.match(line):
            flush_block()
            in_chorus = True
            current_block = Block(kind="chorus")
            continue

        if EOC_RE.match(line):
            flush_block()
            in_chorus = False
            current_block = Block(kind="verse")
            continue

        m_comment = COMMENT_RE.match(line)
        if m_comment:
            flush_block()
            song.blocks.append(Block(kind="comment", text=m_comment.group(2).strip()))
            continue

        m_dir = DIRECTIVE_RE.match(line)
        if m_dir:
            key = m_dir.group(1).strip().lower()
            val = m_dir.group(2).strip()
            song.meta[key] = val
            continue

        tokens: List[Token] = []
        last = 0
        for m in CHORD_TOKEN_RE.finditer(line):
            if m.start() > last:
                tokens.append(Token("lyric", line[last:m.start()]))
            tokens.append(Token("chord", m.group(1)))
            last = m.end()
        if last < len(line):
            tokens.append(Token("lyric", line[last:]))

        current_block.lines.append(Line(tokens=tokens))

    flush_block()
    return song
