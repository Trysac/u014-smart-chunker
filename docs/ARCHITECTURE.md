# Architecture

## Purpose

`trysac-smart-chunker` is a small, dependency-free Python library that splits CommonMark and GFM Markdown into retrieval chunks along headings, tables and code fences under a token budget, with sentence overlap and line-range metadata.

## Shape

```text
caller code --> smart_chunker (public API in __init__.py)
                    |
                    +-- _chunker.py: line-based block parser, then token-budget packer
```

- **Parsing**: `parse_blocks` scans lines (after LF normalization) into top-level blocks. No recursion.
- **Packing**: `chunk_markdown` places blocks into drafts under `max_tokens`, splits oversized blocks (code on lines, tables on rows, text on sentences, words, then characters), adds sentence overlap and records heading paths.
- **Public API**: the names listed in `__all__` of `src/smart_chunker/__init__.py`. Anything else is internal.
- **Errors**: invalid input raises `ChunkerError` with a stable `code`.
- **Side effects**: none beyond a module logger with a `NullHandler`; the library never configures logging and never logs input text.

## Quality contract

`scripts/check.py` is the single definition of the gates; `fabrica.json` tells the factory and CI how to run it. See [TESTING.md](TESTING.md).

## Decisions

Architecture decisions are recorded in [decisions/](decisions/) as numbered ADRs.
