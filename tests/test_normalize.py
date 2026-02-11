"""Tests for edinet_mcp._normalize."""

from __future__ import annotations

import datetime

from edinet_mcp._normalize import (
    _extract_element,
    _extract_period,
    _extract_value,
    _load_taxonomy,
    _normalize_items,
    _strip_edinet_suffixes,
    get_taxonomy_labels,
    normalize_statement,
)
from edinet_mcp.models import (
    AccountingStandard,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)

# ---------------------------------------------------------------------------
# Taxonomy loading
# ---------------------------------------------------------------------------


class TestLoadTaxonomy:
    def test_loads_all_statement_types(self) -> None:
        taxonomy = _load_taxonomy()
        assert "income_statement" in taxonomy
        assert "balance_sheet" in taxonomy
        assert "cash_flow" in taxonomy

    def test_items_have_required_fields(self) -> None:
        taxonomy = _load_taxonomy()
        for stmt_type, items in taxonomy.items():
            for item in items:
                assert "id" in item, f"Missing 'id' in {stmt_type}"
                assert "label" in item, f"Missing 'label' in {stmt_type}"
                assert "elements" in item, f"Missing 'elements' in {stmt_type}"
                assert len(item["elements"]) > 0


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


class TestStripEdinetSuffixes:
    def test_no_suffix(self) -> None:
        assert _strip_edinet_suffixes("TotalAssets") == "TotalAssets"

    def test_ifrs_suffix(self) -> None:
        assert _strip_edinet_suffixes("CurrentAssetsIFRS") == "CurrentAssets"

    def test_summary_suffix(self) -> None:
        assert _strip_edinet_suffixes("NetSalesSummaryOfBusinessResults") == "NetSales"

    def test_ifrs_summary_suffix(self) -> None:
        result = _strip_edinet_suffixes("TotalAssetsIFRSSummaryOfBusinessResults")
        assert result == "TotalAssets"

    def test_key_financial_data_suffix(self) -> None:
        result = _strip_edinet_suffixes("OperatingRevenuesIFRSKeyFinancialData")
        assert result == "OperatingRevenues"

    def test_position_tag_ca(self) -> None:
        assert _strip_edinet_suffixes("OtherCurrentAssetsCAIFRS") == "OtherCurrentAssets"

    def test_position_tag_ncl(self) -> None:
        result = _strip_edinet_suffixes("RetirementBenefitLiabilityNCLIFRS")
        assert result == "RetirementBenefitLiability"

    def test_position_tag_nca(self) -> None:
        result = _strip_edinet_suffixes("OtherFinancialAssetsNCAIFRS")
        assert result == "OtherFinancialAssets"

    def test_opecf_not_stripped(self) -> None:
        """OpeCF is part of canonical taxonomy names — should NOT be stripped."""
        result = _strip_edinet_suffixes("DepreciationAndAmortizationOpeCFIFRS")
        assert result == "DepreciationAndAmortizationOpeCF"

    def test_jgaap_suffix(self) -> None:
        assert _strip_edinet_suffixes("NetSalesJGAAP") == "NetSales"

    def test_usgaap_suffix(self) -> None:
        assert _strip_edinet_suffixes("RevenueUSGAAP") == "Revenue"


class TestExtractElement:
    def test_from_element_key(self) -> None:
        assert _extract_element({"element": "Revenue"}) == "Revenue"

    def test_from_japanese_key(self) -> None:
        assert _extract_element({"要素ID": "NetSales"}) == "NetSales"

    def test_strips_namespace(self) -> None:
        assert _extract_element({"要素ID": "jppfs_cor:NetSales"}) == "NetSales"

    def test_none_when_missing(self) -> None:
        assert _extract_element({"other": "value"}) is None

    def test_strips_edinet_suffixes(self) -> None:
        """Element extraction also strips EDINET suffixes."""
        item = {"element": "TotalAssetsIFRSSummaryOfBusinessResults"}
        assert _extract_element(item) == "TotalAssets"

    def test_strips_namespace_and_suffix(self) -> None:
        item = {"要素ID": "jpcrp_cor:SalesRevenuesIFRS"}
        assert _extract_element(item) == "SalesRevenues"


