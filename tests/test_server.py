"""Tests for MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from edinet_mcp.models import (
    AccountingStandard,
    FinancialStatement,
)
from edinet_mcp.server import (
    compare_financial_periods,
    get_company_info,
    get_filings,
    get_financial_metrics,
    get_financial_statements,
    list_available_labels,
    screen_companies,
    search_companies,
)

# FastMCP's @mcp.tool() wraps functions in FunctionTool objects.
# Access the original async function via .fn for direct testing.
_search_companies = search_companies.fn
_get_filings = get_filings.fn
_get_financial_statements = get_financial_statements.fn
_get_financial_metrics = get_financial_metrics.fn
_compare_financial_periods = compare_financial_periods.fn
_list_available_labels = list_available_labels.fn
_get_company_info = get_company_info.fn
_screen_companies = screen_companies.fn


@pytest.fixture()
def mock_client(sample_company, sample_filing, sample_statement_data):
    """Create a mock EdinetClient with async methods."""
    client = MagicMock()
    client.search_companies = AsyncMock(return_value=[sample_company])
    client.get_company = AsyncMock(return_value=sample_company)
    client.get_filings = AsyncMock(return_value=[sample_filing])
    client.get_financial_statements = AsyncMock(
        return_value=FinancialStatement(
            filing=sample_filing,
            income_statement=sample_statement_data,
            accounting_standard=AccountingStandard.IFRS,
        )
    )
    return client


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the global client singleton between tests."""
    import edinet_mcp.server as server_mod

    server_mod._client = None
    yield
    server_mod._client = None


class TestSearchCompanies:
    async def test_search_returns_list(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _search_companies("トヨタ")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["edinet_code"] == "E02144"

    async def test_search_limits_to_20(self, mock_client, sample_company):
        mock_client.search_companies = AsyncMock(return_value=[sample_company] * 30)
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _search_companies("トヨタ")
        assert len(result) == 20

    async def test_search_empty(self, mock_client):
        mock_client.search_companies = AsyncMock(return_value=[])
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _search_companies("存在しない")
        assert result == []


class TestGetFilings:
    async def test_get_filings_basic(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_filings("E02144", "2024-01-01")
        assert isinstance(result, list)
        assert len(result) == 1
        mock_client.get_filings.assert_called_once()

    async def test_get_filings_limits_to_50(self, mock_client, sample_filing):
        mock_client.get_filings = AsyncMock(return_value=[sample_filing] * 60)
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_filings("E02144", "2024-01-01")
        assert len(result) == 50


class TestGetFinancialStatements:
    async def test_get_statements_returns_dict(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_financial_statements("E02144")
        assert isinstance(result, dict)
        assert "filing" in result
        assert "accounting_standard" in result
        assert result["accounting_standard"] == "IFRS"

    async def test_get_statements_includes_income(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_financial_statements("E02144")
        assert "income_statement" in result
        assert isinstance(result["income_statement"], list)


class TestGetFinancialMetrics:
    async def test_get_metrics_returns_dict(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_financial_metrics("E02144")
        assert isinstance(result, dict)
        assert "filing" in result
        assert result["filing"]["doc_id"] == "S100VVC2"

    async def test_get_metrics_includes_standard(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_financial_metrics("E02144")
        assert "accounting_standard" in result


class TestCompareFinancialPeriods:
    async def test_compare_returns_changes(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _compare_financial_periods("E02144")
        assert isinstance(result, dict)
        assert "changes" in result
        assert "filing" in result
        assert "accounting_standard" in result


class TestListAvailableLabels:
    async def test_income_statement_labels(self):
        result = await _list_available_labels("income_statement")
        assert isinstance(result, list)
        assert len(result) > 0
        assert "label" in result[0]

    async def test_balance_sheet_labels(self):
        result = await _list_available_labels("balance_sheet")
        assert isinstance(result, list)
        assert len(result) > 0

    async def test_cash_flow_labels(self):
        result = await _list_available_labels("cash_flow")
        assert isinstance(result, list)
        assert len(result) > 0


class TestGetCompanyInfo:
    async def test_get_company_info(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_company_info("E02144")
        assert isinstance(result, dict)
        assert result["edinet_code"] == "E02144"
        assert result["name"] == "トヨタ自動車株式会社"


class TestScreenCompanies:
    async def test_screen_returns_results(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _screen_companies(["E02144"])
        assert isinstance(result, dict)
        assert "results" in result
        assert "errors" in result
        assert "count" in result
        assert result["count"] == 1

    async def test_screen_empty_input(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _screen_companies([])
        assert result["count"] == 0
        assert result["results"] == []

    async def test_screen_too_many_companies(self, mock_client):
        codes = [f"E{i:05d}" for i in range(21)]
        with (
            patch("edinet_mcp.server._get_client", return_value=mock_client),
            pytest.raises(ValueError, match="Too many companies"),
        ):
            await _screen_companies(codes)
