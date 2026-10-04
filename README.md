# stocks.py

An agent skill for stock market data and analysis, backed by a single-file CLI tool written in Python powered by Yahoo Finance and the [yfinance](https://github.com/ranaroussi/yfinance) Python library. Enables AI agents to fetch real-time quotes with technical indicators, search for ticker symbols, retrieve news, surface analyst recommendations, retrieve dated financial snapshots, retrieve historical OHLCV data, and generate publication-ready PNG charts.

![Caterpillar 6-month chart](https://raw.githubusercontent.com/vicgarcia/stocks.py/main/chart_example.png)

## Features

- **Single-file executable** - Uses `uv run --script` with inline dependencies (PEP 723)
- **Stock quotes** - Price, valuation metrics, volume, sector, and more
- **Moving averages** - SMA (20/50/200-day) and EMA (9/21-day) with position analysis
- **News** - Latest articles for any ticker or free-text market topic
- **Analyst recommendations** - Factual analyst counts and dated per-firm rating/price-target changes, with retrieval failures shown (including partial failures)
- **Fundamentals** - Compact dated financial snapshot of income, free cash flow, cash, and debt
- **Ticker search** - Find symbols by company name
- **Historical data** - OHLCV data with configurable periods and intervals
- **PNG charts** - Candlestick and line charts with transparent/white/black backgrounds

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

### Install for uv

```bash
# Clone the repo
git clone https://github.com/vicgarcia/stocks.py

# Run directly (dependencies auto-installed)
uv run --script scripts/stocks.py --help

# Install in PATH
cp scripts/stocks.py ~/.local/bin/stocks.py
chmod +x ~/.local/bin/stocks.py
stocks.py --help
```

### Install for Claude Desktop

Download `stocks-v*.zip` from [Releases](https://github.com/vicgarcia/stocks.py/releases).
Install in Claude Desktop as a skill.

## Commands

| Command | Description |
|---------|-------------|
| `quote` | Get stock quote with moving averages |
| `search` | Search for ticker symbols by company name |
| `news` | Latest news articles for a ticker or any search topic |
| `recommendations` | Analyst counts and dated rating/price-target changes |
| `fundamentals` | Compact dated financial snapshot |
| `history` | Get historical OHLCV data |
| `chart` | Generate PNG chart |

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

# Show full article summaries
stocks.py news NVDA --summary
stocks.py news "AI chips" -s -n 3
```

Output includes headline, publisher, timestamp, and URL for each article. Add `--summary` to show the full article summary paragraph.

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

```bash
# Default: 6-month candlestick, white background
stocks.py chart AAPL

# Black background
stocks.py chart MSFT --background black

# Transparent background
stocks.py chart TSLA --background transparent

# Line chart
stocks.py chart NVDA --type line

# Custom options
stocks.py chart AMD --period 1y --width 1400 --height 900 --ma 20 50 200 --output amd.png
```

## Command Options

### News Command

| Option | Default | Description |
|--------|---------|-------------|
| `query` | required | Ticker symbol or any search query string |
| `--count`, `-n` | 5 | Number of articles to return |
| `--summary`, `-s` | off | Show full summary paragraph |

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
| `--period`, `-p` | 6mo | Data period |
| `--type`, `-t` | candlestick | Chart type: candlestick, line |
| `--output`, `-o` | auto | Output file path |
| `--width` | 1200 | Width in pixels |
| `--height` | 800 | Height in pixels |
| `--ma` | 20 50 200 | Moving average periods |
| `--background`, `-b` | white | Background: white, black, transparent |

## Agent Research Workflow

These three commands provide factual inputs for agent research:

```bash
# 1. Fundamentals — Dated financial snapshot
stocks.py fundamentals AAPL --json

# 2. Recommendations — Analyst counts and dated rating/price-target changes
stocks.py recommendations AAPL

# 3. News — What is happening right now? (real-time context)
stocks.py news AAPL --count 10
```

With `--json` on `fundamentals`, an agent can collect the dated financial snapshot alongside analyst records and news. These commands supply data, not computed investment verdicts or business-quality rankings.

## Moving Averages

| Indicator | Period | Use Case |
|-----------|--------|----------|
| SMA 20 | 20 days | Short-term trend |
| SMA 50 | 50 days | Medium-term trend |
| SMA 200 | 200 days | Long-term trend |
| EMA 9 | 9 days | Fast momentum |
| EMA 21 | 21 days | Medium momentum |

## Agent Skill

This project includes a `SKILL.md` file for use with AI coding agents.

### Installation

```bash
# Create skills directory
mkdir -p /path/to/agent/skills/stocks

# Copy skill files
cp SKILL.md /path/to/agent/skills/stocks/
cp -r scripts/ /path/to/agent/skills/stocks/

# Ensure stocks.py is in PATH
cp scripts/stocks.py ~/.local/bin/
chmod +x ~/.local/bin/stocks.py
```

The agent reads `SKILL.md` to understand available commands, parameters, and how to interpret stock data.

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
