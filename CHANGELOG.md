# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] - 2026-02-11

### Added
- **Comprehensive normalization**: Expanded from 73 to 140 financial line items (PL: 35, BS: 72, CF: 33)
  - SGA expense breakdown (personnel, advertising, rent, utilities, etc.)
  - Inventory details (merchandise, products, work-in-progress, raw materials, supplies)
  - PPE breakdown (buildings, structures, machinery, vehicles, tools, land, construction in progress)
  - Intangible assets (software, patents, trademarks)
  - AOCI components (unrealized gains/losses on securities, foreign currency translation, pension adjustments)
  - M&A related items (acquisition/disposal of subsidiary shares)
- **Expanded financial metrics**: Increased from 13 to 26 indicators across 6 categories
  - Efficiency metrics (5): Asset turnover ratios
  - Growth metrics (3): Year-over-year growth rates
  - Enhanced cash flow metrics (6): Operating CF, Free CF, and CF margins
  - Additional stability metrics: Quick ratio, debt ratio, fixed ratio, fixed long-term suitability ratio
- **Comprehensive validation system**
  - Input validation: EDINET code format (`^E\d{5}$`), period format (`^\d{4}$`), document ID validation
  - Data consistency checks: Balance sheet equation, P&L consistency, abnormal value detection
  - Automatic validation on `get_financial_statements()` with `FinancialDataWarning` for quality issues
- **Type safety improvements**
  - Added `Literal` types: `PeriodLabel`, `StatementType`, `MetricCategory`
  - Added `TypedDict` classes for all metric outputs: `ProfitabilityMetrics`, `StabilityMetrics`, `EfficiencyMetrics`, `GrowthMetrics`, `CashFlowMetrics`, `RawValues`

### Security
- API key sanitization in HTTP error messages (prevents accidental key leakage in logs)
- XXE attack protection via `defusedxml` for XBRL parsing (replaces `xml.etree.ElementTree`)
- ZIP bomb and path traversal prevention with strict file count/size limits and containment checks
- Input format validation to prevent injection attacks

### Changed
- All tests passing (115 total, +23 validation tests)

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
