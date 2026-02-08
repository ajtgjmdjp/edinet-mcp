"""edinet-mcp: EDINET XBRL parsing library and MCP server for Japanese financial data.

Quick start::

    from edinet_mcp import EdinetClient

    client = EdinetClient()
    companies = client.search_companies("トヨタ")
    stmt = client.get_financial_statements("E02144", period="2024")
    print(stmt.income_statement.to_polars())
"""

from edinet_mcp.client import EdinetAPIError, EdinetClient
from edinet_mcp.models import (
    AccountingStandard,
    Company,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)
from edinet_mcp.parser import XBRLParser

__all__ = [
    "AccountingStandard",
    "Company",
    "DocType",
    "EdinetAPIError",
    "EdinetClient",
    "Filing",
    "FinancialStatement",
    "StatementData",
    "XBRLParser",
]

__version__ = "0.1.0"
