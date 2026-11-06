# smart-chunker

[![PyPI version](https://img.shields.io/pypi/v/trysac-smart-chunker)](https://pypi.org/project/trysac-smart-chunker/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-smart-chunker)](LICENSE)
[![CI](https://github.com/Trysac/u014-smart-chunker/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u014-smart-chunker/actions/workflows/ci.yml)

Split CommonMark and GFM Markdown into retrieval chunks along headings, tables and code fences under a token budget, with sentence overlap and line-range metadata

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-smart-chunker
# or
uv add trysac-smart-chunker
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import smart_chunker

# normalize() trims surrounding whitespace and lower-cases the text.
print(smart_chunker.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    smart_chunker.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
