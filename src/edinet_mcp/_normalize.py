"""Taxonomy-based normalization of raw XBRL/TSV financial data.

Transforms raw parsed data into canonical Japanese financial labels,
grouping values by period (当期/前期). The normalization mappings are
loaded from ``data/taxonomy.yaml``.

Example output after normalization::

    [
        {"科目": "売上高", "当期": 45095325, "前期": 37154298},
        {"科目": "営業利益", "当期": 5352934, "前期": 2725025},
    ]
"""

from __future__ import annotations

from importlib.resources import files as pkg_files
from typing import Any

import yaml

from edinet_mcp.models import FinancialStatement, PeriodLabel, StatementData, StatementType

# ---------------------------------------------------------------------------
# Taxonomy loading (cached)
# ---------------------------------------------------------------------------

_taxonomy_cache: dict[str, list[dict[str, Any]]] | None = None


def _load_taxonomy() -> dict[str, list[dict[str, Any]]]:
    """Load taxonomy from YAML. Cached after first call."""
    global _taxonomy_cache
    if _taxonomy_cache is not None:
        return _taxonomy_cache

    ref = pkg_files("edinet_mcp").joinpath("data").joinpath("taxonomy.yaml")
    text = ref.read_text(encoding="utf-8")
    _taxonomy_cache = yaml.safe_load(text)
    return _taxonomy_cache


