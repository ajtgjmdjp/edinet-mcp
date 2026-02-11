"""High-level EDINET API v2 client.

This is the primary public interface of edinet-mcp. All EDINET operations —
company search, filing retrieval, financial statement parsing — flow through
:class:`EdinetClient`.

Example::

    from edinet_mcp import EdinetClient

    client = EdinetClient()  # reads EDINET_API_KEY from env
    companies = client.search_companies("トヨタ")
    stmt = client.get_financial_statements("E02144", period="2024")
    print(stmt.income_statement.to_polars())
"""

from __future__ import annotations

import datetime
import io
import json
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Literal

import httpx
from loguru import logger

from edinet_mcp._cache import DiskCache
from edinet_mcp._config import get_settings
from edinet_mcp._normalize import normalize_statement
from edinet_mcp._rate_limiter import RateLimiter
from edinet_mcp._validation import validate_financial_statement
from edinet_mcp.models import (
    Company,
    DocType,
    Filing,
    FinancialStatement,
)
from edinet_mcp.parser import XBRLParser

# Maximum date range to prevent excessive API calls
_MAX_DATE_RANGE_DAYS = 366

# Cache TTL settings (seconds)
_CACHE_TTL_COMPANIES = 30 * 24 * 3600  # 30 days — EDINET code list updates monthly
_CACHE_TTL_FILINGS = 24 * 3600  # 24 hours — new filings appear daily

# Pattern for valid EDINET document IDs (e.g. "S100VVC2")
_DOC_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,20}$")

# Pattern for valid EDINET company codes (e.g. "E02144")
_EDINET_CODE_PATTERN = re.compile(r"^E\d{5}$")

# EDINET API v2 document retrieval type parameter
_DOC_RETRIEVE_XBRL = 1
_DOC_RETRIEVE_PDF = 2
_DOC_RETRIEVE_ATTACH = 3
_DOC_RETRIEVE_ENGLISH = 4

# EDINET API v2 document list type parameter
_DOC_LIST_METADATA = 1
_DOC_LIST_WITH_RESULTS = 2

# HTTP status codes that warrant a retry
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ZIP magic bytes
_ZIP_MAGIC = b"PK"


class EdinetAPIError(Exception):
    """Raised when the EDINET API returns an unexpected response."""


