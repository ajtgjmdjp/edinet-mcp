"""Tests for edinet_mcp.client."""

from __future__ import annotations

import datetime
import io
import zipfile
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from edinet_mcp.client import (
    _DOC_LIST_WITH_RESULTS,
    _RETRYABLE_STATUS,
    _ZIP_MAX_FILES,
    _ZIP_MAX_TOTAL_SIZE,
    EdinetClient,
    _date_range,
    _safe_extractall,
    _to_date,
    _validate_edinet_code,
    _validate_period,
)
from edinet_mcp.models import Company

if TYPE_CHECKING:
    from pathlib import Path


class TestDateUtils:
    def test_to_date_from_string(self) -> None:
        result = _to_date("2024-06-15")
        assert result == datetime.date(2024, 6, 15)

    def test_to_date_from_date(self) -> None:
        d = datetime.date(2024, 6, 15)
        assert _to_date(d) is d

    def test_date_range(self) -> None:
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2024, 1, 3)
        result = _date_range(start, end)
        assert len(result) == 3
        assert result[0] == start
        assert result[-1] == end

    def test_date_range_single_day(self) -> None:
        d = datetime.date(2024, 6, 15)
        assert _date_range(d, d) == [d]

    def test_date_range_reversed(self) -> None:
        start = datetime.date(2024, 1, 3)
        end = datetime.date(2024, 1, 1)
        assert _date_range(start, end) == []


class TestEdinetClientInit:
    def test_default_construction(self) -> None:
        """Client can be constructed with no arguments (API key from env)."""
        with patch.dict("os.environ", {"EDINET_API_KEY": "test_key"}):
            client = EdinetClient(api_key="test_key")
            assert client._api_key == "test_key"

    async def test_context_manager(self) -> None:
        async with EdinetClient(api_key="test") as client:
            assert client._api_key == "test"

    def test_custom_rate_limit(self) -> None:
        client = EdinetClient(api_key="test", rate_limit=2.0)
        assert client._limiter._min_interval == 0.5


class TestSearchCompanies:
    async def test_search_returns_matching(self) -> None:
        """search_companies should filter by name match."""
        client = EdinetClient(api_key="test")

        mock_companies = [
            Company(
                edinet_code="E02144",
                name="トヨタ自動車株式会社",
                ticker="7203",
                is_listed=True,
            ),
            Company(
                edinet_code="E00001",
                name="ソニーグループ株式会社",
                ticker="6758",
                is_listed=True,
            ),
        ]
        client._get_company_list = AsyncMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = await client.search_companies("トヨタ")
        assert len(results) == 1
        assert results[0].edinet_code == "E02144"

    async def test_search_by_ticker(self) -> None:
        client = EdinetClient(api_key="test")

        mock_companies = [
            Company(
                edinet_code="E02144",
                name="トヨタ自動車株式会社",
                ticker="7203",
                is_listed=True,
            ),
        ]
        client._get_company_list = AsyncMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = await client.search_companies("7203")
        assert len(results) == 1

    async def test_search_by_edinet_code(self) -> None:
        client = EdinetClient(api_key="test")

        mock_companies = [
            Company(
                edinet_code="E02144",
                name="トヨタ自動車株式会社",
                ticker="7203",
                is_listed=True,
            ),
        ]
        client._get_company_list = AsyncMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = await client.search_companies("E02144")
        assert len(results) == 1

    async def test_search_no_match(self) -> None:
        client = EdinetClient(api_key="test")

        client._get_company_list = AsyncMock(return_value=[])  # type: ignore[method-assign]

        results = await client.search_companies("存在しない企業")
        assert len(results) == 0


