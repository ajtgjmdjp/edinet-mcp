# edinet-mcp

EDINET XBRL parsing library and MCP server for Japanese financial data.

[![PyPI](https://img.shields.io/pypi/v/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![CI](https://github.com/ajtgjmdjp/edinet-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ajtgjmdjp/edinet-mcp/actions/workflows/ci.yml)
[![Downloads](https://img.shields.io/pypi/dm/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![ClawHub](https://img.shields.io/badge/ClawHub-edinet--mcp-orange)](https://clawhub.com/skills/edinet-mcp)

📝 [日本語チュートリアル: Claude に聞くだけで上場企業の決算がわかる (Zenn)](https://zenn.dev/ajtgjmdjp/articles/edinet-mcp-claude-desktop)

Part of the [Japan Finance Data Stack](https://github.com/ajtgjmdjp/awesome-japan-finance-data): **edinet-mcp** (securities filings) | [tdnet-disclosure-mcp](https://github.com/ajtgjmdjp/tdnet-disclosure-mcp) (timely disclosures) | [estat-mcp](https://github.com/ajtgjmdjp/estat-mcp) (government statistics) | [boj-mcp](https://github.com/ajtgjmdjp/boj-mcp) (Bank of Japan) | [stockprice-mcp](https://github.com/ajtgjmdjp/stockprice-mcp) (stock prices & FX)

> Building a high-throughput pipeline, batch-parsing thousands of filings, or
> need SEC EDGAR coverage too? See [xbrl-facts](https://github.com/ajtgjmdjp/xbrl-facts)
> — a Rust iXBRL engine for SEC + EDINET with byte-range provenance.

## What is this?

**edinet-mcp** provides programmatic access to Japan's [EDINET](https://disclosure.edinet-fsa.go.jp/) financial disclosure system. It normalizes XBRL filings across accounting standards (J-GAAP / IFRS / US-GAAP) into canonical Japanese labels and exposes them as an [MCP](https://modelcontextprotocol.io/) server for AI assistants.

- Search 5,000+ listed Japanese companies
- Retrieve annual/quarterly/semiannual reports (有価証券報告書, 四半期報告書, 半期報告書) plus extraordinary (臨時報告書) and large shareholding (大量保有報告書) filings
- **Automatic normalization**: `stmt["売上高"]` works regardless of accounting standard
- Financial metrics (ROE, ROA, profit margins) and year-over-year comparisons
- Parse XBRL into Polars/pandas DataFrames (BS, PL, CF)
- **Multi-company screening**: Compare financial metrics across up to 20 companies
- **Cross-period diff (xbrl-diff)**: Compare financial statements across periods with change amounts (増減額) and growth rates (増減率)
- MCP server with 9 tools for Claude Desktop and other AI tools

## Quick Start

### Installation

```bash
pip install edinet-mcp
# or
uv add edinet-mcp
# or with Docker
docker run -e EDINET_API_KEY=your_key ghcr.io/ajtgjmdjp/edinet-mcp serve
```

### Get an API Key

Register (free) at [EDINET](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html) and set:

```bash
export EDINET_API_KEY=your_key_here
```

### 30-Second Example

```python
import asyncio
from edinet_mcp import EdinetClient

async def main():
    async with EdinetClient() as client:
        # Search for Toyota
        companies = await client.search_companies("トヨタ")
        print(companies[0].name, companies[0].edinet_code)
        # トヨタ自動車株式会社 E02144

        # Get normalized financial statements
        stmt = await client.get_financial_statements("E02144", period="2025")

        # Dict-like access — works for J-GAAP, IFRS, and US-GAAP
        revenue = stmt.income_statement["売上高"]
        print(revenue)  # {"当期": 45095325000000, "前期": 37154298000000}

        # See all available line items
        print(stmt.income_statement.labels)
        # ["売上高", "売上原価", "売上総利益", "営業利益", ...]

        # Export as DataFrame
        print(stmt.income_statement.to_polars())

asyncio.run(main())
```

### Financial Metrics

```python
import asyncio
from edinet_mcp import EdinetClient, calculate_metrics

async def main():
    async with EdinetClient() as client:
        stmt = await client.get_financial_statements("E02144", period="2025")
        metrics = calculate_metrics(stmt)
        print(metrics["profitability"])
        # {"売上総利益率": "25.30%", "営業利益率": "11.87%", "ROE": "12.50%", ...}

asyncio.run(main())
```

### Multi-Company Screening

```python
import asyncio
from edinet_mcp import EdinetClient, screen_companies

async def main():
    async with EdinetClient() as client:
        result = await screen_companies(
            client,
            ["E02144", "E01777", "E01967"],  # Toyota, Sony, Keyence
            period="2025",
            sort_by="営業利益率",  # Sort by operating margin
        )
        for r in result["results"]:
            print(f"{r['company_name']}: {r['profitability']['営業利益率']}")
        # 株式会社キーエンス: 51.91%
        # ソニーグループ株式会社: 11.69%
        # トヨタ自動車株式会社: 9.98%

asyncio.run(main())
```

### Cross-Period Diff

```python
import asyncio
from edinet_mcp import EdinetClient, diff_statements

async def main():
    async with EdinetClient() as client:
        result = await diff_statements(
            client, "E02144",
            period1="2024", period2="2025",
        )
        for d in result["diffs"][:5]:
            print(f"{d['科目']}: {d['増減額']:+,.0f} ({d['増減率']})")
        # 売上高: +7,941,027,000,000 (+21.38%)
        # 営業利益: +1,204,832,000,000 (+28.44%)
        # ...

asyncio.run(main())
```

## MCP Server

Add to your AI tool's MCP config:

<details>
<summary><b>Claude Desktop</b> (~⁠/Library/Application Support/Claude/claude_desktop_config.json)</summary>

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
</details>

<details>
<summary><b>Cursor</b> (~⁠/.cursor/mcp.json)</summary>

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
</details>

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add edinet -- uvx edinet-mcp serve
# Then set EDINET_API_KEY in your environment
```
</details>

Then ask your AI: "トヨタの最新の営業利益を教えて"

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `search_companies` | 企業名・証券コード・EDINETコードで検索 |
| `get_filings` | 指定期間の開示書類一覧を取得 |
| `get_financial_statements` | 正規化された財務諸表 (BS/PL/CF) を取得 |
| `get_financial_metrics` | ROE・ROA・利益率等の財務指標を計算 |
| `compare_financial_periods` | 前年比較（増減額・増減率） |
| `screen_companies` | 複数企業の財務指標を一括比較（最大20社） |
| `list_available_labels` | 取得可能な財務科目の一覧 |
| `get_company_info` | 企業の詳細情報を取得 |
| `diff_financial_statements` | 2期間の財務諸表を比較（増減額・増減率） |

> **Note**: The `period` parameter is the **filing year**, not the fiscal year. Japanese companies with a March fiscal year-end file annual reports in June of the following year (e.g., FY2024 → filed 2025 → `period="2025"`).

## CLI

```bash
# Search companies
edinet-mcp search トヨタ

# Fetch income statement
edinet-mcp statements -c E02144 -p 2024

# Screen multiple companies
edinet-mcp screen E02144 E01777 E02529 --sort-by ROE

# Compare across periods (xbrl-diff)
edinet-mcp diff -c E02144 -p1 2023 -p2 2024

# Start MCP server
edinet-mcp serve
```

## API Reference

### `EdinetClient`

All client methods are async. Use `async with` for proper resource cleanup:

```python
import asyncio
from edinet_mcp import EdinetClient

async def main():
    async with EdinetClient(
        api_key="...",        # or EDINET_API_KEY env var
        cache_dir="~/.cache/edinet-mcp",
        rate_limit=0.5,       # requests per second
        max_retries=3,        # retry on 429/5xx with exponential backoff
    ) as client:
        # Search
        companies: list[Company] = await client.search_companies("query")
        company: Company = await client.get_company("E02144")

        # Filings
        filings: list[Filing] = await client.get_filings(
            start_date="2024-01-01",
            edinet_code="E02144",
            doc_type="annual_report",
        )

        # Financial statements (by edinet_code + period)
        stmt: FinancialStatement = await client.get_financial_statements(
            edinet_code="E02144",
            period="2024",  # Filing year (not fiscal year)
        )

        # Or get the most recent filing (within past 365 days)
        stmt = await client.get_financial_statements(edinet_code="E02144")

        df = stmt.income_statement.to_polars()  # Polars DataFrame
        df = stmt.income_statement.to_pandas()  # pandas DataFrame (optional dep)

asyncio.run(main())
```

### `Filing`

Filing objects returned by `get_filings()` have the following attributes:

```python
for filing in filings:
    print(filing.description)    # "有価証券報告書－第121期(...)"
    print(filing.filing_date)    # datetime.date(2025, 6, 18)
    print(filing.doc_id)         # "S100VWVY"
    print(filing.company_name)   # "トヨタ自動車株式会社"
    print(filing.period_start)   # datetime.date(2024, 4, 1)
    print(filing.period_end)     # datetime.date(2025, 3, 31)
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

### Normalization

edinet-mcp automatically normalizes XBRL element names across accounting standards:

| Accounting Standard | XBRL Element | Normalized Label |
|---|---|---|
| J-GAAP | `NetSales` | 売上高 |
| IFRS | `Revenue`, `SalesRevenuesIFRS` | 売上高 |
| US-GAAP | `Revenues` | 売上高 |

Mappings are defined in [`taxonomy.yaml`](src/edinet_mcp/data/taxonomy.yaml) — 161 items covering PL (42), BS (79), and CF (40), with IFRS/US-GAAP element variants automatically resolved via suffix stripping. Add new mappings by editing the YAML file, no code changes needed.

```python
from edinet_mcp import get_taxonomy_labels

# Discover available labels
labels = get_taxonomy_labels("income_statement")
# [{"id": "revenue", "label": "売上高", "label_en": "Revenue"}, ...]
```

### EDINET Suffix Stripping

EDINET appends accounting-standard and section-specific suffixes to XBRL element names (e.g., `TotalAssetsIFRSSummaryOfBusinessResults`). These are automatically stripped to match canonical taxonomy entries. Non-consolidated (単体) contexts are filtered out to prefer consolidated figures.

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
uv run pytest -v           # 213 tests
uv run ruff check src/
```

## Data Attribution

This project uses data from [EDINET](https://disclosure.edinet-fsa.go.jp/)
(Electronic Disclosure for Investors' NETwork), operated by the
Financial Services Agency of Japan (金融庁).
EDINET data is provided under the [Public Data License 1.0](https://www.digital.go.jp/resources/open_data/).

## Related Projects

**Japan Finance Data Stack** (by same author):
- [tdnet-disclosure-mcp](https://github.com/ajtgjmdjp/tdnet-disclosure-mcp) — TDNET timely disclosures (適時開示)
- [estat-mcp](https://github.com/ajtgjmdjp/estat-mcp) — Government statistics (e-Stat)
- [boj-mcp](https://github.com/ajtgjmdjp/boj-mcp) — Bank of Japan statistics
- [stockprice-mcp](https://github.com/ajtgjmdjp/stockprice-mcp) — Stock prices & FX rates (yfinance)
- [jfinqa](https://github.com/ajtgjmdjp/jfinqa) — Japanese financial QA benchmark

**Community**:
- [edinet2dataset](https://github.com/SakanaAI/edinet2dataset) — Sakana AI's EDINET XBRL→JSON tool
- [EDINET-Bench](https://github.com/SakanaAI/EDINET-Bench) — Financial classification benchmark

## License

Apache-2.0. See [NOTICE](NOTICE) for third-party attributions.

<!-- mcp-name: io.github.ajtgjmdjp/edinet-mcp -->
