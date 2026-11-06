"""Split CommonMark and GFM Markdown into retrieval chunks under a token budget."""

from __future__ import annotations

from ._chunker import (
    Block,
    Chunk,
    ChunkerError,
    ChunkOptions,
    chunk_markdown,
    default_token_counter,
    parse_blocks,
)

__all__ = [
    "Block",
    "Chunk",
    "ChunkOptions",
    "ChunkerError",
    "__version__",
    "chunk_markdown",
    "default_token_counter",
    "parse_blocks",
]

__version__ = "0.1.0"
