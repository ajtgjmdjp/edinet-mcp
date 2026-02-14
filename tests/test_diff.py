"""Tests for edinet_mcp._diff module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from edinet_mcp._diff import (
    LineItemDiff,
    _calculate_change,
    _calculate_change_rate,
    _calculate_summary,
    _compare_statement,
    _extract_current_value,
    diff_statements,
)
from edinet_mcp.models import FinancialStatement, StatementData


class TestDiffHelpers:
    """Tests for diff helper functions."""

    def test_extract_current_value_success(self) -> None:
        """Test extracting current value from statement."""
        stmt = MagicMock(spec=StatementData)
        stmt.__getitem__ = MagicMock(return_value={"当期": 1000, "前期": 800})
        
        result = _extract_current_value(stmt, "売上高")
        assert result == 1000.0

    def test_extract_current_value_missing(self) -> None:
        """Test extracting value when item is missing."""
        stmt = MagicMock(spec=StatementData)
        stmt.__getitem__ = MagicMock(side_effect=KeyError("not found"))
        
        result = _extract_current_value(stmt, "存在しない科目")
        assert result is None

    def test_calculate_change(self) -> None:
        """Test calculating absolute change."""
        assert _calculate_change(100, 150) == 50
        assert _calculate_change(100, 80) == -20
        assert _calculate_change(None, 100) is None
        assert _calculate_change(100, None) is None

    def test_calculate_change_rate(self) -> None:
        """Test calculating percentage change."""
        assert _calculate_change_rate(100, 150) == "+50.00%"
        assert _calculate_change_rate(100, 80) == "-20.00%"
        assert _calculate_change_rate(100, 100) == "+0.00%"
        assert _calculate_change_rate(None, 100) is None
        assert _calculate_change_rate(0, 100) is None  # Cannot divide by zero

    def test_calculate_summary(self) -> None:
        """Test summary calculation."""
        diffs = [
            LineItemDiff(statement="income_statement", 科目="売上高", period1_value=100, period2_value=150, 増減額=50, 増減率="+50.00%"),
            LineItemDiff(statement="income_statement", 科目="営業利益", period1_value=50, period2_value=30, 増減額=-20, 増減率="-40.00%"),
            LineItemDiff(statement="balance_sheet", 科目="総資産", period1_value=1000, period2_value=1000, 増減額=0, 増減率="+0.00%"),
        ]
        
        summary = _calculate_summary(diffs)
        
        assert summary["total_items"] == 3
        assert summary["increased"] == 1
        assert summary["decreased"] == 1
        assert summary["unchanged"] == 1
        assert len(summary["top_increases"]) == 1
        assert summary["top_increases"][0]["科目"] == "売上高"
        assert len(summary["top_decreases"]) == 1
        assert summary["top_decreases"][0]["科目"] == "営業利益"


class TestCompareStatement:
    """Tests for statement comparison."""

    def test_compare_statement_basic(self) -> None:
        """Test comparing two statements."""
        stmt1 = MagicMock(spec=StatementData)
        stmt1.labels = ["売上高", "営業利益"]
        stmt1.__getitem__ = MagicMock(side_effect=lambda k: {"売上高": {"当期": 100}, "営業利益": {"当期": 50}}[k])
        
        stmt2 = MagicMock(spec=StatementData)
        stmt2.labels = ["売上高", "営業利益"]
        stmt2.__getitem__ = MagicMock(side_effect=lambda k: {"売上高": {"当期": 150}, "営業利益": {"当期": 60}}[k])
        
        diffs = _compare_statement(stmt1, stmt2, "income_statement")
        
        assert len(diffs) == 2
        
        # Check sales diff
        sales_diff = next(d for d in diffs if d["科目"] == "売上高")
        assert sales_diff["period1_value"] == 100
        assert sales_diff["period2_value"] == 150
        assert sales_diff["増減額"] == 50
        assert sales_diff["増減率"] == "+50.00%"

    def test_compare_statement_with_new_items(self) -> None:
        """Test comparing when period2 has new items."""
        stmt1 = MagicMock(spec=StatementData)
        stmt1.labels = ["売上高"]
        def stmt1_getitem(k):
            if k == "売上高":
                return {"当期": 100}
            raise KeyError(k)
        stmt1.__getitem__ = MagicMock(side_effect=stmt1_getitem)
        
        stmt2 = MagicMock(spec=StatementData)
        stmt2.labels = ["売上高", "新しい科目"]
        def stmt2_getitem(k):
            return {"売上高": {"当期": 150}, "新しい科目": {"当期": 50}}[k]
        stmt2.__getitem__ = MagicMock(side_effect=stmt2_getitem)
        
        diffs = _compare_statement(stmt1, stmt2, "income_statement")
        
        assert len(diffs) == 2
        
        new_item = next(d for d in diffs if d["科目"] == "新しい科目")
        assert new_item["period1_value"] is None
        assert new_item["period2_value"] == 50


@pytest.mark.asyncio
class TestDiffStatements:
    """Tests for diff_statements async function."""

    async def test_diff_statements_success(self) -> None:
        """Test successful diff of two periods."""
        from edinet_mcp.models import AccountingStandard
        
        # Mock client
        client = MagicMock()
        
        # Create mock filing
        mock_filing1 = MagicMock()
        mock_filing1.company_name = "テスト会社"
        mock_filing2 = MagicMock()
        mock_filing2.company_name = "テスト会社"
        
        # Create mock statements
        stmt1 = MagicMock()
        stmt1.filing = mock_filing1
        stmt1.accounting_standard = AccountingStandard.JGAAP
        stmt1.income_statement = MagicMock()
        stmt1.income_statement.labels = ["売上高"]
        stmt1.income_statement.__getitem__ = MagicMock(return_value={"当期": 100})
        stmt1.balance_sheet = MagicMock()
        stmt1.balance_sheet.labels = []
        stmt1.cash_flow_statement = MagicMock()
        stmt1.cash_flow_statement.labels = []
        
        stmt2 = MagicMock()
        stmt2.filing = mock_filing2
        stmt2.accounting_standard = AccountingStandard.JGAAP
        stmt2.income_statement = MagicMock()
        stmt2.income_statement.labels = ["売上高"]
        stmt2.income_statement.__getitem__ = MagicMock(return_value={"当期": 150})
        stmt2.balance_sheet = MagicMock()
        stmt2.balance_sheet.labels = []
        stmt2.cash_flow_statement = MagicMock()
        stmt2.cash_flow_statement.labels = []
        
        # Mock get_financial_statements
        with patch.object(client, 'get_financial_statements', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [stmt1, stmt2]
            
            result = await diff_statements(client, "E00001", "2023", "2024")
            
            assert result["edinet_code"] == "E00001"
            assert result["company_name"] == "テスト会社"
            assert result["period1"] == "2023"
            assert result["period2"] == "2024"
            assert len(result["diffs"]) > 0
            assert "summary" in result
            
            # Verify both periods were fetched
            assert mock_get.call_count == 2

    async def test_diff_statements_fetch_error(self) -> None:
        """Test error handling when fetch fails."""
        client = MagicMock()
        
        with patch.object(client, 'get_financial_statements', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Statement not found")
            
            with pytest.raises(ValueError, match="Failed to fetch"):
                await diff_statements(client, "E00001", "2023", "2024")


class TestLineItemDiff:
    """Tests for LineItemDiff TypedDict."""

    def test_line_item_diff_creation(self) -> None:
        """Test creating a LineItemDiff."""
        diff = LineItemDiff(
            statement="income_statement",
            科目="売上高",
            period1_value=100,
            period2_value=150,
            増減額=50,
            増減率="+50.00%",
        )
        
        assert diff["statement"] == "income_statement"
        assert diff["科目"] == "売上高"
        assert diff["増減額"] == 50
        assert diff["増減率"] == "+50.00%"
