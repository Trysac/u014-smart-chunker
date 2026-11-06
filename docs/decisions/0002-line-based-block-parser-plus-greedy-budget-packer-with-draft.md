# Line-based block parser plus greedy budget packer with draft chunks

Status: accepted (generated, pending human review)

## Context

Fixed-size splitting breaks tables and code and loses section and line provenance. The library needs structure-aware chunks under a token budget, with a linear parser, no dependencies and a caller-supplied token counter.

## Decision

Parse normalized LF lines in a single linear pass into top-level blocks (no recursion, nested containers stay inside their outer block). Pack blocks greedily into mutable internal drafts and always measure the exact final text, including overlap prefix and fence lines, with the caller's counter, which is validated on every call. Oversized blocks are cut into units (lines for code and tables, sentences then words then character segments for text), and the largest fitting run is found by binary search. Headings trail-carry into the next chunk so a chunk does not end with a heading. Overlap is built from whole trailing sentences of the previous paragraph or list within the same section. A final pass merges a small trailing chunk of a section into its predecessor when the result fits. One ChunkerError base class carries stable codes.

## Consequences

Chunks keep structure and exact line ranges, and unsplit chunks are verbatim source slices. The token budget holds for any counter that is roughly monotone. Costs are one counter call per candidate, so very large chunks cost quadratic counter time, and a trailing heading at end of document or a heading larger than the budget cannot be honoured. Nested Markdown containers are not parsed.
