#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.0",
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
#     "matplotlib>=3.7.0",
# ]
# ///
"""
yfinance CLI - Stock market data and charting tool

Commands:
    quote           - Get stock quote with moving averages
    search          - Search for ticker symbols by company name
    history         - Get historical OHLCV data
    chart           - Generate PNG chart with white background (default)
    news            - Get latest news for a ticker or any search query
    recommendations - Analyst consensus and recent rating changes
    fundamentals    - Compact financial snapshot (no scoring)
"""

import argparse
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

import yfinance as yf
import pandas as pd
import requests


# --- Quote Command ---

def get_quote(symbol: str) -> Dict[str, Any]:
    """Get stock quote with moving averages."""
    ticker = yf.Ticker(symbol)
    info = ticker.info

    if not info or info.get("regularMarketPrice") is None:
        return {"error": f"No data found for symbol: {symbol}"}

    # Get quote timestamp
    market_time = info.get("regularMarketTime")
    if market_time:
        quote_timestamp = datetime.fromtimestamp(market_time).strftime("%Y-%m-%d %H:%M:%S")
    else:
        quote_timestamp = None

    # Basic quote data
    quote = {
        "symbol": symbol.upper(),
        "company_name": info.get("longName", "N/A"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "quote_time": quote_timestamp,
    }

    # Get historical data for moving averages
    hist = ticker.history(period="1y")
    if len(hist) >= 20:
        prices = hist["Close"]
        current_price = quote["current_price"]

        # Calculate moving averages
        ma_data = {}
        for period, name in [(20, "SMA_20"), (50, "SMA_50"), (200, "SMA_200")]:
            if len(prices) >= period:
                ma_value = prices.rolling(window=period).mean().iloc[-1]
                ma_data[name] = {
                    "value": round(ma_value, 2),
                    "position": "above" if current_price > ma_value else "below",
                    "distance_pct": round((current_price - ma_value) / ma_value * 100, 2),
                }

        # EMA
        for span, name in [(9, "EMA_9"), (21, "EMA_21")]:
            if len(prices) >= span:
                ema_value = prices.ewm(span=span).mean().iloc[-1]
                ma_data[name] = {
                    "value": round(ema_value, 2),
                    "position": "above" if current_price > ema_value else "below",
                }

        quote["moving_averages"] = ma_data

    return quote



def format_quote(quote: Dict[str, Any]) -> str:
    """Format quote data for display."""
    if "error" in quote:
        return f"Error: {quote['error']}"

    lines = [
        f"\n{'='*60}",
        f"  {quote['symbol']} - {quote.get('company_name', 'N/A')}",
        f"{'='*60}",
        "",
        "  PRICE & VALUATION",
        f"  Current Price:    ${float(quote['current_price']):,.2f}" if quote.get('current_price') else "  Current Price:    N/A",
        f"  Market Cap:       ${float(quote['market_cap']):,.0f}" if quote.get('market_cap') else "  Market Cap:       N/A",
        f"  P/E Ratio:        {float(quote['pe_ratio']):.2f}" if quote.get('pe_ratio') else "  P/E Ratio:        N/A",
        f"  Forward P/E:      {float(quote['forward_pe']):.2f}" if quote.get('forward_pe') else "  Forward P/E:      N/A",
        f"  Dividend Yield:   {float(quote['dividend_yield'])*100:.2f}%" if quote.get('dividend_yield') else "  Dividend Yield:   N/A",
        "",
        "  52-WEEK RANGE",
        f"  High:             ${float(quote['52_week_high']):,.2f}" if quote.get('52_week_high') else "  High:             N/A",
        f"  Low:              ${float(quote['52_week_low']):,.2f}" if quote.get('52_week_low') else "  Low:              N/A",
        "",
        "  VOLUME",
        f"  Volume:           {int(quote['volume']):,}" if quote.get('volume') else "  Volume:           N/A",
        f"  Avg Volume:       {int(quote['avg_volume']):,}" if quote.get('avg_volume') else "  Avg Volume:       N/A",
        "",
        "  CLASSIFICATION",
        f"  Sector:           {quote.get('sector', 'N/A')}",
        f"  Industry:         {quote.get('industry', 'N/A')}",
        f"  Beta:             {float(quote['beta']):.2f}" if quote.get('beta') else "  Beta:             N/A",
    ]

    # Moving averages
    if "moving_averages" in quote:
        lines.extend(["", "  MOVING AVERAGES"])
        for ma_name, ma_info in quote["moving_averages"].items():
            position = ma_info.get("position", "")
            distance = ma_info.get("distance_pct", "")
            distance_str = f" ({distance:+.2f}%)" if distance is not None and distance != "" else ""
            lines.append(f"  {ma_name:12}  ${ma_info['value']:>10,.2f}  [{position.upper()}]{distance_str}")

    # Quote timestamp at bottom
    if quote.get("quote_time"):
        lines.append(f"\n  Quote: {quote['quote_time']}")

    lines.append(f"\n{'='*60}\n")
    return "\n".join(lines)


# --- Search Command ---

def search_ticker(query: str, limit: int = 20) -> Dict[str, Any]:
    """Search for ticker symbols by company name."""
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    params = {"q": query, "quotes_count": limit, "country": "United States"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        quotes = response.json().get("quotes", [])

        results = []
        for quote in quotes[:limit]:
            results.append({
                "symbol": quote.get("symbol", "N/A"),
                "name": quote.get("longname") or quote.get("shortname", "N/A"),
                "exchange": quote.get("exchange", "N/A"),
                "type": quote.get("quoteType", "N/A"),
            })

        return {"query": query, "count": len(results), "results": results}

    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


def format_search(data: Dict[str, Any]) -> str:
    """Format search results for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [f"\nSearch results for '{data['query']}': {data['count']} found\n"]

    if not data["results"]:
        lines.append("  No results found.")
    else:
        lines.append(f"  {'SYMBOL':<10} {'EXCHANGE':<10} {'TYPE':<10} NAME")
        lines.append(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*30}")
        for r in data["results"]:
            lines.append(f"  {r['symbol']:<10} {r['exchange']:<10} {r['type']:<10} {r['name']}")

    lines.append("")
    return "\n".join(lines)


# --- History Command ---

def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
    """Get historical OHLCV data."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        return {"error": f"No historical data found for {symbol}"}

    records = []
    for date, row in hist.iterrows():
        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": int(row["Volume"]),
        })

    return {
        "symbol": symbol.upper(),
        "period": period,
        "interval": interval,
        "count": len(records),
        "data": records,
    }


