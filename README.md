# edinet-mcp

EDINET XBRL parsing library and MCP server for Japanese financial data.

[![PyPI](https://img.shields.io/pypi/v/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

## What is this?

**edinet-mcp** provides programmatic access to Japan's [EDINET](https://disclosure.edinet-fsa.go.jp/) financial disclosure system. It normalizes XBRL filings across accounting standards (J-GAAP / IFRS / US-GAAP) into canonical Japanese labels and exposes them as an [MCP](https://modelcontextprotocol.io/) server for AI assistants.

- Search 5,000+ listed Japanese companies
- Retrieve annual/quarterly financial reports (有価証券報告書, 四半期報告書)
- **Automatic normalization**: `stmt["売上高"]` works regardless of accounting standard
- Financial metrics (ROE, ROA, profit margins) and year-over-year comparison
- Parse XBRL into Polars/pandas DataFrames (BS, PL, CF)
- MCP server with 7 tools for Claude Desktop and other AI tools

## Quick Start

### Installation

```bash
pip install edinet-mcp
# or
uv add edinet-mcp
```

### Get an API Key

Register (free) at [EDINET](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html) and set:

```bash
export EDINET_API_KEY=your_key_here
```

### 30-Second Example

```python
from edinet_mcp import EdinetClient

client = EdinetClient()

# Search for Toyota
companies = client.search_companies("トヨタ")
print(companies[0].name, companies[0].edinet_code)
# トヨタ自動車株式会社 E02144

# Get normalized financial statements
stmt = client.get_financial_statements("E02144", period="2025")

# Dict-like access — works for J-GAAP, IFRS, and US-GAAP
revenue = stmt.income_statement["売上高"]
print(revenue)  # {"当期": 45095325000000, "前期": 37154298000000}

# See all available line items
print(stmt.income_statement.labels)
# ["売上高", "売上原価", "売上総利益", "営業利益", ...]

# Export as DataFrame
print(stmt.income_statement.to_polars())
```

### Financial Metrics

```python
from edinet_mcp import EdinetClient, calculate_metrics

client = EdinetClient()
stmt = client.get_financial_statements("E02144", period="2025")
metrics = calculate_metrics(stmt)
print(metrics["profitability"])
# {"売上総利益率": "25.30%", "営業利益率": "11.87%", "ROE": "12.50%", ...}
```

## MCP Server (for Claude Desktop)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "edinet": {
      "command": "uvx",
      "args": ["edinet-mcp", "serve"],
      "env": {
        "EDINET_API_KEY": "your_key_here"
      }
    }
  }
}
```

Then ask Claude: "トヨタの最新の営業利益を教えて"

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `search_companies` | 企業名・証券コード・EDINETコードで検索 |
| `get_filings` | 指定期間の開示書類一覧を取得 |
| `get_financial_statements` | 正規化された財務諸表 (BS/PL/CF) を取得 |
| `get_financial_metrics` | ROE・ROA・利益率等の財務指標を計算 |
| `compare_financial_periods` | 前年比較（増減額・増減率） |
| `list_available_labels` | 取得可能な財務科目の一覧 |
| `get_company_info` | 企業の詳細情報を取得 |

> **Note**: The `period` parameter is the **filing year**, not the fiscal year. Japanese companies with a March fiscal year-end file annual reports in June of the following year (e.g., FY2024 → filed 2025 → `period="2025"`).

## CLI

```bash
# Search companies
edinet-mcp search トヨタ

# Fetch income statement
edinet-mcp statements -c E02144 -p 2024

# Start MCP server
edinet-mcp serve
```

## API Reference

### `EdinetClient`

```python
client = EdinetClient(
    api_key="...",        # or EDINET_API_KEY env var
    cache_dir="~/.cache/edinet-mcp",
    rate_limit=0.5,       # requests per second
)

# Search
companies: list[Company] = client.search_companies("query")
company: Company = client.get_company("E02144")

# Filings
filings: list[Filing] = client.get_filings(
    start_date="2024-01-01",
    edinet_code="E02144",
    doc_type="annual_report",
)

