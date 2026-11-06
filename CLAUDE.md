# CLAUDE.md — stocks.py

## Project Overview

`stocks.py` is a single-file CLI tool for stock market data, backed by Yahoo Finance via the `yfinance` library. It is also packaged as an **agent skill** — a self-contained, documented tool that AI agents can call directly as a subprocess.

The project has two distinct consumers:
- **Human users** running `stocks.py <command>` directly from the terminal
- **AI agents** reading `SKILL.md` to understand available commands, then running them as subprocesses and parsing stdout

---

## Repository Layout

```
stocks.py/
├── .claude-plugin/
│   ├── plugin.json        # Plugin manifest (plugin `stocks`)
│   └── marketplace.json   # Single-plugin marketplace (`stocks-py`, source ".")
├── skills/stocks/
│   ├── SKILL.md           # Agent-facing reference (commands, options, output semantics)
│   └── scripts/
│       └── stocks.py      # The entire CLI — single file, all commands
├── tests/test_stocks.py
├── README.md              # Human-facing docs (installation, usage, examples)
└── CLAUDE.md              # This file
```

The repo root is the plugin, and the skill lives in the standard `skills/<name>/` layout. Don't move `SKILL.md` to the root: Cowork then installs the skill without `scripts/`. SKILL.md runs the script as `uv run --script ${CLAUDE_SKILL_DIR}/scripts/stocks.py`, and its `allowed-tools` rule matches that exact command, so keep the two in sync. Cowork runs it in a cloud sandbox: PyPI is reachable by default, but the Yahoo domains in `compatibility` have to be allowed, and nothing served on localhost reaches the user. The release zip (`.github/workflows/release.yml`) is the same plugin, for upload.

---

## The CLI Tool (`skills/stocks/scripts/stocks.py`)

### Execution Model