class TestExtractValue:
    def test_int(self) -> None:
        assert _extract_value({"value": 12345}) == 12345

    def test_float(self) -> None:
        assert _extract_value({"value": 12.5}) == 12.5

    def test_string_int(self) -> None:
        assert _extract_value({"value": "12345"}) == 12345

    def test_comma_separated(self) -> None:
        assert _extract_value({"value": "1,234,567"}) == 1234567

    def test_japanese_key(self) -> None:
        assert _extract_value({"値": 999}) == 999

    def test_none(self) -> None:
        assert _extract_value({"value": None}) is None
        assert _extract_value({}) is None


class TestExtractPeriod:
    def test_japanese_key(self) -> None:
        assert _extract_period({"相対年度": "当期"}) == "当期"
        assert _extract_period({"相対年度": "前期"}) == "前期"

    def test_xbrl_context_prior(self) -> None:
        assert _extract_period({"context": "PriorYearDuration"}) == "前期"

    def test_xbrl_context_current(self) -> None:
        assert _extract_period({"context": "CurrentYearDuration"}) == "当期"

    def test_default_is_current(self) -> None:
        assert _extract_period({}) == "当期"

    def test_non_consolidated_returns_none(self) -> None:
        """Non-consolidated contexts should be skipped."""
        item = {"context": "CurrentYearInstant_NonConsolidatedMember"}
        assert _extract_period(item) is None

    def test_non_consolidated_prior_returns_none(self) -> None:
        item = {"context": "Prior1YearDuration_NonConsolidatedMember"}
        assert _extract_period(item) is None

    def test_consolidated_context_works(self) -> None:
        """Plain context (consolidated) should work normally."""
        assert _extract_period({"context": "CurrentYearInstant"}) == "当期"
        assert _extract_period({"context": "Prior1YearDuration"}) == "前期"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _make_filing() -> Filing:
    return Filing(
        doc_id="S100TEST",
        edinet_code="E99999",
        company_name="テスト株式会社",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2025, 6, 20),
    )


