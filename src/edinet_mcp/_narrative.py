"""Qualitative narrative (TextBlock) extraction from EDINET XBRL instances.

有価証券報告書 narrative sections (事業等のリスク, MD&A, 経営方針, etc.) are
stored in the XBRL instance as escaped HTML inside ``jpcrp_cor`` TextBlock
elements. This module extracts them and converts the HTML to plain text
suitable for LLM consumption.

Notes on correctness (informed by real filings):

- The XML parser already unescapes the element content, yielding an HTML
  string. That string is fed directly to the HTML parser — calling
  ``html.unescape()`` first would turn double-escaped literals into markup
  and silently destroy content.
- A TextBlock can appear under multiple contexts. Candidates are ranked
  semantically: period class first (filing-date instant, then current-period
  duration, then everything else), then absence of dimension members, with
  the context id as a deterministic tie-break. Candidates whose HTML
  normalizes to empty text fall back to the next-ranked candidate.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING

import defusedxml.ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
    from collections.abc import Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)

# Section key -> ordered tuple of jpcrp_cor local element names (aliases).
# Taxonomy versions may introduce variants; first match in tuple order wins.
NARRATIVE_SECTIONS: dict[str, tuple[str, ...]] = {
    "business_risks": ("BusinessRisksTextBlock",),
    "mdna": ("ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock",),
    "business_policy": ("BusinessPolicyBusinessEnvironmentIssuesToAddressEtcTextBlock",),
    "description_of_business": ("DescriptionOfBusinessTextBlock",),
    "corporate_governance": ("OverviewOfCorporateGovernanceTextBlock",),
    "research_and_development": ("ResearchAndDevelopmentActivitiesTextBlock",),
}

# Defensive cap on a single section's extracted text. Truncation is
# reported via ExtractedNarrative.source_truncated, never silent.
_MAX_SECTION_CHARS = 1_000_000

# Refuse to DOM-parse instances beyond this size (same limit as parser.py's
# _MAX_XBRL_SIZE; real annual-report instances are ~5 MB)
_MAX_INSTANCE_BYTES = 50 * 1024 * 1024

_XBRLI_NS = "http://www.xbrl.org/2003/instance"


# ---------------------------------------------------------------------------
# HTML -> plain text
# ---------------------------------------------------------------------------

_BLOCK_TAGS = frozenset(
    {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "ul", "ol"}
)
_SKIP_TAGS = frozenset({"style", "script"})


class _TextExtractor(HTMLParser):
    """Convert TextBlock HTML to readable plain text.

    Block elements produce line breaks, table cells are tab-joined
    (cells are buffered so block elements inside a cell stay within it),
    list items get a leading marker, and image alt text is preserved.
    ``style``/``script`` content is discarded.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._row_cells: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def _emit(self, fragment: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(fragment)
        else:
            self._parts.append(fragment)

    def _flush_cell(self) -> None:
        if self._cell_parts is None:
            return
        cell = " ".join("".join(self._cell_parts).split())
        self._cell_parts = None
        if self._row_cells is not None:
            self._row_cells.append(cell)
        elif cell:
            self._parts.append(cell + "\n")

    def _flush_row(self) -> None:
        self._flush_cell()
        if self._row_cells is None:
            return
        cells, self._row_cells = self._row_cells, None
        if any(cells):
            self._parts.append("\n" + "\t".join(cells) + "\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "br":
            self._emit("\n")
        elif tag == "tr":
            self._flush_row()
            self._row_cells = []
        elif tag in ("td", "th"):
            self._flush_cell()
            if self._row_cells is None:
                self._row_cells = []
            self._cell_parts = []
        elif tag == "li":
            self._emit("\n- ")
        elif tag in _BLOCK_TAGS:
            self._emit("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self._emit(alt)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in ("td", "th"):
            self._flush_cell()
        elif tag == "tr":
            self._flush_row()
        elif tag == "table":
            self._flush_row()
            self._parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._emit(data.replace("\xa0", " "))

    def close(self) -> None:
        super().close()
        self._flush_row()

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [line.rstrip() for line in raw.splitlines()]
        # Collapse runs of blank lines to a single blank line
        out: list[str] = []
        blank = 0
        for line in lines:
            if line.strip():
                out.append(line)
                blank = 0
            else:
                blank += 1
                if blank == 1 and out:
                    out.append("")
        while out and not out[-1]:
            out.pop()
        return "\n".join(out).strip()


def html_to_text(html: str) -> str:
    """Convert TextBlock HTML content to plain text.

    Input must be the already-unescaped HTML string as returned by the
    XML parser — do NOT pre-apply ``html.unescape()``.
    """
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


# ---------------------------------------------------------------------------
# XBRL instance extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedNarrative:
    """A narrative section extracted from an XBRL instance."""

    section: str
    element: str
    text: str
    context_ref: str
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    source_truncated: bool = False


@dataclass(frozen=True)
class _Context:
    has_dimensions: bool
    instant: datetime.date | None
    start: datetime.date | None
    end: datetime.date | None


def _parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _read_contexts(root: ET.Element) -> dict[str, _Context]:
    contexts: dict[str, _Context] = {}
    for ctx in root.iter(f"{{{_XBRLI_NS}}}context"):
        cid = ctx.get("id")
        if not cid:
            continue
        has_dims = any(
            child.tag.endswith("}explicitMember") or child.tag.endswith("}typedMember")
            for child in ctx.iter()
        )
        instant = start = end = None
        period = ctx.find(f"{{{_XBRLI_NS}}}period")
        if period is not None:
            instant = _parse_date(period.findtext(f"{{{_XBRLI_NS}}}instant"))
            start = _parse_date(period.findtext(f"{{{_XBRLI_NS}}}startDate"))
            end = _parse_date(period.findtext(f"{{{_XBRLI_NS}}}endDate"))
        contexts[cid] = _Context(has_dimensions=has_dims, instant=instant, start=start, end=end)
    return contexts


def _rank(
    context_ref: str,
    contexts: dict[str, _Context],
    period_end: datetime.date | None,
    filing_date: datetime.date | None,
) -> tuple[int, int, str]:
    """Rank a fact's context: lower sorts first.

    Period semantics rank before dimensions: a dimensioned current-period
    context must beat a dimensionless prior-period one. Period classes:

    0. Filing-date instant (``instant == filing_date``) — the canonical
       context for narrative blocks.
    1. Current-period duration (``end == period_end``).
    2. Instant with an unknown relationship (no ``filing_date`` given) —
       likely the filing instant, but unverifiable.
    3. Anything else (prior periods, unknown durations).

    Context id is the deterministic tie-break.
    """
    ctx = contexts.get(context_ref)
    if ctx is None:
        return (4, 1, context_ref)
    if ctx.instant is not None:
        if filing_date is None:
            period_class = 2
        elif ctx.instant == filing_date:
            period_class = 0
        else:
            period_class = 3
    elif period_end is not None and ctx.end == period_end:
        period_class = 1
    else:
        period_class = 3
    dims = 1 if ctx.has_dimensions else 0
    return (period_class, dims, context_ref)


def extract_narratives(
    path: Path,
    sections: Sequence[str] | None = None,
    *,
    period_end: datetime.date | None = None,
    filing_date: datetime.date | None = None,
) -> dict[str, ExtractedNarrative]:
    """Extract narrative sections from an XBRL instance file.

    Args:
        path: Path to the ``.xbrl`` instance (``XBRL/PublicDoc/*.xbrl``).
        sections: Section keys to extract (default: all known sections).
        period_end: The filing's period end date, used to prefer
            current-period contexts over prior-period ones.
        filing_date: The filing's submission date, used to recognize the
            filing-date instant context.

    Returns:
        Mapping of section key -> :class:`ExtractedNarrative` for every
        section found with non-empty text. Missing sections are absent.

    Raises:
        ValueError: For unknown section keys, unsafe/invalid XML, or an
            instance file exceeding the size limit.
    """
    wanted = list(NARRATIVE_SECTIONS) if sections is None else list(sections)
    unknown = [s for s in wanted if s not in NARRATIVE_SECTIONS]
    if unknown:
        msg = f"Unknown section(s): {unknown}. Valid: {sorted(NARRATIVE_SECTIONS)}"
        raise ValueError(msg)

    try:
        size = path.stat().st_size
    except OSError as exc:
        msg = f"Unsafe or invalid XML in {path.name}: {exc}"
        raise ValueError(msg) from exc
    if size > _MAX_INSTANCE_BYTES:
        msg = f"XBRL instance {path.name} too large: {size} bytes > {_MAX_INSTANCE_BYTES} limit"
        raise ValueError(msg)

    # element local name -> (section key, alias priority index)
    element_to_section = {
        elem: (section, idx)
        for section in wanted
        for idx, elem in enumerate(NARRATIVE_SECTIONS[section])
    }

    try:
        tree = DefusedET.parse(str(path))
    except (DefusedXmlException, DefusedET.ParseError, OSError) as exc:
        msg = f"Unsafe or invalid XML in {path.name}: {exc}"
        raise ValueError(msg) from exc

    root = tree.getroot()
    if root is None:
        msg = f"Unsafe or invalid XML in {path.name}: empty document"
        raise ValueError(msg)
    contexts = _read_contexts(root)

    # Collect candidate facts per section, keyed for rank-then-alias ordering
    candidates: dict[str, list[tuple[tuple[int, int, str], int, str, str, str]]] = {}
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1]
        mapping = element_to_section.get(local)
        if mapping is None:
            continue
        section, alias_idx = mapping
        namespace = elem.tag.rsplit("}", 1)[0].lstrip("{")
        if "jpcrp" not in namespace:
            continue
        content = (elem.text or "").strip()
        if not content:
            continue
        context_ref = elem.get("contextRef", "")
        rank = _rank(context_ref, contexts, period_end, filing_date)
        candidates.setdefault(section, []).append((rank, alias_idx, local, context_ref, content))

    result: dict[str, ExtractedNarrative] = {}
    for section, facts in candidates.items():
        # Best context rank first, then documented alias priority
        facts.sort(key=lambda f: (f[0], f[1]))
        for _, _, local, context_ref, content in facts:
            text = html_to_text(content)
            if not text:
                continue  # fall back to the next-ranked candidate
            source_truncated = len(text) > _MAX_SECTION_CHARS
            if source_truncated:
                logger.warning("Narrative section %s truncated from %d chars", section, len(text))
                text = text[:_MAX_SECTION_CHARS]
            ctx = contexts.get(context_ref)
            result[section] = ExtractedNarrative(
                section=section,
                element=local,
                text=text,
                context_ref=context_ref,
                period_start=ctx.start if ctx else None,
                period_end=ctx.end if ctx else None,
                source_truncated=source_truncated,
            )
            break
    return result