def format_history(data: Dict[str, Any]) -> str:
    """Format history data for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [
        f"\n{data['symbol']} Historical Data ({data['period']}, {data['interval']})",
        f"Records: {data['count']}\n",
        f"  {'DATE':<12} {'OPEN':>10} {'HIGH':>10} {'LOW':>10} {'CLOSE':>10} {'VOLUME':>14}",
        f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*14}",
    ]

    for rec in data["data"]:
        lines.append(
            f"  {rec['date']:<12} {rec['open']:>10.2f} {rec['high']:>10.2f} "
            f"{rec['low']:>10.2f} {rec['close']:>10.2f} {rec['volume']:>14,}"
        )

    lines.append("")
    return "\n".join(lines)


# --- Chart Command ---

def generate_chart(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    chart_type: str = "candlestick",
    output: Optional[str] = None,
    width: int = 1200,
    height: int = 800,
    ma_periods: Optional[List[int]] = None,
    background: str = "white",
) -> str:
    """Generate PNG chart with configurable background."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    if ma_periods is None:
        ma_periods = [20, 50, 200]

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        return f"Error: No data found for {symbol}"

    # Detect intraday data and compute bar width + date format accordingly
    if len(hist) > 1:
        bar_delta_days = (hist.index[1] - hist.index[0]).total_seconds() / 86400
    else:
        bar_delta_days = 1.0
    bar_width = bar_delta_days * 0.8
    is_intraday = bar_delta_days < 1.0
    date_fmt = mdates.DateFormatter("%H:%M") if is_intraday else mdates.DateFormatter("%b %d")

    # Color schemes based on background
    if background == "black":
        colors = {
            "price": "#FFFFFF",
            "bullish": "#00FF88",
            "bearish": "#FF6B6B",
            "ma_20": "#FFD93D",
            "ma_50": "#C084FC",
            "ma_200": "#60A5FA",
            "volume_up": "#00FF88",
            "volume_down": "#FF6B6B",
            "grid": "#444444",
            "text": "#FFFFFF",
            "bg": "#000000",
        }
        fig_facecolor = "#000000"
        ax_facecolor = "#000000"
        transparent = False
    elif background == "white":
        colors = {
            "price": "#2C3E50",
            "bullish": "#27AE60",
            "bearish": "#E74C3C",
            "ma_20": "#F39C12",
            "ma_50": "#9B59B6",
            "ma_200": "#3498DB",
            "volume_up": "#27AE60",
            "volume_down": "#E74C3C",
            "grid": "#CCCCCC",
            "text": "#2C3E50",
            "bg": "#FFFFFF",
        }
        fig_facecolor = "#FFFFFF"
        ax_facecolor = "#FFFFFF"
        transparent = False
    else:  # transparent
        colors = {
            "price": "#2C3E50",
            "bullish": "#27AE60",
            "bearish": "#E74C3C",
            "ma_20": "#F39C12",
            "ma_50": "#9B59B6",
            "ma_200": "#3498DB",
            "volume_up": "#27AE60",
            "volume_down": "#E74C3C",
            "grid": "#CCCCCC",
            "text": "#2C3E50",
            "bg": "none",
        }
        fig_facecolor = "none"
        ax_facecolor = "none"
        transparent = True

    # Setup figure
    fig_width = width / 100
    fig_height = height / 100

    if chart_type == "candlestick":
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(fig_width, fig_height),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor=fig_facecolor
        )
        ax1.set_facecolor(ax_facecolor)
        ax2.set_facecolor(ax_facecolor)

        # Candlestick chart
        for i in range(len(hist)):
            date = mdates.date2num(hist.index[i])
            open_price = hist["Open"].iloc[i]
            close_price = hist["Close"].iloc[i]
            high_price = hist["High"].iloc[i]
            low_price = hist["Low"].iloc[i]

            color = colors["bullish"] if close_price >= open_price else colors["bearish"]

            # Wick
            ax1.plot([date, date], [low_price, high_price], color=color, linewidth=0.8)
            # Body
            body_bottom = min(open_price, close_price)
            body_height = abs(close_price - open_price)
            ax1.bar(date, body_height, bottom=body_bottom, width=bar_width, color=color, edgecolor=color)

        # Volume bars
        volume_colors = [
            colors["volume_up"] if hist["Close"].iloc[i] >= hist["Open"].iloc[i] else colors["volume_down"]
            for i in range(len(hist))
        ]
        ax2.bar(mdates.date2num(hist.index), hist["Volume"], width=bar_width, color=volume_colors, alpha=0.7)
        ax2.set_ylabel("Volume", color=colors["text"])
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x/1e6:.1f}M"))
        ax2.xaxis.set_major_formatter(date_fmt)
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax2.tick_params(colors=colors["text"])
        ax2.grid(True, alpha=0.3, color=colors["grid"])

    else:  # line chart
        fig, ax1 = plt.subplots(figsize=(fig_width, fig_height), facecolor=fig_facecolor)
        ax1.set_facecolor(ax_facecolor)
        ax1.plot(hist.index, hist["Close"], color=colors["price"], linewidth=2, label="Close")

    # Add moving averages
    ma_colors = {20: colors["ma_20"], 50: colors["ma_50"], 200: colors["ma_200"]}
    for ma_period in ma_periods:
        if len(hist) >= ma_period:
            ma = hist["Close"].rolling(window=ma_period).mean()
            ax1.plot(
                hist.index, ma,
                color=ma_colors.get(ma_period, "#888888"),
                linewidth=1.5,
                label=f"MA {ma_period}",
                alpha=0.8
            )

    # Styling
    ax1.set_title(f"{symbol.upper()} - {period.upper()}", color=colors["text"], fontsize=14, pad=10)
    ax1.set_ylabel("Price ($)", color=colors["text"])
    ax1.tick_params(colors=colors["text"])
    ax1.grid(True, alpha=0.3, color=colors["grid"])

    # Only show legend if there are labeled elements
    handles, _ = ax1.get_legend_handles_labels()
    if handles:
        ax1.legend(loc="upper left", framealpha=0.8)
    ax1.xaxis.set_major_formatter(date_fmt)
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())

    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right", color=colors["text"])
    if chart_type == "candlestick":
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right", color=colors["text"])

    plt.tight_layout()

    # Output path
    if output is None:
        output = f"{symbol.lower()}_{period}_{chart_type}.png"

    # Save chart
    fig.savefig(output, format="png", dpi=100, bbox_inches="tight", transparent=transparent,
                facecolor=fig_facecolor if not transparent else "none")
    plt.close(fig)

    return f"Chart saved: {output}"


