"""Tests for edinet_mcp.client."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from edinet_mcp.client import EdinetClient, _date_range, _to_date
from edinet_mcp.models import Company


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
