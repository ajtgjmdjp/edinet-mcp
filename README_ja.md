# edinet-mcp

EDINET の XBRL パースライブラリ & MCP サーバー — 日本の企業開示データを Python と AI アシスタントから。

[English README is here](README.md)

[![PyPI](https://img.shields.io/pypi/v/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![CI](https://github.com/ajtgjmdjp/edinet-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ajtgjmdjp/edinet-mcp/actions/workflows/ci.yml)
[![Downloads](https://img.shields.io/pypi/dm/edinet-mcp)](https://pypi.org/project/edinet-mcp/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

## これは何？

**edinet-mcp** は、金融庁の [EDINET](https://disclosure.edinet-fsa.go.jp/)（有価証券報告書等の開示システム）にプログラムからアクセスするためのツールです。XBRL を会計基準（J-GAAP / IFRS / US-GAAP）を問わず共通の科目名に正規化し、Python ライブラリとしても [MCP](https://modelcontextprotocol.io/) サーバーとしても使えます。

- 上場企業 5,000 社以上を企業名・証券コード・EDINET コードで検索
- 有価証券報告書・四半期報告書・半期報告書・臨時報告書・大量保有報告書の取得
- **自動正規化**: 会計基準に関係なく `stmt["売上高"]` で取得（英語ラベル `stmt["Revenue"]` も可）
- **定性情報の抽出**: 事業等のリスク・MD&A・経営方針などをプレーンテキストで（`get_narrative`）
- 財務指標（ROE・ROA・利益率等）と前年比較
- Polars / pandas DataFrame へのエクスポート
- **複数企業スクリーニング**（最大20社）と**期間比較 diff**（増減額・増減率）
- Claude Desktop 等から使える MCP サーバー（ツール10種）

### なぜ edinet-mcp？

商用の EDINET データ API と違い、edinet-mcp は**完全無料・ローカル完結**です。XBRL パーサーはあなたのマシン上で動き、必要な認証情報は金融庁が無料発行する EDINET API キーだけ。すべての数値は元の開示書類まで遡って検証できます。有料プランも利用上限もありません（EDINET 自体のレート制限のみ）。Apache-2.0 ライセンス。

## クイックスタート

### インストール

```bash
pip install edinet-mcp
# または
uv add edinet-mcp
```

### API キーの取得

[EDINET の API 利用登録](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html)（無料）でキーを取得し、環境変数に設定します。

```bash
export EDINET_API_KEY=あなたのキー
```

### 30秒サンプル

```python
import asyncio
from edinet_mcp import EdinetClient

async def main():
    async with EdinetClient() as client:
        # トヨタを検索
        companies = await client.search_companies("トヨタ")
        print(companies[0].name, companies[0].edinet_code)
        # トヨタ自動車株式会社 E02144

        # 正規化された財務諸表を取得
        stmt = await client.get_financial_statements("E02144", period="2025")

        # 会計基準を問わず同じ科目名でアクセス
        print(stmt.income_statement["売上高"])
        # {"当期": 45095325000000, "前期": 37154298000000}

        # DataFrame へ
        print(stmt.income_statement.to_polars())

asyncio.run(main())
```

> **注意**: `period` は**書類の提出年**です（会計年度ではありません）。3月決算企業の FY2024 有報は 2025 年 6 月提出なので `period="2025"` を指定します。

### 定性情報（事業等のリスク・MD&A など）

```python
# 事業等のリスクをプレーンテキストで取得
risks = await client.get_narrative("E02144", "business_risks")
print(risks.text[:200])

# 他のセクション: mdna（経営者による分析）, business_policy（経営方針）,
# description_of_business（事業の内容）, corporate_governance,
# research_and_development
```

### 財務指標とスクリーニング

```python
from edinet_mcp import calculate_metrics, screen_companies

# 単独企業の指標
metrics = calculate_metrics(stmt)
print(metrics["profitability"])  # {"営業利益率": "11.87%", "ROE": "12.50%", ...}

# 複数企業を営業利益率でスクリーニング
result = await screen_companies(
    client, ["E02144", "E01777", "E01967"], period="2025", sort_by="営業利益率",
)
```

## MCP サーバー（Claude Desktop 等）

Claude Desktop の `claude_desktop_config.json` に追加:

```json
{
  "mcpServers": {
    "edinet": {
      "command": "uvx",
      "args": ["edinet-mcp", "serve"],
      "env": {
        "EDINET_API_KEY": "あなたのキー"
      }
    }
  }
}
```

Claude Code の場合:

```bash
claude mcp add edinet -- uvx edinet-mcp serve
```

設定後は AI にそのまま聞くだけです: 「トヨタの最新の営業利益を教えて」「ソニーの事業リスクを要約して」

### MCP ツール一覧

| ツール | 説明 |
|------|------|
| `search_companies` | 企業名・証券コード・EDINETコードで検索 |
| `get_filings` | 指定期間の開示書類一覧を取得 |
| `get_financial_statements` | 正規化された財務諸表 (BS/PL/CF) を取得（`language='en'` で英語出力） |
| `get_financial_metrics` | ROE・ROA・利益率等の財務指標を計算 |
| `compare_financial_periods` | 前年比較（増減額・増減率） |
| `screen_companies` | 複数企業の財務指標を一括比較（最大20社） |
| `get_narrative` | 定性情報（事業等のリスク・MD&A 等）をページング付きで取得 |
| `list_available_labels` | 取得可能な財務科目の一覧 |
| `get_company_info` | 企業の詳細情報を取得 |
| `diff_financial_statements` | 2期間の財務諸表を比較（増減額・増減率） |

## CLI

```bash
edinet-mcp search トヨタ                          # 企業検索
edinet-mcp statements -c E02144 -p 2025           # 財務諸表
edinet-mcp screen E02144 E01777 --sort-by ROE     # スクリーニング
edinet-mcp diff -c E02144 -p1 2024 -p2 2025       # 期間比較
edinet-mcp serve                                  # MCP サーバー起動
```

## 正規化の仕組み

XBRL の要素名は会計基準ごとに異なりますが（J-GAAP `NetSales` / IFRS `Revenue` / US-GAAP `Revenues`）、[`taxonomy.yaml`](src/edinet_mcp/data/taxonomy.yaml) の対応表（161 科目: PL 42・BS 79・CF 40）で共通の日本語・英語ラベルに正規化します。対応表は YAML の編集だけで拡張できます。

## データ出典

本プロジェクトは金融庁が運営する [EDINET](https://disclosure.edinet-fsa.go.jp/) のデータを利用しています。EDINET のデータは[公共データ利用規約（第1.0版）](https://www.digital.go.jp/resources/open_data/)に基づき提供されています。

## 関連プロジェクト

**Japan Finance Data Stack**（同作者）:
- [tdnet-disclosure-mcp](https://github.com/ajtgjmdjp/tdnet-disclosure-mcp) — TDNET 適時開示
- [estat-mcp](https://github.com/ajtgjmdjp/estat-mcp) — 政府統計 (e-Stat)
- [stockprice-mcp](https://github.com/ajtgjmdjp/stockprice-mcp) — 株価・為替
- [jfinqa](https://github.com/ajtgjmdjp/jfinqa) — 日本語金融 QA ベンチマーク

## ライセンス

Apache-2.0。サードパーティの帰属表示は [NOTICE](NOTICE) を参照してください。
