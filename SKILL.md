---
name: stocks
description: Get stock market data from Yahoo Finance. Use when the user asks about stock prices, quotes, company valuations, moving averages, historical data, stock charts, latest news, analyst recommendations, or dated financial snapshots. Supports any publicly traded stock via ticker symbol.
compatibility: Requires uv or stocks.py in PATH.
---

# Stock Market Data Tool

Get stock quotes, news, analyst recommendations, dated financial snapshots, historical data, and charts using the `stocks.py` CLI powered by Yahoo Finance.

## Invocation

If `stocks.py` is installed in PATH:
```bash
stocks.py <command> [args]
```

Or run directly without installing:
```bash
uv run --script /path/to/skill/scripts/stocks.py <command> [args]
```

Examples in this document use `stocks.py` as shorthand for either invocation form above.

## Commands Reference

### Stock Quote
```bash
stocks.py quote AAPL
stocks.py quote TSLA
```

Returns:
- Current price
- Market cap
- P/E ratio (trailing and forward)
- Dividend yield
- 52-week high/low
- Volume (current and average)
- Beta
- Sector and industry
- Moving averages (SMA 20/50/200, EMA 9/21)
- Position relative to each MA (above/below with % distance)

### Generate Charts
```bash
# Default: 6-month candlestick, white background, no moving averages
stocks.py chart AAPL

# Line chart
stocks.py chart TSLA --type line

# Custom period
stocks.py chart MSFT --period 1y

# Black background (dark themes only)
stocks.py chart AMD --background black

# Custom dimensions
stocks.py chart GOOGL --width 1600 --height 1000

# Custom moving averages
stocks.py chart META --ma 9 21 50

# Full options
stocks.py chart AAPL --period 1y --type candlestick --background white --width 1400 --height 900 --ma 20 50 200 --output aapl_chart.png
```

Chart features:
- Candlestick or line chart types
- Moving average overlays (customizable periods)
- Volume subplot (candlestick mode)
- White (default), black, or transparent backgrounds — prefer white unless the output context is explicitly dark-themed
- Auto-contrasting colors for each background

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

# Show full article summary
stocks.py news NVDA --summary
stocks.py news "AI chips" -s -n 3
```

Returns for each article:
- Headline
- Publisher and publish timestamp
- Article URL
- Full summary paragraph (with `--summary`)

Options:
| Option | Default | Description |
|--------|---------|-------------|
| `query` | required | Ticker symbol or any search query string |
| `--count`, `-n` | 5 | Number of articles to return |
| `--summary`, `-s` | off | Show full summary paragraph |

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
# Fundamentals as JSON; recommendations and news as text
stocks.py fundamentals AAPL --json
stocks.py recommendations AAPL
stocks.py news AAPL --count 10
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

# Generate chart for analysis
stocks.py chart TSLA --period 1y --background white
```

### Market / Topic News
```bash
stocks.py news "Federal Reserve"
stocks.py news "oil prices" --count 10
stocks.py news "semiconductor tariffs" --summary
```

### Compare Stocks
```bash
for ticker in AAPL MSFT GOOGL; do
  stocks.py quote $ticker
done
```

### Generate Charts for Presentation
```bash
# Default: white background — works for most documents and slides
stocks.py chart AAPL --width 1400 --height 900

# Black background for explicitly dark-themed presentations
stocks.py chart TSLA --background black

# Transparent for overlay use
stocks.py chart MSFT --background transparent
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
- Chart backgrounds: default is `white` — use `black` only for explicitly dark-themed output, `transparent` for overlay use
- Historical intervals: period and interval must be compatible — see the period/interval table in the Historical Data section. Mismatched combinations silently return empty data.
- Moving averages require sufficient historical data (200+ days for MA 200)
- Quote timestamps are from the last market data update, not current time
