# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `EdinetClient` for EDINET API v2 access (company search, filings, financial statements)
- `XBRLParser` with dual TSV/XBRL extraction paths
- FastMCP server with 4 tools (search, filings, statements, company info)
- Click CLI (`search`, `statements`, `serve`)
- Disk cache with owner-only file permissions
- Rate limiter (sync + async)
- J-GAAP / IFRS / US-GAAP detection
- Polars and pandas DataFrame export
