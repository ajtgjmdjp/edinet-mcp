"""Financial statement diff and period comparison.

Compares financial statements for the same company across two periods,
calculating changes (増減額) and growth rates (増減率) for each line item.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from loguru import logger

if TYPE_CHECKING:
    from edinet_mcp.client import EdinetClient
    from edinet_mcp.models import FinancialStatement, StatementData


class LineItemDiff(TypedDict):
    """Diff result for a single line item."""

    statement: str  # "income_statement", "balance_sheet", or "cash_flow_statement"
    科目: str
    period1_value: float | None
    period2_value: float | None
    増減額: float | None
    増減率: str | None  # Formatted as "+21.38%" or "-10.50%"


class DiffResult(TypedDict):
    """Complete diff result for two periods."""

    edinet_code: str
    company_name: str
    period1: str
    period2: str
    accounting_standard: str
    diffs: list[LineItemDiff]
    summary: dict[str, Any]


async def diff_statements(
    client: EdinetClient,
    edinet_code: str,
    period1: str,
    period2: str,
    *,
    doc_type: str = "annual_report",
) -> DiffResult:
    """Compare financial statements for the same company across two periods.

    Fetches financial statements for both periods and calculates changes
    (増減額) and growth rates (増減率) for each line item.

    Args:
        client: EdinetClient instance.
        edinet_code: Company's EDINET code (e.g. "E02144").
        period1: First period year (e.g. "2024").
        period2: Second period year (e.g. "2025").
        doc_type: Document type label (default: "annual_report").

    Returns:
        DiffResult with detailed diffs and summary statistics.

    Raises:
        ValueError: If either period's statement cannot be fetched.
    """
    logger.info(f"Fetching statements for {edinet_code}: {period1} vs {period2}")

    # Fetch both statements
    try:
        stmt1 = await client.get_financial_statements(
            edinet_code=edinet_code,
            doc_type=doc_type,
            period=period1,
        )
    except Exception as e:
        raise ValueError(f"Failed to fetch {period1} statement: {e}") from e

    try:
        stmt2 = await client.get_financial_statements(
            edinet_code=edinet_code,
            doc_type=doc_type,
            period=period2,
        )
    except Exception as e:
        raise ValueError(f"Failed to fetch {period2} statement: {e}") from e

    # Calculate diffs
    diffs: list[LineItemDiff] = []

    # Compare income statements
    diffs.extend(_compare_statement(
        stmt1.income_statement,
        stmt2.income_statement,
        "income_statement",
    ))

    # Compare balance sheets
    diffs.extend(_compare_statement(
        stmt1.balance_sheet,
        stmt2.balance_sheet,
        "balance_sheet",
    ))

    # Compare cash flow statements
    diffs.extend(_compare_statement(
        stmt1.cash_flow_statement,
        stmt2.cash_flow_statement,
        "cash_flow_statement",
    ))

    # Sort diffs by absolute change magnitude
    diffs.sort(key=lambda x: abs(x.get("増減額") or 0), reverse=True)

    # Calculate summary
    summary = _calculate_summary(diffs)

    return DiffResult(
        edinet_code=edinet_code,
        company_name=stmt2.filing.company_name,
        period1=period1,
        period2=period2,
        accounting_standard=stmt2.accounting_standard.value,
        diffs=diffs,
        summary=summary,
    )


def _compare_statement(
    stmt1: StatementData,
    stmt2: StatementData,
    statement_type: str,
) -> list[LineItemDiff]:
    """Compare two statements and return diffs for each line item."""
    diffs: list[LineItemDiff] = []

    # Get all unique labels from both statements
    labels1 = set(stmt1.labels)
    labels2 = set(stmt2.labels)
    all_labels = labels1 | labels2

    for label in all_labels:
        val1 = _extract_current_value(stmt1, label)
        val2 = _extract_current_value(stmt2, label)

        if val1 is None and val2 is None:
            continue

        change = _calculate_change(val1, val2)
        change_rate = _calculate_change_rate(val1, val2)

        diffs.append(LineItemDiff(
            statement=statement_type,
            科目=label,
            period1_value=val1,
            period2_value=val2,
            増減額=change,
            増減率=change_rate,
        ))

    return diffs


def _extract_current_value(stmt: StatementData, label: str) -> float | None:
    """Extract the '当期' value for a label from a statement."""
    try:
        item = stmt[label]
        value = item.get("当期")
        if value is None:
            return None
        return float(value)
    except (KeyError, ValueError, TypeError):
        return None


def _calculate_change(val1: float | None, val2: float | None) -> float | None:
    """Calculate absolute change between two values."""
    if val1 is None or val2 is None:
        return None
    return val2 - val1


def _calculate_change_rate(val1: float | None, val2: float | None) -> str | None:
    """Calculate percentage change between two values."""
    if val1 is None or val2 is None:
        return None
    if val1 == 0:
        return None  # Cannot calculate rate when base is zero
    rate = (val2 - val1) / abs(val1) * 100
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate:.2f}%"


def _calculate_summary(diffs: list[LineItemDiff]) -> dict[str, Any]:
    """Calculate summary statistics from diffs."""
    total_items = len(diffs)
    increased = sum(1 for d in diffs if (d.get("増減額") or 0) > 0)
    decreased = sum(1 for d in diffs if (d.get("増減額") or 0) < 0)
    unchanged = total_items - increased - decreased

    # Top 5 increases and decreases
    valid_diffs = [d for d in diffs if d.get("増減額") is not None]
    top_increases = [d for d in valid_diffs if d["増減額"] > 0][:5]
    top_decreases = [d for d in valid_diffs if d["増減額"] < 0][:5]

    return {
        "total_items": total_items,
        "increased": increased,
        "decreased": decreased,
        "unchanged": unchanged,
        "top_increases": [
            {"科目": d["科目"], "増減額": d["増減額"], "増減率": d["増減率"]}
            for d in top_increases
        ],
        "top_decreases": [
            {"科目": d["科目"], "増減額": d["増減額"], "増減率": d["増減率"]}
            for d in top_decreases
        ],
    }
