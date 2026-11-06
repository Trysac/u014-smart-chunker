"""Behavior tests for the public API of smart_chunker."""

from __future__ import annotations

import pytest

import smart_chunker


def test_normalize_trims_and_lowercases() -> None:
    assert smart_chunker.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        smart_chunker.normalize(value)


def test_version_is_semver() -> None:
    parts = smart_chunker.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
