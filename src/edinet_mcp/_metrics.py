"""Financial metric calculations from normalized statements.

Computes key financial ratios (ROE, ROA, margins, etc.) and
year-over-year comparisons from normalized :class:`FinancialStatement` data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edinet_mcp.models import FinancialStatement


def _get_val(
    stmt: FinancialStatement,
    statement: str,
    label: str,
    period: str = "当期",
) -> float | None:
    """Safely extract a numeric value from a normalized statement."""
    data = getattr(stmt, statement, None)
    if data is None:
        return None
    info = data.get(label)
    if info is None:
        return None
    val = info.get(period)
    if val is None:
        return None
    return float(val)


def _safe_div(a: float | None, b: float | None) -> float | None:
    """Divide a by b, returning None if either is None or b is zero."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(val: float | None) -> str | None:
    """Format as percentage string, or None."""
    if val is None:
        return None
    return f"{val * 100:.2f}%"


def calculate_metrics(stmt: FinancialStatement) -> dict[str, Any]:
    """Calculate key financial metrics from normalized statements.

    Returns a dict of metric categories, each containing labeled values.
    All ratios are expressed as percentages.

    Example output::

        {
            "profitability": {
                "営業利益率": "11.87%",
                "売上総利益率": "25.30%",
                "当期純利益率": "10.97%",
                "ROA": "5.20%",
                "ROE": "12.50%",
            },
            "stability": {
                "自己資本比率": "41.60%",
                "流動比率": "132.50%",
            },
            "raw_values": {
                "売上高": 45095325,
                "営業利益": 5352934,
                ...
            }
        }
    """
    # Extract key values
    revenue = _get_val(stmt, "income_statement", "売上高")
    gross_profit = _get_val(stmt, "income_statement", "売上総利益")
    operating_income = _get_val(stmt, "income_statement", "営業利益")
    ordinary_income = _get_val(stmt, "income_statement", "経常利益")
    net_income = _get_val(stmt, "income_statement", "当期純利益")
    net_income_parent = _get_val(stmt, "income_statement", "親会社株主に帰属する当期純利益")

    total_assets = _get_val(stmt, "balance_sheet", "資産合計")
    total_liabilities = _get_val(stmt, "balance_sheet", "負債合計")
    net_assets = _get_val(stmt, "balance_sheet", "純資産合計")
    current_assets = _get_val(stmt, "balance_sheet", "流動資産")
    current_liabilities = _get_val(stmt, "balance_sheet", "流動負債")
    shareholders_equity = _get_val(stmt, "balance_sheet", "株主資本")

    operating_cf = _get_val(stmt, "cash_flow_statement", "営業活動によるキャッシュ・フロー")
    investing_cf = _get_val(stmt, "cash_flow_statement", "投資活動によるキャッシュ・フロー")
    financing_cf = _get_val(stmt, "cash_flow_statement", "財務活動によるキャッシュ・フロー")

    # Prefer parent net income for ROE if available
    ni_for_roe = net_income_parent or net_income
    equity_for_roe = shareholders_equity or net_assets

    result: dict[str, Any] = {}

    # --- Profitability ---
    profitability: dict[str, str | None] = {}
    profitability["売上総利益率"] = _pct(_safe_div(gross_profit, revenue))
    profitability["営業利益率"] = _pct(_safe_div(operating_income, revenue))
    profitability["経常利益率"] = _pct(_safe_div(ordinary_income, revenue))
    profitability["当期純利益率"] = _pct(_safe_div(ni_for_roe, revenue))
    profitability["ROA"] = _pct(_safe_div(ordinary_income or operating_income, total_assets))
    profitability["ROE"] = _pct(_safe_div(ni_for_roe, equity_for_roe))
    # Remove None entries
    result["profitability"] = {k: v for k, v in profitability.items() if v is not None}

    # --- Stability ---
    stability: dict[str, str | None] = {}
    stability["自己資本比率"] = _pct(_safe_div(equity_for_roe, total_assets))
    stability["流動比率"] = _pct(_safe_div(current_assets, current_liabilities))
    stability["負債比率"] = _pct(_safe_div(total_liabilities, equity_for_roe))
    result["stability"] = {k: v for k, v in stability.items() if v is not None}

    # --- Cash Flow ---
    if operating_cf is not None or investing_cf is not None or financing_cf is not None:
        cf: dict[str, Any] = {}
        if operating_cf is not None:
            cf["営業CF"] = operating_cf
        if investing_cf is not None:
            cf["投資CF"] = investing_cf
        if financing_cf is not None:
            cf["財務CF"] = financing_cf
        if operating_cf is not None and investing_cf is not None:
            cf["フリーCF"] = operating_cf + investing_cf
        result["cash_flow"] = cf

    # --- Raw values for reference ---
    raw: dict[str, Any] = {}
    for label, val in [
        ("売上高", revenue),
        ("営業利益", operating_income),
        ("経常利益", ordinary_income),
        ("当期純利益", ni_for_roe),
        ("総資産", total_assets),
        ("純資産", equity_for_roe),
    ]:
        if val is not None:
            raw[label] = val
    if raw:
        result["raw_values"] = raw

    return result


def compare_periods(stmt: FinancialStatement) -> list[dict[str, Any]]:
    """Generate year-over-year comparison for all normalized items.

    Returns a list of dicts, one per line item that has both 当期 and 前期 values::

        [
            {
                "statement": "income_statement",
                "科目": "売上高",
                "当期": 45095325,
                "前期": 37154298,
                "増減額": 7941027,
                "増減率": "21.38%",
            },
            ...
        ]
    """
    results: list[dict[str, Any]] = []

    for stmt_name in ("income_statement", "balance_sheet", "cash_flow_statement"):
        data = getattr(stmt, stmt_name, None)
        if data is None or not data.items:
            continue

        for item in data.items:
            label = item.get("科目")
            current = item.get("当期")
            previous = item.get("前期")
            if label is None or current is None or previous is None:
                continue

            current_f = float(current)
            previous_f = float(previous)
            change = current_f - previous_f
            change_pct = (change / abs(previous_f) * 100) if previous_f != 0 else None

            row: dict[str, Any] = {
                "statement": stmt_name,
                "科目": label,
                "当期": current,
                "前期": previous,
                "増減額": change,
            }
            if change_pct is not None:
                row["増減率"] = f"{change_pct:+.2f}%"
            results.append(row)

    return results
