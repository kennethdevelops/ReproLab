"""Line-preserving chunker (ADR-0003).

Code is split at top-level declaration boundaries detected per language; long declarations are
split into overlapping line windows. Markdown is split at headings. Every chunk records 1-based
inclusive start/end lines and its content is exactly those lines of the original file, which is
what makes citations checkable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

CHUNKER_VERSION = "boundary-lines-v1"

MAX_LINES = 80
WINDOW_OVERLAP = 10
MIN_LINES = 6

_JS_DECL = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:function\*?\s+(?P<fn>[A-Za-z_$][\w$]*)"
    r"|class\s+(?P<cls>[A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*)"
    r"|interface\s+(?P<iface>[A-Za-z_$][\w$]*)"
    r"|type\s+(?P<type>[A-Za-z_$][\w$]*)\s*[=<]"
    r"|enum\s+(?P<enum>[A-Za-z_$][\w$]*))"
)
_PY_DECL = re.compile(r"^(?:async\s+)?(?:def|class)\s+(?P<name>[A-Za-z_]\w*)")
_CS_DECL = re.compile(
    r"^\s{0,4}(?:(?:public|private|internal|protected|static|sealed|abstract|partial)\s+)*"
    r"(?:class|record|interface|struct|enum)\s+(?P<name>\w+)"
)
_SQL_DECL = re.compile(
    r"^(?:create|alter)\s+(?:or\s+replace\s+)?(?:table|view|function|index)\s+(?P<name>[\w.\"]+)",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^(#{1,6})\s+(?P<name>.+?)\s*#*\s*$")
_LEADING_COMMENT = ("//", "/*", "*", "#", "@", '"""')

JS_LANGUAGES = {"typescript", "tsx", "javascript", "jsx"}
CODE_LANGUAGES = JS_LANGUAGES | {"python", "csharp", "sql"}


@dataclass(frozen=True)
class Chunk:
    start_line: int
    end_line: int
    symbol: str | None
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _boundary(language: str, line: str) -> tuple[bool, str | None]:
    if language == "markdown":
        m = _HEADING.match(line)
        return (True, m.group("name")) if m else (False, None)
    if language in JS_LANGUAGES:
        m = _JS_DECL.match(line)
        if m:
            return True, next((v for v in m.groupdict().values() if v), None)
        return False, None
    pattern = {"python": _PY_DECL, "csharp": _CS_DECL, "sql": _SQL_DECL}.get(language)
    m = pattern.match(line) if pattern else None
    return (True, m.group("name").strip('"')) if m else (False, None)


def _segments(lines: list[str], language: str) -> list[tuple[int, int, str | None]]:
    """Half-open [start, end) 0-based segments, each beginning at a boundary."""
    starts: list[tuple[int, str | None]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if language == "markdown" and line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        is_start, name = _boundary(language, line)
        if not is_start:
            continue
        # Attach directly preceding comment/decorator lines to the declaration.
        j = i
        if language != "markdown":
            while j > 0 and lines[j - 1].lstrip().startswith(_LEADING_COMMENT):
                j -= 1
        if starts and j <= starts[-1][0]:
            j = i
        starts.append((j, name))
    if not starts or starts[0][0] != 0:
        starts.insert(0, (0, None))
    out = []
    for k, (start, name) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        if end > start:
            out.append((start, end, name))
    return out


def _merge_small(
    segments: list[tuple[int, int, str | None]],
) -> list[tuple[int, int, str | None]]:
    merged: list[tuple[int, int, str | None]] = []
    for seg in segments:
        if merged:
            prev = merged[-1]
            small = seg[1] - seg[0] < MIN_LINES or prev[1] - prev[0] < MIN_LINES
            if small and seg[1] - prev[0] <= MAX_LINES:
                merged[-1] = (prev[0], seg[1], prev[2] or seg[2])
                continue
        merged.append(seg)
    return merged


def _windows(start: int, end: int, symbol: str | None) -> list[tuple[int, int, str | None]]:
    if end - start <= MAX_LINES:
        return [(start, end, symbol)]
    out = []
    s = start
    while True:
        e = min(s + MAX_LINES, end)
        out.append((s, e, symbol))
        if e == end:
            return out
        s += MAX_LINES - WINDOW_OVERLAP


def chunk_text(text: str, language: str) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    if language in CODE_LANGUAGES or language == "markdown":
        segments = _merge_small(_segments(lines, language))
    else:
        segments = [(0, len(lines), None)]
    chunks: list[Chunk] = []
    for start, end, symbol in segments:
        for s, e, sym in _windows(start, end, symbol):
            # Trim blank edges but keep exact line numbers for what remains.
            while s < e and not lines[s].strip():
                s += 1
            while e > s and not lines[e - 1].strip():
                e -= 1
            if e > s:
                chunks.append(Chunk(s + 1, e, sym, "\n".join(lines[s:e])))
    return chunks


_IDENT_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-./]+")


def search_text(path: str, symbol: str | None, content: str) -> str:
    """Text fed to the full-text index: content plus path and identifier pieces, so that
    `useCartTotals` also matches "cart totals" and file names are searchable."""
    idents = set(re.findall(r"[A-Za-z_$][\w$]{2,}", content)) | {path, symbol or ""}
    pieces = {p.lower() for ident in idents for p in _IDENT_SPLIT.split(ident) if len(p) > 1}
    return " ".join([path, symbol or "", content, " ".join(sorted(pieces))])
