"""Tests for edinet_mcp._receipts (evidence receipt integration)."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock

import pytest

from edinet_mcp._receipts import (
    ReceiptsUnavailableError,
    _match_receipts_to_labels,
    get_receipts,
)


# 合成 receipt (er/0.2 形状の最小部分)
def _receipt(concept: str, context: str, value: str) -> dict:
    return {
        "schema": "er/0.2",
        "receipt_id": f"er_{concept}_{context}",
        "claim": {"value": value, "kind": "stated", "doc_id": "S100TEST"},
        "evidence": [
            {
                "source_artifact": {"uri": "edinet://S100TEST", "sha256": "ab" * 32},
                "locator": {
                    "profile": "xbrl",
                    "concept": concept,
                    "context_ref": context,
                    "byte_range": [10, 20],
                },
                "extraction": {"engine": "xbrl-facts-evidence@0.1.0"},
            }
        ],
    }


_JSONL = "\n".join(
    json.dumps(r)
    for r in [
        _receipt("jppfs_cor:NetSales", "CurrentYearDuration", "100"),
        _receipt("jppfs_cor:NetSales", "Prior1YearDuration", "90"),
        _receipt("jppfs_cor:NetSalesSummaryOfBusinessResults", "CurrentYearDuration", "100"),
        _receipt("jppfs_cor:OperatingIncome", "CurrentYearDuration", "20"),
        _receipt("jpcrp_cor:NotesRegardingStock", "FilingDateInstant", "1"),
    ]
)


class TestLabelMatching:
    def test_maps_taxonomy_labels_to_receipts(self) -> None:
        matched = _match_receipts_to_labels(_JSONL, ["売上高", "営業利益"])
        assert set(matched) == {"売上高", "営業利益"}
        # NetSales の当期・前期・サフィックス付き変種すべてが売上高に対応
        assert len(matched["売上高"]) == 3
        assert len(matched["営業利益"]) == 1

    def test_unknown_label_returns_empty(self) -> None:
        matched = _match_receipts_to_labels(_JSONL, ["存在しない科目"])
        assert matched["存在しない科目"] == []

    def test_per_label_cap(self) -> None:
        many = "\n".join(
            json.dumps(_receipt("jppfs_cor:NetSales", f"C{i}", str(i))) for i in range(20)
        )
        matched = _match_receipts_to_labels(many, ["売上高"], max_per_label=8)
        assert len(matched["売上高"]) == 8


class TestGetReceipts:
    @pytest.fixture
    def fake_xbrl_facts(self, monkeypatch):
        mod = types.ModuleType("xbrl_facts")
        mod.receipts_for_bytes = lambda source, doc_id, uri, authority=None: _JSONL  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "xbrl_facts", mod)
        return mod

    async def test_returns_receipts_for_default_labels(
        self, tmp_path, sample_filing, fake_xbrl_facts
    ) -> None:
        from tests.conftest import make_narrative_zip

        client = AsyncMock()
        client._resolve_filing = AsyncMock(return_value=sample_filing)
        client.download_document = AsyncMock(return_value=make_narrative_zip(tmp_path))
        result = await get_receipts(client, "E02144", labels=["売上高"])
        assert result["doc_id"] == sample_filing.doc_id
        assert len(result["receipts"]["売上高"]) == 3
        assert result["schema"] == "er/0.2"

    async def test_missing_dependency_raises_clean_error(
        self, tmp_path, sample_filing, monkeypatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "xbrl_facts", None)
        from tests.conftest import make_narrative_zip

        client = AsyncMock()
        client._resolve_filing = AsyncMock(return_value=sample_filing)
        client.download_document = AsyncMock(return_value=make_narrative_zip(tmp_path))
        with pytest.raises(ReceiptsUnavailableError, match="pip install"):
            await get_receipts(client, "E02144", labels=["売上高"])
