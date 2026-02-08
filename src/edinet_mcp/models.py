"""Domain models for EDINET financial data.

All public models use Pydantic v2 for validation and serialization.
Financial statement data provides dual-format output via `to_polars()` and `to_pandas()`.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DocType(str, Enum):
    """EDINET document type codes (docTypeCode)."""

    ANNUAL_REPORT = "120"  # 有価証券報告書
    QUARTERLY_REPORT = "140"  # 四半期報告書
    SEMIANNUAL_REPORT = "160"  # 半期報告書
    EXTRAORDINARY_REPORT = "180"  # 臨時報告書
    SHELF_REGISTRATION = "030"  # 有価証券届出書
    LARGE_SHAREHOLDING = "350"  # 大量保有報告書
    OTHER = "000"  # その他 (未知のdocTypeCode用)

    @classmethod
    def from_label(cls, label: str) -> DocType:
        """Resolve from a human-readable label.

        >>> DocType.from_label("annual_report")
        <DocType.ANNUAL_REPORT: '120'>
        """
        mapping = {
            "annual_report": cls.ANNUAL_REPORT,
            "quarterly_report": cls.QUARTERLY_REPORT,
            "semiannual_report": cls.SEMIANNUAL_REPORT,
            "extraordinary_report": cls.EXTRAORDINARY_REPORT,
            "large_shareholding": cls.LARGE_SHAREHOLDING,
        }
        if label in mapping:
            return mapping[label]
        # Try direct code
        return cls(label)


class AccountingStandard(str, Enum):
    """Accounting standard used in a filing."""

    JGAAP = "J-GAAP"
    IFRS = "IFRS"
    US_GAAP = "US-GAAP"
    UNKNOWN = "Unknown"


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


class Company(BaseModel):
    """An EDINET-registered entity (company or fund).

    Attributes:
        edinet_code: Unique EDINET identifier (e.g. ``"E02144"``).
        name: Official company name in Japanese.
        name_en: English name, if available.
        ticker: Securities code on TSE (e.g. ``"7203"``), if listed.
        industry: Industry classification.
        accounting_standard: Primary accounting standard.
    """

    edinet_code: str
    name: str
    name_en: str | None = None
    ticker: str | None = None
    industry: str | None = None
    accounting_standard: AccountingStandard = AccountingStandard.UNKNOWN
    is_listed: bool = False

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------


class Filing(BaseModel):
    """A single document filing on EDINET.

    Attributes:
        doc_id: Unique document identifier (e.g. ``"S100VVC2"``).
        edinet_code: Filer's EDINET code.
        company_name: Filer display name.
        doc_type: Document type code.
        filing_date: Date the document was submitted.
        period_start: Start of the reporting period.
        period_end: End of the reporting period.
        has_xbrl: Whether XBRL data is available.
        has_pdf: Whether a PDF is available.
        has_csv: Whether CSV data is available.
        description: Human-readable document description.
    """

    doc_id: str
    edinet_code: str
    company_name: str
    doc_type: DocType
    filing_date: datetime.date
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    has_xbrl: bool = False
    has_pdf: bool = False
    has_csv: bool = False
    description: str = ""

    model_config = {"frozen": True}

    @classmethod
    def from_api_row(cls, row: dict[str, Any]) -> Filing:
        """Construct from an EDINET API v2 ``results[]`` item."""
        raw_code = row.get("docTypeCode")
        try:
            doc_type = DocType(raw_code) if raw_code else DocType.OTHER
        except ValueError:
            doc_type = DocType.OTHER
        return cls(
            doc_id=row["docID"],
            edinet_code=row.get("edinetCode") or "",
            company_name=row.get("filerName") or "",
            doc_type=doc_type,
            filing_date=_parse_date(row.get("submitDateTime") or ""),
            period_start=_parse_date_or_none(row.get("periodStart")),
            period_end=_parse_date_or_none(row.get("periodEnd")),
            has_xbrl=bool(row.get("xbrlFlag")),
            has_pdf=bool(row.get("pdfFlag")),
            has_csv=bool(row.get("csvFlag")),
            description=row.get("docDescription") or "",
        )


# ---------------------------------------------------------------------------
# Financial Statement Data
# ---------------------------------------------------------------------------


class StatementData(BaseModel):
    """A single financial statement (BS / PL / CF).

    After normalization, ``items`` contains canonical rows::

        [{"科目": "売上高", "当期": 45095325, "前期": 37154298}, ...]

    Original parsed data is preserved in ``raw_items`` for advanced use.

    Attributes:
        items: Financial data rows (normalized when available).
        raw_items: Original parsed rows before normalization.
        label: Human-readable label (e.g. ``"IncomeStatement"``).
    """

    items: list[dict[str, Any]] = Field(default_factory=list)
    raw_items: list[dict[str, Any]] = Field(default_factory=list)
    label: str = ""

    def __getitem__(self, label: str) -> dict[str, Any]:
        """Look up a line item by its Japanese label.

        >>> stmt.income_statement["売上高"]
        {"当期": 45095325, "前期": 37154298}
        """
        for item in self.items:
            if item.get("科目") == label:
                return {k: v for k, v in item.items() if k != "科目"}
        raise KeyError(f"'{label}' not found in {self.label}")

    def get(self, label: str, default: Any = None) -> Any:
        """Look up a line item, returning *default* if not found."""
        try:
            return self[label]
        except KeyError:
            return default

    @property
    def labels(self) -> list[str]:
        """Return all available line item labels (科目)."""
        return [item["科目"] for item in self.items if "科目" in item]

    def to_polars(self) -> pl.DataFrame:
        """Convert to a Polars DataFrame."""
        if not self.items:
            return pl.DataFrame()
        return pl.DataFrame(self.items)

    def to_pandas(self) -> Any:
        """Convert to a pandas DataFrame.

        Requires ``pandas`` to be installed (``pip install edinet-mcp[pandas]``).
        """
        return self.to_polars().to_pandas()

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return list-of-dicts representation."""
        return self.items

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return len(self.items) > 0


