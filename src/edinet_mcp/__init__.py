"""edinet-mcp: EDINET XBRL parsing library and MCP server for Japanese financial data.

Quick start::

    import asyncio
    from edinet_mcp import EdinetClient

    async def main():
        async with EdinetClient() as client:
            companies = await client.search_companies("トヨタ")
            stmt = await client.get_financial_statements("E02144", period="2024")
            print(stmt.income_statement.to_polars())

    asyncio.run(main())
"""

from edinet_mcp._metrics import (
    CashFlowMetrics,
    EfficiencyMetrics,
    FinancialMetrics,
    GrowthMetrics,
    PeriodComparison,
    ProfitabilityMetrics,
    RawValues,
    StabilityMetrics,
    calculate_metrics,
    compare_periods,
)
from edinet_mcp._normalize import get_taxonomy_labels, normalize_statement
from edinet_mcp._validation import FinancialDataWarning, validate_financial_statement
from edinet_mcp.client import EdinetAPIError, EdinetClient
from edinet_mcp.models import (
    AccountingStandard,
    Company,
    DocType,
    Filing,
    FinancialStatement,
    MetricCategory,
    PeriodLabel,
    StatementData,
    StatementType,
)
from edinet_mcp.parser import XBRLParser

__all__ = [
    "AccountingStandard",
    "CashFlowMetrics",
    "Company",
    "DocType",
    "EdinetAPIError",
    "EdinetClient",
    "EfficiencyMetrics",
    "Filing",
    "FinancialDataWarning",
    "FinancialMetrics",
    "FinancialStatement",
    "GrowthMetrics",
    "MetricCategory",
    "PeriodComparison",
    "PeriodLabel",
    "ProfitabilityMetrics",
    "RawValues",
    "StabilityMetrics",
    "StatementData",
    "StatementType",
    "XBRLParser",
    "calculate_metrics",
    "compare_periods",
    "get_taxonomy_labels",
    "normalize_statement",
    "validate_financial_statement",
]

__version__ = "0.4.0"