def _is_valid_zip(path: Path) -> bool:
    """Check if a file starts with ZIP magic bytes."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == _ZIP_MAGIC
    except OSError:
        return False


def _validate_edinet_code(edinet_code: str) -> None:
    """Validate EDINET company code format.

    Args:
        edinet_code: Code to validate (e.g. "E02144").

    Raises:
        ValueError: If the code format is invalid.
    """
    if not edinet_code or not _EDINET_CODE_PATTERN.match(edinet_code):
        msg = (
            f"Invalid EDINET code: {edinet_code!r}. "
            "Expected format: E followed by 5 digits (e.g., 'E02144')"
        )
        raise ValueError(msg)


def _validate_period(period: str) -> None:
    """Validate fiscal period format.

    Args:
        period: Fiscal year to validate (e.g. "2024").

    Raises:
        ValueError: If the period format is invalid.
    """
    if not period or not re.match(r"^\d{4}$", period):
        msg = f"Invalid period: {period!r}. Expected 4-digit year (e.g., '2024')"
        raise ValueError(msg)


class EdinetClient:
    """Client for the EDINET API v2.

    Provides methods to search filings, download documents, and parse
    XBRL financial statements into structured data.

    Args:
        api_key: EDINET subscription key. If ``None``, reads from
            the ``EDINET_API_KEY`` environment variable.
        cache_dir: Directory for caching downloaded documents. If ``None``,
            uses ``~/.cache/edinet-mcp/``.
        rate_limit: Maximum requests per second (default: 0.5).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        rate_limit: float | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()

        self._api_key = api_key or settings.edinet_api_key
        if not self._api_key:
            logger.warning("No EDINET API key found. Set EDINET_API_KEY env var or pass api_key=.")

        self._base_url = settings.edinet_base_url.rstrip("/")
        self._timeout = timeout or settings.request_timeout
        self._max_retries = settings.max_retries
        self._limiter = RateLimiter(rate_limit or settings.rate_limit_rps)

        cache_path = Path(cache_dir) if cache_dir else settings.cache_dir
        self._cache = DiskCache(cache_path)

        self._http = httpx.Client(
            timeout=self._timeout,
            headers={"Accept": "application/json"},
        )
        self._parser = XBRLParser()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> EdinetClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _request_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build query parameters with API key."""
        params: dict[str, Any] = {"Subscription-Key": self._api_key}
        if extra:
            params.update(extra)
        return params

    def _request_with_retry(self, url: str, params: dict[str, Any]) -> httpx.Response:
        """Perform a rate-limited GET with exponential-backoff retry.

        Retries on 429/5xx status codes and timeouts.
        """
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            self._limiter.wait()
            try:
                resp = self._http.get(url, params=params)
                if resp.status_code not in _RETRYABLE_STATUS:
                    resp.raise_for_status()
                    return resp
                # Retryable HTTP status
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            except httpx.TimeoutException as e:
                last_exc = e
            except httpx.HTTPError as e:
                # Non-retryable HTTP errors (4xx except 429)
                raise _sanitize_http_error(e, self._api_key) from None

            if attempt < self._max_retries:
                delay = 2**attempt  # 1s, 2s, 4s
                logger.warning(
                    f"Retry {attempt + 1}/{self._max_retries} for {url} "
                    f"after {type(last_exc).__name__} (wait {delay}s)"
                )
                time.sleep(delay)

        # All retries exhausted
        if isinstance(last_exc, httpx.HTTPError):
            raise _sanitize_http_error(last_exc, self._api_key) from None
        raise last_exc  # type: ignore[misc]

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        """Perform a rate-limited GET and return parsed JSON."""
        return self._request_with_retry(url, params).json()

    def _get_bytes(self, url: str, params: dict[str, Any]) -> bytes:
        """Perform a rate-limited GET and return raw bytes."""
        return self._request_with_retry(url, params).content

    # ------------------------------------------------------------------
    # Filing list
    # ------------------------------------------------------------------

    def get_filings(
        self,
        date: str | datetime.date | None = None,
        *,
        start_date: str | datetime.date | None = None,
        end_date: str | datetime.date | None = None,
        edinet_code: str | None = None,
        doc_type: str | DocType | None = None,
    ) -> list[Filing]:
        """List filings from EDINET.

        The EDINET API returns filings for a *single date*. When ``start_date``
        and ``end_date`` are given, this method iterates over each date in the
        range (rate-limited). For a single date, pass ``date`` directly.

        Args:
            date: A single filing date (shortcut for start_date=end_date=date).
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive, defaults to today).
            edinet_code: Filter to a specific company.
            doc_type: Filter by document type (e.g. ``"annual_report"``
                or :class:`DocType`).

        Returns:
            List of :class:`Filing` objects matching the criteria.

        Raises:
            ValueError: If edinet_code format is invalid or date range is too large.
        """
        # Validate edinet_code if provided
        if edinet_code is not None:
            _validate_edinet_code(edinet_code)

        if date is not None:
            dates = [_to_date(date)]
        elif start_date is not None:
            d_start = _to_date(start_date)
            d_end = _to_date(end_date) if end_date else datetime.date.today()
            if (d_end - d_start).days > _MAX_DATE_RANGE_DAYS:
                msg = (
                    f"Date range exceeds {_MAX_DATE_RANGE_DAYS} days. "
                    "Use a narrower range to avoid excessive API calls."
                )
                raise ValueError(msg)
            dates = _date_range(d_start, d_end)
        else:
            dates = [datetime.date.today()]

        resolved_doc_type: DocType | None = None
        if doc_type is not None:
            if isinstance(doc_type, DocType):
                resolved_doc_type = doc_type
            else:
                resolved_doc_type = DocType.from_label(doc_type)

        results: list[Filing] = []
        for d in dates:
            filings = self._fetch_filings_for_date(d)
            for f in filings:
                if edinet_code and f.edinet_code != edinet_code:
                    continue
                if resolved_doc_type and f.doc_type != resolved_doc_type:
                    continue
                results.append(f)

        logger.info(f"Found {len(results)} filings across {len(dates)} date(s)")
        return results

    def _fetch_filings_for_date(self, date: datetime.date) -> list[Filing]:
        """Fetch document list for a single date, with caching."""
        date_str = date.isoformat()
        cache_params = {"date": date_str, "type": _DOC_LIST_WITH_RESULTS}

        cached = self._cache.get_json("filings", cache_params, max_age=_CACHE_TTL_FILINGS)
        if cached is not None:
            return [Filing.from_api_row(row) for row in cached]

        url = f"{self._base_url}/documents.json"
        params = self._request_params({"date": date_str, "type": _DOC_LIST_WITH_RESULTS})

        data = self._get_json(url, params)
        rows: list[dict[str, Any]] = data.get("results", [])
        self._cache.put_json("filings", cache_params, rows)

        return [Filing.from_api_row(row) for row in rows if row.get("docID")]

    # ------------------------------------------------------------------
    # Document download
    # ------------------------------------------------------------------

    def download_document(
        self,
        doc_id: str,
        *,
        format: Literal["xbrl", "pdf", "attach", "english"] = "xbrl",
        output_dir: str | Path | None = None,
    ) -> Path:
        """Download a filing document from EDINET.

        Args:
            doc_id: Document identifier (e.g. ``"S100VVC2"``).
            format: Which rendition to download.
            output_dir: Where to save. If ``None``, uses cache dir.

        Returns:
            Path to the downloaded file.
        """
        if not _DOC_ID_PATTERN.match(doc_id):
            raise ValueError(f"Invalid document ID format: {doc_id!r}")

        type_map = {
            "xbrl": _DOC_RETRIEVE_XBRL,
            "pdf": _DOC_RETRIEVE_PDF,
            "attach": _DOC_RETRIEVE_ATTACH,
            "english": _DOC_RETRIEVE_ENGLISH,
        }
        retrieve_type = type_map.get(format, _DOC_RETRIEVE_XBRL)

        cache_params = {"doc_id": doc_id, "type": retrieve_type}
        cached_path = self._cache.get_file("documents", cache_params, suffix=".zip")
        if cached_path is not None:
            if _is_valid_zip(cached_path):
                logger.debug(f"Cache hit for {doc_id} ({format})")
                return cached_path
            # Cached file is corrupt (e.g. an error response) — remove and re-download
            logger.warning(f"Removing corrupt cached file for {doc_id}")
            cached_path.unlink(missing_ok=True)

        url = f"{self._base_url}/documents/{doc_id}"
        params = self._request_params({"type": retrieve_type})
        data = self._get_bytes(url, params)

        if data[:2] != b"PK":
            # EDINET may return HTTP 200 with a JSON error body
            msg = f"EDINET returned non-ZIP response for {doc_id}"
            try:
                body = json.loads(data)
                msg = f"EDINET API error for {doc_id}: {body.get('message', body)}"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            raise EdinetAPIError(msg)

        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"{doc_id}.zip"
            path.write_bytes(data)
            return path

        return self._cache.put_file("documents", cache_params, data, suffix=".zip")

    # ------------------------------------------------------------------
    # Financial statements
    # ------------------------------------------------------------------

    def get_financial_statements(
        self,
        edinet_code: str,
        *,
        doc_type: str | DocType = "annual_report",
        period: str | None = None,
    ) -> FinancialStatement:
        """Fetch and parse financial statements for a company.

        This is the highest-level convenience method. It:
        1. Finds the most recent matching filing
        2. Downloads the XBRL data
        3. Parses it into structured statements

        Args:
            edinet_code: Company's EDINET code (e.g. ``"E02144"``).
            doc_type: Document type label or :class:`DocType`.
            period: Fiscal year to target (e.g. ``"2024"``). If ``None``,
                uses the most recent filing.

        Returns:
            :class:`FinancialStatement` with BS, PL, CF data.

        Raises:
            ValueError: If no matching filing is found or invalid parameters.
        """
        # Validate inputs
        _validate_edinet_code(edinet_code)
        if period:
            _validate_period(period)

        # Find the filing — use smart search for period queries
        if period:
            filing = self._find_filing_for_period(edinet_code, int(period), doc_type)
        else:
            end = datetime.date.today()
            start = end - datetime.timedelta(days=365)
            filings = self.get_filings(
                start_date=start,
                end_date=end,
                edinet_code=edinet_code,
                doc_type=doc_type,
            )
            if not filings:
                msg = f"No {doc_type} filing found for {edinet_code}"
                raise ValueError(msg)
            filing = sorted(filings, key=lambda f: f.filing_date, reverse=True)[0]
        logger.info(f"Using filing {filing.doc_id} ({filing.description})")

        # Download and parse
        zip_path = self.download_document(filing.doc_id, format="xbrl")
        return self._parse_filing(filing, zip_path)

    def _find_filing_for_period(
        self,
        edinet_code: str,
        year: int,
        doc_type: str | DocType,
    ) -> Filing:
        """Find a filing by checking likely submission months first.

        Japanese companies typically file annual reports in specific months:
        - March fiscal year-end → June filing
        - December fiscal year-end → March filing
        This avoids scanning all 365 days when a period is specified.
        """
        # Most common filing months for Japanese companies
        priority_ranges = [
            (datetime.date(year, 6, 1), datetime.date(year, 6, 30)),  # 3月決算→6月提出
            (datetime.date(year, 3, 1), datetime.date(year, 3, 31)),  # 12月決算→3月提出
        ]
        today = datetime.date.today()

        for start, end in priority_ranges:
            if start > today:
                continue
            end = min(end, today)
            filings = self.get_filings(
                start_date=start,
                end_date=end,
                edinet_code=edinet_code,
                doc_type=doc_type,
            )
            if filings:
                return sorted(filings, key=lambda f: f.filing_date, reverse=True)[0]

        # Fallback: scan the full year
        logger.debug(f"Priority months missed for {edinet_code}, scanning full year {year}")
        start = datetime.date(year, 1, 1)
        end = min(datetime.date(year, 12, 31), today)
        filings = self.get_filings(
            start_date=start,
            end_date=end,
            edinet_code=edinet_code,
            doc_type=doc_type,
        )
        if not filings:
            msg = f"No {doc_type} filing found for {edinet_code} in period {year}"
            raise ValueError(msg)
        return sorted(filings, key=lambda f: f.filing_date, reverse=True)[0]

    def _parse_filing(self, filing: Filing, zip_path: Path) -> FinancialStatement:
        """Extract, parse, and normalize XBRL from a downloaded ZIP."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, tmp)

            raw = self._parser.parse_directory(filing, tmp)
            stmt = normalize_statement(raw)

            # Perform data consistency checks
            validate_financial_statement(stmt)

            return stmt

    # ------------------------------------------------------------------
    # Company search (using EDINET code list)
    # ------------------------------------------------------------------

    def search_companies(self, query: str) -> list[Company]:
        """Search for companies by name (partial match).

        Uses the EDINET code list to perform a local, offline search.
        The code list is downloaded and cached on first use.

        Args:
            query: Search string (Japanese or English, case-insensitive).

        Returns:
            Matching :class:`Company` objects.
        """
        companies = self._get_company_list()
        query_lower = query.lower()
        return [
            c
            for c in companies
            if query_lower in c.name.lower()
            or (c.name_en and query_lower in c.name_en.lower())
            or (c.ticker and query == c.ticker)
            or query == c.edinet_code
        ]

    def get_company(self, edinet_code: str) -> Company:
        """Look up a company by its exact EDINET code.

        Args:
            edinet_code: Company's EDINET code (e.g. ``"E02144"``).

        Returns:
            :class:`Company` object with company information.

        Raises:
            ValueError: If the code format is invalid or not found.
        """
        _validate_edinet_code(edinet_code)
        for c in self._get_company_list():
            if c.edinet_code == edinet_code:
                return c
        raise ValueError(f"EDINET code not found: {edinet_code}")

    def _get_company_list(self) -> list[Company]:
        """Load the EDINET code list, downloading if necessary."""
        cached = self._cache.get_json("companies", {"version": "v2"}, max_age=_CACHE_TTL_COMPANIES)
        if cached is not None:
            return [Company(**c) for c in cached]

        # Download EDINET code list CSV
        # The official list is available at the EDINET site
        url = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
        logger.info("Downloading EDINET code list...")
        data = self._get_bytes(url, {})

        companies = self._parse_code_list_zip(data)
        self._cache.put_json(
            "companies",
            {"version": "v2"},
            [c.model_dump() for c in companies],
        )
        logger.info(f"Cached {len(companies)} companies")
        return companies

    @staticmethod
    def _parse_code_list_zip(data: bytes) -> list[Company]:
        """Parse the EDINET code list ZIP into Company objects."""
        companies: list[Company] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # The ZIP contains a single CSV file
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                logger.warning("No CSV file found in EDINET code list ZIP")
                return companies

            with zf.open(csv_names[0]) as f:
                import csv as csv_mod

                reader = csv_mod.reader(io.TextIOWrapper(f, encoding="cp932", errors="replace"))
                header = next(reader, None)
                if header is None:
                    return companies

                for row in reader:
                    if len(row) < 7:
                        continue
                    edinet_code = row[0].strip()
                    if not edinet_code.startswith("E"):
                        continue

                    # EDINET CSV columns:
                    #  [0] EDINETコード  [1] 提出者種別  [2] 上場区分
                    #  [5] 決算日  [6] 提出者名  [7] 提出者名(英字)
                    #  [10] 提出者業種  [11] 証券コード  [12] 法人番号
                    name_en = row[7].strip() if len(row) > 7 else ""
                    # SEC code is 5 digits (e.g. "72030"); ticker is first 4
                    sec_code = row[11].strip() if len(row) > 11 else ""
                    ticker = sec_code[:4] if sec_code else ""
                    industry = row[10].strip() if len(row) > 10 else ""
                    is_listed = row[2].strip() == "上場" if len(row) > 2 else False
                    companies.append(
                        Company(
                            edinet_code=edinet_code,
                            name=row[6].strip() if len(row) > 6 else "",
                            name_en=name_en or None,
                            ticker=ticker or None,
                            industry=industry or None,
                            is_listed=is_listed,
                        )
                    )
        return companies


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------


