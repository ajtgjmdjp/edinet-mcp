# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.5] - 2026-04-21

### Security
- **XBRL parser hardening**: `defusedxml.common.DefusedXmlException` subclasses (`EntitiesForbidden`, `DTDForbidden`, `ExternalReferenceForbidden`, `NotSupportedError`) raised during XBRL parsing are now caught alongside `xml.etree.ElementTree.ParseError`. Previously, a single hostile XBRL instance inside a filing ZIP (billion-laughs, XXE, external DTD, etc.) would surface an uncaught exception and abort parsing of every remaining sibling instance. The parser now logs the rejection with the exception class name and continues with the next file, returning empty facts for the rejected instance.

### Added
- **Python 3.13 support**: Added `Programming Language :: Python :: 3.13` trove classifier and `"3.13"` to the CI test matrix.

## [0.6.4] - 2026-04-20

### Added
- **Library-safe logging**: `edinet_mcp` attaches a `NullHandler` at import time so consumers see no log output unless they configure handlers themselves (PEP 282).

### Security
- **Trusted publishing**: PyPI releases now use GitHub OIDC (no long-lived API tokens).
- **Supply-chain hardening**: GitHub Actions pinned by commit SHA and workflow `permissions:` set to least-privilege; Dependabot enabled for Action SHA updates.

## [0.6.3] - 2026-03-02

### Added
- **`Company.sec_code` and `Company.corporate_number`**: 5-digit securities code and 13-digit 法人番号 extracted from EDINET CSV. Both are `Optional[str]` for backward compatibility.

### Changed
- Company-list cache version bumped to `v3`; stale entries from older releases are invalidated on first use.

## [0.6.2] - 2026-02-15

### Changed
- **Default filing-search window extended from 365 → 730 days**: annual reports filed more than 6 months ago are now discovered when `period` is omitted from `get_filings()`.

## [0.6.1] - 2026-02-15

### Fixed
- **MCP `period` parameter accepts `int`**: Claude Desktop (and other MCP clients) may send `period` as an integer. A Pydantic `BeforeValidator` now coerces `int` → `str` before validation so previously-rejected calls succeed.

## [0.6.0] - 2026-02-15

### Added
- **CLI `diff` command**: `edinet-mcp diff -c E02144 -p1 2023 -p2 2024` performs cross-period financial-statement comparison from the command line.
- **Public diff API**: `diff_statements`, `DiffResult`, and `LineItemDiff` are now exported from the top-level `edinet_mcp` package.

## [0.5.0] - 2026-02-14

### Added
- **Multi-company screening**: `screen_companies()` function and MCP tool for comparing financial metrics across up to 20 companies in a single call
  - Sort results by any metric (ROE, 営業利益率, etc.)
  - Error-tolerant batch processing (partial results on individual failures)
- **Client batch helper**: `EdinetClient.get_financial_metrics_batch()` for fetching statements for multiple companies
- 13 new tests for screening feature (8 unit + 5 MCP tool)

## [0.4.2] - 2026-02-13

### Security
- Exclude `.env`, `.tokens`, and other secrets from sdist/wheel builds via `pyproject.toml` `[tool.hatch.build.targets.sdist]` exclude patterns
- Add CI `sdist-audit` job to prevent accidental secret leaks in published packages

### Fixed
- Type safety improvements for MCP tool input validation

## [0.4.0] - 2026-02-12

### Changed
- **Native async migration**: Replaced `asyncio.to_thread()` with `httpx.AsyncClient` for all HTTP calls
  - Removes threading overhead and enables true async I/O
  - All 179 tests passing

### Removed
- `httpx` synchronous client usage (now fully async)

## [0.3.0] - 2026-02-11

### Added
- **Production retry logic**: Automatic retry with exponential backoff on 429/5xx errors (configurable `max_retries`)
- **Cache TTL**: Company list cache expires after 30 days, filings after 24 hours
- **Expanded taxonomy**: 140 → 161 financial line items with IFRS suffix stripping
- **Date query optimization**: Narrower search windows for `get_financial_statements()`
- IFRS normalization fixes (suffix stripping for `SummaryOfBusinessResults`, `NonConsolidated` context exclusion)
- Ticker column mapping fix for company search
- 38 additional tests (141 → 179 total)

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