def _build_element_map(
    taxonomy_items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build element_name -> taxonomy_item index for fast lookup."""
    index: dict[str, dict[str, Any]] = {}
    for item in taxonomy_items:
        for elem in item["elements"]:
            index[elem] = item
    return index


# ---------------------------------------------------------------------------
# EDINET suffix stripping
# ---------------------------------------------------------------------------

# EDINET appends accounting-standard and section suffixes to XBRL element
# names.  For example ``TotalAssetsIFRSSummaryOfBusinessResults`` is really
# just ``TotalAssets``.  We strip these suffixes so that the element name
# can match the canonical taxonomy entries.

_EDINET_SUFFIXES = (
    "IFRSSummaryOfBusinessResults",
    "JGAAPSummaryOfBusinessResults",
    "USGAAPSummaryOfBusinessResults",
    "SummaryOfBusinessResults",
    "IFRSKeyFinancialData",
    "KeyFinancialData",
    "IFRS",
    "JGAAP",
    "USGAAP",
)

# Section position tags that EDINET appends *after* the standard suffix.
# CA = Current Assets, CL = Current Liabilities, NCA = Non-Current Assets,
# NCL = Non-Current Liabilities, SS = Shareholders' Equity.
# Note: OpeCF / InvCF / FinCF are intentionally excluded because they
# are already part of canonical taxonomy element names.
_EDINET_POSITION_TAGS = ("NCA", "NCL", "CA", "CL", "SS")


def _strip_edinet_suffixes(name: str) -> str:
    """Strip EDINET-specific suffixes from an XBRL element name.

    Examples:
        >>> _strip_edinet_suffixes("TotalAssetsIFRSSummaryOfBusinessResults")
        'TotalAssets'
        >>> _strip_edinet_suffixes("OtherCurrentAssetsCAIFRS")
        'OtherCurrentAssets'
        >>> _strip_edinet_suffixes("DepreciationAndAmortizationOpeCFIFRS")
        'DepreciationAndAmortizationOpeCF'
    """
    # 1. Strip standard/summary suffix
    for suffix in _EDINET_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    # 2. Strip position tag (only if something remains)
    for tag in _EDINET_POSITION_TAGS:
        if name.endswith(tag) and len(name) > len(tag):
            name = name[: -len(tag)]
            break

    return name


# ---------------------------------------------------------------------------
# Raw item field extraction
# ---------------------------------------------------------------------------


def _extract_element(item: dict[str, Any]) -> str | None:
    """Extract the XBRL element local name from a raw item.

    Handles multiple column name formats:
    - XBRL path: ``{"element": "Revenue", ...}``
    - EDINET TSV: ``{"要素ID": "jppfs_cor:NetSales", ...}``

    EDINET-specific suffixes (IFRS, SummaryOfBusinessResults, etc.)
    are stripped to allow matching against canonical taxonomy entries.
    """
    for key in ("element", "要素ID", "ElementId"):
        val = item.get(key)
        if val:
            s = str(val)
            # Strip namespace prefix: "jppfs_cor:NetSales" -> "NetSales"
            s = s.rsplit(":", 1)[-1] if ":" in s else s
            return _strip_edinet_suffixes(s)
    return None


def _extract_value(item: dict[str, Any]) -> int | float | None:
    """Extract the numeric value from a raw item."""
    for key in ("value", "値", "Value"):
        val = item.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, (int, float)):
            return val
        try:
            cleaned = str(val).replace(",", "")
            return int(cleaned)
        except ValueError:
            try:
                return float(cleaned)
            except ValueError:
                pass
    return None


def _extract_period(item: dict[str, Any]) -> PeriodLabel | None:
    """Determine the period label (当期 or 前期).

    Checks EDINET TSV's ``相対年度`` column first, then falls back
    to inspecting the XBRL context reference for Prior/Previous keywords.

    Returns ``None`` for non-consolidated (単体) contexts so that
    consolidated data is preferred by default.
    """
    # EDINET TSV format
    period = str(item.get("相対年度", ""))
    if period in ("当期", "前期", "前々期"):
        return period  # type: ignore[return-value]

    # XBRL context-based detection
    ctx = str(item.get("context", item.get("コンテキストID", "")))

    # Skip non-consolidated (単体) data — consolidated figures should
    # be used for companies that report both.  Companies without
    # subsidiaries use plain context IDs without this member.
    if "NonConsolidatedMember" in ctx:
        return None

    if "Prior" in ctx or "Previous" in ctx or "LastYear" in ctx:
        return "前期"
    return "当期"


# ---------------------------------------------------------------------------
# Core normalization
# ---------------------------------------------------------------------------


def _normalize_items(
    raw_items: list[dict[str, Any]],
    taxonomy_key: str,
    taxonomy: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Transform raw items into normalized rows.

    Returns:
        Ordered list of dicts ``[{"科目": "売上高", "当期": ..., "前期": ...}, ...]``.
        Returns empty list if no items match the taxonomy.
    """
    taxonomy_items = taxonomy.get(taxonomy_key, [])
    if not taxonomy_items:
        return []

    elem_map = _build_element_map(taxonomy_items)

    # Accumulate: canonical_id -> {period_label: value}
    # NOTE: When multiple values exist for the same element+period
    # (e.g. consolidated vs non-consolidated in XBRL), last-write-wins.
    # This is acceptable because the primary TSV path provides pre-separated
    # data per context, and the XBRL path is only a fallback.
    values: dict[str, dict[str, int | float]] = {}

    for item in raw_items:
        elem_name = _extract_element(item)
        if elem_name is None or elem_name not in elem_map:
            continue

        t_item = elem_map[elem_name]
        cid = t_item["id"]
        val = _extract_value(item)
        period = _extract_period(item)

        if val is not None and period is not None:
            values.setdefault(cid, {})[period] = val

    # Build output in taxonomy display order
    result: list[dict[str, Any]] = []
    for t_item in taxonomy_items:
        cid = t_item["id"]
        if cid not in values:
            continue
        row: dict[str, Any] = {"科目": t_item["label"]}
        row.update(values[cid])
        result.append(row)

    return result


def get_taxonomy_labels(
    statement_type: StatementType = "income_statement",
) -> list[dict[str, str]]:
    """Return available taxonomy labels for a statement type.

    Useful for discovering which labels can be used with
    ``StatementData["label"]`` access.

    Args:
        statement_type: One of ``"income_statement"``, ``"balance_sheet"``,
            or ``"cash_flow"``.

    Returns:
        List of ``{"id": ..., "label": ..., "label_en": ...}`` dicts
        in display order.

    Example::

        >>> from edinet_mcp import get_taxonomy_labels
        >>> labels = get_taxonomy_labels("income_statement")
        >>> labels[0]
        {'id': 'revenue', 'label': '売上高', 'label_en': 'Revenue'}
    """
    taxonomy = _load_taxonomy()
    # Map user-facing names to YAML keys
    key_map = {
        "income_statement": "income_statement",
        "balance_sheet": "balance_sheet",
        "cash_flow_statement": "cash_flow",
        "cash_flow": "cash_flow",
    }
    yaml_key = key_map.get(statement_type, statement_type)
    items = taxonomy.get(yaml_key, [])
    return [
        {"id": item["id"], "label": item["label"], "label_en": item["label_en"]} for item in items
    ]


def normalize_statement(stmt: FinancialStatement) -> FinancialStatement:
    """Normalize all statements in a FinancialStatement.

    Creates a new ``FinancialStatement`` where each ``StatementData``
    contains normalized items (科目 / 当期 / 前期) and preserves the
    original raw data in ``raw_items``.

    If normalization finds no matching items for a statement, the
    original raw data is kept in ``items`` as-is.
    """
    taxonomy = _load_taxonomy()

    def _norm(data: StatementData, taxonomy_key: str) -> StatementData:
        if not data or not data.items:
            return data
        normalized = _normalize_items(data.items, taxonomy_key, taxonomy)
        if not normalized:
            # Keep raw data if nothing matched
            return data
        return StatementData(
            items=normalized,
            raw_items=data.items,
            label=data.label,
        )

    return FinancialStatement(
        filing=stmt.filing,
        balance_sheet=_norm(stmt.balance_sheet, "balance_sheet"),
        income_statement=_norm(stmt.income_statement, "income_statement"),
        cash_flow_statement=_norm(stmt.cash_flow_statement, "cash_flow"),
        summary=stmt.summary,
        accounting_standard=stmt.accounting_standard,
    )