class TestSafeExtractall:
    def test_normal_zip(self, tmp_path: Path) -> None:
        """Normal ZIP extracts successfully."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.txt", "hello")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            _safe_extractall(zf, tmp_path)
        assert (tmp_path / "test.txt").read_text() == "hello"

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """ZIP entries with path traversal are rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../escape.txt", "malicious")
        buf.seek(0)
        with (
            zipfile.ZipFile(buf) as zf,
            pytest.raises(ValueError, match="escapes target directory"),
        ):
            _safe_extractall(zf, tmp_path)

    def test_too_many_files_rejected(self, tmp_path: Path) -> None:
        """ZIP with excessive file count is rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(_ZIP_MAX_FILES + 1):
                zf.writestr(f"file_{i}.txt", "x")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf, pytest.raises(ValueError, match="too many files"):
            _safe_extractall(zf, tmp_path)

    def test_total_size_limit_rejected(self, tmp_path: Path) -> None:
        """ZIP exceeding total uncompressed size limit is rejected."""
        buf = io.BytesIO()
        # Create a ZIP with entries that exceed the total size limit
        chunk = b"x" * (1024 * 1024)  # 1 MB per file
        num_files = (_ZIP_MAX_TOTAL_SIZE // len(chunk)) + 1
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i in range(num_files):
                zf.writestr(f"file_{i}.bin", chunk)
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf, pytest.raises(ValueError, match="exceeds"):
            _safe_extractall(zf, tmp_path)

    def test_nested_directory_extraction(self, tmp_path: Path) -> None:
        """ZIP with nested directories extracts correctly."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("subdir/nested/test.txt", "nested content")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            _safe_extractall(zf, tmp_path)
        assert (tmp_path / "subdir" / "nested" / "test.txt").read_text() == "nested content"


class TestValidation:
    """Tests for input validation functions."""

    def test_validate_edinet_code_valid(self) -> None:
        """Valid EDINET codes pass validation."""
        _validate_edinet_code("E02144")
        _validate_edinet_code("E00001")
        _validate_edinet_code("E99999")

    def test_validate_edinet_code_invalid_format(self) -> None:
        """Invalid EDINET code formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid EDINET code"):
            _validate_edinet_code("E0214")  # Too short

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            _validate_edinet_code("E021444")  # Too long

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            _validate_edinet_code("F02144")  # Wrong prefix

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            _validate_edinet_code("E0214A")  # Contains letter

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            _validate_edinet_code("")  # Empty string

    def test_validate_period_valid(self) -> None:
        """Valid period strings pass validation."""
        _validate_period("2024")
        _validate_period("2000")
        _validate_period("2099")

    def test_validate_period_invalid_format(self) -> None:
        """Invalid period formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid period"):
            _validate_period("24")  # Too short

        with pytest.raises(ValueError, match="Invalid period"):
            _validate_period("20244")  # Too long

        with pytest.raises(ValueError, match="Invalid period"):
            _validate_period("202A")  # Contains letter

        with pytest.raises(ValueError, match="Invalid period"):
            _validate_period("")  # Empty string


class TestClientValidation:
    """Tests for client methods with validation."""

    async def test_get_company_invalid_code(self) -> None:
        """get_company rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            await client.get_company("E0214")  # Too short

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            await client.get_company("INVALID")

    async def test_get_financial_statements_invalid_code(self) -> None:
        """get_financial_statements rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            await client.get_financial_statements("E0214")

    async def test_get_financial_statements_invalid_period(self) -> None:
        """get_financial_statements rejects invalid period."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid period"):
            await client.get_financial_statements("E02144", period="24")

        with pytest.raises(ValueError, match="Invalid period"):
            await client.get_financial_statements("E02144", period="202A")

    async def test_get_filings_invalid_edinet_code(self) -> None:
        """get_filings rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            await client.get_filings(edinet_code="E0214")