# --- News Command ---

def get_news(query: str, count: int = 5) -> Dict[str, Any]:
    """Get news articles for a ticker symbol or general search query."""
    try:
        results = yf.Search(query, news_count=count).news
    except Exception as e:
        return {"error": f"News fetch failed: {str(e)}"}

    if not results:
        return {"query": query, "count": 0, "articles": []}

    articles = []
    for item in results[:count]:
        source = item.get("publisher", "Unknown")

        url = item.get("link", "")

        pub_ts = item.get("providerPublishTime") or item.get("pubDate")
        if isinstance(pub_ts, (int, float)):
            try:
                pub_date = datetime.fromtimestamp(pub_ts).strftime("%b %d %Y, %-I:%M %p")
            except Exception:
                pub_date = str(pub_ts)
        else:
            pub_date = str(pub_ts) if pub_ts else ""

        articles.append({
            "title": item.get("title", "No title"),
            "summary": item.get("summary", ""),
            "pub_date": pub_date,
            "source": source,
            "url": url,
        })

    return {"query": query, "count": len(articles), "articles": articles}


def format_news(data: Dict[str, Any], full_summary: bool = False) -> str:
    """Format news articles for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    query = data["query"]
    count = data["count"]
    sep = "=" * 60

    lines = [
        f"\n{query.upper()}  Latest News  ({count} articles)",
        sep,
    ]

    if not data["articles"]:
        lines.append("\n  No news articles found.")
    else:
        for i, article in enumerate(data["articles"], 1):
            lines.append("")
            lines.append(f"[{i}] {article['title']}")
            lines.append(f"    {article['source']} · {article['pub_date']}")

            summary = article.get("summary", "")
            if summary:
                if full_summary:
                    # Wrap long summaries at ~72 chars
                    words = summary.split()
                    line_buf, wrapped = [], []
                    for word in words:
                        if sum(len(w) + 1 for w in line_buf) + len(word) > 72:
                            wrapped.append("    " + " ".join(line_buf))
                            line_buf = [word]
                        else:
                            line_buf.append(word)
                    if line_buf:
                        wrapped.append("    " + " ".join(line_buf))
                    lines.extend(wrapped)
                else:
                    truncated = summary[:120] + "..." if len(summary) > 120 else summary
                    lines.append(f"    {truncated}")

            if article["url"]:
                lines.append(f"    {article['url']}")

    lines.append(f"\n{sep}\n")
    return "\n".join(lines)


# --- Recommendations Command ---

def get_recommendations(symbol: str, history_months: int = 3) -> Dict[str, Any]:
    """Get analyst consensus and recent rating changes."""
    ticker = yf.Ticker(symbol)

    errors = []
    consensus_failed = False
    changes_failed = False
    # Consensus summary (current + prior months)
    consensus_rows = []
    try:
        summary = ticker.recommendations_summary
        if summary is not None and not summary.empty:
            for _, row in summary.iterrows():
                period = row.get("period", "")
                strong_buy  = int(row.get("strongBuy",  0))
                buy         = int(row.get("buy",        0))
                hold        = int(row.get("hold",       0))
                sell        = int(row.get("sell",       0))
                strong_sell = int(row.get("strongSell", 0))
                total = strong_buy + buy + hold + sell + strong_sell
                consensus_rows.append({
                    "period": period,
                    "strong_buy": strong_buy,
                    "buy": buy,
                    "hold": hold,
                    "sell": sell,
                    "strong_sell": strong_sell,
                    "total": total,
                })
    except Exception as e:
        consensus_failed = True
        errors.append(f"Failed to fetch analyst consensus: {e}")

    # Upgrades/downgrades
    rating_changes = []
    try:
        ud = ticker.upgrades_downgrades
        if ud is not None and not ud.empty:
            # Filter to requested months window
            cutoff = pd.Timestamp.now(tz=ud.index.tz) - pd.DateOffset(months=history_months)
            ud = ud[ud.index >= cutoff]
            ud = ud.sort_index(ascending=False)

            for date, row in ud.iterrows():
                firm        = row.get("Firm", "")
                from_grade  = row.get("FromGrade", "")
                to_grade    = row.get("ToGrade", "")
                action      = row.get("Action", "")
                curr_pt     = row.get("CurrentPriceTarget") or row.get("currentPriceTarget")
                prior_pt    = row.get("PriorPriceTarget") or row.get("priorPriceTarget")

                # Price target annotation
                if curr_pt and prior_pt and curr_pt != prior_pt:
                    try:
                        direction = "up" if float(curr_pt) > float(prior_pt) else "down"
                        pt_note = f"${float(curr_pt):.0f}  {direction} from ${float(prior_pt):.0f}"
                    except (ValueError, TypeError):
                        pt_note = f"${curr_pt}"
                elif curr_pt:
                    try:
                        pt_note = f"${float(curr_pt):.0f}"
                    except (ValueError, TypeError):
                        pt_note = str(curr_pt)
                else:
                    pt_note = ""

                # Action label
                action_lower = str(action).lower()
                if "up" in action_lower:
                    action_label = "upgraded"
                elif "down" in action_lower:
                    action_label = "downgraded"
                else:
                    action_label = "(maintains)"

                rating_changes.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "firm": firm,
                    "from_grade": from_grade,
                    "to_grade": to_grade,
                    "action_label": action_label,
                    "pt_note": pt_note,
                })
    except Exception as e:
        changes_failed = True
        errors.append(f"Failed to fetch rating changes: {e}")

    return {
        "symbol": symbol.upper(),
        "errors": errors,
        "consensus_failed": consensus_failed,
        "rating_changes_failed": changes_failed,
        "consensus": consensus_rows,
        "rating_changes": rating_changes,
        "history_months": history_months,
    }


def format_recommendations(data: Dict[str, Any]) -> str:
    """Format analyst consensus and rating changes for display."""
    symbol = data["symbol"]
    sep = "=" * 60

    lines = [
        f"\n{symbol}  Analyst Consensus",
        sep,
    ]

    for error in data.get("errors", []):
        lines.append(f"\n  Error: {error}")

    # Consensus table
    if data["consensus"]:
        lines.append("")
        lines.append("  CONSENSUS BREAKDOWN")
        lines.append("")
        lines.append(f"  {'Period':<10} {'Strong Buy':>10} {'Buy':>5} {'Hold':>6} {'Sell':>6} {'Strong Sell':>12} {'Total':>7}")
        lines.append(f"  {'-'*10} {'-'*10} {'-'*5} {'-'*6} {'-'*6} {'-'*12} {'-'*7}")

        period_labels = {"0m": "Now", "-1m": "-1 Month", "-2m": "-2 Months"}
        for row in data["consensus"]:
            label = period_labels.get(row["period"], row["period"])
            lines.append(
                f"  {label:<10} {row['strong_buy']:>10} {row['buy']:>5} {row['hold']:>6}"
                f" {row['sell']:>6} {row['strong_sell']:>12} {row['total']:>7}"
            )
    elif not data.get("consensus_failed"):
        lines.append("\n  No consensus data available.")

    # Rating changes
    lines.append("")
    lines.append(f"  RECENT RATING CHANGES  (last {data['history_months']} months)")
    lines.append("")

    if data["rating_changes"]:
        for chg in data["rating_changes"]:
            from_g = chg["from_grade"] or "-"
            to_g   = chg["to_grade"]   or "-"
            grade_str = f"{from_g:<18} -> {to_g:<18}"
            pt = f"  {chg['pt_note']}" if chg["pt_note"] else ""
            lines.append(
                f"  {chg['date']:<10} {chg['firm']:<22} {grade_str}{pt}  {chg['action_label']}"
            )
    elif not data.get("rating_changes_failed"):
        lines.append("  No rating changes found in this period.")

    lines.append(f"\n{sep}\n")
    return "\n".join(lines)


# --- Fundamentals Command ---

def _statement_values(statement, metric: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Return dated values using exact row names; preserve missing fiscal periods."""
    if statement is None or statement.empty:
        return []
    values = []
    for date in statement.columns[:limit]:
        value = statement.loc[metric, date] if metric in statement.index else None
        values.append({
            "period": date.strftime("%Y-%m-%d"),
            "value": float(value) if value is not None and pd.notna(value) else None,
        })
    return values


