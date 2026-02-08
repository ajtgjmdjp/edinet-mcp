"""Command-line interface for edinet-mcp.

Provides three commands:
- ``edinet-mcp search``: Search for companies
- ``edinet-mcp statements``: Fetch financial statements
- ``edinet-mcp serve``: Start the MCP server
"""

from __future__ import annotations

import json
import sys

import click
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

    client = EdinetClient()
    companies = client.search_companies(query)[:limit]

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

    client = EdinetClient()
    try:
        stmt = client.get_financial_statements(
            edinet_code=edinet_code,
            doc_type=doc_type,
            period=period,
        )
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
    mcp.run(transport=transport)  # type: ignore[arg-type]