# Access Filing attributes
for filing in filings:
    print(filing.description)    # "有価証券報告書－第121期(...)"
    print(filing.filing_date)    # datetime.date(2025, 6, 18)
    print(filing.doc_id)         # "S100VWVY"
    print(filing.company_name)   # "トヨタ自動車株式会社"
    print(filing.period_start)   # datetime.date(2024, 4, 1)
    print(filing.period_end)     # datetime.date(2025, 3, 31)

# Financial statements (by edinet_code + period)
stmt: FinancialStatement = client.get_financial_statements(
    edinet_code="E02144",
    period="2024",  # Filing year (not fiscal year)
)

# Or get the most recent filing (within past 365 days)
stmt = client.get_financial_statements(edinet_code="E02144")

df = stmt.income_statement.to_polars()  # Polars DataFrame
df = stmt.income_statement.to_pandas()  # pandas DataFrame (optional dep)
```

### `StatementData`

Each financial statement (BS, PL, CF) is a `StatementData` object with dict-like access:

```python
# Dict-like access by Japanese label
stmt.income_statement["売上高"]       # → {"当期": 45095325, "前期": 37154298}
stmt.income_statement.get("営業利益") # → {"当期": 5352934} or None
stmt.income_statement.labels          # → ["売上高", "営業利益", ...]

# DataFrame export
stmt.balance_sheet.to_polars()    # → polars.DataFrame
stmt.balance_sheet.to_pandas()    # → pandas.DataFrame (requires pandas)
stmt.balance_sheet.to_dicts()     # → list[dict]
len(stmt.balance_sheet)           # number of line items

# Raw XBRL data preserved
stmt.income_statement.raw_items   # original pre-normalization data
```

### `Filing`

Filing objects returned by `get_filings()` have the following attributes:

```python
filing.doc_id          # str: Document ID (e.g., "S100VWVY")
filing.edinet_code     # str: Company EDINET code (e.g., "E02144")
filing.company_name    # str: Company name
filing.description     # str: Document description (e.g., "有価証券報告書－第121期(...)")
filing.filing_date     # datetime.date: Submission date
filing.period_start    # datetime.date | None: Reporting period start
filing.period_end      # datetime.date | None: Reporting period end
filing.doc_type        # DocType: Document type enum
filing.has_xbrl        # bool: XBRL data available
filing.has_pdf         # bool: PDF available
filing.has_csv         # bool: CSV available
```

### Normalization

edinet-mcp automatically normalizes XBRL element names across accounting standards:

| Accounting Standard | XBRL Element | Normalized Label |
|---|---|---|
| J-GAAP | `NetSales` | 売上高 |
| IFRS | `Revenue` | 売上高 |
| US-GAAP | `Revenues` | 売上高 |

Mappings are defined in [`taxonomy.yaml`](src/edinet_mcp/data/taxonomy.yaml) — 140 items covering PL (35), BS (72), and CF (33). Add new mappings by editing the YAML file, no code changes needed.

```python
from edinet_mcp import get_taxonomy_labels

# Discover available labels
labels = get_taxonomy_labels("income_statement")
# [{"id": "revenue", "label": "売上高", "label_en": "Revenue"}, ...]
```

## Architecture

```
EDINET API → Parser (XBRL/TSV) → Normalizer (taxonomy.yaml) → MCP Server
                                        ↓
                              StatementData["売上高"]
                              calculate_metrics(stmt)
                              compare_periods(stmt)
```

## Development

```bash
git clone https://github.com/ajtgjmdjp/edinet-mcp
cd edinet-mcp
uv sync --extra dev
uv run pytest -v           # 85 tests
uv run ruff check src/
```

## Data Attribution

This project uses data from [EDINET](https://disclosure.edinet-fsa.go.jp/)
(Electronic Disclosure for Investors' NETwork), operated by the
Financial Services Agency of Japan (金融庁).
EDINET data is provided under the [Public Data License 1.0](https://www.digital.go.jp/resources/open_data/).

## Related Projects

- [edinet2dataset](https://github.com/SakanaAI/edinet2dataset) — Sakana AI's EDINET XBRL→JSON tool
- [EDINET-Bench](https://github.com/SakanaAI/EDINET-Bench) — Financial classification benchmark
- [jfinqa](https://github.com/ajtgjmdjp/jfinqa) — Japanese financial QA benchmark (companion project)

## License

Apache-2.0. See [NOTICE](NOTICE) for third-party attributions.
