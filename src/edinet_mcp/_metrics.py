"""Financial metric calculations from normalized statements.

Computes key financial ratios (ROE, ROA, margins, etc.) and
year-over-year comparisons from normalized :class:`FinancialStatement` data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict, cast

if TYPE_CHECKING:
    from edinet_mcp.models import FinancialStatement, PeriodLabel

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


@dataclass
class _StatementValues:
    """Extracted financial values from a FinancialStatement."""

    # Income statement (current period)
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    ordinary_income: float | None = None
    net_income: float | None = None
    net_income_parent: float | None = None
    cogs: float | None = None
    # Balance sheet
    total_assets: float | None = None
    total_liabilities: float | None = None
    net_assets: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    shareholders_equity: float | None = None
    accounts_receivable: float | None = None
    inventory: float | None = None
    tangible_fixed_assets: float | None = None
    fixed_assets: float | None = None
    fixed_liabilities: float | None = None
    # Cash flow
    operating_cf: float | None = None
    investing_cf: float | None = None
    financing_cf: float | None = None
    # Prior period
    revenue_prev: float | None = None
    operating_income_prev: float | None = None
    total_assets_prev: float | None = None
    # Derived
    ni_for_roe: float | None = None
    equity_for_roe: float | None = None


def _extract_values(stmt: FinancialStatement) -> _StatementValues:
    """Extract all relevant numeric values from a FinancialStatement."""
    v = _StatementValues()
    # Income statement
    v.revenue = _get_val(stmt, "income_statement", "売上高")
    v.gross_profit = _get_val(stmt, "income_statement", "売上総利益")
    v.operating_income = _get_val(stmt, "income_statement", "営業利益")
    v.ordinary_income = _get_val(stmt, "income_statement", "経常利益")
    v.net_income = _get_val(stmt, "income_statement", "当期純利益")
    v.net_income_parent = _get_val(stmt, "income_statement", "親会社株主に帰属する当期純利益")
    v.cogs = _get_val(stmt, "income_statement", "売上原価")
    # Balance sheet
    v.total_assets = _get_val(stmt, "balance_sheet", "資産合計")
    v.total_liabilities = _get_val(stmt, "balance_sheet", "負債合計")
    v.net_assets = _get_val(stmt, "balance_sheet", "純資産合計")
    v.current_assets = _get_val(stmt, "balance_sheet", "流動資産")
    v.current_liabilities = _get_val(stmt, "balance_sheet", "流動負債")
    v.shareholders_equity = _get_val(stmt, "balance_sheet", "株主資本")
    v.accounts_receivable = _get_val(stmt, "balance_sheet", "売掛金")
    v.inventory = _get_val(stmt, "balance_sheet", "棚卸資産")
    v.tangible_fixed_assets = _get_val(stmt, "balance_sheet", "有形固定資産")
    v.fixed_assets = _get_val(stmt, "balance_sheet", "固定資産")
    v.fixed_liabilities = _get_val(stmt, "balance_sheet", "固定負債")
    # Cash flow
    v.operating_cf = _get_val(stmt, "cash_flow_statement", "営業活動によるキャッシュ・フロー")
    v.investing_cf = _get_val(stmt, "cash_flow_statement", "投資活動によるキャッシュ・フロー")
    v.financing_cf = _get_val(stmt, "cash_flow_statement", "財務活動によるキャッシュ・フロー")
    # Prior period
    v.revenue_prev = _get_val(stmt, "income_statement", "売上高", "前期")
    v.operating_income_prev = _get_val(stmt, "income_statement", "営業利益", "前期")
    v.total_assets_prev = _get_val(stmt, "balance_sheet", "資産合計", "前期")
    # Derived
    v.ni_for_roe = v.net_income_parent or v.net_income
    v.equity_for_roe = v.shareholders_equity or v.net_assets
    return v


def _calc_profitability(v: _StatementValues) -> dict[str, str]:
    """Calculate profitability ratios and return as a dict of pct strings."""
    profitability: dict[str, str] = {}
    if (p := _pct(_safe_div(v.gross_profit, v.revenue))) is not None:
        profitability["売上総利益率"] = p
    if (p := _pct(_safe_div(v.operating_income, v.revenue))) is not None:
        profitability["営業利益率"] = p
    if (p := _pct(_safe_div(v.ordinary_income, v.revenue))) is not None:
        profitability["経常利益率"] = p
    if (p := _pct(_safe_div(v.ni_for_roe, v.revenue))) is not None:
        profitability["当期純利益率"] = p
    if (p := _pct(_safe_div(v.ordinary_income or v.operating_income, v.total_assets))) is not None:
        profitability["ROA"] = p
    if (p := _pct(_safe_div(v.ni_for_roe, v.equity_for_roe))) is not None:
        profitability["ROE"] = p
    return profitability


def _calc_stability(v: _StatementValues) -> dict[str, str]:
    """Calculate financial stability ratios and return as a dict of pct strings."""
    stability: dict[str, str] = {}
    if (p := _pct(_safe_div(v.equity_for_roe, v.total_assets))) is not None:
        stability["自己資本比率"] = p
    if (p := _pct(_safe_div(v.current_assets, v.current_liabilities))) is not None:
        stability["流動比率"] = p
    # Quick ratio: (Current Assets - Inventory) / Current Liabilities
    if (
        v.current_assets is not None
        and v.inventory is not None
        and v.current_liabilities is not None
    ):
        quick_assets = v.current_assets - v.inventory
        if (p := _pct(_safe_div(quick_assets, v.current_liabilities))) is not None:
            stability["当座比率"] = p
    if (p := _pct(_safe_div(v.total_liabilities, v.equity_for_roe))) is not None:
        stability["負債比率"] = p
    # Fixed ratio: Fixed Assets / Net Assets
    if (p := _pct(_safe_div(v.fixed_assets, v.equity_for_roe))) is not None:
        stability["固定比率"] = p
    # Fixed long-term suitability ratio: Fixed Assets / (Net Assets + Fixed Liabilities)
    if v.fixed_assets is not None and v.equity_for_roe is not None:
        long_term_capital = v.equity_for_roe + (v.fixed_liabilities or 0)
        if (p := _pct(_safe_div(v.fixed_assets, long_term_capital))) is not None:
            stability["固定長期適合率"] = p
    return stability


def _calc_efficiency(v: _StatementValues) -> dict[str, float]:
    """Calculate efficiency (turnover) ratios and return as a dict of floats."""
    efficiency: dict[str, float] = {}
    if (ratio := _safe_div(v.revenue, v.total_assets)) is not None:
        efficiency["総資産回転率"] = round(ratio, 2)
    if (ratio := _safe_div(v.revenue, v.fixed_assets)) is not None:
        efficiency["固定資産回転率"] = round(ratio, 2)
    if (ratio := _safe_div(v.revenue, v.accounts_receivable)) is not None:
        efficiency["売上債権回転率"] = round(ratio, 2)
    if (ratio := _safe_div(v.cogs, v.inventory)) is not None:
        efficiency["棚卸資産回転率"] = round(ratio, 2)
    if (ratio := _safe_div(v.revenue, v.tangible_fixed_assets)) is not None:
        efficiency["有形固定資産回転率"] = round(ratio, 2)
    return efficiency


def _calc_growth(v: _StatementValues) -> dict[str, str]:
    """Calculate YoY growth rates and return as a dict of pct strings."""
    growth: dict[str, str] = {}
    if v.revenue is not None and v.revenue_prev is not None and v.revenue_prev != 0:
        rate = (v.revenue - v.revenue_prev) / v.revenue_prev
        growth["売上高成長率"] = _pct(rate) or ""
    if (
        v.operating_income is not None
        and v.operating_income_prev is not None
        and v.operating_income_prev != 0
    ):
        rate = (v.operating_income - v.operating_income_prev) / v.operating_income_prev
        growth["営業利益成長率"] = _pct(rate) or ""
    if v.total_assets is not None and v.total_assets_prev is not None and v.total_assets_prev != 0:
        rate = (v.total_assets - v.total_assets_prev) / v.total_assets_prev
        growth["総資産成長率"] = _pct(rate) or ""
    return growth


def _calc_cash_flow(v: _StatementValues) -> dict[str, str | float]:
    """Calculate cash flow metrics and return as a dict."""
    if v.operating_cf is None and v.investing_cf is None and v.financing_cf is None:
        return {}
    cf: dict[str, str | float] = {}
    if v.operating_cf is not None:
        cf["営業CF"] = v.operating_cf
        if (p := _pct(_safe_div(v.operating_cf, v.revenue))) is not None:
            cf["営業CFマージン"] = p
    if v.investing_cf is not None:
        cf["投資CF"] = v.investing_cf
    if v.financing_cf is not None:
        cf["財務CF"] = v.financing_cf
    if v.operating_cf is not None and v.investing_cf is not None:
        free_cf = v.operating_cf + v.investing_cf
        cf["フリーCF"] = free_cf
        if (p := _pct(_safe_div(free_cf, v.revenue))) is not None:
            cf["FCFマージン"] = p
    return cf


def _build_raw_values(v: _StatementValues) -> dict[str, float]:
    """Build a dict of raw financial values, omitting None entries."""
    raw: dict[str, float] = {}
    for label, val in [
        ("売上高", v.revenue),
        ("営業利益", v.operating_income),
        ("経常利益", v.ordinary_income),
        ("当期純利益", v.ni_for_roe),
        ("総資産", v.total_assets),
        ("純資産", v.equity_for_roe),
    ]:
        if val is not None:
            raw[label] = val
    return raw


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
    v = _extract_values(stmt)
    result: dict[str, Any] = {}

    if prof := _calc_profitability(v):
        result["profitability"] = prof
    if stab := _calc_stability(v):
        result["stability"] = stab
    if eff := _calc_efficiency(v):
        result["efficiency"] = eff
    if grow := _calc_growth(v):
        result["growth"] = grow
    if cf := _calc_cash_flow(v):
        result["cash_flow"] = cf
    if raw := _build_raw_values(v):
        result["raw_values"] = raw

    return cast("FinancialMetrics", result)


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

    return cast("list[PeriodComparison]", results)
