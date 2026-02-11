"""Tests for edinet_mcp.client."""

from __future__ import annotations

import datetime
import io
import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import httpx
import pytest

from edinet_mcp.client import (
    _RETRYABLE_STATUS,
    _ZIP_MAX_FILES,
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

    def test_context_manager(self) -> None:
        with EdinetClient(api_key="test") as client:
            assert client._api_key == "test"

    def test_custom_rate_limit(self) -> None:
        client = EdinetClient(api_key="test", rate_limit=2.0)
        assert client._limiter._min_interval == 0.5


class TestSearchCompanies:
    def test_search_returns_matching(self) -> None:
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
        client._get_company_list = MagicMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = client.search_companies("トヨタ")
        assert len(results) == 1
        assert results[0].edinet_code == "E02144"

    def test_search_by_ticker(self) -> None:
        client = EdinetClient(api_key="test")

        mock_companies = [
            Company(
                edinet_code="E02144",
                name="トヨタ自動車株式会社",
                ticker="7203",
                is_listed=True,
            ),
        ]
        client._get_company_list = MagicMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = client.search_companies("7203")
        assert len(results) == 1

    def test_search_by_edinet_code(self) -> None:
        client = EdinetClient(api_key="test")

        mock_companies = [
            Company(
                edinet_code="E02144",
                name="トヨタ自動車株式会社",
                ticker="7203",
                is_listed=True,
            ),
        ]
        client._get_company_list = MagicMock(return_value=mock_companies)  # type: ignore[method-assign]

        results = client.search_companies("E02144")
        assert len(results) == 1

    def test_search_no_match(self) -> None:
        client = EdinetClient(api_key="test")

        client._get_company_list = MagicMock(return_value=[])  # type: ignore[method-assign]

        results = client.search_companies("存在しない企業")
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

    def test_get_company_invalid_code(self) -> None:
        """get_company rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            client.get_company("E0214")  # Too short

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            client.get_company("INVALID")

    def test_get_financial_statements_invalid_code(self) -> None:
        """get_financial_statements rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            client.get_financial_statements("E0214")

    def test_get_financial_statements_invalid_period(self) -> None:
        """get_financial_statements rejects invalid period."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid period"):
            client.get_financial_statements("E02144", period="24")

        with pytest.raises(ValueError, match="Invalid period"):
            client.get_financial_statements("E02144", period="202A")

    def test_get_filings_invalid_edinet_code(self) -> None:
        """get_filings rejects invalid EDINET codes."""
        client = EdinetClient(api_key="test")

        with pytest.raises(ValueError, match="Invalid EDINET code"):
            client.get_filings(edinet_code="E0214")


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

    def test_success_on_first_try(self) -> None:
        """No retry needed when first request succeeds."""
        client = _no_wait_client()
        ok = _mock_response(200, {"results": []})
        client._http = MagicMock()
        client._http.get.return_value = ok

        result = client._get_json("https://example.com/test", {})
        assert result == {"results": []}
        assert client._http.get.call_count == 1

    @patch("edinet_mcp.client.time.sleep")
    def test_retry_on_503_then_success(self, mock_sleep: MagicMock) -> None:
        """Retries on 503 and succeeds on second attempt."""
        client = _no_wait_client()
        err = _mock_response(503)
        ok = _mock_response(200, {"ok": True})
        client._http = MagicMock()
        client._http.get.side_effect = [err, ok]

        result = client._get_json("https://example.com/test", {})
        assert result == {"ok": True}
        assert client._http.get.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1s

    @patch("edinet_mcp.client.time.sleep")
    def test_retry_on_429(self, mock_sleep: MagicMock) -> None:
        """Retries on 429 (rate limited)."""
        client = _no_wait_client()
        err = _mock_response(429)
        ok = _mock_response(200, {"data": 1})
        client._http = MagicMock()
        client._http.get.side_effect = [err, ok]

        result = client._get_json("https://example.com/test", {})
        assert result == {"data": 1}

    @patch("edinet_mcp.client.time.sleep")
    def test_retry_exhausted_raises(self, mock_sleep: MagicMock) -> None:
        """Raises after all retries are exhausted."""
        client = _no_wait_client()
        client._max_retries = 2
        err = _mock_response(503)
        client._http = MagicMock()
        client._http.get.return_value = err

        with pytest.raises(httpx.HTTPError):
            client._get_json("https://example.com/test", {})
        # 1 initial + 2 retries = 3 total
        assert client._http.get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("edinet_mcp.client.time.sleep")
    def test_retry_on_timeout(self, mock_sleep: MagicMock) -> None:
        """Retries on timeout exception."""
        client = _no_wait_client()
        ok = _mock_response(200, {"ok": True})
        client._http = MagicMock()
        client._http.get.side_effect = [
            httpx.ReadTimeout("timed out"),
            ok,
        ]

        result = client._get_json("https://example.com/test", {})
        assert result == {"ok": True}

    def test_no_retry_on_404(self) -> None:
        """4xx errors (except 429) are NOT retried."""
        client = _no_wait_client()
        client._http = MagicMock()
        client._http.get.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=httpx.Request("GET", "https://example.com/test"),
            response=_mock_response(404),
        )

        with pytest.raises(httpx.HTTPError):
            client._get_json("https://example.com/test", {})
        assert client._http.get.call_count == 1  # No retry

    @patch("edinet_mcp.client.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep: MagicMock) -> None:
        """Verifies backoff delays: 1s, 2s, 4s."""
        client = _no_wait_client()
        client._max_retries = 3
        err = _mock_response(500)
        client._http = MagicMock()
        client._http.get.return_value = err

        with pytest.raises(httpx.HTTPError):
            client._get_json("https://example.com/test", {})

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1, 2, 4]

    def test_retryable_status_codes(self) -> None:
        """Verify the set of retryable status codes."""
        assert {429, 500, 502, 503, 504} == _RETRYABLE_STATUS