Uses the `uv run --script` shebang pattern (PEP 723) with inline dependency declarations:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.54",
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
# ]
# ///
```

Run directly: `uv run --script skills/stocks/scripts/stocks.py <command>` or, if installed in PATH, `stocks.py <command>`.

### Code Structure

Each command follows the same three-part pattern:

1. **`get_*()`** — fetches and normalizes data from yfinance, returns a plain `dict[str, Any]`
2. **`format_*()`** — takes the dict, returns a formatted string for stdout
3. **Subparser + dispatch** — registered in `main()`, calls get → format → print, or get → `to_json()` → print with `--json`

The data dict is the JSON contract: `--json` prints it as is through `to_json()` (NaN becomes `null`), so anything an agent needs belongs in the dict, not only in the formatted text. Every command except the chart server gets `--json` from one loop in `main()`; `chart --json` is its own.

Retrieval failures are returned as data rather than raised as exceptions. Formatters display failures explicitly. Recommendations must preserve successful source data while also displaying any partial retrieval failures, rather than silently treating failed sources as empty results.

### Commands

| Command | Get function | Format function | Key data source |
|---------|-------------|-----------------|-----------------|
| `quote` | `get_quote()` | `format_quote()` | `ticker.info`, `ticker.history()` |
| `search` | `search_ticker()` | `format_search()` | Yahoo Finance search API |
| `history` | `get_history()` | `format_history()` | `ticker.history()` |
| `chart` | `get_chart_data()`, `get_chart_info()` | `chart_page()` (HTML) | `ticker.history()`, `ticker.info` |
| `news` | `get_news()` | `format_news()` | `yf.Search(query).news` |
| `recommendations` | `get_recommendations()` | `format_recommendations()` | `ticker.recommendations_summary`, `ticker.upgrades_downgrades` |
| `fundamentals` | `get_fundamentals()` | `format_fundamentals()` | `ticker.income_stmt`, `ticker.balance_sheet`, `ticker.cashflow`, TTM variants |

`main()` prints the formatted output (or JSON) and exits 1 on any retrieval failure (`"error"` in the dict, or a non-empty `errors` list), including partial ones. Shared helpers: `RULE` (the `=` divider), `plural()`, `to_json()`. `format_quote()` shows net assets and the expense ratio for funds, which have no market cap.

### Chart Pipeline

`chart` follows drones.py's `map`: `chart_page()` fills the `CHART_PAGE` template (TradingView lightweight-charts, pinned on unpkg) with the first range's bars inlined, and `serve_chart()` serves it on `127.0.0.1` (default port 8767, free-port fallback). `CHART_PAGE` is indented as nested HTML inside `textwrap.dedent()` so it folds in an editor; keep new markup, CSS and JS at the matching level.

- **Data:** the page's range buttons fetch `/data.json?period=&interval=`, which calls `get_chart_data()` live. Yahoo has no moving-average series, so `get_chart_data()` computes them server-side: a second `history(start=...)` call fetches enough bars before the range (`_lookback_start()`) for the longest average, and each average is returned aligned with the bars (null where history ran out).
- **Stats strip:** `quote_from_info()` maps `ticker.info` to quote fields for both `quote` and the page (`get_chart_info()`); yfinance >= 0.2.54 reports `dividendYield` and `netExpenseRatio` as percentages already. `quote` uses Yahoo's `fiftyDayAverage` / `twoHundredDayAverage` and computes only SMA 20 and the EMAs.
- **Credits:** the library's own TradingView logo is kept and its link retargeted to the symbol's page (`tradingview_url()` maps Yahoo symbols to TradingView's). The Yahoo icon is an inline SVG from Simple Icons 9.0.0 linking to the symbol's Yahoo Finance page.
- **Output modes:** `--png` serves the page with controls hidden and a pinned size, and screenshots it with headless Chrome/Edge/Chromium (`find_browser()`, `STOCKS_BROWSER` override). `--json` prints the data. There is no matplotlib.

### Fundamentals Pipeline

`fundamentals` uses a two-stage data → formatting pipeline:

```
get_fundamentals(symbol)   →  factual financial snapshot dict with source dates
format_fundamentals(data)  →  compact stdout snapshot
to_json(data)              →  the same factual data as JSON (--json)
```

`--json` changes serialization, not the data content; `--raw` is removed.

`score_fundamentals` and all scoring/analysis helpers are removed. There are no computed scores, ratios, trends, CAGR, or dot meters. Extraction and formatting preserve factual values and actual source dates, including cashflow dates independently of income-statement dates.

### yfinance Data Shape Notes

- `ticker.income_stmt` / `ticker.balance_sheet` / `ticker.cashflow` — DataFrame where **columns are dates (newest first)** and **rows are metric names**. Preserve each statement's actual dates; do not substitute income-statement dates for cashflow or balance-sheet dates. Cash uses the `Cash And Cash Equivalents` row, not a broader cash/investments metric.
- `ticker.ttm_income_stmt` / `ticker.ttm_cashflow` — dated DataFrames, extracted with exact metric row names via `_statement_values()`; missing values retain their dates.
- `ticker.upgrades_downgrades` — DataFrame indexed by `GradeDate`. Use `pd.Timestamp.now(tz=ud.index.tz)` to support both timezone-aware and naive indexes.
- `ticker.recommendations_summary` — DataFrame with `period` column (`"0m"`, `"-1m"`, ... currently down to `"-3m"`; `period_label()` handles any depth) and columns `strongBuy`, `buy`, `hold`, `sell`, `strongSell`.
- `ticker.upgrades_downgrades` — `Action` is one of `up`, `down`, `init`, `main`, `reit` (`ACTION_LABELS`); price targets are `currentPriceTarget` / `priorPriceTarget` and can be NaN.
- `ticker.history()` — can end with today's bar holding volume but no prices just after the close; `quote`, `history` and `chart` drop it.
- `yf.Search(query, news_count=n).news` — returns a list of dicts with keys: `title`, `publisher`, `link`, `providerPublishTime` (Unix timestamp int), `type`, `relatedTickers`, `thumbnail`, `uuid`. No summary field, so there is no `--summary` option.

---

## The Skill (`SKILL.md`)

`SKILL.md` is the agent-facing contract. It follows the skill frontmatter format:

```yaml
---
name: stocks
description: <one-line trigger description for the agent>
compatibility: <runtime requirement>
---
```

The `description` field is what an agent uses to decide when to invoke this skill. Keep it comprehensive but accurate — it should list all major use cases so the agent picks this skill for the right queries.

### Skill vs README

| | `SKILL.md` | `README.md` |
|--|-----------|-------------|
| Audience | AI agents | Human developers/users |
| Tone | Precise, structured, scannable | Friendly, instructional |
| Focus | Command syntax, return values, option semantics | Installation, features, examples |
| Workflows | Agent research inputs (JSON snapshots, data collection loops) | Human workflows (charting, research) |

When adding a new command, update **both** files. SKILL.md should include the exact output fields the agent will need to parse or pass to an LLM.

---

## Adding a New Command

1. Add a `get_<name>()` function that returns `Dict[str, Any]` with `"error"` on failure
2. Add a `format_<name>()` function that checks for `"error"` first, then formats stdout
3. Register a subparser in `main()` with `subparsers.add_parser(...)`
4. Add a dispatch case in `main()` calling get → format → print
5. Update the docstring at the top of the file
6. Update `SKILL.md` — command section, options table, relevant workflow examples
7. Update `README.md` — Features list, Commands table, Usage section, Command Options table

---

## Financial Snapshot Contract (`fundamentals`)

Default output is compact and dated:

| Source | Rows | Periods |
|--------|------|---------|
| Income statement | Revenue, Gross Profit, Operating Income, Net Income | TTM and up to three fiscal years, with actual period dates |
| Cashflow | Free Cash Flow | TTM and up to three fiscal years, with its own period dates |
| Latest balance sheet | Cash (`Cash And Cash Equivalents`), Total Debt | Latest balance-sheet values with the actual date |

`--json` outputs the same factual values and dates. Amounts are displayed in billions of reported currency. JSON retains unscaled values. Retrieval failures exit with status 1. The command does not produce business-quality signals or rankings.

## Recommendations Contract

Retain strongBuy / buy / hold / sell / strongSell analyst counts for the current month and available prior months, plus dated per-firm rating/price-target changes for the requested history window (`--history` / `-H`, default 3 months). Do not compute BUY/SELL/HOLD verdicts. Display retrieval failures explicitly, including partial failures, alongside any successfully retrieved data.

---

## Agent Use Case

These three commands provide factual research inputs for an agent:

```bash
stocks.py fundamentals <TICKER> --json      # Dated financial snapshot
stocks.py recommendations <TICKER> --json   # Analyst counts and dated rating/price-target changes
stocks.py news <TICKER|TOPIC> --json        # Current news context
```

`--json` outputs the same factual data and dates as the default text output. Agents can collect these inputs across tickers without treating them as tool-generated investment verdicts, business-quality signals, or rankings.