def _mock_response(status_code: int, json_data: object = None) -> httpx.Response:
    """Build a minimal httpx.Response for testing."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.com/test"),
    )


def _no_wait_client() -> EdinetClient:
    """Create a client with rate limiter disabled for fast tests."""
    client = EdinetClient(api_key="test", rate_limit=100_000.0)
    return client


class TestRetryLogic:
    """Tests for _request_with_retry exponential backoff."""

    async def test_success_on_first_try(self) -> None:
        """No retry needed when first request succeeds."""
        client = _no_wait_client()
        ok = _mock_response(200, {"results": []})
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=ok)

        result = await client._get_json("https://example.com/test", {})
        assert result == {"results": []}
        assert client._http.get.call_count == 1

    @patch("edinet_mcp.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_503_then_success(self, mock_sleep: AsyncMock) -> None:
        """Retries on 503 and succeeds on second attempt."""
        client = _no_wait_client()
        err = _mock_response(503)
        ok = _mock_response(200, {"ok": True})
        client._http = MagicMock()
        client._http.get = AsyncMock(side_effect=[err, ok])

        result = await client._get_json("https://example.com/test", {})
        assert result == {"ok": True}
        assert client._http.get.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1s

    @patch("edinet_mcp.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_429(self, mock_sleep: AsyncMock) -> None:
        """Retries on 429 (rate limited)."""
        client = _no_wait_client()
        err = _mock_response(429)
        ok = _mock_response(200, {"data": 1})
        client._http = MagicMock()
        client._http.get = AsyncMock(side_effect=[err, ok])

        result = await client._get_json("https://example.com/test", {})
        assert result == {"data": 1}

    @patch("edinet_mcp.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_exhausted_raises(self, mock_sleep: AsyncMock) -> None:
        """Raises after all retries are exhausted."""
        client = _no_wait_client()
        client._max_retries = 2
        err = _mock_response(503)
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=err)

        with pytest.raises(httpx.HTTPError):
            await client._get_json("https://example.com/test", {})
        # 1 initial + 2 retries = 3 total
        assert client._http.get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("edinet_mcp.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_timeout(self, mock_sleep: AsyncMock) -> None:
        """Retries on timeout exception."""
        client = _no_wait_client()
        ok = _mock_response(200, {"ok": True})
        client._http = MagicMock()
        client._http.get = AsyncMock(
            side_effect=[
                httpx.ReadTimeout("timed out"),
                ok,
            ]
        )

        result = await client._get_json("https://example.com/test", {})
        assert result == {"ok": True}

    async def test_no_retry_on_404(self) -> None:
        """4xx errors (except 429) are NOT retried."""
        client = _no_wait_client()
        client._http = MagicMock()
        client._http.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=httpx.Request("GET", "https://example.com/test"),
                response=_mock_response(404),
            )
        )

        with pytest.raises(httpx.HTTPError):
            await client._get_json("https://example.com/test", {})
        assert client._http.get.call_count == 1  # No retry

    @patch("edinet_mcp.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_exponential_backoff_timing(self, mock_sleep: AsyncMock) -> None:
        """Verifies backoff delays: 1s, 2s, 4s."""
        client = _no_wait_client()
        client._max_retries = 3
        err = _mock_response(500)
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=err)

        with pytest.raises(httpx.HTTPError):
            await client._get_json("https://example.com/test", {})

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1, 2, 4]

    def test_retryable_status_codes(self) -> None:
        """Verify the set of retryable status codes."""
        assert {429, 500, 502, 503, 504} == _RETRYABLE_STATUS

    async def test_no_attempts_raises_runtime_error(self) -> None:
        """If the retry loop records no exception, a RuntimeError is raised."""
        client = _no_wait_client()
        client._max_retries = -1  # loop body never executes -> last_exc stays None
        client._http = MagicMock()
        client._http.get = AsyncMock()

        with pytest.raises(RuntimeError, match="retries exhausted"):
            await client._request_with_retry("https://example.com/test", {})


class TestFetchFilingsCache:
    """Tests for _fetch_filings_for_date cache consistency (docID filtering)."""

    _DATE = datetime.date(2025, 6, 20)

    @staticmethod
    def _cache_params(client: EdinetClient) -> dict[str, Any]:
        return {
            "date": "2025-06-20",
            "type": _DOC_LIST_WITH_RESULTS,
            "base_url": client._base_url,
        }

    @staticmethod
    def _client(tmp_path: Path) -> EdinetClient:
        return EdinetClient(api_key="test", cache_dir=tmp_path, rate_limit=100_000.0)

    async def test_cache_miss_filters_docid_less_rows_before_caching(
        self, tmp_path: Path, sample_api_row: dict[str, Any]
    ) -> None:
        """Rows without docID must be filtered BEFORE writing to the cache."""
        client = self._client(tmp_path)
        docid_less_row = dict(sample_api_row, docID=None)
        client._get_json = AsyncMock(  # type: ignore[method-assign]
            return_value={"results": [sample_api_row, docid_less_row]}
        )

        filings = await client._fetch_filings_for_date(self._DATE)
        assert len(filings) == 1
        assert filings[0].doc_id == "S100VVC2"

        cached = client._cache.get_json("filings", self._cache_params(client))
        assert cached is not None
        assert all(row.get("docID") for row in cached), "cache must not contain rows without docID"

    async def test_cache_hit_with_docid_less_row_does_not_raise(
        self, tmp_path: Path, sample_api_row: dict[str, Any]
    ) -> None:
        """A poisoned cache entry (row without docID) must not raise KeyError."""
        client = self._client(tmp_path)
        docid_less_row = dict(sample_api_row, docID=None)
        # Simulate a cache poisoned by a previous buggy version
        client._cache.put_json(
            "filings", self._cache_params(client), [sample_api_row, docid_less_row]
        )

        filings = await client._fetch_filings_for_date(self._DATE)
        assert len(filings) == 1
        assert filings[0].doc_id == "S100VVC2"


class TestParseCodeListZip:
    """Tests for EdinetClient._parse_code_list_zip (EDINET CSV parsing)."""

    @staticmethod
    def _make_zip(rows: list[list[str]]) -> bytes:
        """Build a ZIP containing a single cp932-encoded CSV."""
        header = [
            "EDINETコード",
            "提出者種別",
            "上場区分",
            "連結の有無",
            "資本金",
            "決算日",
            "提出者名",
            "提出者名（英字表記）",
            "提出者名（ヨミ）",
            "所在地",
            "提出者業種",
            "証券コード",
            "提出者法人番号",
        ]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            import csv as csv_mod

            csv_buf = io.StringIO()
            writer = csv_mod.writer(csv_buf)
            writer.writerow(header)
            for row in rows:
                writer.writerow(row)
            zf.writestr("EdinetcodeDlInfo.csv", csv_buf.getvalue().encode("cp932"))
        return buf.getvalue()

    def test_basic_parsing(self) -> None:
        """Parse a single listed company with all fields."""
        data = self._make_zip(
            [
                [
                    "E02144",
                    "内国法人・組合",
                    "上場",
                    "有",
                    "635401",
                    "3月31日",
                    "トヨタ自動車株式会社",
                    "Toyota Motor Corporation",
                    "トヨタジドウシャ",
                    "愛知県豊田市",
                    "輸送用機器",
                    "72030",
                    "2180001012461",
                ],
            ]
        )
        companies = EdinetClient._parse_code_list_zip(data)
        assert len(companies) == 1
        c = companies[0]
        assert c.edinet_code == "E02144"
        assert c.name == "トヨタ自動車株式会社"
        assert c.name_en == "Toyota Motor Corporation"
        assert c.ticker == "7203"
        assert c.sec_code == "72030"
        assert c.corporate_number == "2180001012461"
        assert c.industry == "輸送用機器"
        assert c.is_listed is True

    def test_unlisted_company(self) -> None:
        """Unlisted company has no sec_code or ticker."""
        data = self._make_zip(
            [
                [
                    "E31000",
                    "内国法人・組合",
                    "非上場",
                    "無",
                    "1000",
                    "3月31日",
                    "テスト株式会社",
                    "",
                    "",
                    "東京都",
                    "その他",
                    "",
                    "1234567890123",
                ],
            ]
        )
        companies = EdinetClient._parse_code_list_zip(data)
        assert len(companies) == 1
        c = companies[0]
        assert c.edinet_code == "E31000"
        assert c.ticker is None
        assert c.sec_code is None
        assert c.corporate_number == "1234567890123"
        assert c.is_listed is False

    def test_missing_corporate_number(self) -> None:
        """Company with blank corporate number parses as None."""
        data = self._make_zip(
            [
                [
                    "E50000",
                    "内国法人・組合",
                    "上場",
                    "有",
                    "500",
                    "3月31日",
                    "コード無し株式会社",
                    "",
                    "",
                    "東京都",
                    "情報・通信業",
                    "99990",
                    "",
                ],
            ]
        )
        companies = EdinetClient._parse_code_list_zip(data)
        assert len(companies) == 1
        c = companies[0]
        assert c.sec_code == "99990"
        assert c.corporate_number is None

    def test_short_row_skipped(self) -> None:
        """Rows with fewer than 7 columns are skipped."""
        data = self._make_zip(
            [
                ["E00001", "内国法人", "上場"],  # too short
            ]
        )
        companies = EdinetClient._parse_code_list_zip(data)
        assert len(companies) == 0

    def test_non_edinet_code_skipped(self) -> None:
        """Rows not starting with 'E' are skipped."""
        data = self._make_zip(
            [
                [
                    "X99999",
                    "内国法人・組合",
                    "上場",
                    "有",
                    "100",
                    "3月31日",
                    "不正コード株式会社",
                    "",
                    "",
                    "東京都",
                    "その他",
                    "12340",
                    "9999999999999",
                ],
            ]
        )
        companies = EdinetClient._parse_code_list_zip(data)
        assert len(companies) == 0

    def test_empty_zip(self) -> None:
        """ZIP with no CSV returns empty list."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no csv here")
        companies = EdinetClient._parse_code_list_zip(buf.getvalue())
        assert companies == []