def _to_date(value: str | datetime.date | datetime.datetime) -> datetime.date:
    # Check datetime.datetime first (it's a subclass of datetime.date)
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


def _date_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """Generate a list of dates from start to end inclusive."""
    days = (end - start).days + 1
    return [start + datetime.timedelta(days=i) for i in range(max(0, days))]


# ZIP bomb limits — EDINET filings are typically 1-10 MB uncompressed.
_ZIP_MAX_FILES = 5000
_ZIP_MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB


def _safe_extractall(zf: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract a ZIP file safely, preventing path traversal and ZIP bombs.

    Validates that no entry would be written outside *target_dir*,
    and enforces limits on file count and total uncompressed size.
    Uses ``Path.relative_to`` for strict containment checking.
    """
    resolved_target = target_dir.resolve()
    total_size = 0
    entries = zf.infolist()

    if len(entries) > _ZIP_MAX_FILES:
        msg = f"ZIP contains too many files ({len(entries)} > {_ZIP_MAX_FILES})"
        raise ValueError(msg)

    for info in entries:
        total_size += info.file_size
        if total_size > _ZIP_MAX_TOTAL_SIZE:
            msg = f"ZIP total uncompressed size exceeds {_ZIP_MAX_TOTAL_SIZE // (1024 * 1024)} MB"
            raise ValueError(msg)

        target_path = (target_dir / info.filename).resolve()
        try:
            target_path.relative_to(resolved_target)
        except ValueError:
            msg = f"ZIP entry escapes target directory: {info.filename!r}"
            raise ValueError(msg) from None

    zf.extractall(target_dir)


def _sanitize_http_error(error: httpx.HTTPError, api_key: str | None) -> httpx.HTTPError:
    """Remove API key from HTTP error messages to prevent leaking credentials.

    Re-raises the original exception with its args sanitized, rather than
    constructing a new instance (which may require additional positional
    arguments depending on the exception subclass).
    """
    if not api_key:
        return error
    sanitized_args = tuple(
        arg.replace(api_key, "***") if isinstance(arg, str) else arg for arg in error.args
    )
    error.args = sanitized_args
    return error
