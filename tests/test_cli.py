"""Tests for CLI commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from edinet_mcp.cli import cli


def _async_client_mock(**method_returns: object) -> MagicMock:
    """Create a mock EdinetClient that supports ``async with``."""
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    for name, value in method_returns.items():
        setattr(instance, name, AsyncMock(return_value=value))
    return instance


@patch("edinet_mcp.client.EdinetClient")
class TestSearchCommand:
    def test_search_basic(self, mock_cls, sample_company):
        mock_cls.return_value = _async_client_mock(search_companies=[sample_company])
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ"])
        assert result.exit_code == 0
        assert "E02144" in result.output
        assert "7203" in result.output
        assert "トヨタ自動車株式会社" in result.output

    def test_search_no_results(self, mock_cls):
        mock_cls.return_value = _async_client_mock(search_companies=[])
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "存在しない企業"])
        assert result.exit_code == 0
        assert "No companies found" in result.output

    def test_search_json_output(self, mock_cls, sample_company):
        mock_cls.return_value = _async_client_mock(search_companies=[sample_company])
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["edinet_code"] == "E02144"

    def test_search_limit(self, mock_cls, sample_company):
        companies = [sample_company] * 5
        mock_cls.return_value = _async_client_mock(search_companies=companies)
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ", "--limit", "2"])
        assert result.exit_code == 0
        assert result.output.count("E02144") == 2

    def test_search_missing_query(self, mock_cls):
        runner = CliRunner()
        result = runner.invoke(cli, ["search"])
        assert result.exit_code != 0


@patch("edinet_mcp.client.EdinetClient")
class TestStatementsCommand:
    def _make_stmt(self, sample_filing, sample_statement_data):
        from edinet_mcp.models import AccountingStandard, FinancialStatement

        return FinancialStatement(
            filing=sample_filing,
            income_statement=sample_statement_data,
            accounting_standard=AccountingStandard.IFRS,
        )

    def test_statements_table(self, mock_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_cls.return_value = _async_client_mock(get_financial_statements=stmt)
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "E02144", "-s", "income_statement"])
        assert result.exit_code == 0
        assert "Filing:" in result.output
        assert "IFRS" in result.output

    def test_statements_json(self, mock_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_cls.return_value = _async_client_mock(get_financial_statements=stmt)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["statements", "-c", "E02144", "-s", "income_statement", "-f", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output.split("\n\n", 1)[1])
        assert isinstance(data, list)

    def test_statements_csv(self, mock_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_cls.return_value = _async_client_mock(get_financial_statements=stmt)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["statements", "-c", "E02144", "-s", "income_statement", "-f", "csv"],
        )
        assert result.exit_code == 0
        assert "element" in result.output  # CSV header

    def test_statements_not_found(self, mock_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_cls.return_value = _async_client_mock(get_financial_statements=stmt)
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "E02144", "-s", "balance_sheet"])
        assert result.exit_code != 0
        assert "No balance_sheet data found" in result.output

    def test_statements_value_error(self, mock_cls):
        instance = _async_client_mock()
        instance.get_financial_statements = AsyncMock(
            side_effect=ValueError("Invalid EDINET code")
        )
        mock_cls.return_value = instance
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "INVALID"])
        assert result.exit_code != 0
        assert "Error:" in result.output

    def test_statements_missing_code(self, mock_cls):
        runner = CliRunner()
        result = runner.invoke(cli, ["statements"])
        assert result.exit_code != 0


@patch("edinet_mcp.client.EdinetClient")
class TestTestCommand:
    def test_success(self, mock_cls, sample_company):
        mock_cls.return_value = _async_client_mock(
            search_companies=[sample_company]
        )
        runner = CliRunner(env={"EDINET_API_KEY": "test_key_abc"})
        result = runner.invoke(cli, ["test"])
        assert result.exit_code == 0
        assert "[OK]   EDINET_API_KEY is set" in result.output
        assert "All checks passed" in result.output

    def test_missing_api_key(self, mock_cls):
        runner = CliRunner(env={"EDINET_API_KEY": ""})
        result = runner.invoke(cli, ["test"])
        assert result.exit_code != 0
        assert "FAIL" in result.output

    def test_api_error(self, mock_cls):
        instance = _async_client_mock()
        instance.search_companies = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        mock_cls.return_value = instance
        runner = CliRunner(env={"EDINET_API_KEY": "test_key_abc"})
        result = runner.invoke(cli, ["test"])
        assert result.exit_code != 0
        assert "API error" in result.output


class TestVerboseFlag:
    def test_verbose_sets_debug(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0
