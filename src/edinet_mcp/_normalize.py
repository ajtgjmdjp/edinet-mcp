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

from edinet_mcp.models import FinancialStatement, StatementData

# ---------------------------------------------------------------------------
# Taxonomy loading (cached)
# ---------------------------------------------------------------------------

_taxonomy_cache: dict[str, list[dict[str, Any]]] | None = None


def _load_taxonomy() -> dict[str, list[dict[str, Any]]]:
    """Load taxonomy from YAML. Cached after first call."""
    global _taxonomy_cache
    if _taxonomy_cache is not None:
        return _taxonomy_cache

    ref = pkg_files("edinet_mcp").joinpath("data", "taxonomy.yaml")
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
# Raw item field extraction
# ---------------------------------------------------------------------------


def _extract_element(item: dict[str, Any]) -> str | None:
    """Extract the XBRL element local name from a raw item.

    Handles multiple column name formats:
    - XBRL path: ``{"element": "Revenue", ...}``
    - EDINET TSV: ``{"要素ID": "jppfs_cor:NetSales", ...}``
    """
    for key in ("element", "要素ID", "ElementId"):
        val = item.get(key)
        if val:
            s = str(val)
            # Strip namespace prefix: "jppfs_cor:NetSales" -> "NetSales"
            return s.rsplit(":", 1)[-1] if ":" in s else s
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


def _extract_period(item: dict[str, Any]) -> str:
    """Determine the period label (当期 or 前期).

    Checks EDINET TSV's ``相対年度`` column first, then falls back
    to inspecting the XBRL context reference for Prior/Previous keywords.
    """
    # EDINET TSV format
    period = item.get("相対年度", "")
    if period in ("当期", "前期", "前々期"):
        return period

    # XBRL context-based detection
    ctx = str(item.get("context", item.get("コンテキストID", "")))
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
    values: dict[str, dict[str, int | float]] = {}

    for item in raw_items:
        elem_name = _extract_element(item)
        if elem_name is None or elem_name not in elem_map:
            continue

        t_item = elem_map[elem_name]
        cid = t_item["id"]
        val = _extract_value(item)
        period = _extract_period(item)

        if val is not None:
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
    statement_type: str = "income_statement",
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
