# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.3] - 2026-07-28

### Changed
- Published the retirement maintenance notice to PyPI. Public hosted access
  retired July 28, 2026; this SDK remains available for Ryan McMillan's private
  deployment and as a verifiable engineering artifact. Package metadata points
  to the canonical case study and no longer presents Delega as a generally
  available hosted service.

## [0.6.2] - 2026-07-22

### Security
- The shared path-segment encoder now rejects empty, `.` and `..` identifiers,
  preventing URL normalization from changing the intended API route.

## [0.6.1] - 2026-07-22

### Security
- All URL path parameters (task, agent, recurrence, link, and webhook IDs) are
  now percent-encoded before the request path is built, so an untrusted ID
  containing `/`, `?`, `#`, or `..` can no longer manipulate the request path
  or query. This matches the MCP client's handling.
- `verify_webhook` now rejects timestamps dated meaningfully in the future (the
  previous symmetric tolerance window accepted timestamps up to the full
  tolerance ahead), and compares the signature hex case-insensitively so a
  valid uppercase-hex signature is no longer falsely rejected.

### Fixed
- `__version__` now matches the packaged version, so the `User-Agent` header
  reports the correct SDK version.
