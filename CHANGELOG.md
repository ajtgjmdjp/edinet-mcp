# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.2] - 2026-07-20

Performance release for the period-omitted "latest filing" path — the first
path new users touch. Design reviewed with gpt-5.3-codex
(thread 019f700e-3f16-7c33-8440-b8f3b13b05a4).

### Changed
- **Fiscal-year-end heuristic**: the EDINET code list's 決算日 column is now
  parsed into `Company.fiscal_year_end` (companies cache schema v4). With
  `period` omitted, annual-report resolution probes the company's statutory
  filing-deadline month (決算月+3, then +2) before the backwards scan —
  cold lookups drop to ~1 month window (~60s at the default rate limit)
  regardless of fiscal calendar, verified end-to-end against the live API.
  Probes are restricted to the current filing cycle: per review, accepting
  a previous-year window could shadow a newer off-window filing, so prior
  cycles are always reached via the reverse-chronological scan instead.
- **Tiered filings-cache TTL**: per-date lists age from 24h (last 7 days)
  to 7 days (≤90 days) to 60 days (older), making repeated scans
  effectively instant. Bounded TTLs were chosen over permanent caching
  because list rows are not strictly immutable (withdrawals/metadata
  edits) and a permanently cached empty anomaly would never heal.
- Any code-list lookup failure silently degrades to the plain scan —
  malformed 決算日 data can never break filing resolution.

## [0.8.1] - 2026-07-17

Correctness release from a whole-codebase review (self-review + gpt-5.3-codex,
thread 019f700e-3f16-7c33-8440-b8f3b13b05a4). No new features.

### Fixed
- **P0 — period-omitted retrieval always failed**: `get_financial_statements`
  / `get_narrative` / screening with `period=None` built a 730-day search
  range that `get_filings` itself rejects (366-day limit), so every
  documented "latest filing" call raised immediately. The search now scans
  backwards month-by-month (~2 years) and stops at the first hit, which is
  also far cheaper than a full-range scan.
- **XBRL facts are now routed by taxonomy membership, not name keywords**:
  `CashAndDeposits` went to cash flow (contains "cash") and
  `TradeReceivables` was dropped entirely; real filings were missing
  balance-sheet rows. Facts from all instance files are pooled before
  categorizing (was first-file-wins), and a missing cash-flow statement now
  triggers the XBRL fallback too. Keyword routing remains only as a
  fallback for extension elements.
- **EDINET availability flags parsed correctly**: the API sends
  `"0"`/`"1"` strings; `bool("0")` is `True`, so `has_xbrl`/`has_pdf`/
  `has_csv` were always reported as available.
- **Screening**: companies missing the sort metric appeared first (not
  last) under the default descending sort; `EdinetAPIError` from a single
  company aborted the whole screening call instead of landing in `errors`.
- **Growth rates use `abs(prior)` denominators**: an operating loss
  improving from -100 to -50 reported -50% growth; now +50%, consistent
  with `compare_periods` and the diff module.
- **Diff**: row order was nondeterministic (set iteration) although the
  MCP tool truncates to 50 rows; summaries counted added/removed rows as
  "unchanged". Order now follows the newer period's display order and the
  summary reports `added` / `removed` separately.
- **Disk cache hardening**: atomic writes (same-directory temp file +
  fsync + `os.replace`, `O_EXCL|O_NOFOLLOW` so planted symlinks are never
  followed); corrupt JSON entries are treated as a miss and deleted; cache
  keys now include the API `base_url` so staging/test responses can never
  be served against production.
- **Balance-sheet validation tolerance fixed**: values on the XBRL path
  are raw JPY, so the documented ¥1M tolerance was actually ¥1,000.

### Documentation
- Parser docs no longer claim production ZIPs contain TSVs; CLI `--period`
  is described as the filing year; `get_filings` no longer suggests
  passing `doc_id` to `get_financial_statements`; README removes the
  unsupported `max_retries` parameter; metric units documented as raw JPY
  and ratio bases documented as ending-balance approximations.

### Deferred to v0.9 (known limitations)
- Dimensional contexts (e.g. business segments) can still overwrite
  consolidated totals in normalization (last-write-wins) — the v0.9
  segment work will make normalization context/dimension-aware.
- The XBRL fallback does not populate the `summary` statement.

## [0.8.0] - 2026-07-17

