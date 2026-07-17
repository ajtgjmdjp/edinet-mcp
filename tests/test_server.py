"""Tests for MCP server tools."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from edinet_mcp.models import (
    AccountingStandard,
    FinancialStatement,
    StatementData,
)
from edinet_mcp.server import (
    compare_financial_periods,
    get_company_info,
    get_filings,
    get_financial_metrics,
    get_financial_statements,
    get_narrative,
    list_available_labels,
    screen_companies,
    search_companies,
)

# FastMCP's @mcp.tool() wraps functions in FunctionTool objects.
# Access the original async function via .fn for direct testing.
_search_companies = search_companies.fn
_get_filings = get_filings.fn
_get_financial_statements = get_financial_statements.fn
_get_narrative = get_narrative.fn
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


class TestGetFinancialStatementsEnglish:
    """language='en' renders normalized rows with English keys."""

    @staticmethod
    def _client_with(statement: FinancialStatement) -> MagicMock:
        client = MagicMock()
        client.get_financial_statements = AsyncMock(return_value=statement)
        return client

    async def test_language_en_translates_labels_and_periods(self, sample_filing):
        stmt = FinancialStatement(
            filing=sample_filing,
            income_statement=StatementData(
                items=[{"科目": "売上高", "当期": 100, "前期": 90}],
                label="IncomeStatement",
            ),
        )
        with patch("edinet_mcp.server._get_client", return_value=self._client_with(stmt)):
            result = await _get_financial_statements("E02144", language="en")
        assert result["income_statement"] == [{"label": "Revenue", "current": 100, "prior": 90}]

    async def test_language_en_uses_statement_scoped_translation(self, sample_filing):
        stmt = FinancialStatement(
            filing=sample_filing,
            cash_flow_statement=StatementData(
                items=[{"科目": "減損損失", "当期": 1}],
                label="CashFlowStatement",
            ),
        )
        with patch("edinet_mcp.server._get_client", return_value=self._client_with(stmt)):
            result = await _get_financial_statements("E02144", language="en")
        assert result["cash_flow_statement"] == [{"label": "Impairment Loss (CF)", "current": 1}]

    async def test_language_en_keeps_unmapped_labels_japanese(self, sample_filing):
        stmt = FinancialStatement(
            filing=sample_filing,
            income_statement=StatementData(
                items=[{"科目": "独自科目", "当期": 1}],
                label="IncomeStatement",
            ),
        )
        with patch("edinet_mcp.server._get_client", return_value=self._client_with(stmt)):
            result = await _get_financial_statements("E02144", language="en")
        assert result["income_statement"] == [{"label": "独自科目", "current": 1}]

    async def test_default_language_is_japanese(self, mock_client):
        with patch("edinet_mcp.server._get_client", return_value=mock_client):
            result = await _get_financial_statements("E02144")
        assert "income_statement" in result
        # Raw (non-normalized) rows pass through untouched by default
        assert result["income_statement"][0].get("element") == "Revenue"

    async def test_invalid_language_raises(self, mock_client):
        with (
            patch("edinet_mcp.server._get_client", return_value=mock_client),
            pytest.raises(ValueError, match="Invalid language"),
        ):
            await _get_financial_statements("E02144", language="fr")

    async def test_language_en_passes_summary_rows_through(self, sample_filing):
        # summary is never normalized; its raw rows pass through unchanged
        stmt = FinancialStatement(
            filing=sample_filing,
            summary=StatementData(
                items=[{"element": "ROE", "value": 0.12}],
                label="summary",
            ),
        )
        with patch("edinet_mcp.server._get_client", return_value=self._client_with(stmt)):
            result = await _get_financial_statements("E02144", language="en")
        assert result["summary"] == [{"element": "ROE", "value": 0.12}]


class TestGetNarrativeTool:
    """get_narrative MCP tool — paging over narrative text."""

    def _client_returning(self, narrative):
        client = MagicMock()
        client.get_narrative = AsyncMock(return_value=narrative)
        return client

    def _narrative(self, text: str):
        from edinet_mcp.models import NarrativeSection

        return NarrativeSection(
            section="business_risks",
            element="BusinessRisksTextBlock",
            text=text,
            context_ref="FilingDateInstant",
            doc_id="S100TEST",
            filing_date=datetime.date(2025, 6, 20),
        )

    async def test_returns_full_text_when_short(self) -> None:
        client = self._client_returning(self._narrative("short risk text"))
        with patch("edinet_mcp.server._get_client", return_value=client):
            result = await _get_narrative("E02144", "business_risks")
        assert result["available"] is True
        assert result["text"] == "short risk text"
        assert result["truncated"] is False
        assert result["next_offset"] is None
        assert result["total_chars"] == len("short risk text")

    async def test_pages_long_text(self) -> None:
        client = self._client_returning(self._narrative("あ" * 25000))
        with patch("edinet_mcp.server._get_client", return_value=client):
            page1 = await _get_narrative("E02144", "business_risks", max_chars=10000)
        assert page1["truncated"] is True
        assert page1["returned_chars"] == 10000
        assert page1["next_offset"] == 10000
        with patch("edinet_mcp.server._get_client", return_value=client):
            page3 = await _get_narrative("E02144", "business_risks", max_chars=10000, offset=20000)
        assert page3["returned_chars"] == 5000
        assert page3["truncated"] is False
        assert page3["next_offset"] is None

    async def test_offset_past_end(self) -> None:
        client = self._client_returning(self._narrative("abc"))
        with patch("edinet_mcp.server._get_client", return_value=client):
            result = await _get_narrative("E02144", "business_risks", offset=100)
        assert result["text"] == ""
        assert result["truncated"] is False
        assert result["next_offset"] is None

    async def test_unavailable_section(self) -> None:
        client = self._client_returning(None)
        with patch("edinet_mcp.server._get_client", return_value=client):
            result = await _get_narrative("E02144", "business_risks")
        assert result["available"] is False

    async def test_invalid_section_raises(self) -> None:
        client = self._client_returning(None)
        with (
            patch("edinet_mcp.server._get_client", return_value=client),
            pytest.raises(ValueError, match="Invalid section"),
        ):
            await _get_narrative("E02144", "bogus")

    async def test_invalid_offset_raises(self) -> None:
        client = self._client_returning(self._narrative("abc"))
        with (
            patch("edinet_mcp.server._get_client", return_value=client),
            pytest.raises(ValueError, match="offset"),
        ):
            await _get_narrative("E02144", "business_risks", offset=-1)

    async def test_max_chars_capped(self) -> None:
        client = self._client_returning(self._narrative("abc"))
        with (
            patch("edinet_mcp.server._get_client", return_value=client),
            pytest.raises(ValueError, match="max_chars"),
        ):
            await _get_narrative("E02144", "business_risks", max_chars=100000)
