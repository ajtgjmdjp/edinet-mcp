"""Tests for logging architecture: library-safe, no stdout pollution."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from click.testing import CliRunner

from edinet_mcp.cli import cli

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestLibraryLogging:
    """Library modules must use stdlib logging with NullHandler."""

    def test_import_produces_no_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Importing edinet_mcp must not print anything to stdout."""
        import importlib

        importlib.reload(__import__("edinet_mcp"))
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_null_handler_configured(self) -> None:
        """edinet_mcp logger must have NullHandler to prevent 'No handlers' warning."""
        logger = logging.getLogger("edinet_mcp")
        handler_types = [type(h) for h in logger.handlers]
        assert logging.NullHandler in handler_types

    def test_library_modules_use_stdlib_logging(self) -> None:
        """Library modules must use stdlib logging, not loguru."""
        from edinet_mcp import _diff, _screening, client, parser

        for mod in [client, parser, _diff, _screening]:
            mod_logger = getattr(mod, "logger", None)
            assert mod_logger is not None, f"{mod.__name__} has no logger"
            assert isinstance(mod_logger, logging.Logger), (
                f"{mod.__name__}.logger is {type(mod_logger).__name__}, expected logging.Logger"
            )


def _assert_no_log_lines(text: str) -> None:
    for line in text.strip().split("\n"):
        # Log lines from loguru contain " | " with level names
        assert not (
            " | " in line and any(lvl in line for lvl in ("INFO", "DEBUG", "WARNING", "ERROR"))
        ), f"Log message leaked to stdout: {line}"


class TestCLILogging:
    """CLI must route all logs to stderr, never stdout.

    Note: ``result.output`` mixes stdout and stderr in click >= 8.2, so
    assertions must use ``result.stdout``. The no-API-key warning is forced
    to fire (env var removed, cwd moved away from any ``.env`` file) so the
    stream separation is actually exercised.
    """

    def test_cli_stdout_has_no_log_lines(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Log lines (e.g. the no-API-key warning) must go to stderr, not stdout."""
        monkeypatch.delenv("EDINET_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        # search for a nonexistent query — triggers the full pipeline
        result = runner.invoke(cli, ["search", "test_nonexistent_xyz_99999"])
        _assert_no_log_lines(result.stdout)
        assert "No EDINET API key found" in result.stderr

    def test_cli_json_stdout_purity(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """JSON output on stdout must stay machine-parseable despite warnings."""
        monkeypatch.delenv("EDINET_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "test_nonexistent_xyz_99999", "--json-output"])
        _assert_no_log_lines(result.stdout)
        json.loads(result.stdout)
        assert "No EDINET API key found" in result.stderr
