"""Financial metric calculations from normalized statements.

Computes key financial ratios (ROE, ROA, margins, etc.) and
year-over-year comparisons from normalized :class:`FinancialStatement` data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from edinet_mcp.models import FinancialStatement

from edinet_mcp.models import PeriodLabel


# ---------------------------------------------------------------------------
# Type definitions for metric outputs
# ---------------------------------------------------------------------------


class ProfitabilityMetrics(TypedDict, total=False):
    """Profitability ratios (all values are percentage strings)."""

    売上総利益率: str
    営業利益率: str
    経常利益率: str
    当期純利益率: str
    ROA: str
    ROE: str


class StabilityMetrics(TypedDict, total=False):
    """Financial stability ratios (all values are percentage strings)."""

    自己資本比率: str
    流動比率: str
    当座比率: str
    負債比率: str
    固定比率: str
    固定長期適合率: str


class EfficiencyMetrics(TypedDict, total=False):
    """Asset utilization efficiency ratios (回転率)."""

    総資産回転率: float  # 回 (times per year)
    固定資産回転率: float
    売上債権回転率: float
    棚卸資産回転率: float
    有形固定資産回転率: float


class GrowthMetrics(TypedDict, total=False):
    """Year-over-year growth rates (all values are percentage strings)."""

    売上高成長率: str
    営業利益成長率: str
    総資産成長率: str


class CashFlowMetrics(TypedDict, total=False):
    """Cash flow values and margins."""

    営業CF: float  # thousands of yen
    投資CF: float
    財務CF: float
    フリーCF: float
    営業CFマージン: str  # percentage
    FCFマージン: str


class RawValues(TypedDict, total=False):
    """Raw financial values (in thousands of yen)."""

    売上高: float
    営業利益: float
    経常利益: float
    当期純利益: float
    総資産: float
    純資産: float


class FinancialMetrics(TypedDict, total=False):
    """Complete financial metrics output structure."""

    profitability: ProfitabilityMetrics
    stability: StabilityMetrics
    efficiency: EfficiencyMetrics
    growth: GrowthMetrics
    cash_flow: CashFlowMetrics
    raw_values: RawValues


class PeriodComparison(TypedDict, total=False):
    """Year-over-year comparison for a single line item."""

    statement: str  # "income_statement", "balance_sheet", or "cash_flow_statement"
    科目: str
    当期: float
    前期: float
    増減額: float
    増減率: str  # Formatted as "+21.38%"


def _get_val(
    stmt: FinancialStatement,
    statement: str,
    label: str,
    period: PeriodLabel = "当期",
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


def calculate_metrics(stmt: FinancialStatement) -> FinancialMetrics:
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
    # Extract key values (current period)
    revenue = _get_val(stmt, "income_statement", "売上高")
    gross_profit = _get_val(stmt, "income_statement", "売上総利益")
    operating_income = _get_val(stmt, "income_statement", "営業利益")
    ordinary_income = _get_val(stmt, "income_statement", "経常利益")
    net_income = _get_val(stmt, "income_statement", "当期純利益")
    net_income_parent = _get_val(stmt, "income_statement", "親会社株主に帰属する当期純利益")
    cogs = _get_val(stmt, "income_statement", "売上原価")

    total_assets = _get_val(stmt, "balance_sheet", "資産合計")
    total_liabilities = _get_val(stmt, "balance_sheet", "負債合計")
    net_assets = _get_val(stmt, "balance_sheet", "純資産合計")
    current_assets = _get_val(stmt, "balance_sheet", "流動資産")
    current_liabilities = _get_val(stmt, "balance_sheet", "流動負債")
    shareholders_equity = _get_val(stmt, "balance_sheet", "株主資本")
    accounts_receivable = _get_val(stmt, "balance_sheet", "売掛金")
    inventory = _get_val(stmt, "balance_sheet", "棚卸資産")
    tangible_fixed_assets = _get_val(stmt, "balance_sheet", "有形固定資産")
    fixed_assets = _get_val(stmt, "balance_sheet", "固定資産")
    fixed_liabilities = _get_val(stmt, "balance_sheet", "固定負債")

    operating_cf = _get_val(stmt, "cash_flow_statement", "営業活動によるキャッシュ・フロー")
    investing_cf = _get_val(stmt, "cash_flow_statement", "投資活動によるキャッシュ・フロー")
    financing_cf = _get_val(stmt, "cash_flow_statement", "財務活動によるキャッシュ・フロー")

    # Extract prior period values for growth metrics
    revenue_prev = _get_val(stmt, "income_statement", "売上高", "前期")
    operating_income_prev = _get_val(stmt, "income_statement", "営業利益", "前期")
    total_assets_prev = _get_val(stmt, "balance_sheet", "資産合計", "前期")

    # Prefer parent net income for ROE if available
    ni_for_roe = net_income_parent or net_income
    equity_for_roe = shareholders_equity or net_assets

    result: dict[str, Any] = {}

    # --- Profitability ---
    profitability: dict[str, str] = {}
    if (v := _pct(_safe_div(gross_profit, revenue))) is not None:
        profitability["売上総利益率"] = v
    if (v := _pct(_safe_div(operating_income, revenue))) is not None:
        profitability["営業利益率"] = v
    if (v := _pct(_safe_div(ordinary_income, revenue))) is not None:
        profitability["経常利益率"] = v
    if (v := _pct(_safe_div(ni_for_roe, revenue))) is not None:
        profitability["当期純利益率"] = v
    if (v := _pct(_safe_div(ordinary_income or operating_income, total_assets))) is not None:
        profitability["ROA"] = v
    if (v := _pct(_safe_div(ni_for_roe, equity_for_roe))) is not None:
        profitability["ROE"] = v
    if profitability:
        result["profitability"] = profitability

    # --- Stability ---
    stability: dict[str, str] = {}
    if (v := _pct(_safe_div(equity_for_roe, total_assets))) is not None:
        stability["自己資本比率"] = v
    if (v := _pct(_safe_div(current_assets, current_liabilities))) is not None:
        stability["流動比率"] = v
    # Quick ratio: (Current Assets - Inventory) / Current Liabilities
    if current_assets is not None and inventory is not None and current_liabilities is not None:
        quick_assets = current_assets - inventory
        if (v := _pct(_safe_div(quick_assets, current_liabilities))) is not None:
            stability["当座比率"] = v
    if (v := _pct(_safe_div(total_liabilities, equity_for_roe))) is not None:
        stability["負債比率"] = v
    # Fixed ratio: Fixed Assets / Net Assets
    if (v := _pct(_safe_div(fixed_assets, equity_for_roe))) is not None:
        stability["固定比率"] = v
    # Fixed long-term suitability ratio: Fixed Assets / (Net Assets + Fixed Liabilities)
    if fixed_assets is not None and equity_for_roe is not None:
        long_term_capital = equity_for_roe + (fixed_liabilities or 0)
        if (v := _pct(_safe_div(fixed_assets, long_term_capital))) is not None:
            stability["固定長期適合率"] = v
    if stability:
        result["stability"] = stability

    # --- Efficiency (Turnover Ratios) ---
    efficiency: dict[str, float] = {}
    if (v := _safe_div(revenue, total_assets)) is not None:
        efficiency["総資産回転率"] = round(v, 2)
    if (v := _safe_div(revenue, fixed_assets)) is not None:
        efficiency["固定資産回転率"] = round(v, 2)
    if (v := _safe_div(revenue, accounts_receivable)) is not None:
        efficiency["売上債権回転率"] = round(v, 2)
    if (v := _safe_div(cogs, inventory)) is not None:
        efficiency["棚卸資産回転率"] = round(v, 2)
    if (v := _safe_div(revenue, tangible_fixed_assets)) is not None:
        efficiency["有形固定資産回転率"] = round(v, 2)
    if efficiency:
        result["efficiency"] = efficiency

    # --- Growth (YoY Growth Rates) ---
    growth: dict[str, str] = {}
    if revenue is not None and revenue_prev is not None and revenue_prev != 0:
        growth_rate = (revenue - revenue_prev) / revenue_prev
        growth["売上高成長率"] = _pct(growth_rate) or ""
    if operating_income is not None and operating_income_prev is not None and operating_income_prev != 0:
        growth_rate = (operating_income - operating_income_prev) / operating_income_prev
        growth["営業利益成長率"] = _pct(growth_rate) or ""
    if total_assets is not None and total_assets_prev is not None and total_assets_prev != 0:
        growth_rate = (total_assets - total_assets_prev) / total_assets_prev
        growth["総資産成長率"] = _pct(growth_rate) or ""
    if growth:
        result["growth"] = growth

    # --- Cash Flow ---
    if operating_cf is not None or investing_cf is not None or financing_cf is not None:
        cf: dict[str, str | float] = {}
        if operating_cf is not None:
            cf["営業CF"] = operating_cf
            # Operating CF Margin = Operating CF / Revenue
            if (v := _pct(_safe_div(operating_cf, revenue))) is not None:
                cf["営業CFマージン"] = v
        if investing_cf is not None:
            cf["投資CF"] = investing_cf
        if financing_cf is not None:
            cf["財務CF"] = financing_cf
        if operating_cf is not None and investing_cf is not None:
            free_cf = operating_cf + investing_cf
            cf["フリーCF"] = free_cf
            # FCF Margin = Free CF / Revenue
            if (v := _pct(_safe_div(free_cf, revenue))) is not None:
                cf["FCFマージン"] = v
        result["cash_flow"] = cf

    # --- Raw values for reference ---
    raw: dict[str, float] = {}
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

    return result  # type: ignore[return-value]


def compare_periods(stmt: FinancialStatement) -> list[PeriodComparison]:
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

    return results  # type: ignore[return-value]
