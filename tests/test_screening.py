"""Tests for multi-company screening module."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from edinet_mcp._screening import screen_companies
from edinet_mcp.models import (
    AccountingStandard,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)


def _make_statement(
    edinet_code: str,
    company_name: str,
    revenue: float,
    operating_income: float,
) -> FinancialStatement:
    """Create a minimal FinancialStatement for testing."""
    filing = Filing(
        doc_id=f"S100{edinet_code[-4:]}",
        edinet_code=edinet_code,
        company_name=company_name,
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2025, 6, 20),
        period_end=datetime.date(2025, 3, 31),
        has_xbrl=True,
    )
    income = StatementData(
        items=[
            {"科目": "売上高", "当期": revenue, "前期": revenue * 0.9},
            {"科目": "営業利益", "当期": operating_income, "前期": operating_income * 0.8},
        ],
        label="IncomeStatement",
    )
    return FinancialStatement(
        filing=filing,
        income_statement=income,
        accounting_standard=AccountingStandard.IFRS,
    )


def _mock_client(*statements: tuple[str, FinancialStatement]) -> MagicMock:
    """Create a mock client that returns specific statements by code."""
    stmt_map = {code: stmt for code, stmt in statements}

    async def _get_stmts(edinet_code: str, **kwargs: object) -> FinancialStatement:
        if edinet_code in stmt_map:
            return stmt_map[edinet_code]
        raise ValueError(f"No filing found for {edinet_code}")

    client = MagicMock()
    client.get_financial_statements = AsyncMock(side_effect=_get_stmts)
    return client


class TestScreenCompanies:
    async def test_screen_single_company(self):
        stmt = _make_statement("E02144", "トヨタ自動車", 45_000_000, 5_000_000)
        client = _mock_client(("E02144", stmt))

        result = await screen_companies(client, ["E02144"])

        assert result["count"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["edinet_code"] == "E02144"
        assert result["results"][0]["company_name"] == "トヨタ自動車"
        assert "profitability" in result["results"][0]
        assert result["errors"] == []

    async def test_screen_multiple_companies(self):
        stmt1 = _make_statement("E02144", "トヨタ自動車", 45_000_000, 5_000_000)
        stmt2 = _make_statement("E01777", "ソニーグループ", 13_000_000, 1_200_000)
        stmt3 = _make_statement("E02529", "キーエンス", 9_000_000, 4_000_000)
        client = _mock_client(
            ("E02144", stmt1),
            ("E01777", stmt2),
            ("E02529", stmt3),
        )

        result = await screen_companies(client, ["E02144", "E01777", "E02529"])

        assert result["count"] == 3
        assert len(result["results"]) == 3
        codes = [r["edinet_code"] for r in result["results"]]
        assert "E02144" in codes
        assert "E01777" in codes
        assert "E02529" in codes

    async def test_screen_with_error(self):
        stmt = _make_statement("E02144", "トヨタ自動車", 45_000_000, 5_000_000)
        client = _mock_client(("E02144", stmt))

        result = await screen_companies(client, ["E02144", "E99999"])

        assert result["count"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["edinet_code"] == "E02144"
        assert len(result["errors"]) == 1
        assert result["errors"][0]["edinet_code"] == "E99999"

    async def test_screen_sort_by_metric(self):
        # Toyota: 営業利益率 = 5M/45M = 11.1%
        stmt1 = _make_statement("E02144", "トヨタ", 45_000_000, 5_000_000)
        # Keyence: 営業利益率 = 4M/9M = 44.4%
        stmt2 = _make_statement("E02529", "キーエンス", 9_000_000, 4_000_000)
        # Sony: 営業利益率 = 1.2M/13M = 9.2%
        stmt3 = _make_statement("E01777", "ソニー", 13_000_000, 1_200_000)
        client = _mock_client(
            ("E02144", stmt1),
            ("E02529", stmt2),
            ("E01777", stmt3),
        )

        result = await screen_companies(
            client,
            ["E02144", "E02529", "E01777"],
            sort_by="営業利益率",
            sort_desc=True,
        )

        assert result["count"] == 3
        codes = [r["edinet_code"] for r in result["results"]]
        # Keyence (44.4%) > Toyota (11.1%) > Sony (9.2%)
        assert codes == ["E02529", "E02144", "E01777"]

    async def test_screen_max_companies_limit(self):
        client = MagicMock()
        codes = [f"E{i:05d}" for i in range(21)]

        with pytest.raises(ValueError, match="Too many companies"):
            await screen_companies(client, codes)

    async def test_screen_empty_list(self):
        client = MagicMock()

        result = await screen_companies(client, [])

        assert result["count"] == 0
        assert result["results"] == []
        assert result["errors"] == []

    async def test_screen_passes_period_and_doc_type(self):
        stmt = _make_statement("E02144", "トヨタ", 45_000_000, 5_000_000)
        client = _mock_client(("E02144", stmt))

        await screen_companies(
            client,
            ["E02144"],
            period="2025",
            doc_type="quarterly_report",
        )

        client.get_financial_statements.assert_called_once_with(
            edinet_code="E02144",
            doc_type="quarterly_report",
            period="2025",
        )

    async def test_screen_all_fail(self):
        client = _mock_client()  # No statements, all will fail

        result = await screen_companies(client, ["E99998", "E99999"])

        assert result["count"] == 0
        assert result["results"] == []
        assert len(result["errors"]) == 2
