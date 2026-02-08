#!/usr/bin/env bash
# Generate a review prompt for Codex (or any LLM code reviewer).
# Usage: ./scripts/codex_review.sh > review_prompt.txt
#        Then paste into Codex / ChatGPT / Claude.

set -euo pipefail
cd "$(dirname "$0")/.."

SEPARATOR="
================================================================================
"

cat <<'REVIEW_HEADER'
# Code Review Request: edinet-mcp v0.2.0

## Project Overview
edinet-mcp is an EDINET XBRL parsing library and MCP (Model Context Protocol) server
for Japanese financial data. It normalizes XBRL filings across J-GAAP/IFRS/US-GAAP
into canonical Japanese labels and exposes 7 MCP tools for AI assistants.

## Review Scope
Please review the following for:

1. **Correctness**: Logic bugs, edge cases, off-by-one errors
2. **Security**: API key leakage, injection risks, unsafe deserialization, XXE, ZIP Slip
3. **Design**: Is the architecture clean? Are abstractions appropriate? Any over-engineering?
4. **Usability**: Can a developer (or AI agent via MCP) actually use this effectively?
5. **Performance**: Any obvious bottlenecks? Unnecessary allocations?
6. **Test coverage**: Are critical paths tested? Any missing edge cases?
7. **Python best practices**: Type annotations, Pydantic usage, error handling

## Architecture
```
EDINET API → Parser (XBRL/TSV) → Normalizer (taxonomy.yaml) → MCP Server (7 tools)
                                        ↓
                              StatementData["売上高"]
                              calculate_metrics(stmt)
                              compare_periods(stmt)
```

## Key Design Decisions
- taxonomy.yaml: Data-driven XBRL element mapping (no hardcoded element names)
- Normalization auto-applied in client.py after parsing
- StatementData supports dict-like access: stmt.income_statement["売上高"]
- raw_items preserves original XBRL data alongside normalized data
- _metrics.py uses hardcoded Japanese label strings (coupled to taxonomy.yaml labels)

## Files to Review
REVIEW_HEADER

# Source files
for f in \
    src/edinet_mcp/__init__.py \
    src/edinet_mcp/models.py \
    src/edinet_mcp/_normalize.py \
    src/edinet_mcp/_metrics.py \
    src/edinet_mcp/server.py \
    src/edinet_mcp/client.py \
    src/edinet_mcp/parser.py \
    src/edinet_mcp/_config.py \
    src/edinet_mcp/_cache.py \
    src/edinet_mcp/_rate_limiter.py \
    src/edinet_mcp/data/taxonomy.yaml \
    pyproject.toml \
; do
    echo "$SEPARATOR### $f"
    echo '```'
    cat "$f"
    echo '```'
done

# Test files
for f in \
    tests/test_normalize.py \
    tests/test_metrics.py \
    tests/test_models.py \
    tests/test_client.py \
    tests/test_parser.py \
; do
    echo "$SEPARATOR### $f (test)"
    echo '```'
    cat "$f"
    echo '```'
done

cat <<'REVIEW_FOOTER'

================================================================================
## Review Questions

Please specifically address:

1. Is there any risk of API key leakage in error messages, logs, or cached data?
2. Are the XML/XBRL parsers safe against XXE and billion laughs attacks?
3. Does the ZIP extraction properly prevent path traversal (ZIP Slip)?
4. Is the normalization layer robust against unexpected XBRL data formats?
5. Are the financial metric calculations correct (ROE, ROA, margins)?
6. Is the MCP tool interface well-designed for AI agent consumption?
7. Are there any missing tests for critical code paths?
8. Is the dependency list appropriate (any unnecessary or risky deps)?
9. Is the taxonomy.yaml comprehensive enough for real EDINET data?
10. Any suggestions for improving the library API or MCP tool design?

Please provide your review as a structured report with severity levels
(Critical / High / Medium / Low / Note) for each finding.
REVIEW_FOOTER
