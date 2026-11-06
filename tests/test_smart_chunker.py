"""Tests for the smart_chunker public API."""

from __future__ import annotations

import hashlib
import logging
import re

import pytest

import smart_chunker as sc

OPTS = sc.ChunkOptions(max_tokens=50, overlap_tokens=10, min_tokens=0)


def words(text: str) -> int:
    return len(text.split())


def sentences(count: int) -> str:
    return " ".join(f"S{i} aa bb cc dd." for i in range(count))


def test_budget_holds_with_overlap_and_fences() -> None:
    code = "\n".join(f"c{i}" for i in range(30))
    md = "# T\n\n" + sentences(40) + "\n\n```py\n" + code + "\n```\n"
    chunks = sc.chunk_markdown(md, OPTS, counter=words)
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.tokens <= 50
        assert chunk.tokens == words(chunk.text)


def test_code_whole_or_split_with_fences() -> None:
    small = "```py\n" + "\n".join(f"c{i}" for i in range(28)) + "\n```"
    out = sc.chunk_markdown(small, OPTS, counter=words)
    assert len(out) == 1
    assert "split" not in out[0].kinds
    assert out[0].text == small
    big = "```py\n" + "\n".join(f"c{i}" for i in range(118)) + "\n```"
    out = sc.chunk_markdown(big, OPTS, counter=words)
    assert len(out) > 1
    for chunk in out:
        rows = chunk.text.split("\n")
        assert rows[0] == "```py"
        assert rows[-1] == "```"
        assert "split" in chunk.kinds
        assert chunk.tokens <= 50


def test_table_split_repeats_header() -> None:
    header = "| a | b |\n| --- | --- |"
    rows = "\n".join("| x | y |" for _ in range(22))
    out = sc.chunk_markdown(header + "\n" + rows, OPTS, counter=words)
    assert len(out) > 1
    for chunk in out:
        assert chunk.text.startswith(header + "\n")
        assert "split" in chunk.kinds
        assert chunk.tokens <= 50


def test_heading_sections_and_paths() -> None:
    chunks = sc.chunk_markdown("# A\n## B\ntext\n## C\nmore")
    assert [c.text for c in chunks] == ["# A\n## B\ntext", "## C\nmore"]
    assert [c.heading_path for c in chunks] == [("A", "B"), ("A", "C")]
    fixtures = [
        "# A\n## B\ntext\n## C\nmore",
        "# A\n\n### d\n\ntext\n\n## E\n\nmore",
        "# T\n\n" + sentences(30),
    ]
    for md in fixtures:
        for chunk in sc.chunk_markdown(md, OPTS, counter=words):
            assert not chunk.text.split("\n")[-1].startswith("#")


def test_overlap_prefix() -> None:
    opts = sc.ChunkOptions(max_tokens=50, overlap_tokens=12, min_tokens=0)
    chunks = sc.chunk_markdown(sentences(40), opts, counter=words)
    prefix = " ".join(re.findall(r"S\d+ aa bb cc dd\.", chunks[0].text)[-2:])
    assert prefix == "S8 aa bb cc dd. S9 aa bb cc dd."
    assert words(prefix) <= 12
    assert chunks[1].text.startswith(prefix + "\nS10 ")
    assert chunks[1].overlap_chars == len(prefix)
    assert chunks[0].overlap_chars == 0


def test_no_overlap_across_headings_or_from_code() -> None:
    md = "# A\n\n" + sentences(12) + "\n\n# B\n\n" + sentences(12)
    chunks = sc.chunk_markdown(md, OPTS, counter=words)
    starts = [c for c in chunks if c.text.startswith("# B")]
    assert len(starts) == 1
    assert starts[0].overlap_chars == 0
    md2 = "one two three four five six.\n\n```\na b c d e\n```\n\nmore text here"
    opts = sc.ChunkOptions(max_tokens=8, overlap_tokens=7, min_tokens=0)
    out = sc.chunk_markdown(md2, opts, counter=words)
    assert len(out) == 3
    assert [c.overlap_chars for c in out] == [0, 0, 0]


