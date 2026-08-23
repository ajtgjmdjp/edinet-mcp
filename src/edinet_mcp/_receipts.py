"""Evidence receipt integration (xbrl-facts).

Attaches audit-grade evidence receipts (er/0.2 schema, see the
xbrl-facts project) to financial figures served by edinet-mcp. The
receipt schema and its canonicalization have exactly one implementation
— the Rust engine behind the optional ``xbrl-facts`` package — so this
module never builds or hashes receipts itself; it only requests and
filters them.

Install with: ``pip install edinet-mcp[receipts]``
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from edinet_mcp._normalize import _load_taxonomy, _strip_edinet_suffixes

if TYPE_CHECKING:
    from edinet_mcp.client import EdinetClient

# Default: the headline figures analysts cite most
DEFAULT_RECEIPT_LABELS = [
    "売上高",
    "営業利益",
    "経常利益",
    "当期純利益",
    "資産合計",
    "純資産合計",
]

_MAX_PER_LABEL = 8


class ReceiptsUnavailableError(RuntimeError):
    """Raised when the optional xbrl-facts dependency is not installed."""


def _require_engine() -> Any:
    """Import the Rust engine, or raise a clean error."""
    try:
        import xbrl_facts
    except ImportError as exc:  # pragma: no cover - environment dependent
        msg = "evidence receipts require the optional dependency: pip install edinet-mcp[receipts]"
        raise ReceiptsUnavailableError(msg) from exc
    if xbrl_facts is None:  # test hook: sys.modules["xbrl_facts"] = None
        msg = "evidence receipts require the optional dependency: pip install edinet-mcp[receipts]"
        raise ReceiptsUnavailableError(msg)
    return xbrl_facts


def _emit_receipts(source_bytes: bytes, doc_id: str, uri: str) -> str:
    """Emit receipts JSONL via the Rust engine."""
    engine = _require_engine()
    return str(engine.receipts_for_bytes(source_bytes, doc_id, uri, "jp.fsa.edinet"))


def _label_element_map(labels: list[str]) -> dict[str, set[str]]:
    """Map requested Japanese labels -> taxonomy element local names."""
    taxonomy = _load_taxonomy()
    wanted = {label: set() for label in labels}  # type: dict[str, set[str]]
    for items in taxonomy.values():
        for item in items:
            if item["label"] in wanted:
                wanted[item["label"]].update(item["elements"])
    return wanted


def _match_receipts_to_labels(
    receipts_jsonl: str,
    labels: list[str],
    max_per_label: int = _MAX_PER_LABEL,
) -> dict[str, list[dict[str, Any]]]:
    """Filter emitted receipts down to the requested canonical labels.

    A receipt matches a label when its locator concept (namespace prefix
    stripped, EDINET suffixes stripped) is one of the label's taxonomy
    element aliases.
    """
    element_map = _label_element_map(labels)
    matched: dict[str, list[dict[str, Any]]] = {label: [] for label in labels}

    for line in receipts_jsonl.splitlines():
        if not line.strip():
            continue
        receipt = json.loads(line)
        evidence = receipt.get("evidence") or []
        if not evidence:
            continue
        concept = str(evidence[0].get("locator", {}).get("concept", ""))
        local = concept.rsplit(":", 1)[-1]
        local = _strip_edinet_suffixes(local)
        for label, elements in element_map.items():
            if local in elements and len(matched[label]) < max_per_label:
                matched[label].append(receipt)
    return matched


async def get_receipts(
    client: EdinetClient,
    edinet_code: str,
    *,
    labels: list[str] | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """Fetch evidence receipts for a company's key financial figures.

    Downloads the filing (cached), emits receipts via the Rust engine,
    and returns the ones matching the requested canonical labels.
    """
    _require_engine()  # fail fast before any network work
    labels = labels or DEFAULT_RECEIPT_LABELS
    filing = await client._resolve_filing(edinet_code, "annual_report", period)
    zip_path = await client.download_document(filing.doc_id, format="xbrl")

    from edinet_mcp.client import _safe_extractall

    receipts_jsonl = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extractall(zf, tmp)
        for instance in sorted((tmp / "XBRL" / "PublicDoc").glob("*.xbrl")):
            receipts_jsonl = _emit_receipts(
                instance.read_bytes(),
                filing.doc_id,
                f"edinet://{filing.doc_id}/{instance.name}",
            )
            if receipts_jsonl:
                break

    matched = _match_receipts_to_labels(receipts_jsonl, labels)
    return {
        "schema": "er/0.2",
        "doc_id": filing.doc_id,
        "filing_date": filing.filing_date.isoformat(),
        "receipts": matched,
        "verify_hint": (
            "Each receipt is machine-verifiable against the original filing "
            "with the xbrl-facts verifier (xbrl-facts CLI: 'verify'). "
            "receipt_id is a content hash; any tampering fails verification."
        ),
    }
