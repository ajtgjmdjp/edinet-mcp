"""Data validation and consistency checks for financial statements."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edinet_mcp.models import FinancialStatement


class FinancialDataWarning(UserWarning):
    """Warning raised for potential data quality issues in financial statements."""


def validate_financial_statement(stmt: FinancialStatement) -> None:
    """Perform comprehensive data consistency checks on a financial statement.

    This function checks for:
    - Balance sheet equation (Assets = Liabilities + Equity)
    - Income statement consistency (Gross Profit = Revenue - COGS)
    - Abnormal negative values in assets/equity
    - Missing critical financial items

    Args:
        stmt: Financial statement to validate.

    Raises:
        FinancialDataWarning: If data quality issues are detected.
    """
    _check_balance_sheet_equation(stmt)
    _check_income_statement_consistency(stmt)
    _check_abnormal_values(stmt)
    _check_critical_items(stmt)


def _check_balance_sheet_equation(stmt: FinancialStatement) -> None:
    """Check if Assets = Liabilities + Equity (within tolerance).

    Tolerates rounding differences up to 1 million yen (千円単位で1000)
    since EDINET reports in thousands of yen.
    """
    bs = stmt.balance_sheet

    # Try to find total assets
    total_assets = None
    for label in ["総資産", "資産合計", "資産の部合計"]:
        if label in bs.labels:
            total_assets = bs[label].get("当期")
            break

    # Try to find liabilities + equity
    liab_equity = None
    for label in ["負債純資産合計", "負債及び純資産合計", "負債資本合計"]:
        if label in bs.labels:
            liab_equity = bs[label].get("当期")
            break

    if total_assets is not None and liab_equity is not None:
        # Both values are in thousands of yen
        diff = abs(total_assets - liab_equity)
        # Tolerance: 1 million yen = 1000 (in thousands)
        if diff > 1000:
            warnings.warn(
                f"Balance sheet imbalance detected: "
                f"Total Assets = {total_assets:,} thousand yen, "
                f"Liabilities + Equity = {liab_equity:,} thousand yen, "
                f"Difference = {diff:,} thousand yen",
                FinancialDataWarning,
                stacklevel=3,
            )


def _check_income_statement_consistency(stmt: FinancialStatement) -> None:
    """Check if Gross Profit = Revenue - COGS (if all are present)."""
    pl = stmt.income_statement

    # Try to find revenue
    revenue = None
    for label in ["売上高", "営業収益"]:
        if label in pl.labels:
            revenue = pl[label].get("当期")
            break

    # Try to find COGS
    cogs = None
    for label in ["売上原価", "営業費用"]:
        if label in pl.labels:
            cogs = pl[label].get("当期")
            break

    # Try to find gross profit
    gross_profit = None
    for label in ["売上総利益", "売上総損失"]:
        if label in pl.labels:
            gross_profit = pl[label].get("当期")
            break

    if revenue is not None and cogs is not None and gross_profit is not None:
        expected_gross = revenue - cogs
        diff = abs(gross_profit - expected_gross)
        # Tolerance: 1 million yen
        if diff > 1000:
            warnings.warn(
                f"Income statement inconsistency: "
                f"Gross Profit = {gross_profit:,}, "
                f"Revenue - COGS = {expected_gross:,}, "
                f"Difference = {diff:,} thousand yen",
                FinancialDataWarning,
                stacklevel=3,
            )


def _check_abnormal_values(stmt: FinancialStatement) -> None:
    """Check for abnormal negative values in assets and equity.

    Negative assets or equity usually indicate data errors (except for
    specific items like treasury stock which are legitimately negative).
    """
    bs = stmt.balance_sheet

    # Check total assets
    for label in ["総資産", "資産合計"]:
        if label in bs.labels:
            value = bs[label].get("当期")
            if value is not None and value < 0:
                warnings.warn(
                    f"Negative total assets detected: {value:,} thousand yen. "
                    "This may indicate a data error.",
                    FinancialDataWarning,
                    stacklevel=3,
                )

    # Check total equity
    for label in ["純資産", "純資産合計", "資本合計"]:
        if label in bs.labels:
            value = bs[label].get("当期")
            if value is not None and value < 0:
                warnings.warn(
                    f"Negative equity detected: {value:,} thousand yen. "
                    "Company may be in financial distress or this is a data error.",
                    FinancialDataWarning,
                    stacklevel=3,
                )


def _check_critical_items(stmt: FinancialStatement) -> None:
    """Warn if critical financial items are missing.

    Most companies should have basic items like revenue. Missing critical
    items may indicate incomplete data extraction or non-standard reporting.
    """
    pl = stmt.income_statement

    # Check for revenue
    has_revenue = any(
        label in pl.labels for label in ["売上高", "営業収益", "経常収益"]
    )
    if not has_revenue:
        warnings.warn(
            "No revenue line item found in income statement. "
            "This may indicate incomplete data or non-standard reporting.",
            FinancialDataWarning,
            stacklevel=3,
        )

    bs = stmt.balance_sheet

    # Check for total assets
    has_total_assets = any(
        label in bs.labels for label in ["総資産", "資産合計", "資産の部合計"]
    )
    if not has_total_assets:
        warnings.warn(
            "No total assets found in balance sheet. "
            "This may indicate incomplete data extraction.",
            FinancialDataWarning,
            stacklevel=3,
        )