class TestGetNarrative:
    """client.get_narrative — qualitative section extraction (annual reports)."""

    def _client_with_zip(self, zip_path, sample_filing):
        client = EdinetClient(api_key="test")
        client._resolve_filing = AsyncMock(return_value=sample_filing)  # type: ignore[method-assign]
        client.download_document = AsyncMock(return_value=zip_path)  # type: ignore[method-assign]
        return client

    async def test_returns_narrative_section(self, tmp_path, sample_filing) -> None:
        from tests.conftest import make_narrative_zip

        client = self._client_with_zip(make_narrative_zip(tmp_path), sample_filing)
        nar = await client.get_narrative("E02144", "business_risks")
        assert nar is not None
        assert "為替変動リスク" in nar.text
        assert nar.section == "business_risks"
        assert nar.doc_id == sample_filing.doc_id
        assert nar.char_count == len(nar.text)

    async def test_missing_section_returns_none(self, tmp_path, sample_filing) -> None:
        from tests.conftest import make_narrative_zip

        client = self._client_with_zip(make_narrative_zip(tmp_path), sample_filing)
        assert await client.get_narrative("E02144", "corporate_governance") is None

    async def test_invalid_section_raises(self, tmp_path, sample_filing) -> None:
        from tests.conftest import make_narrative_zip

        client = self._client_with_zip(make_narrative_zip(tmp_path), sample_filing)
        with pytest.raises(ValueError, match="Unknown section"):
            await client.get_narrative("E02144", "no_such_section")

    async def test_invalid_edinet_code_raises(self) -> None:
        client = EdinetClient(api_key="test")
        with pytest.raises(ValueError, match="Invalid EDINET code"):
            await client.get_narrative("E0214", "business_risks")

    async def test_resolve_filing_used_by_get_financial_statements(self) -> None:
        """_resolve_filing is the shared filing-resolution path."""
        client = EdinetClient(api_key="test")
        assert hasattr(client, "_resolve_filing")

    async def test_narrative_cached_across_calls(self, tmp_path, sample_filing) -> None:
        from tests.conftest import make_narrative_zip

        client = self._client_with_zip(make_narrative_zip(tmp_path), sample_filing)
        first = await client.get_narrative("E02144", "business_risks")
        second = await client.get_narrative("E02144", "business_risks")
        assert first == second
        assert client.download_document.call_count == 1

    async def test_invalid_first_instance_skipped(self, tmp_path, sample_filing) -> None:
        import zipfile

        from tests.conftest import _JPCRP_NS_2023, NARRATIVE_XBRL_BODY

        instance = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:jpcrp_cor="{_JPCRP_NS_2023}">
  <xbrli:context id="FilingDateInstant">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00001-000</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-06-20</xbrli:instant></xbrli:period>
  </xbrli:context>
  {NARRATIVE_XBRL_BODY}