def get_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch a factual financial snapshot without scoring or investment verdicts."""
    ticker = yf.Ticker(symbol)
    try:
        income = ticker.income_stmt
        balance = ticker.balance_sheet
        cashflow = ticker.cashflow
        ttm_income = ticker.ttm_income_stmt
        ttm_cashflow = ticker.ttm_cashflow
    except Exception as e:
        return {"error": f"Failed to fetch fundamentals for {symbol}: {e}"}

    metrics = []
    for label, metric, annual, ttm in [
        ("Revenue", "Total Revenue", income, ttm_income),
        ("Gross Profit", "Gross Profit", income, ttm_income),
        ("Operating Income", "Operating Income", income, ttm_income),
        ("Net Income", "Net Income", income, ttm_income),
        ("Free Cash Flow", "Free Cash Flow", cashflow, ttm_cashflow),
    ]:
        latest = _statement_values(ttm, metric, 1)
        metrics.append({
            "label": label,
            "ttm": latest[0] if latest else None,
            "annual": _statement_values(annual, metric),
        })

    balance_metrics = []
    for label, metric in [
        ("Cash", "Cash And Cash Equivalents"),
        ("Total Debt", "Total Debt"),
    ]:
        latest = _statement_values(balance, metric, 1)
        balance_metrics.append({
            "label": label,
            "latest": latest[0] if latest else None,
        })

    if not any(
        entry["value"] is not None
        for metric in metrics
        for entry in ([metric["ttm"]] if metric["ttm"] else []) + metric["annual"]
    ) and not any(
        metric["latest"] and metric["latest"]["value"] is not None
        for metric in balance_metrics
    ):
        return {"error": f"No fundamental data found for {symbol}"}

    return {
        "symbol": symbol.upper(),
        "financials": metrics,
        "balance_sheet": balance_metrics,
    }


def format_fundamentals(data: Dict[str, Any], as_json: bool = False) -> str:
    """Display a compact snapshot, preserving each statement's period labels."""
    if as_json:
        import json
        return json.dumps(data, indent=2)
    if "error" in data:
        return f"Error: {data['error']}"

    def amount(entry):
        if entry is None or entry["value"] is None:
            return "N/A"
        return f'{entry["value"] / 1e9:,.2f}B'

    lines = [
        f"\n{data['symbol']}  Financial Snapshot",
        "=" * 60,
        "  Amounts in billions of reported currency; TTM = trailing twelve months.",
        "",
    ]
    # Statement dates can differ: group only metrics with identical dates.
    groups = {}
    for metric in data["financials"]:
        dates = tuple(entry["period"] for entry in metric["annual"])
        ttm_date = metric["ttm"]["period"] if metric["ttm"] else None
        groups.setdefault((ttm_date, dates), []).append(metric)
    for (ttm_date, dates), metrics in groups.items():
        headers = [f"TTM {ttm_date}" if ttm_date else "TTM (unavailable)", *dates]
        lines.append(f"  {'Metric':<20}" + "".join(f"{header:>20}" for header in headers))
        for metric in metrics:
            entries = [metric["ttm"], *metric["annual"]]
            lines.append(f"  {metric['label']:<20}" + "".join(f"{amount(entry):>20}" for entry in entries))
        lines.append("")

    for metric in data["balance_sheet"]:
        latest = metric["latest"]
        date = latest["period"] if latest else "date unavailable"
        lines.append(f"  {metric['label']:<20} {amount(latest):>12}  ({date})")
    return "\n".join(lines) + "\n"


