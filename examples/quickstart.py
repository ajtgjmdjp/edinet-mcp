"""Quick start example for edinet-mcp.

Before running, set your EDINET API key:
    export EDINET_API_KEY=your_key_here

Usage:
    uv run python examples/quickstart.py
"""

import asyncio

from edinet_mcp import EdinetClient


async def main() -> None:
    async with EdinetClient() as client:
        # 1. Search for a company
        print("=== Company Search ===")
        companies = await client.search_companies("トヨタ")
        for c in companies[:3]:
            print(f"  {c.edinet_code}  {c.ticker or '----':>6}  {c.name}")

        if not companies:
            print("  No companies found. Check your API key.")
            return

        # 2. Get financial statements
        edinet_code = companies[0].edinet_code
        print(f"\n=== Financial Statements for {edinet_code} ===")

        try:
            stmt = await client.get_financial_statements(edinet_code)
            print(f"  Filing: {stmt.filing.doc_id}")
            print(f"  Standard: {stmt.accounting_standard.value}")
            print(f"\n  Income Statement ({len(stmt.income_statement)} rows):")
            if stmt.income_statement:
                df = stmt.income_statement.to_polars()
                print(df.head(10))
        except ValueError as e:
            print(f"  {e}")


if __name__ == "__main__":
    asyncio.run(main())
