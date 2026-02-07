# edinet-mcp

EDINET XBRL parsing library and MCP server for Japanese financial data.

[![PyPI](https://img.shields.io/pypi/v/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

## What is this?

**edinet-mcp** provides programmatic access to Japan's [EDINET](https://disclosure.edinet-fsa.go.jp/) financial disclosure system. It parses XBRL filings into structured DataFrames and exposes them as an [MCP](https://modelcontextprotocol.io/) server for AI assistants.

- Search 5,000+ listed Japanese companies
- Retrieve annual/quarterly financial reports (有価証券報告書, 四半期報告書)
- Parse XBRL into Polars/pandas DataFrames (BS, PL, CF)
- MCP server for Claude Desktop and other AI tools
- J-GAAP / IFRS / US-GAAP detection

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

# Get financial statements as a Polars DataFrame
stmt = client.get_financial_statements("E02144", period="2024")
print(stmt.income_statement.to_polars())
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
| `get_financial_statements` | 財務諸表 (BS/PL/CF) を構造化データで取得 |
| `get_company_info` | 企業の詳細情報を取得 |

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

# Financial statements
stmt: FinancialStatement = client.get_financial_statements(
    edinet_code="E02144",
    period="2024",
)
df = stmt.income_statement.to_polars()  # Polars DataFrame
df = stmt.income_statement.to_pandas()  # pandas DataFrame (optional dep)
```

### `StatementData`

Each financial statement (BS, PL, CF) is a `StatementData` object:

```python
stmt.balance_sheet.to_polars()    # → polars.DataFrame
stmt.balance_sheet.to_pandas()    # → pandas.DataFrame (requires pandas)
stmt.balance_sheet.to_dicts()     # → list[dict]
len(stmt.balance_sheet)           # number of line items
```

## Development

```bash
git clone https://github.com/ajtgjmdjp/edinet-mcp
cd edinet-mcp
uv sync --dev
uv run pytest -v
uv run ruff check .
uv run mypy src/
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
