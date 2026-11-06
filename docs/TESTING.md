# Testing

## Running

```sh
uv run pytest --cov=smart_chunker   # tests with coverage report
uv run python scripts/check.py      # every gate, as CI and the factory run it
```

## Policy

- Branch coverage of `src/smart_chunker` must stay at or above 80 %; the gate fails below it.
- Tests exercise the public API (`import smart_chunker`) and assert return values, raised exceptions and their codes.
- Each bug fix starts with a failing test that reproduces it.
- Tests are deterministic: no network, no wall clock, no dependence on test order.

## Layout

`tests/test_<module>.py` mirrors each public module. Shared fixtures go in `tests/conftest.py`.

Expected coverage of behaviour: token budget with custom counters, fence and table splitting, heading paths and no chunk ending in a heading, sentence overlap, CommonMark edge cases (ATX, setext, indented and fenced code, CRLF), option and counter validation, and determinism.