def test_not_headings_and_fences() -> None:
    assert sc.parse_blocks("#5 is not a heading")[0].kind == "paragraph"
    indented = sc.parse_blocks("    # x")
    assert [b.kind for b in indented] == ["code"]
    fenced = sc.parse_blocks("```\n# x\n```")
    assert len(fenced) == 1
    assert fenced[0].kind == "code"
    tilde = sc.parse_blocks("~~~\n```\nstill\n~~~\nafter")
    assert [(b.kind, b.end_line) for b in tilde] == [("code", 4), ("paragraph", 5)]
    open_fence = sc.parse_blocks("```\nopen\n# x")
    assert len(open_fence) == 1
    assert open_fence[0].end_line == 3
    lf = "# A\ntext\n\n## B\nmore"
    crlf = lf.replace("\n", "\r\n")
    assert sc.chunk_markdown(crlf) == sc.chunk_markdown(lf)
    assert sc.chunk_markdown("") == []


def test_line_range_and_hash() -> None:
    md = "# A\n\nfirst para\n\n\nsecond para\n\n## B\n\nthird"
    lines = md.split("\n")
    chunks = sc.chunk_markdown(md)
    assert len(chunks) == 2
    for chunk in chunks:
        low = chunk.start_line - 1
        high = chunk.end_line
        assert chunk.text == "\n".join(lines[low:high])
        assert chunk.sha256 == hashlib.sha256(chunk.text.encode()).hexdigest()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"overlap_tokens": 512},
        {"max_tokens": 0},
        {"min_tokens": 600},
        {"overlap_tokens": -1},
        {"min_tokens": -1},
        {"respect_headings_level": 7},
        {"max_chars": 0},
        {"max_tokens": True},
        {"max_tokens": 1.5},
    ],
)
def test_invalid_options(kwargs: dict[str, object]) -> None:
    with pytest.raises(sc.ChunkerError) as info:
        sc.ChunkOptions(**kwargs)  # type: ignore[arg-type]
    assert info.value.code == "invalid_options"
    assert isinstance(info.value, ValueError)


def test_input_too_large_and_bad_type() -> None:
    with pytest.raises(sc.ChunkerError) as info:
        sc.chunk_markdown("x" * 6, sc.ChunkOptions(max_chars=5))
    assert info.value.code == "input_too_large"
    with pytest.raises(sc.ChunkerError) as info2:
        sc.parse_blocks("x" * 10_000_001)
    assert info2.value.code == "input_too_large"
    with pytest.raises(sc.ChunkerError) as info3:
        sc.chunk_markdown(123)  # type: ignore[arg-type]
    assert info3.value.code == "invalid_options"


@pytest.mark.parametrize("bad", [True, -1, 1.5])
def test_invalid_counter(bad: object) -> None:
    with pytest.raises(sc.ChunkerError) as info:
        sc.chunk_markdown("hello", counter=lambda _: bad)  # type: ignore[arg-type,return-value]
    assert info.value.code == "invalid_counter"


def test_default_counter() -> None:
    assert sc.default_token_counter("") == 0
    assert sc.default_token_counter("abcd") == 1
    assert sc.default_token_counter("abcde") == 2


def test_forced_split_and_table_mismatch_and_determinism() -> None:
    opts = sc.ChunkOptions(max_tokens=10, overlap_tokens=2, min_tokens=0)
    chunks = sc.chunk_markdown("a" * 400, opts)
    assert len(chunks) == 10
    assert all("forced" in c.kinds and c.tokens <= 10 for c in chunks)
    assert "".join(c.text for c in chunks) == "a" * 400
    blocks = sc.parse_blocks("| a | b |\n| --- |\n")
    assert [b.kind for b in blocks] == ["paragraph"]
    md = "# A\n\n" + sentences(30)
    assert sc.chunk_markdown(md, OPTS, counter=words) == sc.chunk_markdown(md, OPTS, counter=words)


def test_block_kinds_and_ranges() -> None:
    lines = [
        "Title",
        "=====",
        "",
        "## Sub ##",
        "",
        "---",
        "",
        "- a",
        "- b",
        "",
        "  more",
        "",
        "> quote",
        "continued",
        "",
        "| a | b |",
        "| --- | :-: |",
        "| 1 | 2 |",
        "",
        "1. one",
        "",
        "Sub2",
        "---",
        "",
        "text",
        "# H",
    ]
    blocks = sc.parse_blocks("\n".join(lines))
    kinds = [b.kind for b in blocks]
    expected = ["heading", "heading", "hr", "list", "blockquote", "table", "list"]
    assert kinds == [*expected, "heading", "paragraph", "heading"]
    assert [b.level for b in blocks[:3]] == [1, 2, None]
    assert (blocks[0].start_line, blocks[0].end_line) == (1, 2)
    assert (blocks[3].start_line, blocks[3].end_line) == (8, 11)
    assert (blocks[4].start_line, blocks[4].end_line) == (13, 14)
    assert (blocks[5].start_line, blocks[5].end_line) == (16, 18)
    assert (blocks[7].start_line, blocks[7].end_line) == (22, 23)


