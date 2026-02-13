"""Command-line interface for edinet-mcp.

Provides four commands:
- ``edinet-mcp search``: Search for companies
- ``edinet-mcp statements``: Fetch financial statements
- ``edinet-mcp test``: Test API key and connectivity
- ``edinet-mcp serve``: Start the MCP server
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Literal, cast

import click

if TYPE_CHECKING:
    from edinet_mcp.models import Company, FinancialStatement
from loguru import logger


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """EDINET financial data tools and MCP server."""
    level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level:<7} | {message}")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results to show.")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output as JSON.")
def search(query: str, limit: int, as_json: bool) -> None:
    """Search for companies by name, ticker, or EDINET code.

    Examples:

        edinet-mcp search トヨタ

        edinet-mcp search 7203

        edinet-mcp search E02144 --json-output
    """
    from edinet_mcp.client import EdinetClient

    async def _run() -> list[Company]:
        async with EdinetClient() as client:
            return await client.search_companies(query)

    companies = asyncio.run(_run())[:limit]

    if as_json:
        click.echo(json.dumps([c.model_dump() for c in companies], ensure_ascii=False, indent=2))
        return

    if not companies:
        click.echo(f"No companies found for '{query}'")
        return

    for c in companies:
        ticker = c.ticker or "----"
        click.echo(f"  {c.edinet_code}  {ticker:>6}  {c.name}")


@cli.command()
@click.option("--edinet-code", "-c", required=True, help="EDINET code (e.g. E02144).")
@click.option("--period", "-p", default=None, help="Fiscal year (e.g. 2024).")
@click.option("--doc-type", "-t", default="annual_report", help="Document type.")
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--statement",
    "-s",
    default="income_statement",
    type=click.Choice(["balance_sheet", "income_statement", "cash_flow_statement", "summary"]),
    help="Which statement to display.",
)
def statements(
    edinet_code: str,
    period: str | None,
    doc_type: str,
    fmt: str,
    statement: str,
) -> None:
    """Fetch and display financial statements for a company.

    Examples:

        edinet-mcp statements -c E02144 -p 2024

        edinet-mcp statements -c E02144 -s balance_sheet --format json
    """
    from edinet_mcp.client import EdinetClient

    async def _run() -> FinancialStatement:
        async with EdinetClient() as client:
            return await client.get_financial_statements(
                edinet_code=edinet_code,
                doc_type=doc_type,
                period=period,
            )

    try:
        stmt = asyncio.run(_run())
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    data = stmt.all_statements.get(statement)
    if not data:
        click.echo(f"No {statement} data found in the filing.", err=True)
        sys.exit(1)

    click.echo(
        f"Filing: {stmt.filing.doc_id} | {stmt.filing.description} | "
        f"Standard: {stmt.accounting_standard.value}"
    )
    click.echo(f"Statement: {statement} ({len(data)} rows)\n")

    if fmt == "json":
        click.echo(json.dumps(data.to_dicts(), ensure_ascii=False, indent=2))
    elif fmt == "csv":
        import csv
        import io

        if not data.items:
            return
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data.items[0].keys()))
        writer.writeheader()
        writer.writerows(data.items)
        click.echo(output.getvalue())
    else:
        # Table format using Polars' built-in pretty printing
        df = data.to_polars()
        click.echo(str(df))


@cli.command("test")
def test_connection() -> None:
    """Test API key and connectivity to EDINET.

    Verifies that your EDINET_API_KEY is set and working by making
    a lightweight API call. Also checks cache directory status.

    Examples:

        edinet-mcp test
    """
    import os

    from edinet_mcp import __version__

    click.echo(f"edinet-mcp v{__version__}\n")

    # 1. Check API key
    api_key = os.environ.get("EDINET_API_KEY", "")
    if not api_key:
        click.echo("[FAIL] EDINET_API_KEY is not set", err=True)
        click.echo(
            "  Set it with: export EDINET_API_KEY=your_key_here",
            err=True,
        )
        sys.exit(1)
    click.echo(f"[OK]   EDINET_API_KEY is set ({api_key[:4]}...{api_key[-2:]})")

    # 2. Check cache directory
    from edinet_mcp._config import get_settings

    settings = get_settings()
    cache_dir = settings.cache_dir
    if cache_dir.exists():
        cache_files = [f for f in cache_dir.rglob("*") if f.is_file()]
        cache_bytes = sum(f.stat().st_size for f in cache_files)
        cache_mb = cache_bytes / 1024 / 1024
        click.echo(
            f"[OK]   Cache: {cache_dir} ({len(cache_files)} files, {cache_mb:.1f} MB)"
        )
    else:
        click.echo(f"[INFO] Cache: {cache_dir} (not created yet)")

    # 3. Test API connectivity
    click.echo("\nTesting API connectivity...")

    from edinet_mcp.client import EdinetClient

    async def _test() -> str:
        async with EdinetClient() as client:
            companies = await client.search_companies("トヨタ")
            if companies:
                return f"Found {len(companies)} results (e.g. {companies[0].name})"
            return "API responded but no results for test query"

    try:
        result = asyncio.run(_test())
        click.echo(f"[OK]   {result}")
    except Exception as e:
        click.echo(f"[FAIL] API error: {e}", err=True)
        sys.exit(1)

    click.echo("\nAll checks passed.")


@cli.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="MCP transport protocol.",
)
def serve(transport: str) -> None:
    """Start the EDINET MCP server.

    For Claude Desktop, add this to your config:

        {"mcpServers": {"edinet": {"command": "uvx", "args": ["edinet-mcp", "serve"]}}}
    """
    from edinet_mcp.server import mcp

    logger.info(f"Starting EDINET MCP server ({transport} transport)")
    mcp.run(transport=cast('Literal["stdio", "sse"]', transport))