class TestNormalizeItems:
    def test_basic_pl_normalization(self) -> None:
        taxonomy = _load_taxonomy()
        raw = [
            {"element": "Revenue", "value": 100000, "context": "CurrentYearDuration"},
            {"element": "Revenue", "value": 90000, "context": "PriorYearDuration"},
            {"element": "OperatingProfit", "value": 20000, "context": "CurrentYearDuration"},
        ]
        result = _normalize_items(raw, "income_statement", taxonomy)

        assert len(result) == 2
        assert result[0]["科目"] == "売上高"
        assert result[0]["当期"] == 100000
        assert result[0]["前期"] == 90000
        assert result[1]["科目"] == "営業利益"
        assert result[1]["当期"] == 20000

    def test_jgaap_elements(self) -> None:
        taxonomy = _load_taxonomy()
        raw = [
            {"element": "NetSales", "value": 50000, "context": "Current"},
            {"element": "OperatingIncome", "value": 10000, "context": "Current"},
        ]
        result = _normalize_items(raw, "income_statement", taxonomy)

        assert result[0]["科目"] == "売上高"
        assert result[1]["科目"] == "営業利益"

    def test_preserves_display_order(self) -> None:
        taxonomy = _load_taxonomy()
        # Items in reverse order
        raw = [
            {"element": "OperatingProfit", "value": 20000, "context": "Current"},
            {"element": "Revenue", "value": 100000, "context": "Current"},
        ]
        result = _normalize_items(raw, "income_statement", taxonomy)

        # Revenue should come before OperatingProfit in output
        labels = [r["科目"] for r in result]
        assert labels.index("売上高") < labels.index("営業利益")

    def test_unknown_elements_ignored(self) -> None:
        taxonomy = _load_taxonomy()
        raw = [
            {"element": "Revenue", "value": 100000, "context": "Current"},
            {"element": "UnknownElement", "value": 999, "context": "Current"},
        ]
        result = _normalize_items(raw, "income_statement", taxonomy)
        assert len(result) == 1

    def test_empty_input(self) -> None:
        taxonomy = _load_taxonomy()
        assert _normalize_items([], "income_statement", taxonomy) == []

    def test_bs_normalization(self) -> None:
        taxonomy = _load_taxonomy()
        raw = [
            {"element": "TotalAssets", "value": 500000, "context": "Current"},
            {"element": "TotalLiabilities", "value": 300000, "context": "Current"},
        ]
        result = _normalize_items(raw, "balance_sheet", taxonomy)
        labels = [r["科目"] for r in result]
        assert "資産合計" in labels
        assert "負債合計" in labels

    def test_cf_normalization(self) -> None:
        taxonomy = _load_taxonomy()
        raw = [
            {"element": "CashFlowsFromOperatingActivities", "value": 80000, "context": "Current"},
        ]
        result = _normalize_items(raw, "cash_flow", taxonomy)
        assert result[0]["科目"] == "営業活動によるキャッシュ・フロー"

    def test_ifrs_suffix_stripping_in_normalization(self) -> None:
        """IFRS suffixes should be stripped before matching taxonomy."""
        taxonomy = _load_taxonomy()
        raw = [
            {
                "element": "TotalAssetsIFRSSummaryOfBusinessResults",
                "value": 90000000,
                "context": "CurrentYearInstant",
            },
            {
                "element": "TotalAssetsIFRSSummaryOfBusinessResults",
                "value": 80000000,
                "context": "Prior1YearInstant",
            },
        ]
        result = _normalize_items(raw, "balance_sheet", taxonomy)
        assert len(result) >= 1
        assert result[0]["科目"] == "資産合計"
        assert result[0]["当期"] == 90000000
        assert result[0]["前期"] == 80000000

    def test_ifrs_cf_normalization(self) -> None:
        """IFRS CF elements should be normalized after suffix stripping."""
        taxonomy = _load_taxonomy()
        raw = [
            {
                "element": "CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults",
                "value": 4000000,
                "context": "CurrentYearDuration",
            },
            {
                "element": "NetCashProvidedByUsedInInvestingActivitiesIFRS",
                "value": -2000000,
                "context": "CurrentYearDuration",
            },
        ]
        result = _normalize_items(raw, "cash_flow", taxonomy)
        labels = [r["科目"] for r in result]
        assert "営業活動によるキャッシュ・フロー" in labels
        assert "投資活動によるキャッシュ・フロー" in labels

    def test_non_consolidated_filtered_out(self) -> None:
        """Non-consolidated data should be skipped, keeping consolidated."""
        taxonomy = _load_taxonomy()
        raw = [
            {
                "element": "TotalAssets",
                "value": 90000000,
                "context": "CurrentYearInstant",
            },
            {
                "element": "TotalAssets",
                "value": 30000000,
                "context": "CurrentYearInstant_NonConsolidatedMember",
            },
        ]
        result = _normalize_items(raw, "balance_sheet", taxonomy)
        # Only consolidated value should be kept
        total_assets = next(r for r in result if r["科目"] == "資産合計")
        assert total_assets["当期"] == 90000000


