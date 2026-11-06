# Security notes

## Threat model

`trysac-smart-chunker` is a pure library without I/O.

Defended:

- **Untrusted input**: input is validated; non-string input and input above `max_chars` (default 10,000,000 characters) raise `ChunkerError` with codes `invalid_options` or `input_too_large`. Invalid token counters raise `invalid_counter`. The code never calls `eval`, `exec` or deserializes data.
- **Linear parsing**: the parser is line-based, without recursion, and the packer uses bounded binary searches, so hostile input is not expected to cause recursion errors.
- **Log leakage**: the library never logs input text.

Not defended:

- **Resource use within limits**: inputs up to `max_chars` are processed fully; callers must lower `max_chars` for constrained environments.
- **Custom counters**: a caller-supplied `counter` is executed as given; its cost and behaviour are the caller's responsibility.
- **Content semantics**: the library does not sanitize Markdown or HTML content; output must be escaped by the consumer if rendered.

Supply chain: no runtime dependencies; Dependabot weekly updates; actions pinned to major versions; minimal workflow permissions.

Secrets: `gitleaks` runs in the local gates and in CI; `.env` files are git-ignored.

## Publishing

Releases are published to PyPI with trusted publishing (OIDC) when available, never with a long-lived token stored in the repository.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).
