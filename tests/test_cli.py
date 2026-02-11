"""Tests for CLI commands."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from edinet_mcp.cli import cli


@patch("edinet_mcp.client.EdinetClient")
class TestSearchCommand:
    def test_search_basic(self, mock_client_cls, sample_company):
        mock_client_cls.return_value.search_companies.return_value = [sample_company]
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ"])
        assert result.exit_code == 0
        assert "E02144" in result.output
        assert "7203" in result.output
        assert "トヨタ自動車株式会社" in result.output

    def test_search_no_results(self, mock_client_cls):
        mock_client_cls.return_value.search_companies.return_value = []
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "存在しない企業"])
        assert result.exit_code == 0
        assert "No companies found" in result.output

    def test_search_json_output(self, mock_client_cls, sample_company):
        mock_client_cls.return_value.search_companies.return_value = [sample_company]
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["edinet_code"] == "E02144"

    def test_search_limit(self, mock_client_cls, sample_company):
        companies = [sample_company] * 5
        mock_client_cls.return_value.search_companies.return_value = companies
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "トヨタ", "--limit", "2"])
        assert result.exit_code == 0
        assert result.output.count("E02144") == 2

    def test_search_missing_query(self, mock_client_cls):
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

    def test_statements_table(self, mock_client_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_client_cls.return_value.get_financial_statements.return_value = stmt
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "E02144", "-s", "income_statement"])
        assert result.exit_code == 0
        assert "Filing:" in result.output
        assert "IFRS" in result.output

    def test_statements_json(self, mock_client_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_client_cls.return_value.get_financial_statements.return_value = stmt
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["statements", "-c", "E02144", "-s", "income_statement", "-f", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output.split("\n\n", 1)[1])
        assert isinstance(data, list)

    def test_statements_csv(self, mock_client_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_client_cls.return_value.get_financial_statements.return_value = stmt
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["statements", "-c", "E02144", "-s", "income_statement", "-f", "csv"],
        )
        assert result.exit_code == 0
        assert "element" in result.output  # CSV header

    def test_statements_not_found(self, mock_client_cls, sample_filing, sample_statement_data):
        stmt = self._make_stmt(sample_filing, sample_statement_data)
        mock_client_cls.return_value.get_financial_statements.return_value = stmt
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "E02144", "-s", "balance_sheet"])
        assert result.exit_code != 0
        assert "No balance_sheet data found" in result.output

    def test_statements_value_error(self, mock_client_cls):
        mock_client_cls.return_value.get_financial_statements.side_effect = ValueError(
            "Invalid EDINET code"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["statements", "-c", "INVALID"])
        assert result.exit_code != 0
        assert "Error:" in result.output

    def test_statements_missing_code(self, mock_client_cls):
        runner = CliRunner()
        result = runner.invoke(cli, ["statements"])
        assert result.exit_code != 0


class TestVerboseFlag:
    def test_verbose_sets_debug(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0
