# stocks.py

An agent skill for stock market data and analysis, backed by a single-file CLI tool written in Python powered by Yahoo Finance and the [yfinance](https://github.com/ranaroussi/yfinance) Python library. Enables AI agents to fetch real-time quotes with technical indicators, search for ticker symbols, retrieve news, surface analyst recommendations, retrieve dated financial snapshots, retrieve historical OHLCV data, and open interactive charts in the browser or save them as PNGs.

![Caterpillar 6-month chart](https://raw.githubusercontent.com/vicgarcia/stocks.py/main/screenshot.png)

## Features

- **Single-file executable** - Uses `uv run --script` with inline dependencies (PEP 723)
- **Stock quotes** - Price, valuation metrics, volume, sector, and more
- **Moving averages** - SMA (20/50/200-day) and EMA (9/21-day) with position analysis
- **News** - Latest articles for any ticker or free-text market topic
- **Analyst recommendations** - Factual analyst counts and dated per-firm rating/price-target changes, with retrieval failures shown (including partial failures)
- **Fundamentals** - Compact dated financial snapshot of income, free cash flow, cash, and debt
- **Ticker search** - Find symbols by company name
- **Historical data** - OHLCV data with configurable periods and intervals
- **Interactive charts** - Candlestick or line chart served on localhost, with quote stats, range buttons, moving average toggles, a crosshair readout, and light/dark themes; `--png` saves a screenshot of it

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

### Install for uv

```bash
# Clone the repo
git clone https://github.com/vicgarcia/stocks.py

# Run directly (dependencies auto-installed)
uv run --script skills/stocks/scripts/stocks.py --help

# Install in PATH
cp skills/stocks/scripts/stocks.py ~/.local/bin/stocks.py
chmod +x ~/.local/bin/stocks.py
stocks.py --help
```

### Install as a Claude plugin (Cowork, Claude Code)

The repo is a plugin marketplace with one plugin, `stocks`.

- **Cowork / Claude Desktop:** Customize > Plugins > Add > Add marketplace, enter `vicgarcia/stocks.py`, then add the `stocks` plugin. Or download `stocks-v*.zip` from [Releases](https://github.com/vicgarcia/stocks.py/releases) and upload it as a custom plugin, or upload `stocks-skill-v*.zip` under Customize > Skills to add just the skill.
- **Claude Code:** `/plugin marketplace add vicgarcia/stocks.py`, then `/plugin install stocks@stocks-py`.

The skill runs the script with `uv run --script`, so the environment needs uv and network access to PyPI (for the dependencies) and Yahoo Finance (`query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com`, `finance.yahoo.com`). Cowork's sandbox allows package managers by default, but not Yahoo: add those domains under Settings > Capabilities (on Team and Enterprise, the organization's network egress allowlist), then start a new session. The interactive chart needs a local machine with a browser. In a sandbox, Claude uses `chart --json` instead.

## Commands

| Command | Description |
|---------|-------------|
| `quote` | Get stock quote with moving averages |
| `search` | Search for ticker symbols by company name |
| `news` | Latest news articles for a ticker or any search topic |
| `recommendations` | Analyst counts and dated rating/price-target changes |
| `fundamentals` | Compact dated financial snapshot |
| `history` | Get historical OHLCV data |
| `chart` | Serve an interactive chart on localhost, or save a PNG of it |

Add `--json` to any command except the chart server to get the data as JSON instead of formatted text, for scripts and agents. For example, `stocks.py quote AAPL --json`. Failures print `{"error": "..."}` and exit with status 1.

## Usage

### News

```bash
# News for a specific ticker
stocks.py news AAPL
stocks.py news TSLA --count 10

# General market or topic news
stocks.py news "oil prices"
stocks.py news "Federal Reserve interest rates"
stocks.py news "semiconductor tariffs"
```

Output includes headline, publisher, timestamp, and URL for each article.

### Analyst Recommendations

```bash
# Analyst counts + last 3 months of dated rating/price-target changes
stocks.py recommendations AAPL

# Extended history
stocks.py recommendations TSLA --history 6
stocks.py recommendations NVDA -H 1
```

Output includes:
- **Analyst counts** — strongBuy / buy / hold / sell / strongSell counts for current month and available prior months; no computed BUY/SELL/HOLD verdict
- **Dated rating/price-target changes** — per-firm actions with grade transitions and price targets
- **Retrieval failures** — displayed explicitly, including partial failures when one source succeeds and another fails; available data remains visible

### Fundamentals

```bash
# Compact dated financial snapshot (default)
stocks.py fundamentals AAPL

# Same factual data as JSON for agents/LLMs
stocks.py fundamentals META --json
```

The default output is a compact financial snapshot:
- **Income statement** — Revenue, Gross Profit, Operating Income, and Net Income for TTM and up to three fiscal years, with actual period dates
- **Cash flow** — Free Cash Flow for TTM and up to three fiscal years, using its own cashflow period dates rather than income-statement dates
- **Latest balance sheet** — Cash (Cash And Cash Equivalents) and Total Debt, with the actual balance-sheet date

`--json` outputs the same factual data and dates. Text displays billions of reported currency; JSON retains unscaled values. Retrieval failures exit with status 1. No scores, ratios, trends, CAGR, dot meters, or business-quality/ranking signals are produced. There is no `--raw` flag.

### Stock Quote

```bash
stocks.py quote AAPL
stocks.py quote TSLA
```

Output includes:
- Current price and market cap
- P/E ratios (trailing and forward)
- Dividend yield
- 52-week high/low
- Volume metrics
- Sector and industry
- Moving averages with position (above/below)

### Search Tickers

```bash
# Search by company name
stocks.py search "Apple"
stocks.py search "electric vehicles"

# Limit results
stocks.py search "semiconductor" --limit 10
```

### Historical Data

```bash
# Default: 1 month daily
stocks.py history AAPL

# Custom period and interval
stocks.py history TSLA --period 1y --interval 1d
stocks.py history MSFT --period 3mo --interval 1wk
stocks.py history NVDA --period 5d --interval 1h
```

### Generate Charts

`chart` starts a small web server on `127.0.0.1` and opens the chart in your browser. The page can switch ranges (1D to Max), candles and line, moving averages, and theme; other ranges are fetched live. Press Ctrl+C to stop it.

```bash
# Interactive 6-month candlestick chart
stocks.py chart AAPL

# Start on 1 year with the 50 and 200-day moving averages, dark theme
stocks.py chart MSFT --period 1y --ma 50 200 --theme dark

# Save a PNG instead (needs Chrome, Edge or Chromium)
stocks.py chart NVDA --png nvda.png
stocks.py chart TSLA --type line --size 1600x900 --png tsla.png

# Print the bars as JSON
stocks.py chart AMD --period 5d --json
```

`--png` loads the same page in headless Chrome, Edge or Chromium and screenshots it. Set `STOCKS_BROWSER` to the browser's path if it isn't found.

## Command Options

### News Command

| Option | Default | Description |
|--------|---------|-------------|
| `query` | required | Ticker symbol or any search query string |
| `--count`, `-n` | 5 | Number of articles to return |

### Recommendations Command

| Option | Default | Description |
|--------|---------|-------------|
| `symbol` | required | Stock ticker symbol |
| `--history`, `-H` | 3 | Months of rating change history to show |

### Fundamentals Command

| Option | Description |
|--------|-------------|
| `symbol` | Stock ticker symbol (required) |
| `--json` | Output the same factual financial snapshot and dates as JSON |

### Quote Command

| Option | Description |
|--------|-------------|
| `symbol` | Stock ticker symbol (required) |

### Search Command

| Option | Default | Description |
|--------|---------|-------------|
| `query` | required | Company name to search |
| `--limit`, `-l` | 20 | Maximum results to return |

### History Command

| Option | Default | Description |
|--------|---------|-------------|
| `symbol` | required | Stock ticker symbol |
| `--period`, `-p` | 1mo | Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max |
| `--interval`, `-i` | 1d | Interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo |

### Chart Command

| Option | Default | Description |
|--------|---------|-------------|
| `symbol` | required | Stock ticker symbol |
| `--period`, `-p` | 6mo | Starting period: 1d, 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max |
| `--interval`, `-i` | per period | Bar interval: 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo |
| `--type`, `-t` | candlestick | Chart type: candlestick, line |
| `--ma` | none | Moving averages shown at start (20, 50, 200 are always toggleable) |
| `--theme` | light | Color theme: light, dark |
| `--port` | 8767 | Port to serve on; falls back to a free port if taken |
| `--no-open` | off | Don't open a browser |
| `--png FILE` | - | Save a screenshot instead of serving |
| `--size` | 1200x800 | Screenshot size for `--png` |
| `--json` | off | Print the chart data as JSON instead of serving |

## Agent Research Workflow

These three commands provide factual inputs for agent research:

```bash
# 1. Fundamentals — Dated financial snapshot
stocks.py fundamentals AAPL --json

# 2. Recommendations — Analyst counts and dated rating/price-target changes
stocks.py recommendations AAPL --json

# 3. News — What is happening right now? (real-time context)
stocks.py news AAPL --count 10 --json
```

With `--json`, an agent can collect the dated financial snapshot alongside analyst records and news. These commands supply data, not computed investment verdicts or business-quality rankings.

## Moving Averages

| Indicator | Period | Use Case |
|-----------|--------|----------|
| SMA 20 | 20 days | Short-term trend |
| SMA 50 | 50 days | Medium-term trend |
| SMA 200 | 200 days | Long-term trend |
| EMA 9 | 9 days | Fast momentum |
| EMA 21 | 21 days | Medium momentum |

## Agent Skill

The skill lives in `skills/stocks/` (`SKILL.md` plus `scripts/`). For Claude, install it as a plugin (see Installation). For other agents, copy that folder into their skills directory:

```bash
cp -r skills/stocks /path/to/agent/skills/
```

`SKILL.md` runs the script as `uv run --script ${CLAUDE_SKILL_DIR}/scripts/stocks.py`. Claude fills in `${CLAUDE_SKILL_DIR}`; for other agents, replace it with the skill directory's path.

## Ticker Symbol Reference

Beyond stocks, yfinance supports indexes, commodities, currencies, and crypto using special symbol patterns.

### Major US Indexes

| Symbol | Name |
|--------|------|
| `^DJI` | Dow Jones Industrial Average |
| `^GSPC` | S&P 500 |
| `^IXIC` | NASDAQ Composite |
| `^RUT` | Russell 2000 |
| `^VIX` | CBOE Volatility Index |
| `^TNX` | 10-Year Treasury Yield |

### International Indexes

| Symbol | Name |
|--------|------|
| `^FTSE` | FTSE 100 (UK) |
| `^GDAXI` | DAX (Germany) |
| `^N225` | Nikkei 225 (Japan) |
| `^HSI` | Hang Seng (Hong Kong) |

### Commodities (Futures)

#### Energy
| Symbol | Name |
|--------|------|
| `CL=F` | WTI Crude Oil |
| `BZ=F` | Brent Crude Oil |
| `NG=F` | Natural Gas |
| `RB=F` | Gasoline (RBOB) |
| `HO=F` | Heating Oil |

#### Metals
| Symbol | Name |
|--------|------|
| `GC=F` | Gold |
| `SI=F` | Silver |
| `HG=F` | Copper |
| `PL=F` | Platinum |
| `PA=F` | Palladium |

#### Agriculture
| Symbol | Name |
|--------|------|
| `ZC=F` | Corn |
| `ZW=F` | Wheat |
| `ZS=F` | Soybeans |
| `KC=F` | Coffee |
| `SB=F` | Sugar |
| `CC=F` | Cocoa |
| `CT=F` | Cotton |
| `LC=F` | Live Cattle |
| `LH=F` | Lean Hogs |

### Currencies

| Symbol | Name |
|--------|------|
| `EURUSD=X` | Euro / US Dollar |
| `GBPUSD=X` | British Pound / US Dollar |
| `USDJPY=X` | US Dollar / Japanese Yen |
| `DX-Y.NYB` | US Dollar Index (DXY) |

### Cryptocurrencies

| Symbol | Name |
|--------|------|
| `BTC-USD` | Bitcoin |
| `ETH-USD` | Ethereum |
| `SOL-USD` | Solana |

### Symbol Patterns

| Type | Pattern | Example |
|------|---------|---------|
| Stocks | Plain symbol | `AAPL`, `TSLA` |
| Indexes | `^` prefix | `^DJI`, `^GSPC` |
| Futures | `=F` suffix | `CL=F`, `GC=F` |
| Currencies | `=X` suffix | `EURUSD=X` |
| Crypto | `-USD` suffix | `BTC-USD` |

## Data Source

- **Provider**: Yahoo Finance (via yfinance library)
- **Coverage**: US and international exchanges
- **Real-time**: ~15 minute delay for free tier
- **Historical**: Daily data back to IPO for most stocks
