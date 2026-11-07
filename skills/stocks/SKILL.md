---
name: stocks
description: Get stock market data from Yahoo Finance. Use when the user asks about stock prices, quotes, company valuations, moving averages, historical data, stock charts, latest news, analyst recommendations, or dated financial snapshots. Supports any publicly traded stock via ticker symbol.
compatibility: Requires uv and network access to query1.finance.yahoo.com, query2.finance.yahoo.com, fc.yahoo.com and finance.yahoo.com. uv installs Python packages from PyPI on first run.
allowed-tools: Bash(uv run --script ${CLAUDE_SKILL_DIR}/scripts/stocks.py *)
---

# Stock Market Data Tool

Get stock quotes, news, analyst recommendations, dated financial snapshots, historical data, and charts using the `stocks.py` CLI powered by Yahoo Finance.

## Invocation

```bash
uv run --script ${CLAUDE_SKILL_DIR}/scripts/stocks.py <command> [args]
```

Examples in this document write `stocks.py` as shorthand for that whole command; always run the full form. uv installs the script's dependencies on first run, so the first call can take a few seconds longer.

If every command fails with a connection or DNS error, the sandbox is blocking Yahoo Finance. Tell the user to allow the domains listed under `compatibility` in their network settings (Cowork: Settings > Capabilities, or the organization's network egress allowlist) and start a new session, since network changes don't apply to a session that's already running. Don't fall back to made-up prices.

## JSON Output

Every command except the `chart` server takes `--json`, which prints the command's data as JSON instead of formatted text. Prefer it when you'll parse the result. Missing values are `null`, and a failure prints `{"error": "..."}` and exits 1.

| Command | Top-level JSON keys |
|---------|---------------------|
| `quote` | `symbol`, `company_name`, `quote_type`, `exchange`, `currency`, `current_price`, `market_cap`, `net_assets`, `pe_ratio`, `forward_pe`, `dividend_yield` and `expense_ratio` (already percentages: `0.33` = 0.33%), `52_week_high`, `52_week_low`, `volume`, `avg_volume`, `beta`, `sector`, `industry`, `market_time` (Unix seconds), `quote_time`, `yahoo_url` (the symbol's Yahoo Finance page), `moving_averages` (`SMA_20`… each `{value, position, distance_pct}`) |
| `search` | `query`, `count`, `results` (each `{symbol, name, exchange, type}`) |
| `history` | `symbol`, `period`, `interval`, `count`, `data` (each `{date, open, high, low, close, volume}`, prices to 2 decimals) |
| `news` | `query`, `count`, `articles` (each `{title, source, pub_date, url}`) |
| `recommendations` | `symbol`, `consensus` (each `{period, strong_buy, buy, hold, sell, strong_sell, total}`), `rating_changes` (each `{date, firm, from_grade, to_grade, action_label, pt_note}`), `history_months`, `errors`, `consensus_failed`, `rating_changes_failed` |
| `fundamentals` | `symbol`, `financials`, `balance_sheet` (see Fundamentals) |

`chart --json` prints the chart's bars and moving averages; see Charts.

## Commands Reference

### Stock Quote
```bash
stocks.py quote AAPL
stocks.py quote TSLA
```

Returns:
- Current price
- Market cap (funds such as SPY: net assets instead)
- P/E ratio (trailing and forward)
- Dividend yield (funds: plus expense ratio)
- 52-week high/low
- Volume (current and average)
- Beta
- Sector and industry
- Moving averages: SMA 50/200 as published by Yahoo; SMA 20 and EMA 9/21 computed from 6 months of daily closes
- Position relative to each MA (above/below with % distance)
- Link to the symbol's Yahoo Finance page

### Charts
```bash
# Interactive chart for the user: serves on localhost and opens their browser.
# Blocks until Ctrl+C, so run it in the background or let the user run it.
stocks.py chart AAPL
stocks.py chart MSFT --period 1y --ma 50 200 --theme dark

# The chart's bars as JSON
stocks.py chart AMD --period 5d --json
```

The page shows the symbol, name, exchange, last price, and change over the range; a stats strip from the same data as `quote` (market cap or a fund's net assets, P/E, forward P/E, dividend yield, expense ratio, beta, volume, average volume, 52-week range, sector and industry, skipping whatever Yahoo lacks for the asset type); a candlestick (or line) chart with a volume pane, and a crosshair readout of OHLCV and moving average values. In the browser the user can switch range (1D, 5D, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y, Max), chart type, MA20/50/200 overlays, and theme. Failures print `Error: ...` and exit 1.

The served page needs the user's own machine: it is only reachable from the computer the server runs on. In a sandbox such as Cowork, where the user can't open your localhost, don't start the server. Use `chart --json` and draw the chart yourself, or give the user the `yahoo_url` from `quote`.

Options:
| Option | Default | Description |
|--------|---------|-------------|
| `symbol` | required | Ticker symbol |
| `--period`, `-p` | 6mo | Starting period: 1d, 5d, 1mo, 3mo, 6mo, ytd, 1y, 2y, 5y, 10y, max |
| `--interval`, `-i` | per period | 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo. Defaults: 1d→5m, 5d→15m, 1mo→1h, 2y/5y→1wk, max→1mo, others 1d |
| `--type`, `-t` | candlestick | candlestick or line |
| `--ma` | none | Moving averages shown at start, e.g. `--ma 20 50 200` |
| `--theme` | light | light or dark |
| `--port` | 8767 | Serve port; falls back to a free port if taken |
| `--no-open` | off | Serve without opening a browser |
| `--json` | off | Print `symbol`, `name`, `exchange`, `currency`, `period`, `interval`, `intraday`, `bars` (`time`, `open`, `high`, `low`, `close`, `volume`), and `ma` (per period, e.g. `"200"`, a list of values aligned with `bars`) |

Intraday `time` values are Unix seconds of the exchange's wall-clock time (read them as UTC); daily and longer bars use `YYYY-MM-DD`. Moving averages are simple averages over that many **bars** of the chart's interval (MA200 on a weekly chart is 200 weeks), computed with history from before the range so they cover the whole chart. `ma` values are null only where history runs out (the start of `max`, or intraday data past Yahoo's limits).

### Search for Tickers
```bash
stocks.py search "Apple"
stocks.py search "electric vehicles" --limit 10
stocks.py search "semiconductor"
```

Returns:
- Ticker symbol
- Company name
- Exchange
- Quote type (EQUITY, ETF, etc.)

### Latest News
```bash
# News for a specific ticker
stocks.py news AAPL
stocks.py news TSLA --count 10

# General market/topic news
stocks.py news "oil prices"
stocks.py news "Federal Reserve interest rates"
stocks.py news "semiconductor sector"
```

Returns for each article:
- Headline
- Publisher and publish timestamp
- Article URL

Yahoo's news search returns no article summaries, so open the URL for the full story.

Options:
| Option | Default | Description |
|--------|---------|-------------|
| `query` | required | Ticker symbol or any search query string |
| `--count`, `-n` | 5 | Number of articles to return |

### Historical Data
```bash
# Default: 1 month of daily data
stocks.py history AAPL

# 1 year of daily data
stocks.py history TSLA --period 1y

# 3 months of weekly data
stocks.py history MSFT --period 3mo --interval 1wk

# 5 days of hourly data
stocks.py history NVDA --period 5d --interval 1h
```

Period/interval compatibility — not all combinations are valid in yfinance:

| Period | Valid intervals |
|--------|----------------|
| `1d` | `1m`, `5m`, `15m`, `1h` |
| `5d` | `1m`, `5m`, `15m`, `1h`, `1d` |
| `1mo` | `5m`, `15m`, `1h`, `1d` |
| `3mo` | `1h`, `1d` |
| `6mo`, `1y`, `2y` | `1d`, `1wk` |
| `5y`, `max` | `1d`, `1wk`, `1mo` |

Rule of thumb: use shorter intervals only with shorter periods. `1m` data is only available for the last 7 days; `1h` data for the last 730 days. Mismatched combinations return empty data without an error.

Returns OHLCV data:
- Date
- Open, High, Low, Close prices
- Volume

### Fundamentals
```bash
# Compact dated financial snapshot (default)
stocks.py fundamentals AAPL

# Same factual data as JSON for agent/LLM use
stocks.py fundamentals META --json
```

Returns a compact dated financial snapshot:
- **Income statement** — Revenue, Gross Profit, Operating Income, and Net Income for TTM and up to three fiscal years, with actual period dates
- **Cash flow** — Free Cash Flow for TTM and up to three fiscal years, with its own cashflow period dates (not borrowed from the income statement)
- **Latest balance sheet** — Cash (Cash And Cash Equivalents) and Total Debt with the actual balance-sheet date

`--json` contains the same factual data and dates as the default output. JSON fields are `symbol`, `financials` (each entry has `label`, `ttm`, and `annual`), and `balance_sheet` (entries have `label` and `latest`). Each dated value is `{period, value}`; missing values are null. JSON amounts are unscaled, while text displays billions of reported currency. Retrieval failures exit with status 1. No scores, ratios, trends, CAGR, dot meters, or business-quality/ranking signals are produced. There is no `--raw` flag.

Options:
| Option | Description |
|--------|-------------|
| `symbol` | Stock ticker symbol (required) |
| `--json` | Output the same factual financial snapshot and dates as JSON |

### Analyst Recommendations
```bash
# Analyst counts + dated rating/price-target changes
stocks.py recommendations AAPL

# Extended history
stocks.py recommendations TSLA --history 6
stocks.py recommendations NVDA -H 1
```

Returns:
- **Analyst counts** — strongBuy / buy / hold / sell / strongSell counts for current month and available prior months; no computed BUY/SELL/HOLD verdict
- **Dated rating/price-target changes** — per-firm actions with FromGrade → ToGrade, price targets, and action label (upgraded / downgraded / maintains)
- **Retrieval failures** — displayed explicitly, including partial failures when one source succeeds and another fails; available data remains visible

Options:
| Option | Default | Description |
|--------|---------|-------------|
| `symbol` | required | Stock ticker symbol |
| `--history`, `-H` | 3 | Months of rating change history to show |

## Example Workflows

### Quick Stock Check
```bash
stocks.py quote AAPL
```

### Company Research
```bash
# Dated financial snapshot
stocks.py fundamentals AAPL

# Analyst counts and dated rating/price-target changes
stocks.py recommendations AAPL

# Current news context
stocks.py news AAPL
```

### Agent Research Inputs
```bash
# All as JSON for parsing
stocks.py fundamentals AAPL --json
stocks.py recommendations AAPL --json
stocks.py news AAPL --count 10 --json
```

### Collect Financial Snapshots
```bash
# Collect dated factual data across multiple tickers (no rankings)
for ticker in AAPL MSFT GOOGL META AMZN; do
  stocks.py fundamentals $ticker
done
```

### Research a Company
```bash
# Find the ticker
stocks.py search "Tesla"

# Get quote
stocks.py quote TSLA

# Get a dated financial snapshot
stocks.py fundamentals TSLA

# View analyst counts and dated changes
stocks.py recommendations TSLA

# Latest news
stocks.py news TSLA

# View historical performance
stocks.py history TSLA --period 1y

# Chart data for analysis
stocks.py chart TSLA --period 1y --json
```

### Market / Topic News
```bash
stocks.py news "Federal Reserve"
stocks.py news "oil prices" --count 10
stocks.py news "semiconductor tariffs" -n 3
```

### Compare Stocks
```bash
for ticker in AAPL MSFT GOOGL; do
  stocks.py quote $ticker
done
```

### Historical Analysis
```bash
# Get weekly data for trend analysis
stocks.py history SPY --period 2y --interval 1wk

# Get daily data for recent moves
stocks.py history QQQ --period 3mo
```

## Understanding the Output

### Moving Averages
| Indicator | Description | Use Case |
|-----------|-------------|----------|
| SMA 20 | 20-day Simple Moving Average | Short-term trend |
| SMA 50 | 50-day Simple Moving Average | Medium-term trend |
| SMA 200 | 200-day Simple Moving Average | Long-term trend |
| EMA 9 | 9-day Exponential Moving Average | Fast signal |
| EMA 21 | 21-day Exponential Moving Average | Medium signal |

## Ticker Symbol Reference

### Major US Indexes
| Symbol | Name |
|--------|------|
| `^DJI` | Dow Jones Industrial Average |
| `^GSPC` | S&P 500 |
| `^IXIC` | NASDAQ Composite |
| `^RUT` | Russell 2000 |
| `^VIX` | CBOE Volatility Index (VIX) |
| `^TNX` | 10-Year Treasury Yield |
| `^TYX` | 30-Year Treasury Yield |

### International Indexes
| Symbol | Name |
|--------|------|
| `^FTSE` | FTSE 100 (UK) |
| `^GDAXI` | DAX (Germany) |
| `^N225` | Nikkei 225 (Japan) |
| `^HSI` | Hang Seng (Hong Kong) |
| `^STOXX50E` | Euro Stoxx 50 |

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
| `USDCAD=X` | US Dollar / Canadian Dollar |
| `AUDUSD=X` | Australian Dollar / US Dollar |
| `DX-Y.NYB` | US Dollar Index (DXY) |

### Cryptocurrencies
| Symbol | Name |
|--------|------|
| `BTC-USD` | Bitcoin |
| `ETH-USD` | Ethereum |
| `SOL-USD` | Solana |
| `XRP-USD` | Ripple |
| `DOGE-USD` | Dogecoin |

### Symbol Patterns
| Type | Pattern | Example |
|------|---------|---------|
| Stocks | Plain symbol | `AAPL`, `TSLA` |
| Indexes | `^` prefix | `^DJI`, `^GSPC` |
| Futures | `=F` suffix | `CL=F`, `GC=F` |
| Currencies | `=X` suffix | `EURUSD=X` |
| Crypto | `-USD` suffix | `BTC-USD` |

## Tips

- Use `search` when you don't know the exact ticker symbol
- Charts: `chart` without `--json` runs a server until stopped; use `--json` when you need the data yourself
- Historical intervals: period and interval must be compatible — see the period/interval table in the Historical Data section. Mismatched combinations silently return empty data.
- Quote's SMA 200 is Yahoo's figure; it can differ slightly from the chart's MA200 on daily bars, which uses dividend-adjusted closes
- Quote timestamps are from the last market data update, not current time
