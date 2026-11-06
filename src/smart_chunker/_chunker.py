"""Markdown chunker: CommonMark/GFM block parsing and token-budget packing."""

from __future__ import annotations

import hashlib
import logging
import re
from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

BlockKind = Literal["heading", "paragraph", "list", "code", "table", "blockquote", "hr"]
ErrorCode = Literal["invalid_options", "input_too_large", "invalid_counter"]
TokenCounter = Callable[[str], int]

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*))?$")
_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_HR = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_BQ = re.compile(r"^ {0,3}>")
_LIST = re.compile(r"^ {0,3}([-+*]|\d{1,9}[.)])(?:[ \t]|$)")
_DELIM = re.compile(r"^:?-+:?$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_SENT_END = re.compile(r"[.!?](?=\s)")
_WORD = re.compile(r"\S+")
_SPLITTABLE = ("paragraph", "list", "code", "table", "blockquote")


class ChunkerError(ValueError):
    """Base error of the library; ``code`` is a stable machine-readable identifier."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message[:200])
        self.code: ErrorCode = code


def default_token_counter(text: str) -> int:
    """Approximate token count: ``ceil(len(text) / 4)``."""
    return -(-len(text) // 4)


@dataclass(frozen=True)
class ChunkOptions:
    """Validated chunking options."""

    max_tokens: int = 512
    overlap_tokens: int = 64
    min_tokens: int = 32
    respect_headings_level: int = 2
    max_chars: int = 10_000_000

    def __post_init__(self) -> None:
        values = {
            "max_tokens": self.max_tokens,
            "overlap_tokens": self.overlap_tokens,
            "min_tokens": self.min_tokens,
            "respect_headings_level": self.respect_headings_level,
            "max_chars": self.max_chars,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ChunkerError("invalid_options", f"{name} must be an integer")
        if self.max_tokens < 1:
            raise ChunkerError("invalid_options", "max_tokens must be >= 1")
        if not 0 <= self.overlap_tokens < self.max_tokens:
            raise ChunkerError("invalid_options", "overlap_tokens must be >= 0 and < max_tokens")
        if not 0 <= self.min_tokens <= self.max_tokens:
            raise ChunkerError("invalid_options", "min_tokens must be >= 0 and <= max_tokens")
        if not 0 <= self.respect_headings_level <= 6:
            raise ChunkerError("invalid_options", "respect_headings_level must be 0..6")
        if self.max_chars < 1:
            raise ChunkerError("invalid_options", "max_chars must be >= 1")


_DEFAULT_OPTIONS = ChunkOptions()


@dataclass(frozen=True)
class Block:
    """A top-level Markdown block with its 1-based inclusive line range."""

    kind: BlockKind
    text: str
    level: int | None
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Chunk:
    """A retrieval chunk with provenance metadata."""

    text: str
    index: int
    heading_path: tuple[str, ...]
    start_line: int
    end_line: int
    tokens: int
    sha256: str
    kinds: frozenset[str]
    overlap_chars: int


# ---------------------------------------------------------------- parsing


def _fence_open(line: str) -> re.Match[str] | None:
    match = _FENCE.match(line)
    if match is None:
        return None
    if match.group(2)[0] == "`" and "`" in match.group(3):
        return None
    return match


def _closer(marker: str) -> re.Pattern[str]:
    return re.compile("^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + ",}[ \t]*$")


def _fence_end(lines: list[str], start: int, marker: str) -> int:
    closer = _closer(marker)
    for j in range(start + 1, len(lines)):
        if closer.match(lines[j]) is not None:
            return j
    return len(lines) - 1


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in _CELL_SPLIT.split(body)]


def _is_table_start(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines) or "|" not in lines[i]:
        return False
    delim = _cells(lines[i + 1])
    if len(delim) != len(_cells(lines[i])):
        return False
    return all(_DELIM.match(cell) is not None for cell in delim)


def _hard_break(line: str) -> bool:
    return (
        _fence_open(line) is not None or _ATX.match(line) is not None or _HR.match(line) is not None
    )


def _interrupts(line: str) -> bool:
    if _hard_break(line) or _BQ.match(line) is not None:
        return True
    match = _LIST.match(line)
    if match is None:
        return False
    marker = match.group(1)
    if not line[match.end() :].strip():
        return False
    return marker[0] in "-+*" or marker[:-1] == "1"


def _lazy_end(lines: list[str], i: int) -> int:
    j = i + 1
    while j < len(lines) and lines[j].strip() and not _hard_break(lines[j]):
        j += 1
    return j - 1


def _list_end(lines: list[str], i: int) -> int:
    n = len(lines)
    last = i
    j = i + 1
    while j < n:
        line = lines[j]
        if line.strip():
            if not line.startswith("  ") and (_hard_break(line) or _BQ.match(line) is not None):
                break
            last = j
            j += 1
            continue
        k = j
        while k < n and not lines[k].strip():
            k += 1
        if k < n and (lines[k].startswith("  ") or _LIST.match(lines[k]) is not None):
            j = k
        else:
            break
    return last


def _scan_paragraph(lines: list[str], i: int) -> tuple[BlockKind, int | None, int]:
    n = len(lines)
    j = i + 1
    while j < n and lines[j].strip():
        setext = _SETEXT.match(lines[j])
        if setext is not None:
            return "heading", 1 if setext.group(1)[0] == "=" else 2, j
        if _interrupts(lines[j]):
            break
        j += 1
    return "paragraph", None, j - 1


def _scan_block(lines: list[str], i: int) -> tuple[BlockKind, int | None, int]:
    n = len(lines)
    line = lines[i]
    fence = _fence_open(line)
    if fence is not None:
        return "code", None, _fence_end(lines, i, fence.group(2))
    if line.startswith(("    ", "\t")):
        last = i
        j = i + 1
        while j < n:
            if lines[j].startswith(("    ", "\t")) and lines[j].strip():
                last = j
            elif lines[j].strip():
                break
            j += 1
        return "code", None, last
    atx = _ATX.match(line)
    if atx is not None:
        return "heading", len(atx.group(1)), i
    if _HR.match(line) is not None:
        return "hr", None, i
    if _is_table_start(lines, i):
        j = i + 2
        while j < n and lines[j].strip() and not _hard_break(lines[j]):
            j += 1
        return "table", None, j - 1
    if _BQ.match(line) is not None:
        return "blockquote", None, _lazy_end(lines, i)
    if _LIST.match(line) is not None:
        return "list", None, _list_end(lines, i)
    return _scan_paragraph(lines, i)


def _parse(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    n = len(lines)
    i = 0
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        kind, level, last = _scan_block(lines, i)
        text = "\n".join(lines[i : last + 1])
        blocks.append(Block(kind, text, level, i + 1, last + 1))
        i = last + 1
    return blocks


def _split_lines(markdown: str, max_chars: int) -> list[str]:
    if not isinstance(markdown, str):
        raise ChunkerError("invalid_options", "markdown must be a string")
    if len(markdown) > max_chars:
        raise ChunkerError("input_too_large", f"input exceeds {max_chars} characters")
    if not markdown:
        return []
    return markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_blocks(markdown: str) -> list[Block]:
    """Parse ``markdown`` into top-level blocks with 1-based inclusive line ranges.

    Raises:
        ChunkerError: ``input_too_large`` above the default ``max_chars``.
    """
    return _parse(_split_lines(markdown, _DEFAULT_OPTIONS.max_chars))


def _atx_content(line: str) -> str:
    match = _ATX.match(line)
    content = (match.group(2) or "").strip() if match else ""
    trimmed = content.rstrip("#")
    if not trimmed or trimmed[-1] in " \t":
        return trimmed.strip()
    return content


def _heading_text(block: Block) -> str:
    rows = block.text.split("\n")
    if len(rows) == 1:
        return _atx_content(rows[0])
    return " ".join(row.strip() for row in rows[:-1])


# ---------------------------------------------------------------- packing


@dataclass(frozen=True)
class _Item:
    text: str
    start: int
    end: int
    kind: str
    exact: bool


@dataclass(frozen=True)
class _Unit:
    text: str
    start: int
    end: int
    sep: str


@dataclass(frozen=True)
class _Plan:
    units: list[_Unit]
    head: str
    tail: str
    forced: bool


def _sep(prev: _Item, item: _Item, lines: list[str]) -> str:
    if prev.exact and item.exact and item.start > prev.end + 1:
        low = prev.end
        high = item.start - 1
        return "\n" + "".join(f"{gap}\n" for gap in lines[low:high])
    return "\n"


class _Draft:
    def __init__(self, section: int, prefix: str) -> None:
        self.items: list[_Item] = []
        self.body = ""
        self.prefix = prefix
        self.section = section
        self.path: tuple[str, ...] = ()
        self.frozen = False
        self.split = False
        self.forced = False

    def has_body(self) -> bool:
        return any(item.kind != "heading" for item in self.items)

    def body_with(self, item: _Item, lines: list[str]) -> str:
        if not self.items:
            return item.text
        return self.body + _sep(self.items[-1], item, lines) + item.text

    def compose(self, body: str) -> str:
        return f"{self.prefix}\n{body}" if self.prefix else body

    def text_with(self, item: _Item, lines: list[str]) -> str:
        return self.compose(self.body_with(item, lines))

    def text(self) -> str:
        return self.compose(self.body)

    def append(self, item: _Item, lines: list[str]) -> None:
        self.body = self.body_with(item, lines)
        self.items.append(item)

    def rebuild(self, items: list[_Item], lines: list[str]) -> None:
        self.items = []
        self.body = ""
        for item in items:
            self.append(item, lines)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    n = len(text)
    i = 0
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        match = _SENT_END.search(text, i)
        if match is not None:
            end = match.end()
        else:
            end = n
            while text[end - 1].isspace():
                end -= 1
        spans.append((i, end))
        i = end
    return spans


def _segments(text: str, fits: Callable[[str], bool]) -> list[str]:
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        lo = 1
        hi = len(text) - pos
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(text[pos : pos + mid]):
                lo = mid
            else:
                hi = mid - 1
        parts.append(text[pos : pos + lo])
        pos += lo
    return parts


def _line_plan(block: Block, count: TokenCounter, max_tokens: int) -> _Plan:
    rows = block.text.split("\n")
    head = ""
    tail = ""
    first = 0
    end = len(rows)
    if block.kind == "table":
        head = rows[0] + "\n" + rows[1] + "\n"
        first = 2
    else:
        fence = _fence_open(rows[0])
        if fence is not None:
            marker = fence.group(2)
            head = rows[0] + "\n"
            tail = "\n" + marker
            first = 1
            if len(rows) > 1 and _closer(marker).match(rows[-1]) is not None:
                end = len(rows) - 1
    units: list[_Unit] = []
    forced = False
    for offset in range(first, end):
        row = rows[offset]
        number = block.start_line + offset
        if count(head + row + tail) <= max_tokens:
            units.append(_Unit(row, number, number, "\n"))
            continue
        forced = True
        for part in _segments(row, lambda piece: count(head + piece + tail) <= max_tokens):
            units.append(_Unit(part, number, number, "\n"))
    return _Plan(units, head, tail, forced)


def _text_plan(block: Block, count: TokenCounter, max_tokens: int) -> _Plan:
    text = block.text
    newlines = [i for i, ch in enumerate(text) if ch == "\n"]
    units: list[_Unit] = []
    forced = False
    prev_end = 0

    def add(start: int, end: int) -> None:
        nonlocal prev_end
        sep = text[prev_end:start] if units else ""
        first = block.start_line + bisect_left(newlines, start)
        last = block.start_line + bisect_left(newlines, end - 1)
        units.append(_Unit(text[start:end], first, last, sep))
        prev_end = end

    for start, end in _sentence_spans(text):
        if count(text[start:end]) <= max_tokens:
            add(start, end)
            continue
        for word in _WORD.finditer(text[start:end]):
            w_start = start + word.start()
            w_end = start + word.end()
            if count(text[w_start:w_end]) <= max_tokens:
                add(w_start, w_end)
                continue
            forced = True
            offset = w_start
            for part in _segments(text[w_start:w_end], lambda piece: count(piece) <= max_tokens):
                add(offset, offset + len(part))
                offset += len(part)
    return _Plan(units, "", "", forced)


def _piece(block: Block, plan: _Plan, s: int, e: int) -> _Item:
    units = plan.units
    body = units[s].text + "".join(unit.sep + unit.text for unit in units[s + 1 : e + 1])
    text = plan.head + body + plan.tail
    return _Item(text, units[s].start, units[e].end, block.kind, False)


class _Packer:
    def __init__(self, lines: list[str], opts: ChunkOptions, count: TokenCounter) -> None:
        self.lines = lines
        self.opts = opts
        self.count = count
        self.drafts: list[_Draft] = []
        self.cur: _Draft | None = None
        self.carry: list[_Item] = []
        self.section = 0
        self.stack: list[tuple[int, str]] = []
        self.last: _Draft | None = None

    def _prefix(self) -> str:
        last = self.last
        if last is None or last.section != self.section or self.opts.overlap_tokens <= 0:
            return ""
        tail = last.items[-1]
        if tail.kind not in ("paragraph", "list"):
            return ""
        sentences = [tail.text[a:b] for a, b in _sentence_spans(tail.text)]
        best = ""
        for start in range(len(sentences) - 1, -1, -1):
            candidate = " ".join(sentences[start:])
            if self.count(candidate) > self.opts.overlap_tokens:
                break
            best = candidate
        return best

    def _ensure(self, allow_prefix: bool) -> _Draft:
        if self.cur is None:
            carry, self.carry = self.carry, []
            prefix = self._prefix() if allow_prefix and not carry else ""
            draft = _Draft(self.section, prefix)
            for item in carry:
                draft.append(item, self.lines)
            self.cur = draft
        return self.cur

    def _fits(self, draft: _Draft, item: _Item) -> bool:
        return self.count(draft.text_with(item, self.lines)) <= self.opts.max_tokens

    def _push(self, draft: _Draft, item: _Item) -> None:
        draft.append(item, self.lines)
        if not draft.frozen:
            draft.section = self.section
            draft.path = tuple(text for _, text in self.stack)
            draft.frozen = item.kind != "heading"

    def _flush(self, pop: bool = True) -> None:
        draft = self.cur
        self.cur = None
        if draft is None or not draft.items:
            return
        if pop and draft.has_body():
            k = len(draft.items)
            while draft.items[k - 1].kind == "heading":
                k -= 1
            if k < len(draft.items):
                self.carry = draft.items[k:]
                draft.rebuild(draft.items[:k], self.lines)
        self.drafts.append(draft)
        self.last = draft

    def add(self, block: Block) -> None:
        item = _Item(block.text, block.start_line, block.end_line, block.kind, True)
        if block.kind == "heading":
            level = block.level or 1
            while self.stack and self.stack[-1][0] >= level:
                self.stack.pop()
            self.stack.append((level, _heading_text(block)))
            if level <= self.opts.respect_headings_level:
                self.section += 1
                if self.cur is not None and self.cur.has_body():
                    self._flush()
        self._place(item, block)

    def _place(self, item: _Item, block: Block) -> None:
        allow = block.kind != "heading"
        splittable = block.kind in _SPLITTABLE
        if splittable and self.count(item.text) > self.opts.max_tokens and self._split(block):
            return
        draft = self._ensure(allow)
        if self._fits(draft, item):
            self._push(draft, item)
            return
        if draft.has_body():
            self._flush()
            draft = self._ensure(allow)
            if self._fits(draft, item):
                self._push(draft, item)
                return
        if draft.prefix:
            draft.prefix = ""
            if self._fits(draft, item):
                self._push(draft, item)
                return
        if splittable and self._split(block):
            return
        if draft.items:
            self._flush(pop=False)
            draft = self._ensure(False)
        self._push(draft, item)

    def _plan(self, block: Block) -> _Plan:
        if block.kind in ("code", "table"):
            return _line_plan(block, self.count, self.opts.max_tokens)
        return _text_plan(block, self.count, self.opts.max_tokens)

    def _grow(self, draft: _Draft, block: Block, plan: _Plan, s: int) -> int:
        lo = s
        hi = len(plan.units) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._fits(draft, _piece(block, plan, s, mid)):
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _split(self, block: Block) -> bool:
        plan = self._plan(block)
        total = len(plan.units)
        if total == 0:
            return False
        s = 0
        while s < total:
            draft = self._ensure(True)
            first = _piece(block, plan, s, s)
            if self._fits(draft, first):
                e = self._grow(draft, block, plan, s)
            else:
                if draft.has_body():
                    self._flush()
                    continue
                if draft.prefix:
                    draft.prefix = ""
                    continue
                if draft.items:
                    self._flush(pop=False)
                    continue
                e = s
            item = first if e == s else _piece(block, plan, s, e)
            self._push(draft, item)
            draft.split = True
            draft.forced = draft.forced or plan.forced
            s = e + 1
            if s < total:
                self._flush()
        return True

    def finish(self) -> list[_Draft]:
        if self.cur is None and self.carry:
            self._ensure(False)
        self._flush(pop=False)
        return self.drafts


def _join_drafts(prev: _Draft, nxt: _Draft, lines: list[str]) -> _Draft:
    joined = _Draft(prev.section, prev.prefix)
    joined.rebuild([*prev.items, *nxt.items], lines)
    joined.path = prev.path
    joined.frozen = True
    joined.split = prev.split or nxt.split
    joined.forced = prev.forced or nxt.forced
    return joined


def _merge(
    drafts: list[_Draft], lines: list[str], opts: ChunkOptions, count: TokenCounter
) -> list[_Draft]:
    merged: list[_Draft] = []
    for idx, draft in enumerate(drafts):
        is_tail = idx == len(drafts) - 1 or drafts[idx + 1].section != draft.section
        prev = merged[-1] if merged else None
        if prev is not None and is_tail and prev.section == draft.section:
            joined = _join_drafts(prev, draft, lines)
            small = count(draft.text()) < opts.min_tokens
            if small and count(joined.text()) <= opts.max_tokens:
                merged[-1] = joined
                continue
        merged.append(draft)
    return merged


def _checked(counter: TokenCounter) -> TokenCounter:
    def count(text: str) -> int:
        value = counter(text)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ChunkerError("invalid_counter", "counter must return a non-bool int >= 0")
        return value

    return count


def chunk_markdown(
    markdown: str,
    options: ChunkOptions = _DEFAULT_OPTIONS,
    *,
    counter: TokenCounter = default_token_counter,
) -> list[Chunk]:
    """Split ``markdown`` into chunks that respect structure and the token budget.

    Raises:
        ChunkerError: ``input_too_large``, ``invalid_counter`` or ``invalid_options``.
    """
    lines = _split_lines(markdown, options.max_chars)
    blocks = _parse(lines)
    count = _checked(counter)
    packer = _Packer(lines, options, count)
    for block in blocks:
        packer.add(block)
    drafts = _merge(packer.finish(), lines, options, count)
    chunks: list[Chunk] = []
    for index, draft in enumerate(drafts):
        text = draft.text()
        kinds = {item.kind for item in draft.items}
        if draft.split:
            kinds.add("split")
        if draft.forced:
            kinds.add("forced")
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
        chunks.append(
            Chunk(
                text=text,
                index=index,
                heading_path=draft.path,
                start_line=draft.items[0].start,
                end_line=draft.items[-1].end,
                tokens=count(text),
                sha256=digest,
                kinds=frozenset(kinds),
                overlap_chars=len(draft.prefix),
            )
        )
    logger.debug("chunked %d blocks into %d chunks", len(blocks), len(chunks))
    return chunks