</xbrli:xbrl>
"""
        zip_path = tmp_path / "narrative.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("XBRL/PublicDoc/aaa_broken.xbrl", "not xml <<<")
            zf.writestr("XBRL/PublicDoc/bbb_valid.xbrl", instance)
        client = self._client_with_zip(zip_path, sample_filing)
        nar = await client.get_narrative("E02144", "business_risks")
        assert nar is not None
        assert "為替変動リスク" in nar.text


class TestResolveFilingLatest:
    """period=None must not exceed the 366-day range limit (P0 regression).

    The old implementation requested a single 730-day range, which
    get_filings itself rejects — so every documented period-omitted call
    (get_financial_statements, get_narrative, screening) failed instantly.
    """

    async def test_latest_search_does_not_raise_range_error(self, sample_filing) -> None:
        client = EdinetClient(api_key="test")
        calls: list[int] = []
        real_get_filings = client.get_filings

        async def fake_get_filings(*, start_date, end_date, edinet_code, doc_type):
            span = (end_date - start_date).days
            calls.append(span)
            assert span <= 366, f"window of {span} days would be rejected"
            return [sample_filing] if len(calls) >= 2 else []

        client.get_filings = fake_get_filings  # type: ignore[method-assign]
        filing = await client._resolve_filing("E02144", "annual_report", None)
        assert filing == sample_filing
        assert len(calls) == 2  # stopped as soon as a window matched
        del real_get_filings

    async def test_latest_search_stops_on_first_window_hit(self, sample_filing) -> None:
        client = EdinetClient(api_key="test")
        client.get_filings = AsyncMock(return_value=[sample_filing])  # type: ignore[method-assign]
        filing = await client._resolve_filing("E02144", "annual_report", None)
        assert filing == sample_filing
        assert client.get_filings.call_count == 1

    async def test_latest_search_exhausted_raises(self) -> None:
        client = EdinetClient(api_key="test")
        client.get_filings = AsyncMock(return_value=[])  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="No annual_report filing found"):
            await client._resolve_filing("E02144", "annual_report", None)
        # Coverage must span roughly two years of history
        assert client.get_filings.call_count >= 20


class TestCacheKeySourceScoping:
    """Cache entries must be scoped to the API base_url (no cross-source poisoning)."""

    async def test_filings_cache_key_includes_base_url(self, tmp_path, sample_api_row) -> None:
        client = EdinetClient(api_key="test", cache_dir=tmp_path)
        client._get_json = AsyncMock(return_value={"results": [sample_api_row]})  # type: ignore[method-assign]
        date = datetime.date(2025, 6, 20)
        await client._fetch_filings_for_date(date)

        # Same date but a different endpoint must MISS the cache
        client2 = EdinetClient(api_key="test", cache_dir=tmp_path)
        client2._base_url = "https://staging.example.com/api"
        client2._get_json = AsyncMock(return_value={"results": []})  # type: ignore[method-assign]
        result = await client2._fetch_filings_for_date(date)
        assert client2._get_json.call_count == 1
        assert result == []
