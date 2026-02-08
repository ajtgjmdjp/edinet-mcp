"""XBRL and TSV parser for EDINET filing documents.

Handles the extraction and structuring of financial data from EDINET's
XBRL/TSV/CSV files into :class:`FinancialStatement` objects.

The EDINET API returns a ZIP file containing:
- XBRL instance files (XML)
- TSV summary files (for quick access to key financial items)
- PDF renditions
- manifest.xml

This parser supports two extraction paths:
1. **TSV-based** (fast, structured): Parse the TSV files that EDINET provides
   alongside the XBRL. These are pre-extracted tabular data.
2. **XBRL-based** (comprehensive): Parse the raw XBRL instance documents
   for full coverage.

The TSV path is used by default as it's faster and covers the most common
use cases (BS, PL, CF, summary). The XBRL path is available for deeper
extraction needs.
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from loguru import logger

from edinet_mcp.models import (
    AccountingStandard,
    Filing,
    FinancialStatement,
    StatementData,
)

# XBRL namespace prefixes used in EDINET filings
_NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "jppfs_cor": "http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor",
    "jpcrp_cor": "http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2023-11-01/jpcrp_cor",
    "jpdei_cor": "http://disclosure.edinet-fsa.go.jp/taxonomy/jpdei/2013-01-01/jpdei_cor",
}

# TSV file patterns in EDINET ZIP extracts
_TSV_PATTERNS = {
    "balance_sheet": re.compile(r"jpcrp.*BS.*\.tsv$", re.IGNORECASE),
    "income_statement": re.compile(r"jpcrp.*PL.*\.tsv$", re.IGNORECASE),
    "cash_flow_statement": re.compile(r"jpcrp.*CF.*\.tsv$", re.IGNORECASE),
    "summary": re.compile(r"jpcrp.*Summary.*\.tsv$", re.IGNORECASE),
}


class XBRLParser:
    """Parser for EDINET XBRL/TSV financial data.

    This parser extracts structured financial data from the files
    contained within a downloaded EDINET document ZIP.
    """

    def parse_directory(self, filing: Filing, directory: Path) -> FinancialStatement:
        """Parse all financial data from an extracted EDINET ZIP directory.

        Attempts TSV-based extraction first (faster), falling back to
        XBRL parsing for any missing statements.

        Args:
            filing: The source filing metadata.
            directory: Path to the extracted ZIP contents.

        Returns:
            Populated :class:`FinancialStatement`.
        """
        stmt = FinancialStatement(filing=filing)

        # Try TSV path first
        tsv_found = self._parse_tsv_files(directory, stmt)
        if tsv_found:
            logger.debug(f"Parsed {tsv_found} statement(s) from TSV files")

        # Try XBRL path for any missing data
        if not stmt.balance_sheet or not stmt.income_statement:
            xbrl_found = self._parse_xbrl_files(directory, stmt)
            if xbrl_found:
                logger.debug(f"Parsed {xbrl_found} additional item(s) from XBRL")

        # Detect accounting standard
        stmt.accounting_standard = self._detect_accounting_standard(directory)

        return stmt

    # ------------------------------------------------------------------
    # TSV parsing
    # ------------------------------------------------------------------

    def _parse_tsv_files(self, directory: Path, stmt: FinancialStatement) -> int:
        """Scan for and parse TSV files in the directory."""
        found = 0
        all_files = list(directory.rglob("*"))

        for stmt_name, pattern in _TSV_PATTERNS.items():
            matching = [f for f in all_files if pattern.search(f.name)]
            if not matching:
                continue

            tsv_file = matching[0]
            items = self._read_tsv(tsv_file)
            if items:
                data = StatementData(items=items, label=stmt_name)
                setattr(stmt, stmt_name, data)
                found += 1
                logger.debug(f"  {stmt_name}: {len(items)} rows from {tsv_file.name}")

        return found

    @staticmethod
    def _read_tsv(path: Path) -> list[dict[str, Any]]:
        """Read a TSV file into a list of dicts."""
        items: list[dict[str, Any]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="cp932", errors="replace")

        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        for row in reader:
            cleaned = {k.strip(): _coerce_value(v) for k, v in row.items() if k}
            if cleaned:
                items.append(cleaned)
        return items

    # ------------------------------------------------------------------
    # XBRL parsing
    # ------------------------------------------------------------------

    def _parse_xbrl_files(self, directory: Path, stmt: FinancialStatement) -> int:
        """Parse XBRL instance files for financial facts."""
        xbrl_files = list(directory.rglob("*.xbrl")) + list(directory.rglob("*.xml"))
        # Filter to likely instance documents
        xbrl_files = [
            f
            for f in xbrl_files
            if "manifest" not in f.name.lower()
            and "linkbase" not in f.name.lower()
            and "schema" not in f.name.lower()
        ]

        found = 0
        for xbrl_file in xbrl_files:
            try:
                facts = self._extract_xbrl_facts(xbrl_file)
                if facts:
                    found += len(facts)
                    self._categorize_facts(facts, stmt)
            except ET.ParseError as e:
                logger.warning(f"Failed to parse {xbrl_file.name}: {e}")

        return found

    # Maximum XBRL file size to parse (50 MB).  Protects against
    # decompression bombs and billion-laughs-style entity expansion.
    # Source files come from EDINET's HTTPS API so the risk is minimal,
    # but a size guard is cheap defense-in-depth.
    _MAX_XBRL_SIZE = 50 * 1024 * 1024

    def _extract_xbrl_facts(self, path: Path) -> list[dict[str, Any]]:
        """Extract financial facts from an XBRL instance document."""
        facts: list[dict[str, Any]] = []

        file_size = path.stat().st_size
        if file_size > self._MAX_XBRL_SIZE:
            logger.warning(f"Skipping oversized XBRL file ({file_size} bytes): {path.name}")
            return facts

        try:
            tree = ET.parse(path)
        except ET.ParseError:
            return facts

        root = tree.getroot()

        for elem in root.iter():
            tag = elem.tag
            text = elem.text
            if text is None or not text.strip():
                continue

            # Extract namespace and local name
            if tag.startswith("{"):
                ns_end = tag.index("}")
                namespace = tag[1:ns_end]
                local_name = tag[ns_end + 1 :]
            else:
                namespace = ""
                local_name = tag

            # Only process financial fact elements
            if not _is_financial_element(namespace, local_name):
                continue

            context_ref = elem.get("contextRef", "")
            unit_ref = elem.get("unitRef", "")
            decimals = elem.get("decimals", "")

            facts.append(
                {
                    "element": local_name,
                    "namespace": namespace,
                    "value": _coerce_value(text.strip()),
                    "context": context_ref,
                    "unit": unit_ref,
                    "decimals": decimals,
                }
            )

        return facts

    @staticmethod
    def _categorize_facts(facts: list[dict[str, Any]], stmt: FinancialStatement) -> None:
        """Route parsed XBRL facts into the appropriate statement."""
        bs_items = []
        pl_items = []
        cf_items = []

        for fact in facts:
            elem = fact["element"].lower()
            if any(k in elem for k in ("asset", "liabilit", "equity", "netasset")):
                bs_items.append(fact)
            elif any(
                k in elem for k in ("revenue", "profit", "loss", "income", "expense", "sales")
            ):
                pl_items.append(fact)
            elif "cashflow" in elem or "cash" in elem:
                cf_items.append(fact)

        if bs_items and not stmt.balance_sheet:
            stmt.balance_sheet = StatementData(items=bs_items, label="BalanceSheet")
        if pl_items and not stmt.income_statement:
            stmt.income_statement = StatementData(items=pl_items, label="IncomeStatement")
        if cf_items and not stmt.cash_flow_statement:
            stmt.cash_flow_statement = StatementData(items=cf_items, label="CashFlowStatement")

    def _detect_accounting_standard(self, directory: Path) -> AccountingStandard:
        """Detect which accounting standard the filing uses."""
        all_files = [f.name.lower() for f in directory.rglob("*")]
        all_text = " ".join(all_files)

        if "ifrs" in all_text:
            return AccountingStandard.IFRS
        if "usgaap" in all_text or "us-gaap" in all_text:
            return AccountingStandard.US_GAAP
        if "jppfs" in all_text or "jpcrp" in all_text:
            return AccountingStandard.JGAAP

        return AccountingStandard.UNKNOWN


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _coerce_value(value: str | None) -> Any:
    """Attempt to convert a string value to a numeric type."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None

    # Try integer
    try:
        return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    return value


def _is_financial_element(namespace: str, local_name: str) -> bool:
    """Check if an XBRL element is likely a financial fact (not metadata)."""
    # Filter out common non-financial namespaces
    skip_ns = {"http://www.xbrl.org/2003/linkbase", "http://www.w3.org/1999/xlink"}
    if namespace in skip_ns:
        return False

    # Filter out common non-fact elements
    skip_names = {"context", "unit", "schemaRef", "linkbaseRef", "roleRef"}
    if local_name in skip_names:
        return False

    # EDINET financial fact namespaces
    financial_ns_patterns = ("jppfs", "jpcrp", "jpdei", "jpigp", "ifrs")
    return any(p in namespace for p in financial_ns_patterns)
