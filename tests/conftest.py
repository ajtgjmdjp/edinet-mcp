"""Shared test fixtures for edinet-mcp."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

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
        sec_code="72030",
        corporate_number="2180001012461",
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


_JPCRP_NS_2023 = "http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2023-11-01/jpcrp_cor"

NARRATIVE_XBRL_BODY = (
    '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
    "&lt;h3&gt;事業等のリスク&lt;/h3&gt;&lt;p&gt;為替変動リスクがあります。&lt;/p&gt;"
    "</jpcrp_cor:BusinessRisksTextBlock>"
)


def make_narrative_zip(tmp_path: Path, body: str = NARRATIVE_XBRL_BODY) -> Path:
    """Build a minimal EDINET-layout ZIP with a synthetic XBRL instance."""
    import zipfile

    instance = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:jpcrp_cor="{_JPCRP_NS_2023}">
  <xbrli:context id="FilingDateInstant">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-06-20</xbrli:instant></xbrli:period>
  </xbrli:context>
  {body}
</xbrli:xbrl>
"""
    zip_path = tmp_path / "narrative.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("XBRL/PublicDoc/jpcrp030000-asr-001_test.xbrl", instance)
    return zip_path