class FinancialStatement(BaseModel):
    """Parsed financial statements for a single filing.

    Contains balance sheet, income statement, and cash flow statement,
    each as a :class:`StatementData` with dual-format output.

    Attributes:
        filing: The source filing metadata.
        balance_sheet: BS data.
        income_statement: PL data.
        cash_flow_statement: CF data.
        summary: Summary/highlight data, if available.
        accounting_standard: Detected accounting standard.
    """

    filing: Filing
    balance_sheet: StatementData = Field(
        default_factory=lambda: StatementData(label="BalanceSheet")
    )
    income_statement: StatementData = Field(
        default_factory=lambda: StatementData(label="IncomeStatement")
    )
    cash_flow_statement: StatementData = Field(
        default_factory=lambda: StatementData(label="CashFlowStatement")
    )
    summary: StatementData | None = None
    accounting_standard: AccountingStandard = AccountingStandard.UNKNOWN

    @property
    def all_statements(self) -> dict[str, StatementData]:
        """Return all non-empty statements as a name→data mapping."""
        stmts: dict[str, StatementData] = {}
        if self.balance_sheet:
            stmts["balance_sheet"] = self.balance_sheet
        if self.income_statement:
            stmts["income_statement"] = self.income_statement
        if self.cash_flow_statement:
            stmts["cash_flow_statement"] = self.cash_flow_statement
        if self.summary:
            stmts["summary"] = self.summary
        return stmts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime.date:
    """Parse an ISO-ish date or datetime string.

    Falls back to ``datetime.date.min`` for missing values so that filings
    without a submit date sort as the *oldest*, not the newest.
    """
    if not value:
        return datetime.date.min
    # EDINET returns dates as "YYYY-MM-DD" or datetimes as "YYYY-MM-DDTHH:MM:SS+09:00"
    return datetime.date.fromisoformat(value[:10])


def _parse_date_or_none(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None
