"""Tests for edinet_mcp._validation."""

from __future__ import annotations

import datetime
import warnings

import pytest

from edinet_mcp._validation import (
    FinancialDataWarning,
    _check_abnormal_values,
    _check_balance_sheet_equation,
    _check_critical_items,
    _check_income_statement_consistency,
    validate_financial_statement,
)
from edinet_mcp.models import AccountingStandard, DocType, Filing, FinancialStatement, StatementData


def _make_statement(
    bs_data: dict[str, dict[str, float | None]] | None = None,
    pl_data: dict[str, dict[str, float | None]] | None = None,
    cf_data: dict[str, dict[str, float | None]] | None = None,
) -> FinancialStatement:
    """Helper to create a FinancialStatement for testing."""
    bs_items = []
    if bs_data:
        for label, values in bs_data.items():
            bs_items.append({"科目": label, **values})

    pl_items = []
    if pl_data:
        for label, values in pl_data.items():
            pl_items.append({"科目": label, **values})

    cf_items = []
    if cf_data:
        for label, values in cf_data.items():
            cf_items.append({"科目": label, **values})

    # Create a mock Filing
    filing = Filing(
        doc_id="S100TEST",
        edinet_code="E00000",
        company_name="Test Company",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2024, 6, 20),
    )

    return FinancialStatement(
        filing=filing,
        balance_sheet=StatementData(items=bs_items),
        income_statement=StatementData(items=pl_items),
        cash_flow_statement=StatementData(items=cf_items),
        accounting_standard=AccountingStandard.JGAAP,
    )


class TestBalanceSheetEquation:
    def test_balanced_statement_no_warning(self) -> None:
        """Balanced BS (Assets = Liabilities + Equity) should not warn."""
        stmt = _make_statement(
            bs_data={
                "総資産": {"当期": 1000000},
                "負債純資産合計": {"当期": 1000000},
            }
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_balance_sheet_equation(stmt)  # Should not raise

    def test_small_diff_no_warning(self) -> None:
        """Small differences (< 1 million yen) should not warn."""
        stmt = _make_statement(
            bs_data={
                "総資産": {"当期": 1000000},
                "負債純資産合計": {"当期": 1000500},  # 500k diff
            }
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_balance_sheet_equation(stmt)  # Should not raise

    def test_large_diff_warns(self) -> None:
        """Large differences (> 1 million yen) should warn."""
        stmt = _make_statement(
            bs_data={
                "総資産": {"当期": 1000000},
                "負債純資産合計": {"当期": 1002000},  # 2M diff
            }
        )

        with pytest.warns(FinancialDataWarning, match="Balance sheet imbalance"):
            _check_balance_sheet_equation(stmt)

    def test_missing_fields_no_warning(self) -> None:
        """Missing fields should not cause warnings."""
        stmt = _make_statement(bs_data={"総資産": {"当期": 1000000}})

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_balance_sheet_equation(stmt)  # Should not raise


class TestIncomeStatementConsistency:
    def test_consistent_gross_profit_no_warning(self) -> None:
        """Gross Profit = Revenue - COGS should not warn."""
        stmt = _make_statement(
            pl_data={
                "売上高": {"当期": 100000},
                "売上原価": {"当期": 60000},
                "売上総利益": {"当期": 40000},
            }
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_income_statement_consistency(stmt)

    def test_inconsistent_gross_profit_warns(self) -> None:
        """Inconsistent Gross Profit should warn."""
        stmt = _make_statement(
            pl_data={
                "売上高": {"当期": 100000},
                "売上原価": {"当期": 60000},
                "売上総利益": {"当期": 42000},  # Should be 40000
            }
        )

        with pytest.warns(FinancialDataWarning, match="Income statement inconsistency"):
            _check_income_statement_consistency(stmt)

    def test_missing_fields_no_warning(self) -> None:
        """Missing fields should not cause warnings."""
        stmt = _make_statement(pl_data={"売上高": {"当期": 100000}})

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_income_statement_consistency(stmt)


class TestAbnormalValues:
    def test_positive_assets_no_warning(self) -> None:
        """Positive total assets should not warn."""
        stmt = _make_statement(bs_data={"総資産": {"当期": 1000000}})

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_abnormal_values(stmt)

    def test_negative_assets_warns(self) -> None:
        """Negative total assets should warn."""
        stmt = _make_statement(bs_data={"総資産": {"当期": -1000}})

        with pytest.warns(FinancialDataWarning, match="Negative total assets"):
            _check_abnormal_values(stmt)

    def test_negative_equity_warns(self) -> None:
        """Negative equity should warn."""
        stmt = _make_statement(bs_data={"純資産": {"当期": -500}})

        with pytest.warns(FinancialDataWarning, match="Negative equity"):
            _check_abnormal_values(stmt)


class TestCriticalItems:
    def test_has_revenue_no_warning(self) -> None:
        """Statement with revenue should not warn."""
        stmt = _make_statement(
            pl_data={"売上高": {"当期": 100000}},
            bs_data={"総資産": {"当期": 500000}},
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            _check_critical_items(stmt)

    def test_missing_revenue_warns(self) -> None:
        """Missing revenue should warn."""
        stmt = _make_statement(pl_data={}, bs_data={"総資産": {"当期": 500000}})

        with pytest.warns(FinancialDataWarning, match="No revenue line item"):
            _check_critical_items(stmt)

    def test_missing_total_assets_warns(self) -> None:
        """Missing total assets should warn."""
        stmt = _make_statement(pl_data={"売上高": {"当期": 100000}}, bs_data={})

        with pytest.warns(FinancialDataWarning, match="No total assets"):
            _check_critical_items(stmt)


class TestValidateFinancialStatement:
    def test_comprehensive_validation(self) -> None:
        """Full validation should run all checks."""
        stmt = _make_statement(
            bs_data={
                "総資産": {"当期": 1000000},
                "負債純資産合計": {"当期": 1000000},
                "純資産": {"当期": 400000},
            },
            pl_data={
                "売上高": {"当期": 100000},
                "売上原価": {"当期": 60000},
                "売上総利益": {"当期": 40000},
            },
        )

        # Should not raise any warnings for a valid statement
        with warnings.catch_warnings():
            warnings.simplefilter("error", FinancialDataWarning)
            validate_financial_statement(stmt)

    def test_multiple_issues_multiple_warnings(self) -> None:
        """Statement with multiple issues should generate multiple warnings."""
        stmt = _make_statement(
            bs_data={
                "総資産": {"当期": -1000},  # Negative assets
                "純資産": {"当期": -500},  # Negative equity
            },
            pl_data={},  # Missing revenue
        )

        with pytest.warns(FinancialDataWarning) as record:
            validate_financial_statement(stmt)

        # Should have at least 3 warnings (negative assets, negative equity, missing revenue)
        assert len(record) >= 3