### Added
- **Qualitative narrative extraction (`get_narrative`)**: 事業等のリスク
  (`business_risks`), MD&A (`mdna`), 経営方針 (`business_policy`), 事業の内容
  (`description_of_business`), コーポレート・ガバナンスの概要
  (`corporate_governance`), and 研究開発活動 (`research_and_development`) are
  extracted from the annual report XBRL instance as plain text. Available as
  `EdinetClient.get_narrative()` (returns `NarrativeSection` with context/doc
  provenance) and a paged MCP tool (`max_chars`/`offset`, `next_offset` for
  continuation). Annual reports (有価証券報告書) only in this release.
- New `_narrative` module with semantic XBRL context selection (prefers
  dimensionless, current-period contexts; deterministic tie-breaks) and an
  HTML→text converter that preserves headings, paragraphs, lists, table rows,
  and image alt text while dropping styles/scripts. Design reviewed with
  gpt-5.3-codex (thread 019f6fe5-af9d-7f01-b25f-8b6122615b85): HTML is taken
  directly from the XML parser without a second `html.unescape()` pass, so
  double-escaped literals survive intact.
- `EdinetClient._resolve_filing()` — filing resolution shared by statements
  and narratives instead of duplicated logic.

### Fixed (post-review hardening, gpt-5.3-codex code review of b35975b)
- Instance files are size-checked (50 MB, same as the parser) before DOM
  parsing instead of relying only on the post-conversion character cap.
- Context ranking now puts period semantics before dimensions and only
  treats `instant == filing_date` as the filing-date context, so a
  prior-year instant or a dimensionless prior-year duration can no longer
  outrank the current period. Empty-normalizing candidates fall back to the
  next-ranked one, and alias order in `NARRATIVE_SECTIONS` is honored.
- Table cells containing block elements (`<td><p>A</p></td>`) are buffered
  per cell and tab-joined instead of splitting into separate lines.
- Extracted narratives are cached per `(doc_id, section)` (bounded, 64
  entries) so MCP paging does not re-download/re-parse per page; an invalid
  XBRL instance no longer masks a valid sibling instance.
- The 1M-character defensive cap is reported as `source_truncated` on
  `NarrativeSection` and in the MCP response instead of silently lying in
  `total_chars`.

## [0.7.0] - 2026-07-17

### Added
- **Bilingual (English/Japanese) line item access**: `stmt.income_statement["Revenue"]`
  now works alongside `stmt.income_statement["売上高"]` (case-insensitive), backed by
  the `label_en` fields already present in the taxonomy. New `StatementData.labels_en`
  property lists English labels, using statement-scoped translations so labels that
  appear in both PL and CF (e.g. 減損損失 → "Impairment Loss" vs "Impairment Loss (CF)")
  resolve correctly.
- **`language='en'` option on the `get_financial_statements` MCP tool**: renders
  normalized rows with English keys and line item names —
  `{"label": "Revenue", "current": ..., "prior": ...}` instead of
  `{"科目": "売上高", "当期": ..., "前期": ...}`. Default output is unchanged.
- `get_label_aliases()` helper in `_normalize` exposing cached EN↔JA label maps,
  globally or scoped per statement type.
- **All supported `doc_type` values are now documented in the MCP tool
  descriptions and README**: `semiannual_report` (半期報告書, code 160),
  `extraordinary_report` (臨時報告書, code 180), and `large_shareholding`
  (大量保有報告書, code 350) join `annual_report` / `quarterly_report`, with
  tests locking the label → docTypeCode mapping. Contributed by @hjjkkl (#6).

## [0.6.6] - 2026-07-03

### Fixed
- **Filing-list cache no longer poisoned by rows without `docID`**: rows lacking
  `docID` are filtered before being cached (and defensively on cache reads), so a
  single malformed API row can no longer cause repeated `KeyError` failures for a
  cached date until TTL expiry.
- **Financial metrics treat `0` as a valid value, not as missing**: ROA no longer
  silently substitutes operating income when ordinary income is exactly `0`, and
  ROE no longer falls back when net income or shareholders' equity is `0`.
  Loss-year ratios are now computed correctly.

### Changed
- **Library modules now use stdlib `logging` instead of loguru**: importing
  `edinet_mcp` no longer emits log output to stderr. A `NullHandler` is attached
  to the `edinet_mcp` logger per library best practice; applications can opt in
  via standard `logging` configuration. The CLI keeps its loguru-formatted
  stderr output (stdlib records are routed through it), and stdout stays clean
  for JSON consumers.
- Retry exhaustion in the HTTP client now raises a clear `RuntimeError` instead
  of relying on a type-ignored re-raise.

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
