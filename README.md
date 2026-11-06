# smart-chunker

[![PyPI version](https://img.shields.io/pypi/v/trysac-smart-chunker)](https://pypi.org/project/trysac-smart-chunker/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-smart-chunker)](LICENSE)
[![CI](https://github.com/Trysac/u014-smart-chunker/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u014-smart-chunker/actions/workflows/ci.yml)

Split CommonMark and GFM Markdown into retrieval chunks along headings, tables and code fences under a token budget, with sentence overlap and line-range metadata.

## Problem

Fixed-size character splitting cuts tables in half, separates code from its explanation and loses which section a chunk came from, which hurts retrieval quality and makes citations impossible to trace back to lines. This library parses Markdown into blocks with a CommonMark-compatible line parser and packs them into chunks under a token budget, keeping structure intact and recording heading paths and exact line ranges.

## Install

```sh
pip install trysac-smart-chunker
# or
uv add trysac-smart-chunker
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
from smart_chunker import ChunkOptions, chunk_markdown

doc = "# Guide\n\nIntro text.\n\n## Setup\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"
opts = ChunkOptions(max_tokens=64, overlap_tokens=8, min_tokens=0)
for chunk in chunk_markdown(doc, opts):
    print(chunk.index, chunk.heading_path, chunk.start_line, chunk.end_line)
```

## API

- `chunk_markdown(markdown, options=ChunkOptions(), *, counter=default_token_counter) -> list[Chunk]`
- `parse_blocks(markdown) -> list[Block]`: top-level blocks with 1-based inclusive line ranges.
- `default_token_counter(text) -> int`: approximate count, `ceil(len(text) / 4)`. Any `Callable[[str], int]` may be passed; it must return a non-bool int >= 0.
- `ChunkOptions(max_tokens=512, overlap_tokens=64, min_tokens=32, respect_headings_level=2, max_chars=10_000_000)`: frozen and validated on construction. `min_tokens` lets a trailing chunk below it merge into the previous chunk of the same section when the result fits.
- `Chunk` fields: `text`, `index`, `heading_path`, `start_line`, `end_line`, `tokens`, `sha256` (UTF-8 of the final text), `kinds`, `overlap_chars`.
- `Block` fields: `kind` (`heading`, `paragraph`, `list`, `code`, `table`, `blockquote`, `hr`), `text`, `level`, `start_line`, `end_line`.

Errors: `ChunkerError(ValueError)` with `code` set to `invalid_options`, `input_too_large` or `invalid_counter`.

Limits: input above `max_chars` is rejected; nested containers stay inside their outer block; a table or code line longer than the budget is cut by characters and marked `forced`; a single word longer than the budget is cut by characters.

Not supported: HTML or PDF input, semantic splitting, model tokenizers.

## Why not LangChain text splitters?

LangChain splitters split tables and do not provide line ranges. This library keeps tables and fenced code whole when they fit and records exact line ranges.

## Security

See [docs/SECURITY.md](docs/SECURITY.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
