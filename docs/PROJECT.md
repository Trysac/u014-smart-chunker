# Project record

## Objective

Split CommonMark and GFM Markdown into retrieval chunks along headings, tables and code fences under a token budget, with sentence overlap and line-range metadata. Fixed-size splitting cuts tables, separates code from its explanation and loses section and line provenance; this library keeps structure intact and records heading paths and exact line ranges.

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: HTML or PDF input, semantic splitting, model tokenizers, nested container splitting, and anything that needs runtime dependencies or I/O without an accepted ADR.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 157666 / 334096 |
| Hours (human) | pending measurement |
| Cost (USD) | 1.7382 |

## Factory run u014 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2374 | 128000 | 0 | 4246 | 0.6428 |
| generation | claude-sonnet-5-5 | yes | 2374 | 128000 | 0 | 4246 | 0.6428 |
| generation | claude-sonnet-5-5 | yes | 2374 | 74260 | 0 | 4246 | 0.3741 |
| docs | claude-haiku-5-5 | no | 137806 | 3836 | 0 | 0 | 0.0785 |

Total: $1.7382. Prices: Anthropic list prices.
