"""Tests for edinet_mcp.parser."""

from __future__ import annotations

import datetime
from pathlib import Path
from textwrap import dedent

import pytest

from edinet_mcp.models import DocType, Filing
from edinet_mcp.parser import XBRLParser, _coerce_value, _is_financial_element


class TestCoerceValue:
    def test_integer(self) -> None:
        assert _coerce_value("12345") == 12345

    def test_float(self) -> None:
        assert _coerce_value("12.5") == 12.5

    def test_string(self) -> None:
        assert _coerce_value("トヨタ") == "トヨタ"

    def test_none(self) -> None:
        assert _coerce_value(None) is None

    def test_empty(self) -> None:
        assert _coerce_value("") is None

    def test_whitespace(self) -> None:
        assert _coerce_value("  ") is None

    def test_negative_integer(self) -> None:
        assert _coerce_value("-500") == -500

    def test_large_number(self) -> None:
        assert _coerce_value("45095325000000") == 45095325000000


class TestIsFinancialElement:
    def test_jppfs_element(self) -> None:
        ns = "http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor"
        assert _is_financial_element(ns, "Revenue") is True

    def test_linkbase_excluded(self) -> None:
        ns = "http://www.xbrl.org/2003/linkbase"
        assert _is_financial_element(ns, "anything") is False

    def test_context_excluded(self) -> None:
        ns = "http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor"
        assert _is_financial_element(ns, "context") is False


class TestXBRLParserTSV:
    def test_parse_tsv_directory(self, tmp_path: Path) -> None:
        """Parser should read TSV files that match known patterns."""
        # Create a mock TSV file
        tsv_dir = tmp_path / "XBRL" / "PublicDoc"
        tsv_dir.mkdir(parents=True)
        tsv_file = tsv_dir / "jpcrp030000-asr-001_E02144-000_2025-03-31_01_2025-06-20_PL.tsv"
        tsv_file.write_text(
            "element\tvalue\tunit\n"
            "Revenue\t45095325000000\tJPY\n"
            "OperatingProfit\t5352934000000\tJPY\n",
            encoding="utf-8",
        )

        parser = XBRLParser()
        filing = Filing(
            doc_id="S100VVC2",
            edinet_code="E02144",
            company_name="テスト企業",
            doc_type=DocType.ANNUAL_REPORT,
            filing_date=datetime.date(2025, 6, 20),
        )
        result = parser.parse_directory(filing, tmp_path)

        assert result.income_statement
        assert len(result.income_statement) == 2
        items = result.income_statement.to_dicts()
        assert items[0]["element"] == "Revenue"
        assert items[0]["value"] == 45095325000000
