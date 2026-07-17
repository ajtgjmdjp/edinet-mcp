"""Tests for edinet_mcp._narrative (qualitative TextBlock extraction)."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from edinet_mcp._narrative import (
    NARRATIVE_SECTIONS,
    extract_narratives,
    html_to_text,
)

_JPCRP_NS = "http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2023-11-01/jpcrp_cor"


def _instance(body: str) -> str:
    """Wrap facts in a minimal XBRL instance with common contexts."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
            xmlns:jpcrp_cor="{_JPCRP_NS}">
  <xbrli:context id="FilingDateInstant">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-06-20</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="CurrentYearDuration">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2024-04-01</xbrli:startDate>
      <xbrli:endDate>2025-03-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="Prior1YearDuration">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2023-04-01</xbrli:startDate>
      <xbrli:endDate>2024-03-31</xbrli:endDate>
    </xbrli:period>
  </xbrli:context>
  <xbrli:context id="FilingDateInstant_TestMember">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember
            dimension="jpcrp_cor:TestAxis">jpcrp_cor:TestMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-06-20</xbrli:instant></xbrli:period>
  </xbrli:context>
  {body}
</xbrli:xbrl>
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.xbrl"
    p.write_text(content, encoding="utf-8")
    return p


_PERIOD_END = datetime.date(2025, 3, 31)


class TestHtmlToText:
    def test_paragraphs_become_lines(self) -> None:
        out = html_to_text("<p>first</p><p>second</p>")
        assert "first" in out
        assert "second" in out
        assert out.index("first") < out.index("second")
        assert "\n" in out

    def test_headings_preserved_as_lines(self) -> None:
        out = html_to_text("<h3>Section Title</h3><p>body</p>")
        assert out.splitlines()[0] == "Section Title"

    def test_style_and_script_dropped(self) -> None:
        out = html_to_text("<style>p { color: red }</style><p>keep</p><script>alert(1)</script>")
        assert out == "keep"

    def test_inline_styles_dropped(self) -> None:
        out = html_to_text('<p style="margin-left: 24px">text</p>')
        assert out == "text"

    def test_br_breaks_line(self) -> None:
        out = html_to_text("<p>a<br/>b</p>")
        assert "a\nb" in out

    def test_table_rows_tab_joined(self) -> None:
        out = html_to_text(
            "<table><tr><td>k1</td><td>v1</td></tr><tr><td>k2</td><td>v2</td></tr></table>"
        )
        lines = [ln for ln in out.splitlines() if ln]
        assert lines == ["k1\tv1", "k2\tv2"]

    def test_list_items_get_markers(self) -> None:
        out = html_to_text("<ul><li>one</li><li>two</li></ul>")
        lines = [ln for ln in out.splitlines() if ln]
        assert lines == ["- one", "- two"]

    def test_img_alt_preserved(self) -> None:
        out = html_to_text('<p>see <img src="x.png" alt="図表1"/> here</p>')
        assert "図表1" in out

    def test_double_escaped_entities_stay_literal(self) -> None:
        # "&lt;tag&gt;" inside the HTML is literal text, not markup
        out = html_to_text("<p>&lt;tag&gt; is literal</p>")
        assert out == "<tag> is literal"

    def test_nbsp_becomes_space(self) -> None:
        out = html_to_text("<p>a&nbsp;b</p>")
        assert out == "a b"

    def test_malformed_html_does_not_crash(self) -> None:
        out = html_to_text("<p>unclosed <b>bold <td>stray")
        assert "unclosed" in out
        assert "bold" in out

    def test_excess_blank_lines_collapsed(self) -> None:
        out = html_to_text("<p>a</p><p> </p><p> </p><p> </p><p>b</p>")
        assert "\n\n\n" not in out


class TestExtractNarratives:
    def test_extracts_business_risks(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
            "&lt;h3&gt;事業等のリスク&lt;/h3&gt;&lt;p&gt;為替変動リスクがあります。&lt;/p&gt;"
            "</jpcrp_cor:BusinessRisksTextBlock>"
        )
        result = extract_narratives(_write(tmp_path, _instance(body)), period_end=_PERIOD_END)
        assert "business_risks" in result
        nar = result["business_risks"]
        assert "為替変動リスク" in nar.text
        assert nar.element == "BusinessRisksTextBlock"
        assert nar.context_ref == "FilingDateInstant"

    def test_prefers_context_without_dimensions(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant_TestMember">'
            "&lt;p&gt;dimensioned&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
            "&lt;p&gt;plain&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
        )
        result = extract_narratives(_write(tmp_path, _instance(body)), period_end=_PERIOD_END)
        assert result["business_risks"].text == "plain"

    def test_prefers_current_period_over_prior(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="Prior1YearDuration">'
            "&lt;p&gt;prior year text&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="CurrentYearDuration">'
            "&lt;p&gt;current year text&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
        )
        result = extract_narratives(_write(tmp_path, _instance(body)), period_end=_PERIOD_END)
        assert result["business_risks"].text == "current year text"

    def test_missing_section_absent(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
            "&lt;p&gt;risks&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
        )
        result = extract_narratives(_write(tmp_path, _instance(body)), period_end=_PERIOD_END)
        assert "corporate_governance" not in result

    def test_empty_element_treated_as_missing(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
            "</jpcrp_cor:BusinessRisksTextBlock>"
        )
        result = extract_narratives(_write(tmp_path, _instance(body)), period_end=_PERIOD_END)
        assert "business_risks" not in result

    def test_sections_filter(self, tmp_path: Path) -> None:
        body = (
            '<jpcrp_cor:BusinessRisksTextBlock contextRef="FilingDateInstant">'
            "&lt;p&gt;risks&lt;/p&gt;</jpcrp_cor:BusinessRisksTextBlock>"
            '<jpcrp_cor:DescriptionOfBusinessTextBlock contextRef="FilingDateInstant">'
            "&lt;p&gt;business&lt;/p&gt;</jpcrp_cor:DescriptionOfBusinessTextBlock>"
        )
        path = _write(tmp_path, _instance(body))
        result = extract_narratives(path, sections=["business_risks"], period_end=_PERIOD_END)
        assert list(result) == ["business_risks"]

    def test_unknown_section_raises(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _instance(""))
        with pytest.raises(ValueError, match="Unknown section"):
            extract_narratives(path, sections=["no_such_section"], period_end=_PERIOD_END)

    def test_all_documented_sections_have_elements(self) -> None:
        assert set(NARRATIVE_SECTIONS) == {
            "business_risks",
            "mdna",
            "business_policy",
            "description_of_business",
            "corporate_governance",
            "research_and_development",
        }
        for aliases in NARRATIVE_SECTIONS.values():
            assert aliases, "each section needs at least one element name"

    def test_unsafe_xml_rejected(self, tmp_path: Path) -> None:
        evil = (
            '<?xml version="1.0"?><!DOCTYPE bomb [<!ENTITY a "aaa">]>'
            f'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            f'xmlns:jpcrp_cor="{_JPCRP_NS}"><jpcrp_cor:BusinessRisksTextBlock '
            'contextRef="c">&a;</jpcrp_cor:BusinessRisksTextBlock></xbrli:xbrl>'
        )
        with pytest.raises(ValueError, match="Unsafe or invalid XML"):
            extract_narratives(_write(tmp_path, evil), period_end=_PERIOD_END)

    def test_invalid_xml_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsafe or invalid XML"):
            extract_narratives(_write(tmp_path, "not xml at all <<<"), period_end=_PERIOD_END)
