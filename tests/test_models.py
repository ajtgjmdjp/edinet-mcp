"""Tests for edinet_mcp.models."""

from __future__ import annotations

import datetime
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError

from edinet_mcp.models import (
    AccountingStandard,
    Company,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)


class TestDocType:
    def test_from_label_annual(self) -> None:
        assert DocType.from_label("annual_report") == DocType.ANNUAL_REPORT

    def test_from_label_quarterly(self) -> None:
        assert DocType.from_label("quarterly_report") == DocType.QUARTERLY_REPORT

    def test_from_code_direct(self) -> None:
        assert DocType.from_label("120") == DocType.ANNUAL_REPORT

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            DocType.from_label("nonexistent_type")


class TestCompany:
    def test_frozen(self, sample_company: Company) -> None:
        with pytest.raises(ValidationError):
            sample_company.name = "Changed"  # type: ignore[misc]

    def test_fields(self, sample_company: Company) -> None:
        assert sample_company.edinet_code == "E02144"
        assert sample_company.ticker == "7203"
        assert sample_company.is_listed is True


class TestFiling:
    def test_from_api_row(self, sample_api_row: dict[str, Any]) -> None:
        filing = Filing.from_api_row(sample_api_row)
        assert filing.doc_id == "S100VVC2"
        assert filing.edinet_code == "E02144"
        assert filing.doc_type == DocType.ANNUAL_REPORT
        assert filing.filing_date == datetime.date(2025, 6, 20)
        assert filing.period_start == datetime.date(2024, 4, 1)
        assert filing.period_end == datetime.date(2025, 3, 31)
        assert filing.has_xbrl is True
        assert filing.has_pdf is True
        assert "有価証券報告書" in filing.description


class TestStatementData:
    def test_to_polars(self, sample_statement_data: StatementData) -> None:
        df = sample_statement_data.to_polars()
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 3
        assert "element" in df.columns
        assert "value" in df.columns

    def test_to_dicts(self, sample_statement_data: StatementData) -> None:
        dicts = sample_statement_data.to_dicts()
        assert len(dicts) == 3
        assert dicts[0]["element"] == "Revenue"

    def test_len_and_bool(self) -> None:
        empty = StatementData()
        assert len(empty) == 0
        assert not empty

        data = StatementData(items=[{"a": 1}])
        assert len(data) == 1
        assert data

    def test_empty_to_polars(self) -> None:
        empty = StatementData()
        df = empty.to_polars()
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0


class TestFinancialStatement:
    def test_all_statements(self, sample_financial_statement: FinancialStatement) -> None:
        stmts = sample_financial_statement.all_statements
        assert "income_statement" in stmts
        assert stmts["income_statement"].label == "IncomeStatement"

    def test_accounting_standard(self, sample_financial_statement: FinancialStatement) -> None:
        assert sample_financial_statement.accounting_standard == AccountingStandard.IFRS
