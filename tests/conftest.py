"""Shared test fixtures for edinet-mcp."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from edinet_mcp.models import (
    AccountingStandard,
    Company,
    DocType,
    Filing,
    FinancialStatement,
    StatementData,
)


@pytest.fixture()
def sample_company() -> Company:
    return Company(
        edinet_code="E02144",
        name="トヨタ自動車株式会社",
        name_en="Toyota Motor Corporation",
        ticker="7203",
        industry="輸送用機器",
        accounting_standard=AccountingStandard.IFRS,
        is_listed=True,
    )


@pytest.fixture()
def sample_filing() -> Filing:
    return Filing(
        doc_id="S100VVC2",
        edinet_code="E02144",
        company_name="トヨタ自動車株式会社",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2025, 6, 20),
        period_start=datetime.date(2024, 4, 1),
        period_end=datetime.date(2025, 3, 31),
        has_xbrl=True,
        has_pdf=True,
        description="有価証券報告書",
    )


@pytest.fixture()
def sample_statement_data() -> StatementData:
    return StatementData(
        items=[
            {"element": "Revenue", "value": 45095325000000, "unit": "JPY"},
            {"element": "OperatingProfit", "value": 5352934000000, "unit": "JPY"},
            {"element": "NetIncome", "value": 4944898000000, "unit": "JPY"},
        ],
        label="IncomeStatement",
    )


@pytest.fixture()
def sample_financial_statement(
    sample_filing: Filing, sample_statement_data: StatementData
) -> FinancialStatement:
    return FinancialStatement(
        filing=sample_filing,
        income_statement=sample_statement_data,
        accounting_standard=AccountingStandard.IFRS,
    )


@pytest.fixture()
def sample_api_row() -> dict[str, Any]:
    """A raw row from the EDINET API v2 document list."""
    return {
        "seqNumber": 1,
        "docID": "S100VVC2",
        "edinetCode": "E02144",
        "secCode": "72030",
        "JCN": "1180301018771",
        "filerName": "トヨタ自動車株式会社",
        "fundCode": None,
        "ordinanceCode": "010",
        "formCode": "030000",
        "docTypeCode": "120",
        "periodStart": "2024-04-01",
        "periodEnd": "2025-03-31",
        "submitDateTime": "2025-06-20T09:00:00+09:00",
        "docDescription": "有価証券報告書 第121期",
        "issuerEdinetCode": None,
        "subjectEdinetCode": None,
        "subsidiaryEdinetCode": None,
        "currentReportReason": None,
        "parentDocID": None,
        "opeDateTime": None,
        "withdrawalStatus": "0",
        "docInfoEditStatus": "0",
        "disclosureStatus": "0",
        "xbrlFlag": True,
        "pdfFlag": True,
        "attachDocFlag": False,
        "englishDocFlag": False,
        "csvFlag": True,
    }
