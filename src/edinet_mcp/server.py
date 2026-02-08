"""MCP server exposing EDINET tools to LLMs via FastMCP.

This module defines the MCP (Model Context Protocol) server that allows
AI assistants like Claude to search Japanese companies, retrieve financial
filings, and parse XBRL financial statements through EDINET.

Usage with Claude Desktop (add to ``claude_desktop_config.json``)::

    {
      "mcpServers": {
        "edinet": {
          "command": "uvx",
          "args": ["edinet-mcp", "serve"]
        }
      }
    }
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from edinet_mcp._metrics import calculate_metrics, compare_periods
from edinet_mcp._normalize import get_taxonomy_labels
from edinet_mcp.client import EdinetClient

mcp = FastMCP(
    name="EDINET",
    instructions=(
        "EDINET MCP server provides tools for accessing Japanese financial "
        "disclosure data. You can search for companies listed on the Tokyo "
        "Stock Exchange, retrieve financial filings (有価証券報告書, 四半期報告書), "
        "and parse XBRL financial statements (BS, PL, CF) into structured data.\n\n"
        "All financial data comes from EDINET, the Electronic Disclosure for "
        "Investors' NETwork operated by Japan's Financial Services Agency (FSA).\n\n"
        "Key tools:\n"
        "- search_companies: Find companies by name/ticker/code\n"
        "- get_financial_statements: Get normalized BS/PL/CF data\n"
        "- get_financial_metrics: Get calculated ratios (ROE, ROA, margins)\n"
        "- compare_financial_periods: Get year-over-year changes\n"
        "- list_available_labels: See which labels are available\n\n"
        "IMPORTANT: The 'period' parameter is the FILING year, not fiscal year. "
        "Japanese companies with March fiscal year-end file annual reports in "
        "June of the following year (e.g., FY2024 → filed 2025 → period='2025')."
    ),
)

# Lazily initialized client
_client: EdinetClient | None = None


def _get_client() -> EdinetClient:
    global _client
    if _client is None:
        _client = EdinetClient()
    return _client


def _fetch_stmt(edinet_code: str, period: str | None, doc_type: str) -> Any:
    """Shared helper to fetch a financial statement."""
    client = _get_client()
    return client.get_financial_statements(
        edinet_code=edinet_code,
        doc_type=doc_type,
        period=period,
    )


@mcp.tool()
async def search_companies(
    query: Annotated[
        str,
        Field(description="企業名(日本語 or 英語)、証券コード、またはEDINETコードで検索"),
    ],
) -> list[dict[str, Any]]:
    """Search for Japanese companies registered in EDINET.

    Examples:
    - search_companies("トヨタ") → Toyota Motor Corporation
    - search_companies("7203") → Toyota (by ticker)
    - search_companies("E02144") → Toyota (by EDINET code)
    """
    client = _get_client()
    companies = client.search_companies(query)
    return [c.model_dump() for c in companies[:20]]


@mcp.tool()
async def get_filings(
    edinet_code: Annotated[
        str,
        Field(description="企業のEDINETコード (例: 'E02144')"),
    ],
    start_date: Annotated[
        str,
        Field(description="検索開始日 (YYYY-MM-DD形式)"),
    ],
    end_date: Annotated[
        str | None,
        Field(description="検索終了日 (YYYY-MM-DD形式、省略時は今日)"),
    ] = None,
    doc_type: Annotated[
        str | None,
        Field(
            description=(
                "書類タイプでフィルタ: 'annual_report' (有価証券報告書), "
                "'quarterly_report' (四半期報告書), または省略で全件"
            )
        ),
    ] = None,
) -> list[dict[str, Any]]:
    """List financial filings for a company within a date range.

    Returns filing metadata including doc_id, filing date, and document type.
    Use the doc_id with get_financial_statements to retrieve actual data.
    """
    client = _get_client()
    filings = client.get_filings(
        start_date=start_date,
        end_date=end_date,
        edinet_code=edinet_code,
        doc_type=doc_type,
    )
    return [f.model_dump(mode="json") for f in filings[:50]]


@mcp.tool()
async def get_financial_statements(
    edinet_code: Annotated[
        str,
        Field(description="企業のEDINETコード (例: 'E02144')"),
    ],
    period: Annotated[
        str | None,
        Field(
            description=(
                "書類が提出された年 (例: '2024')。"
                "3月決算企業のFY2024報告書は2025年提出のため period='2025' を指定。"
                "省略時は直近1年間の最新報告書を取得"
            )
        ),
    ] = None,
    doc_type: Annotated[
        str,
        Field(description="'annual_report' (有価証券報告書) or 'quarterly_report' (四半期報告書)"),
    ] = "annual_report",
) -> dict[str, Any]:
    """Retrieve and parse financial statements (BS, PL, CF) for a company.

    Returns normalized financial data with Japanese labels.
    Each line item has 当期 (current) and 前期 (previous) values.

    Example response:
      income_statement: [{"科目": "売上高", "当期": 45095325, "前期": 37154298}, ...]
    """
    stmt = _fetch_stmt(edinet_code, period, doc_type)
    result: dict[str, Any] = {
        "filing": stmt.filing.model_dump(mode="json"),
        "accounting_standard": stmt.accounting_standard.value,
    }
    for name, data in stmt.all_statements.items():
        result[name] = data.to_dicts()
    return result


@mcp.tool()
async def get_financial_metrics(
    edinet_code: Annotated[
        str,
        Field(description="企業のEDINETコード (例: 'E02144')"),
    ],
    period: Annotated[
        str | None,
        Field(
            description=(
                "書類が提出された年 (例: '2024')。"
                "3月決算企業のFY2024報告書は2025年提出のため period='2025' を指定。"
                "省略時は最新"
            )
        ),
    ] = None,
    doc_type: Annotated[
        str,
        Field(description="'annual_report' or 'quarterly_report'"),
    ] = "annual_report",
) -> dict[str, Any]:
    """Calculate key financial metrics (ROE, ROA, profit margins, etc.).

    Returns profitability ratios, stability ratios, and cash flow summary
    computed from the company's financial statements.

    Example: get_financial_metrics("E02144") → {
      "profitability": {"営業利益率": "11.87%", "ROE": "12.50%", ...},
      "stability": {"自己資本比率": "41.60%", ...},
      "cash_flow": {"営業CF": 5000000, "フリーCF": 3000000, ...}
    }
    """
    stmt = _fetch_stmt(edinet_code, period, doc_type)
    metrics = calculate_metrics(stmt)
    metrics["filing"] = {
        "doc_id": stmt.filing.doc_id,
        "company_name": stmt.filing.company_name,
        "period_end": stmt.filing.period_end.isoformat() if stmt.filing.period_end else None,
    }
    metrics["accounting_standard"] = stmt.accounting_standard.value
    return metrics


@mcp.tool()
async def compare_financial_periods(
    edinet_code: Annotated[
        str,
        Field(description="企業のEDINETコード (例: 'E02144')"),
    ],
    period: Annotated[
        str | None,
        Field(
            description=(
                "書類が提出された年 (例: '2024')。"
                "3月決算企業のFY2024報告書は2025年提出のため period='2025' を指定。"
                "省略時は最新"
            )
        ),
    ] = None,
    doc_type: Annotated[
        str,
        Field(description="'annual_report' or 'quarterly_report'"),
    ] = "annual_report",
) -> dict[str, Any]:
    """Compare financial data between current and previous periods.

    Returns year-over-year changes (増減額 and 増減率) for all items
    that have both 当期 and 前期 data.

    Example: compare_financial_periods("E02144") → {
      "changes": [
        {"科目": "売上高", "当期": 45095325, "前期": 37154298, "増減率": "+21.38%"},
        ...
      ]
    }
    """
    stmt = _fetch_stmt(edinet_code, period, doc_type)
    changes = compare_periods(stmt)
    return {
        "filing": {
            "doc_id": stmt.filing.doc_id,
            "company_name": stmt.filing.company_name,
            "period_end": stmt.filing.period_end.isoformat() if stmt.filing.period_end else None,
        },
        "accounting_standard": stmt.accounting_standard.value,
        "changes": changes,
    }


@mcp.tool()
async def list_available_labels(
    statement_type: Annotated[
        str,
        Field(
            description=(
                "財務諸表の種類: 'income_statement' (PL), 'balance_sheet' (BS), 'cash_flow' (CF)"
            )
        ),
    ] = "income_statement",
) -> list[dict[str, str]]:
    """List all available financial line item labels for a statement type.

    Use this to discover which labels (科目) are available when
    accessing financial data via get_financial_statements.

    Returns labels in display order with Japanese and English names.
    """
    return get_taxonomy_labels(statement_type)


@mcp.tool()
async def get_company_info(
    edinet_code: Annotated[
        str,
        Field(description="企業のEDINETコード (例: 'E02144')"),
    ],
) -> dict[str, Any]:
    """Get detailed information about a company by EDINET code."""
    client = _get_client()
    company = client.get_company(edinet_code)
    return company.model_dump()