# --- CLI Entry Point ---

def main():
    parser = argparse.ArgumentParser(
        description="yfinance CLI - Stock market data and charting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # quote command
    quote_parser = subparsers.add_parser("quote", help="Get stock quote with moving averages")
    quote_parser.add_argument("symbol", help="Stock ticker symbol (e.g., AAPL)")

    # search command
    search_parser = subparsers.add_parser("search", help="Search for ticker symbols")
    search_parser.add_argument("query", help="Company name to search")
    search_parser.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20)")

    # history command
    history_parser = subparsers.add_parser("history", help="Get historical OHLCV data")
    history_parser.add_argument("symbol", help="Stock ticker symbol")
    history_parser.add_argument("--period", "-p", default="1mo", help="Period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,max (default: 1mo)")
    history_parser.add_argument("--interval", "-i", default="1d", help="Interval: 1m,5m,15m,1h,1d,1wk,1mo (default: 1d)")

    # chart command
    chart_parser = subparsers.add_parser("chart", help="Generate PNG chart")
    chart_parser.add_argument("symbol", help="Stock ticker symbol")
    chart_parser.add_argument("--period", "-p", default="6mo", help="Period (default: 6mo)")
    chart_parser.add_argument("--interval", "-i", default="1d", help="Interval: 1m,5m,15m,1h,1d,1wk,1mo (default: 1d)")
    chart_parser.add_argument("--type", "-t", choices=["candlestick", "line"], default="candlestick", help="Chart type")
    chart_parser.add_argument("--output", "-o", help="Output file path")
    chart_parser.add_argument("--width", type=int, default=1200, help="Width in pixels (default: 1200)")
    chart_parser.add_argument("--height", type=int, default=800, help="Height in pixels (default: 800)")
    chart_parser.add_argument("--ma", nargs="+", type=int, default=[], help="Moving average periods to overlay (e.g. --ma 20 50 200)")
    chart_parser.add_argument("--background", "-b", choices=["transparent", "white", "black"], default="white", help="Background color (default: white)")

    # fundamentals command
    fund_parser = subparsers.add_parser("fundamentals", help="Compact financial snapshot (no scoring)")
    fund_parser.add_argument("symbol", help="Stock ticker symbol (e.g., AAPL)")
    fund_parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON for agent/LLM use")

    # recommendations command
    rec_parser = subparsers.add_parser("recommendations", help="Analyst consensus and recent rating changes")
    rec_parser.add_argument("symbol", help="Stock ticker symbol (e.g., AAPL)")
    rec_parser.add_argument("--history", "-H", type=int, default=3, help="Months of rating history to show (default: 3)")

    # news command
    news_parser = subparsers.add_parser("news", help="Get latest news for a ticker or search query")
    news_parser.add_argument("query", help="Ticker symbol or search query (e.g., AAPL or 'oil prices')")
    news_parser.add_argument("--count", "-n", type=int, default=5, help="Number of articles (default: 5)")
    news_parser.add_argument("--summary", "-s", action="store_true", help="Show full summary paragraph")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "quote":
        data = get_quote(args.symbol)
        print(format_quote(data))

    elif args.command == "search":
        data = search_ticker(args.query, limit=args.limit)
        print(format_search(data))

    elif args.command == "history":
        data = get_history(args.symbol, period=args.period, interval=args.interval)
        print(format_history(data))

    elif args.command == "fundamentals":
        data = get_fundamentals(args.symbol)
        print(format_fundamentals(data, as_json=args.as_json))
        if "error" in data:
            sys.exit(1)

    elif args.command == "recommendations":
        data = get_recommendations(args.symbol, history_months=args.history)
        print(format_recommendations(data))
        if data["errors"]:
            sys.exit(1)

    elif args.command == "news":
        data = get_news(args.query, count=args.count)
        print(format_news(data, full_summary=args.summary))

    elif args.command == "chart":
        result = generate_chart(
            args.symbol,
            period=args.period,
            interval=args.interval,
            chart_type=args.type,
            output=args.output,
            width=args.width,
            height=args.height,
            ma_periods=args.ma,
            background=args.background,
        )
        print(result)


if __name__ == "__main__":
    main()
