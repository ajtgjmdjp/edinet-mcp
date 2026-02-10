# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-02-10

### Fixed
- Fix `get_filings()` returning 0 results when passed `datetime.datetime` objects instead of `datetime.date`. The `_to_date()` helper now correctly converts `datetime.datetime` to `datetime.date` by checking for the more specific type first.

### Documentation
- Add `Filing` object attribute reference to README (all 10 attributes documented with examples)
- Add example of accessing `Filing` attributes (`description`, `filing_date`, `doc_id`, etc.)
- Clarify `get_financial_statements()` usage patterns (by `edinet_code` + `period`, not by `doc_id`)

## [0.1.1] - 2026-02-08

### Fixed
- Validate ZIP magic bytes on downloaded and cached EDINET API responses. Previously, EDINET HTTP 200 responses containing JSON error bodies (e.g. 401 "Access denied") were cached as `.zip` files, causing persistent "File is not a zip file" errors.
- `EdinetAPIError` exception raised with clear message when EDINET returns a non-ZIP response.

### Added
- `EdinetAPIError` exception class exported from the package.

## [0.1.0] - 2026-02-08

### Added
- `EdinetClient` for EDINET API v2 access (company search, filings, financial statements)
- `XBRLParser` with dual TSV/XBRL extraction paths
- FastMCP server with 4 tools (search, filings, statements, company info)
- Click CLI (`search`, `statements`, `serve`)
- Disk cache with owner-only file permissions
- Rate limiter (sync + async)
- J-GAAP / IFRS / US-GAAP detection
- Polars and pandas DataFrame export

### Known Limitations
- XBRL parsing uses first-match strategy per statement type; data split across multiple XBRL instance files within a single filing may be incomplete
- MCP server tools use synchronous I/O internally (acceptable for single-user, rate-limited usage)