def test_paragraph_interruptions_and_indented_code() -> None:
    assert [b.kind for b in sc.parse_blocks("para\n- item")] == ["paragraph", "list"]
    assert [b.kind for b in sc.parse_blocks("para\n2. y")] == ["paragraph"]
    assert [b.kind for b in sc.parse_blocks("para\n***")] == ["paragraph", "hr"]
    code = sc.parse_blocks("    a\n\n    b\ntext")
    assert [(b.kind, b.end_line) for b in code] == [("code", 3), ("paragraph", 4)]
    assert [b.kind for b in sc.parse_blocks("text\n> q\n\n* * *")] == [
        "paragraph",
        "blockquote",
        "hr",
    ]


def test_heading_paths_setext_and_closing_hashes() -> None:
    chunks = sc.chunk_markdown("Title\n=====\n\n## Sub ##\n\ntext")
    assert len(chunks) == 1
    assert chunks[0].heading_path == ("Title", "Sub")
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 6)
    assert sc.chunk_markdown("# foo ###\ntext")[0].heading_path == ("foo",)
    assert sc.chunk_markdown("#\ntext")[0].heading_path == ("",)


def test_trailing_heading_and_unsplittable_heading() -> None:
    chunks = sc.chunk_markdown("text\n\n## End")
    assert [c.text for c in chunks] == ["text", "## End"]
    opts = sc.ChunkOptions(max_tokens=3, overlap_tokens=1, min_tokens=0)
    big = sc.chunk_markdown("# " + "a" * 100, opts)
    assert len(big) == 1


def test_deep_heading_is_carried_to_next_chunk() -> None:
    md = "intro one two three.\n\n### Deep\n\nbody one two three"
    opts = sc.ChunkOptions(max_tokens=6, overlap_tokens=2, min_tokens=0)
    chunks = sc.chunk_markdown(md, opts, counter=words)
    assert len(chunks) == 2
    assert chunks[0].text.endswith("three.")
    assert chunks[1].text.startswith("### Deep")


def test_sentence_and_word_splitting() -> None:
    opts = sc.ChunkOptions(max_tokens=20, overlap_tokens=1, min_tokens=0)
    para = " ".join(["a b c d e f g h i j."] * 5)
    chunks = sc.chunk_markdown(para, opts, counter=words)
    assert len(chunks) == 3
    assert all(c.tokens <= 20 and "split" in c.kinds and "forced" not in c.kinds for c in chunks)
    long_sentence = " ".join(f"w{i}" for i in range(40)) + "."
    opts2 = sc.ChunkOptions(max_tokens=10, overlap_tokens=1, min_tokens=0)
    parts = sc.chunk_markdown(long_sentence, opts2, counter=words)
    assert len(parts) == 4
    assert all(c.tokens <= 10 and "forced" not in c.kinds for c in parts)
    assert " ".join(c.text for c in parts) == long_sentence


def test_long_rows_and_code_lines_are_forced_apart() -> None:
    opts = sc.ChunkOptions(max_tokens=20, overlap_tokens=2, min_tokens=0)
    table = "| a | b |\n| - | - |\n| " + "x" * 200 + " | y |"
    code = "```\n" + "z" * 200 + "\n```"
    for md in (table, code):
        chunks = sc.chunk_markdown(md, opts)
        assert chunks
        assert all(c.tokens <= 20 for c in chunks)
        assert all("forced" in c.kinds for c in chunks)


def test_trailing_small_chunk_merges_when_it_fits() -> None:
    calls: list[int] = []

    def counter(text: str) -> int:
        if text == "aaa\n\nbbb":
            calls.append(1)
            return 11 if len(calls) == 1 else 7
        return 3

    opts = sc.ChunkOptions(max_tokens=10, overlap_tokens=0, min_tokens=5)
    chunks = sc.chunk_markdown("aaa\n\nbbb", opts, counter=counter)
    assert [c.text for c in chunks] == ["aaa\n\nbbb"]
    assert chunks[0].tokens == 7


def test_logging_is_not_configured() -> None:
    log = logging.getLogger("smart_chunker._chunker")
    assert any(isinstance(h, logging.NullHandler) for h in log.handlers)
    assert sc.__version__ == "0.1.0"
