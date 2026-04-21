"""Security-focused tests for :mod:`edinet_mcp.parser`.

These tests verify that `XBRLParser` safely handles hostile XBRL input:
entity-expansion (billion-laughs), external entity references (XXE), and
mixed (good + malicious) directories. `defusedxml` raises subclasses of
`DefusedXmlException` (a `ValueError` subclass), which is *not* an
`xml.etree.ElementTree.ParseError`; without an explicit catch these
propagate and abort parsing of the entire filing ZIP.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from edinet_mcp.models import DocType, Filing, FinancialStatement
from edinet_mcp.parser import XBRLParser

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Hostile XBRL samples
# ---------------------------------------------------------------------------

# Billion-laughs: exponential entity expansion. defusedxml's
# `EntitiesForbidden` fires on the first nested entity definition.
_MALICIOUS_ENTITIES = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <lolz>&lol3;</lolz>
</xbrli:xbrl>
"""

# XXE: external entity referencing a local file. defusedxml raises
# `DTDForbidden` (DTDs disabled) before the external reference is resolved.
_MALICIOUS_XXE = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ELEMENT foo ANY>
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <foo>&xxe;</foo>
</xbrli:xbrl>
"""

# Minimal well-formed XBRL with one jppfs_cor financial fact. `Revenue`
# routes into `income_statement` via `_categorize_facts`.
_GOOD_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:jppfs_cor="http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-11-01/jppfs_cor">
  <xbrli:context id="CurrentYear">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E99999</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2024-03-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>
  <jppfs_cor:Revenue contextRef="CurrentYear" unitRef="JPY" decimals="0">
    1000000
  </jppfs_cor:Revenue>
</xbrli:xbrl>
"""


def _make_filing() -> Filing:
    """Build a Filing that satisfies the real Pydantic model.

    `doc_type` must be a `DocType` enum and `filing_date` must be a
    `datetime.date` — both are required fields on the frozen model.
    """
    return Filing(
        doc_id="S100TEST",
        edinet_code="E99999",
        company_name="テスト株式会社",
        doc_type=DocType.ANNUAL_REPORT,
        filing_date=datetime.date(2024, 6, 28),
        period_start=datetime.date(2023, 4, 1),
        period_end=datetime.date(2024, 3, 31),
        has_xbrl=True,
        description="有価証券報告書 (security test fixture)",
    )


class TestXBRLParserSecurity:
    """Regression tests for defusedxml rejection handling."""

    def test_parser_rejects_billion_laughs(self, tmp_path: Path) -> None:
        """Entity-expansion XBRL must not raise; returns empty facts."""
        xbrl = tmp_path / "malicious_entities.xbrl"
        xbrl.write_text(_MALICIOUS_ENTITIES, encoding="utf-8")

        parser = XBRLParser()
        # If `EntitiesForbidden` were uncaught, this call would raise.
        facts = parser._extract_xbrl_facts(xbrl)

        assert facts == []

    def test_parser_rejects_xxe(self, tmp_path: Path) -> None:
        """XXE (external entity) XBRL must not raise; returns empty facts."""
        xbrl = tmp_path / "xxe.xbrl"
        xbrl.write_text(_MALICIOUS_XXE, encoding="utf-8")

        parser = XBRLParser()
        # If `DTDForbidden` were uncaught, this call would raise.
        facts = parser._extract_xbrl_facts(xbrl)

        assert facts == []

    def test_parser_continues_after_rejected_sibling(self, tmp_path: Path) -> None:
        """One hostile XBRL must not abort parsing of well-formed siblings."""
        (tmp_path / "bad.xbrl").write_text(_MALICIOUS_ENTITIES, encoding="utf-8")
        (tmp_path / "good.xbrl").write_text(_GOOD_XBRL, encoding="utf-8")

        filing = _make_filing()
        stmt = FinancialStatement(filing=filing)
        parser = XBRLParser()

        # Sanity: verify the good file alone yields a jppfs_cor:Revenue fact,
        # so the sibling-continuation assertion below is meaningful.
        good_facts = parser._extract_xbrl_facts(tmp_path / "good.xbrl")
        assert any(f["element"] == "Revenue" and "jppfs" in f["namespace"] for f in good_facts), (
            f"Good XBRL fixture produced no Revenue fact: {good_facts!r}"
        )

        # The real check: must not raise on the mixed directory, and the
        # good file's Revenue fact must end up routed into income_statement.
        found = parser._parse_xbrl_files(tmp_path, stmt)

        assert found >= 1, "Sibling good.xbrl was not processed after bad.xbrl"
        assert stmt.income_statement, "income_statement should have been populated"
        revenue_items = [
            item for item in stmt.income_statement.items if item.get("element") == "Revenue"
        ]
        assert revenue_items, (
            f"Revenue fact missing from income_statement: {stmt.income_statement.items!r}"
        )
        assert revenue_items[0]["value"] == 1000000