class TestNormalizeStatement:
    def test_normalizes_all_statements(self) -> None:
        filing = _make_filing()
        stmt = FinancialStatement(
            filing=filing,
            income_statement=StatementData(
                items=[
                    {"element": "Revenue", "value": 100000, "context": "CurrentYearDuration"},
                    {"element": "Revenue", "value": 90000, "context": "PriorYearDuration"},
                ],
                label="IncomeStatement",
            ),
            balance_sheet=StatementData(
                items=[
                    {"element": "TotalAssets", "value": 500000, "context": "Current"},
                ],
                label="BalanceSheet",
            ),
            accounting_standard=AccountingStandard.IFRS,
        )

        result = normalize_statement(stmt)

        # Income statement normalized
        assert result.income_statement["売上高"]["当期"] == 100000
        assert result.income_statement["売上高"]["前期"] == 90000

        # Balance sheet normalized
        assert result.balance_sheet["資産合計"]["当期"] == 500000

        # Raw data preserved
        assert len(result.income_statement.raw_items) == 2
        assert result.income_statement.raw_items[0]["element"] == "Revenue"

        # Filing preserved
        assert result.filing.doc_id == "S100TEST"
        assert result.accounting_standard == AccountingStandard.IFRS

    def test_empty_statement_unchanged(self) -> None:
        filing = _make_filing()
        stmt = FinancialStatement(filing=filing)
        result = normalize_statement(stmt)
        assert not result.income_statement
        assert not result.balance_sheet

    def test_unmatched_elements_keep_raw(self) -> None:
        filing = _make_filing()
        stmt = FinancialStatement(
            filing=filing,
            income_statement=StatementData(
                items=[{"element": "CompletelyUnknown", "value": 999}],
                label="IncomeStatement",
            ),
        )
        result = normalize_statement(stmt)
        # When nothing matches, raw items are kept
        assert result.income_statement.items == [{"element": "CompletelyUnknown", "value": 999}]


class TestStatementDataAccess:
    def test_getitem(self) -> None:
        data = StatementData(
            items=[
                {"科目": "売上高", "当期": 100000, "前期": 90000},
                {"科目": "営業利益", "当期": 20000},
            ],
            label="IncomeStatement",
        )
        assert data["売上高"] == {"当期": 100000, "前期": 90000}
        assert data["営業利益"] == {"当期": 20000}

    def test_getitem_missing_raises(self) -> None:
        import pytest

        data = StatementData(
            items=[{"科目": "売上高", "当期": 100000}],
            label="IncomeStatement",
        )
        with pytest.raises(KeyError):
            data["存在しない科目"]

    def test_get_with_default(self) -> None:
        data = StatementData(
            items=[{"科目": "売上高", "当期": 100000}],
            label="IncomeStatement",
        )
        assert data.get("売上高") == {"当期": 100000}
        assert data.get("存在しない", None) is None

    def test_labels(self) -> None:
        data = StatementData(
            items=[
                {"科目": "売上高", "当期": 100000},
                {"科目": "営業利益", "当期": 20000},
            ],
        )
        assert data.labels == ["売上高", "営業利益"]

    def test_labels_empty(self) -> None:
        data = StatementData(items=[{"element": "Revenue", "value": 100}])
        assert data.labels == []


class TestGetTaxonomyLabels:
    def test_income_statement(self) -> None:
        labels = get_taxonomy_labels("income_statement")
        assert len(labels) > 0
        assert labels[0]["label"] == "売上高"
        assert labels[0]["label_en"] == "Revenue"
        assert labels[0]["id"] == "revenue"

    def test_balance_sheet(self) -> None:
        labels = get_taxonomy_labels("balance_sheet")
        ids = [item["id"] for item in labels]
        assert "total_assets" in ids
        assert "net_assets" in ids

    def test_cash_flow(self) -> None:
        labels = get_taxonomy_labels("cash_flow")
        ids = [item["id"] for item in labels]
        assert "operating_cf" in ids

    def test_cash_flow_statement_alias(self) -> None:
        """'cash_flow_statement' maps to 'cash_flow' in YAML."""
        labels = get_taxonomy_labels("cash_flow_statement")
        assert len(labels) > 0
        assert labels == get_taxonomy_labels("cash_flow")

    def test_unknown_returns_empty(self) -> None:
        assert get_taxonomy_labels("nonexistent") == []
