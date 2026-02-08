"""Tests for edinet_mcp._metrics."""

from __future__ import annotations

import datetime

from edinet_mcp._metrics import calculate_metrics, compare_periods
from edinet_mcp.models import (
    AccountingStandard,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)


def _make_filing() -> Filing:
    return Filing(
        doc_id="S100TEST",
        edinet_code="E99999",
        company_name="テスト株式会社",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2025, 6, 20),
    )


def _make_stmt(
    pl_items: list | None = None,
    bs_items: list | None = None,
    cf_items: list | None = None,
) -> FinancialStatement:
    return FinancialStatement(
        filing=_make_filing(),
        income_statement=StatementData(items=pl_items or [], label="IncomeStatement"),
        balance_sheet=StatementData(items=bs_items or [], label="BalanceSheet"),
        cash_flow_statement=StatementData(items=cf_items or [], label="CashFlowStatement"),
        accounting_standard=AccountingStandard.JGAAP,
    )


class TestCalculateMetrics:
    def test_profitability_ratios(self) -> None:
        stmt = _make_stmt(
            pl_items=[
                {"科目": "売上高", "当期": 1000},
                {"科目": "売上総利益", "当期": 300},
                {"科目": "営業利益", "当期": 100},
                {"科目": "当期純利益", "当期": 60},
            ],
            bs_items=[
                {"科目": "資産合計", "当期": 2000},
                {"科目": "純資産合計", "当期": 800},
            ],
        )
        metrics = calculate_metrics(stmt)

        assert "profitability" in metrics
        p = metrics["profitability"]
        assert p["売上総利益率"] == "30.00%"
        assert p["営業利益率"] == "10.00%"
        assert p["当期純利益率"] == "6.00%"
        assert p["ROA"] == "5.00%"  # 100/2000
        assert p["ROE"] == "7.50%"  # 60/800

    def test_stability_ratios(self) -> None:
        stmt = _make_stmt(
            bs_items=[
                {"科目": "資産合計", "当期": 2000},
                {"科目": "負債合計", "当期": 1200},
                {"科目": "純資産合計", "当期": 800},
                {"科目": "流動資産", "当期": 1000},
                {"科目": "流動負債", "当期": 500},
            ],
        )
        metrics = calculate_metrics(stmt)

        s = metrics["stability"]
        assert s["自己資本比率"] == "40.00%"
        assert s["流動比率"] == "200.00%"
        assert s["負債比率"] == "150.00%"

    def test_cash_flow_summary(self) -> None:
        stmt = _make_stmt(
            cf_items=[
                {"科目": "営業活動によるキャッシュ・フロー", "当期": 500},
                {"科目": "投資活動によるキャッシュ・フロー", "当期": -200},
                {"科目": "財務活動によるキャッシュ・フロー", "当期": -100},
            ],
        )
        metrics = calculate_metrics(stmt)

        cf = metrics["cash_flow"]
        assert cf["営業CF"] == 500
        assert cf["投資CF"] == -200
        assert cf["財務CF"] == -100
        assert cf["フリーCF"] == 300  # 500 + (-200)

    def test_empty_statement(self) -> None:
        stmt = _make_stmt()
        metrics = calculate_metrics(stmt)
        # No profitability/stability if no data
        assert metrics.get("profitability") == {} or "profitability" not in metrics
        assert "cash_flow" not in metrics

    def test_partial_data(self) -> None:
        """Only available metrics are returned."""
        stmt = _make_stmt(
            pl_items=[{"科目": "売上高", "当期": 1000}],
        )
        metrics = calculate_metrics(stmt)
        p = metrics.get("profitability", {})
        # Can't compute margins without numerator
        assert "営業利益率" not in p
        assert "ROE" not in p

    def test_roe_prefers_parent_net_income(self) -> None:
        stmt = _make_stmt(
            pl_items=[
                {"科目": "売上高", "当期": 1000},
                {"科目": "当期純利益", "当期": 60},
                {"科目": "親会社株主に帰属する当期純利益", "当期": 50},
            ],
            bs_items=[
                {"科目": "純資産合計", "当期": 500},
            ],
        )
        metrics = calculate_metrics(stmt)
        # Should use parent net income (50) not total net income (60)
        assert metrics["profitability"]["ROE"] == "10.00%"  # 50/500


class TestComparePeriods:
    def test_basic_comparison(self) -> None:
        stmt = _make_stmt(
            pl_items=[
                {"科目": "売上高", "当期": 1200, "前期": 1000},
                {"科目": "営業利益", "当期": 150, "前期": 100},
            ],
        )
        changes = compare_periods(stmt)

        assert len(changes) == 2
        assert changes[0]["科目"] == "売上高"
        assert changes[0]["増減額"] == 200.0
        assert changes[0]["増減率"] == "+20.00%"
        assert changes[1]["科目"] == "営業利益"
        assert changes[1]["増減額"] == 50.0
        assert changes[1]["増減率"] == "+50.00%"

    def test_decrease(self) -> None:
        stmt = _make_stmt(
            pl_items=[{"科目": "売上高", "当期": 800, "前期": 1000}],
        )
        changes = compare_periods(stmt)
        assert changes[0]["増減額"] == -200.0
        assert changes[0]["増減率"] == "-20.00%"

    def test_skips_items_without_both_periods(self) -> None:
        stmt = _make_stmt(
            pl_items=[
                {"科目": "売上高", "当期": 1000},  # No 前期
                {"科目": "営業利益", "当期": 100, "前期": 80},
            ],
        )
        changes = compare_periods(stmt)
        assert len(changes) == 1
        assert changes[0]["科目"] == "営業利益"

    def test_empty_statement(self) -> None:
        stmt = _make_stmt()
        assert compare_periods(stmt) == []

    def test_cross_statement(self) -> None:
        """Comparison includes items from all statement types."""
        stmt = _make_stmt(
            pl_items=[{"科目": "売上高", "当期": 1000, "前期": 900}],
            bs_items=[{"科目": "資産合計", "当期": 5000, "前期": 4500}],
        )
        changes = compare_periods(stmt)
        labels = [c["科目"] for c in changes]
        assert "売上高" in labels
        assert "資産合計" in labels

    def test_zero_previous_no_rate(self) -> None:
        """When previous is 0, 増減率 should not be included."""
        stmt = _make_stmt(
            pl_items=[{"科目": "特別利益", "当期": 100, "前期": 0}],
        )
        changes = compare_periods(stmt)
        assert len(changes) == 1
        assert "増減率" not in changes[0]
