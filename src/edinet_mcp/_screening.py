"""Multi-company financial screening and comparison.

Fetches financial metrics for multiple companies in batch and returns
a comparison table, optionally sorted/filtered by a specific metric.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from edinet_mcp._metrics import calculate_metrics

if TYPE_CHECKING:
    from edinet_mcp.client import EdinetClient

# Maximum companies per screening request (rate limit safety)
_MAX_COMPANIES = 20


async def screen_companies(
    client: EdinetClient,
    edinet_codes: list[str],
    *,
    period: str | None = None,
    doc_type: str = "annual_report",
    sort_by: str | None = None,
    sort_desc: bool = True,
) -> dict[str, Any]:
    """Screen multiple companies by fetching and comparing financial metrics.

    Iterates over the given EDINET codes, fetches financial statements for
    each, calculates metrics, and returns a comparison table.

    Args:
        client: EdinetClient instance (rate limiter handles pacing).
        edinet_codes: List of EDINET codes to screen (max 20).
        period: Filing year (e.g. "2025"). If None, uses latest.
        doc_type: Document type label (default: "annual_report").
        sort_by: Metric key to sort by (e.g. "ROE", "営業利益率").
        sort_desc: Sort descending if True (default).

    Returns:
        Dict with "results" (list of company metrics), "errors" (failed
        companies), and "count" (number of successful results).

    Raises:
        ValueError: If more than 20 EDINET codes are provided.
    """
    if len(edinet_codes) > _MAX_COMPANIES:
        msg = f"Too many companies: {len(edinet_codes)} (max {_MAX_COMPANIES})"
        raise ValueError(msg)

    if not edinet_codes:
        return {"results": [], "errors": [], "count": 0}

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for code in edinet_codes:
        try:
            stmt = await client.get_financial_statements(
                edinet_code=code,
                doc_type=doc_type,
                period=period,
            )
            metrics = calculate_metrics(stmt)
            row: dict[str, Any] = {
                "edinet_code": code,
                "company_name": stmt.filing.company_name,
                "period_end": (
                    stmt.filing.period_end.isoformat() if stmt.filing.period_end else None
                ),
                "accounting_standard": stmt.accounting_standard.value,
            }
            row.update(metrics)
            results.append(row)
        except Exception as e:
            logger.warning(f"Screening failed for {code}: {e}")
            errors.append({"edinet_code": code, "error": str(e)})

    # Sort by metric if requested
    if sort_by and results:
        results = _sort_by_metric(results, sort_by, sort_desc)

    return {"results": results, "errors": errors, "count": len(results)}


def _sort_by_metric(
    results: list[dict[str, Any]],
    sort_by: str,
    descending: bool,
) -> list[dict[str, Any]]:
    """Sort screening results by a metric value.

    Searches through metric categories (profitability, stability, etc.)
    and raw_values for the sort key. Companies missing the metric are
    placed at the end.
    """
    metric_categories = (
        "profitability",
        "stability",
        "efficiency",
        "growth",
        "cash_flow",
        "raw_values",
    )

    def _extract_sort_value(row: dict[str, Any]) -> float | None:
        for category in metric_categories:
            cat_data = row.get(category)
            if isinstance(cat_data, dict) and sort_by in cat_data:
                val = cat_data[sort_by]
                if isinstance(val, str) and val.endswith("%"):
                    try:
                        return float(val.rstrip("%"))
                    except ValueError:
                        return None
                if isinstance(val, (int, float)):
                    return float(val)
                return None
        return None

    def _sort_key(row: dict[str, Any]) -> tuple[int, float]:
        val = _extract_sort_value(row)
        if val is None:
            return (1, 0.0)  # Missing values go to the end
        return (0, val)

    return sorted(results, key=_sort_key, reverse=descending)
