"""Tests for edinet_mcp.parser."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from edinet_mcp.models import DocType, Filing, FinancialStatement
from edinet_mcp.parser import XBRLParser, _coerce_value, _is_financial_element


def _make_filing() -> Filing:
    return Filing(
        doc_id="S100TEST",
        edinet_code="E00001",
        company_name="Test Co.",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2025, 6, 20),
    )


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


class TestTaxonomyBasedRouting:
    """Codex P1: facts must be routed by taxonomy membership, not keywords."""

    @staticmethod
    def _fact(element: str) -> dict[str, object]:
        return {
            "element": element,
            "namespace": "http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor",
            "value": 100,
            "context": "CurrentYearInstant",
            "unit": "JPY",
            "decimals": "0",
        }

    def test_cash_and_deposits_routes_to_balance_sheet(self) -> None:
        # Keyword routing sent this to cash flow because it contains "cash"
        stmt = FinancialStatement(filing=_make_filing())
        XBRLParser._categorize_facts([self._fact("CashAndDeposits")], stmt)
        assert stmt.balance_sheet
        assert not stmt.cash_flow_statement

    def test_trade_receivables_not_dropped(self) -> None:
        # Keyword routing matched no bucket and silently discarded this
        stmt = FinancialStatement(filing=_make_filing())
        XBRLParser._categorize_facts([self._fact("TradeReceivables")], stmt)
        assert stmt.balance_sheet

    def test_cf_element_routes_to_cash_flow(self) -> None:
        stmt = FinancialStatement(filing=_make_filing())
        XBRLParser._categorize_facts(
            [self._fact("NetCashProvidedByUsedInOperatingActivities")], stmt
        )
        assert stmt.cash_flow_statement
        assert not stmt.balance_sheet

    def test_suffixed_element_routes_via_stripping(self) -> None:
        stmt = FinancialStatement(filing=_make_filing())
        XBRLParser._categorize_facts([self._fact("NetSalesSummaryOfBusinessResults")], stmt)
        assert stmt.income_statement

    def test_unknown_extension_falls_back_to_keywords(self) -> None:
        # Not in the taxonomy, but clearly PL-flavored — keep, don't drop
        stmt = FinancialStatement(filing=_make_filing())
        XBRLParser._categorize_facts([self._fact("SpecialFooSalesExpense")], stmt)
        assert stmt.income_statement


class TestXbrlFallbackAccumulation:
    """Facts from ALL instance files must be pooled before categorizing."""

    _NS = (
        'xmlns:jppfs_cor="http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor"'
    )

    def _write_instance(self, directory: Path, name: str, facts_xml: str) -> None:
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<xbrli:xbrl {self._NS} "
            'xmlns:xbrli="http://www.xbrl.org/2003/instance">'
            f"{facts_xml}</xbrli:xbrl>"
        )
        (directory / name).write_text(content, encoding="utf-8")

    def test_facts_across_files_are_merged(self, tmp_path: Path) -> None:
        # File A holds only PL facts, file B only BS facts. The old
        # first-file-wins logic left the BS empty.
        self._write_instance(
            tmp_path,
            "aaa.xbrl",
            '<jppfs_cor:NetSales contextRef="c">100</jppfs_cor:NetSales>',
        )
        self._write_instance(
            tmp_path,
            "bbb.xbrl",
            '<jppfs_cor:CashAndDeposits contextRef="c">50</jppfs_cor:CashAndDeposits>',
        )
        stmt = FinancialStatement(filing=_make_filing())
        parser = XBRLParser()
        parser._parse_xbrl_files(tmp_path, stmt)
        assert stmt.income_statement
        assert stmt.balance_sheet

    def test_fallback_triggered_when_only_cash_flow_missing(self, tmp_path: Path) -> None:
        # BS/PL already populated (e.g. from TSV) — a missing CF must
        # still trigger the XBRL fallback.
        self._write_instance(
            tmp_path,
            "inst.xbrl",
            '<jppfs_cor:NetCashProvidedByUsedInOperatingActivities contextRef="c">'
            "10</jppfs_cor:NetCashProvidedByUsedInOperatingActivities>",
        )
        parser = XBRLParser()
        filing = _make_filing()
        stmt = parser.parse_directory(filing, tmp_path)
        assert stmt.cash_flow_statement
