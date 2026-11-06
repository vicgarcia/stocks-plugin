#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yfinance>=0.2.54",
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""
yfinance CLI - Stock market data and charting tool

Commands:
    quote           - Get stock quote with moving averages
    search          - Search for ticker symbols by company name
    history         - Get historical OHLCV data
    chart           - Serve an interactive chart on localhost, or save a PNG of it
    news            - Get latest news for a ticker or any search query
    recommendations - Analyst consensus and recent rating changes
    fundamentals    - Compact financial snapshot (no scoring)
"""

import argparse
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from typing import Any

import yfinance as yf
import pandas as pd
import requests

RULE = "=" * 60


def plural(count: int, word: str) -> str:
    """'1 month', '3 months'."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def to_json(data: Any) -> str:
    """The --json output: a command's data dict, with NaN as null so it stays valid JSON."""
    def clean(value: Any) -> Any:
        if isinstance(value, float) and value != value:
            return None
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value
    return json.dumps(clean(data), indent=2, default=str)


# --- Quote Command ---

def quote_from_info(symbol: str, info: dict[str, Any]) -> dict[str, Any]:
    """Quote fields from ticker.info, shared by the quote command and the chart page."""
    market_time = info.get("regularMarketTime")
    return {
        "symbol": symbol.upper(),
        "company_name": info.get("longName") or info.get("shortName"),
        "quote_type": info.get("quoteType"),
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "currency": info.get("currency"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "net_assets": info.get("totalAssets"),  # funds report this instead of market cap
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        # yfinance reports both as percentages already (0.33 = 0.33%)
        "dividend_yield": info.get("dividendYield"),
        "expense_ratio": info.get("netExpenseRatio"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "beta": info.get("beta") or info.get("beta3Year"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_time": market_time,
        "quote_time": (datetime.fromtimestamp(market_time).strftime("%Y-%m-%d %H:%M:%S")
                       if market_time else None),
        "yahoo_url": f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol.upper())}/",
    }


def get_quote(symbol: str) -> dict[str, Any]:
    """Get stock quote with moving averages."""
    ticker = yf.Ticker(symbol)
    info = ticker.info

    if not info or info.get("regularMarketPrice") is None:
        return {"error": f"No data found for symbol: {symbol}"}

    quote = quote_from_info(symbol, info)
    current_price = quote["current_price"]

    def position(ma_value: float) -> dict[str, Any]:
        return {
            "value": round(ma_value, 2),
            "position": "above" if current_price > ma_value else "below",
            "distance_pct": round((current_price - ma_value) / ma_value * 100, 2),
        }

    # Yahoo publishes the 50 and 200-day averages; the rest come from history.
    # Six months covers SMA 20 and lets the EMAs settle. dropna: Yahoo can
    # include today's bar with volume but no prices yet.
    ma_data = {}
    prices = ticker.history(period="6mo")["Close"].dropna()
    if len(prices) >= 20:
        ma_data["SMA_20"] = position(prices.rolling(window=20).mean().iloc[-1])
    for key, name in [("fiftyDayAverage", "SMA_50"), ("twoHundredDayAverage", "SMA_200")]:
        if info.get(key):
            ma_data[name] = position(float(info[key]))
    for span, name in [(9, "EMA_9"), (21, "EMA_21")]:
        if len(prices) >= span:
            ma_data[name] = position(prices.ewm(span=span).mean().iloc[-1])
    if ma_data:
        quote["moving_averages"] = ma_data

    return quote


def format_quote(quote: dict[str, Any]) -> str:
    """Format quote data for display."""
    if "error" in quote:
        return f"Error: {quote['error']}"

    def field(label: str, key: str, fmt: str = "{}") -> str:
        value = quote.get(key)
        return f"{label + ':':<18}" + (fmt.format(value) if value else "N/A")

    # Funds report net assets and an expense ratio instead of a market cap
    size = (field("Net Assets", "net_assets", "${:,.0f}")
            if quote.get("net_assets") and not quote.get("market_cap")
            else field("Market Cap", "market_cap", "${:,.0f}"))
    expense = [field("Expense Ratio", "expense_ratio", "{:.2f}%")] if quote.get("expense_ratio") else []

    lines = [
        "", RULE, f"{quote['symbol']} - {quote.get('company_name') or 'N/A'}", RULE,
        "",
        "PRICE & VALUATION",
        field("Current Price", "current_price", "${:,.2f}"),
        size,
        field("P/E Ratio", "pe_ratio", "{:.2f}"),
        field("Forward P/E", "forward_pe", "{:.2f}"),
        field("Dividend Yield", "dividend_yield", "{:.2f}%"),
        *expense,
        "",
        "52-WEEK RANGE",
        field("High", "52_week_high", "${:,.2f}"),
        field("Low", "52_week_low", "${:,.2f}"),
        "",
        "VOLUME",
        field("Volume", "volume", "{:,.0f}"),
        field("Avg Volume", "avg_volume", "{:,.0f}"),
        "",
        "CLASSIFICATION",
        field("Sector", "sector"),
        field("Industry", "industry"),
        field("Beta", "beta", "{:.2f}"),
    ]
    if quote.get("moving_averages"):
        lines += ["", "MOVING AVERAGES"]
        for name, ma in quote["moving_averages"].items():
            lines.append(f"{name:12}  ${ma['value']:>10,.2f}  "
                         f"[{ma['position'].upper()}] ({ma['distance_pct']:+.2f}%)")
    lines.append("")
    if quote.get("quote_time"):
        lines.append(f"Quote: {quote['quote_time']}")
    if quote.get("yahoo_url"):
        lines.append(f"Yahoo: {quote['yahoo_url']}")
    lines += ["", RULE, ""]
    return "\n".join(lines)


# --- Search Command ---

def search_ticker(query: str, limit: int = 20) -> dict[str, Any]:
    """Search for ticker symbols by company name."""
    try:
        response = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotes_count": limit, "country": "United States"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=10,
        )
        response.raise_for_status()
        quotes = response.json().get("quotes", [])
    except Exception as e:
        return {"error": f"Search failed: {e}"}

    results = [{
        "symbol": quote.get("symbol", "N/A"),
        "name": quote.get("longname") or quote.get("shortname", "N/A"),
        "exchange": quote.get("exchange", "N/A"),
        "type": quote.get("quoteType", "N/A"),
    } for quote in quotes[:limit]]
    return {"query": query, "count": len(results), "results": results}


def format_search(data: dict[str, Any]) -> str:
    """Format search results for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [f"\nSearch results for '{data['query']}': {data['count']} found\n"]

    if not data["results"]:
        lines.append("No results found.")
    else:
        lines.append(f"{'SYMBOL':<10} {'EXCHANGE':<10} {'TYPE':<10} NAME")
        lines.append(f"{'-'*10} {'-'*10} {'-'*10} {'-'*30}")
        for r in data["results"]:
            lines.append(f"{r['symbol']:<10} {r['exchange']:<10} {r['type']:<10} {r['name']}")

    lines.append("")
    return "\n".join(lines)


# --- History Command ---

def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> dict[str, Any]:
    """Get historical OHLCV data."""
    hist = yf.Ticker(symbol).history(period=period, interval=interval)
    # Yahoo can include today's bar with volume but no prices yet
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    if hist.empty:
        return {"error": f"No historical data found for {symbol}"}

    records = [{
        "date": date.strftime("%Y-%m-%d"),
        "open": round(row["Open"], 2),
        "high": round(row["High"], 2),
        "low": round(row["Low"], 2),
        "close": round(row["Close"], 2),
        "volume": int(row["Volume"]),
    } for date, row in hist.iterrows()]
    return {
        "symbol": symbol.upper(),
        "period": period,
        "interval": interval,
        "count": len(records),
        "data": records,
    }


def format_history(data: dict[str, Any]) -> str:
    """Format history data for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [
        f"\n{data['symbol']} Historical Data ({data['period']}, {data['interval']})",
        f"Records: {data['count']}\n",
        f"{'DATE':<12} {'OPEN':>10} {'HIGH':>10} {'LOW':>10} {'CLOSE':>10} {'VOLUME':>14}",
        f"{'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*14}",
    ]

    for rec in data["data"]:
        lines.append(
            f"{rec['date']:<12} {rec['open']:>10.2f} {rec['high']:>10.2f} "
            f"{rec['low']:>10.2f} {rec['close']:>10.2f} {rec['volume']:>14,}"
        )

    lines.append("")
    return "\n".join(lines)


# --- Chart Command ---

# Range buttons on the chart page: (label, yfinance period, interval)
CHART_RANGES = [
    ("1D", "1d", "5m"),
    ("5D", "5d", "15m"),
    ("1M", "1mo", "1h"),
    ("3M", "3mo", "1d"),
    ("6M", "6mo", "1d"),
    ("YTD", "ytd", "1d"),
    ("1Y", "1y", "1d"),
    ("2Y", "2y", "1wk"),
    ("5Y", "5y", "1wk"),
    ("Max", "max", "1mo"),
]
CHART_PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max"]
CHART_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
DEFAULT_INTERVALS = {period: interval for _, period, interval in CHART_RANGES}
# Moving averages offered as toggles; --ma adds others and picks which start on
CHART_MAS = [20, 50, 200]
CHART_PORT = 8767
DEFAULT_PNG_SIZE = (1200, 800)
# Page time headless Chromium allows for the chart library to load and draw
SCREENSHOT_WAIT_MS = 5000

# Colors for both themes; the page turns these into CSS variables too
CHART_THEMES = {
    "light": {
        "bg": "#ffffff", "panel": "#f4f5f7", "text": "#1f2328", "muted": "#656d76",
        "grid": "#eef0f3", "border": "#d8dee4", "accent": "#2563eb",
        "up": "#1a7f37", "down": "#cf222e", "line": "#2563eb", "yahoo": "#6001d2",
        "ma": ["#d97706", "#7c3aed", "#0891b2", "#db2777", "#4d7c0f"],
    },
    "dark": {
        "bg": "#0d1117", "panel": "#161b22", "text": "#e6edf3", "muted": "#8d96a0",
        "grid": "#1b2129", "border": "#30363d", "accent": "#58a6ff",
        "up": "#3fb950", "down": "#f85149", "line": "#58a6ff", "yahoo": "#a77bff",
        "ma": ["#f2cc60", "#bc8cff", "#39c5cf", "#ff7b9c", "#a5d66b"],
    },
}

CHART_PAGE = textwrap.dedent("""\
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>__TITLE__</title>
        <script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
        <style>
          * { box-sizing: border-box; }
          html, body { height: 100%; margin: 0; }
          body {
            background: var(--bg); color: var(--text);
            font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
          }
          #app { display: flex; flex-direction: column; height: 100%; padding: 16px 20px 12px; gap: 12px; }
          header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; }
          .symbol { font-size: 22px; font-weight: 700; letter-spacing: .01em; }
          .name { color: var(--muted); }
          .quote { margin-left: auto; display: flex; align-items: baseline; gap: 10px; font-variant-numeric: tabular-nums; }
          .price { font-size: 22px; font-weight: 600; }
          .change.up { color: var(--up); }
          .change.down { color: var(--down); }
          .span { color: var(--muted); font-size: 12px; }
          .stats {
            display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 28px;
            padding: 10px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
          }
          .stats:empty { display: none; }
          .stat { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
          .stat .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
          .stat .value { font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
          .stat .value.wrap { white-space: normal; }
          .range .value { display: flex; align-items: center; gap: 8px; }
          .range .track { position: relative; width: 140px; height: 4px; border-radius: 2px; background: var(--border); }
          .range .dot {
            position: absolute; top: 50%; width: 10px; height: 10px; margin: -5px 0 0 -5px;
            border-radius: 50%; background: var(--accent); border: 2px solid var(--bg);
          }
          .asof { margin-left: auto; color: var(--muted); font-size: 12px; }
          .toolbar { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
          .group { display: flex; gap: 2px; background: var(--panel); border-radius: 8px; padding: 2px; }
          .toolbar button {
            font: inherit; font-size: 13px; color: var(--muted); background: none;
            border: 0; border-radius: 6px; padding: 4px 10px; cursor: pointer;
          }
          .toolbar button:hover { color: var(--text); }
          .toolbar button.on { background: var(--bg); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
          .toolbar .ma.on { color: var(--c); }
          .toolbar .theme { margin-left: auto; }
          #chart-wrap { position: relative; flex: 1; min-height: 240px; }
          #chart { position: absolute; inset: 0; }
          .legend {
            position: absolute; top: 4px; left: 4px; z-index: 3; pointer-events: none;
            font-size: 12px; font-variant-numeric: tabular-nums; color: var(--muted);
            display: flex; flex-wrap: wrap; gap: 2px 12px; max-width: calc(100% - 80px);
          }
          .legend b { color: var(--text); font-weight: 500; }
          .notice {
            position: absolute; inset: 0; z-index: 4; display: none;
            align-items: center; justify-content: center; color: var(--muted);
          }
          .notice.show { display: flex; }
          .notice.error { color: var(--down); }
          /* Data credit, beside the chart library's own logo in the bottom-left corner */
          .source {
            position: absolute; left: 58px; bottom: 37px; z-index: 3; display: flex;
            color: var(--yahoo); transition: transform .15s;
            /* A halo in the page colour keeps it readable over the volume bars */
            filter: drop-shadow(0 0 1px var(--bg)) drop-shadow(0 0 1px var(--bg)) drop-shadow(0 0 2px var(--bg));
          }
          .source:hover { transform: scale(1.15); }
          .static .toolbar { display: none; }
          __SCREENSHOT_CSS__
        </style>
      </head>
      <body>
        <div id="app">
          <header>
            <span class="symbol" id="symbol"></span>
            <span class="name" id="name"></span>
            <span class="quote">
              <span class="price" id="price"></span>
              <span class="change" id="change"></span>
              <span class="span" id="span"></span>
            </span>
          </header>
          <div class="stats" id="stats"></div>
          <div class="toolbar">
            <div class="group" id="ranges"></div>
            <div class="group" id="types">
              <button data-type="candlestick">Candles</button>
              <button data-type="line">Line</button>
            </div>
            <div class="group" id="mas"></div>
            <div class="group theme"><button id="theme" title="Toggle theme"></button></div>
          </div>
          <div id="chart-wrap">
            <div id="chart"></div>
            <div class="legend" id="legend"></div>
            <div class="notice" id="notice"></div>
            <a class="source" id="source" target="_blank" rel="noopener" aria-label="Yahoo Finance">
              <!-- Yahoo! mark from Simple Icons 9.0.0 (CC0); the trademark is Yahoo's -->
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M18.86 1.56L14.27 11.87H19.4L24 1.56H18.86M0 6.71L5.15 18.27L3.3 22.44H7.83L14.69 6.71H10.19L7.39 13.44L4.62 6.71H0M15.62 12.87C13.95 12.87 12.71 14.12 12.71 15.58C12.71 17 13.91 18.19 15.5 18.19C17.18 18.19 18.43 16.96 18.43 15.5C18.43 14.03 17.23 12.87 15.62 12.87Z"/></svg>
            </a>
          </div>
        </div>
        <script>
          const INFO = __INFO__;
          const RANGES = __RANGES__;
          const THEMES = __THEMES__;
          const MA_CHOICES = __MA_CHOICES__;
          const STATIC = __STATIC__;
          const state = __STATE__;
          let data = __DATA__;

          const $ = id => document.getElementById(id);
          const LWC = LightweightCharts;
          let chart, main, volume, maSeries = [];

          function esc(value) {
            return String(value).replace(/[&<>"']/g, c => ({
              '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[c]));
          }

          // Cents for most prices, more places for currencies and coins below $10
          function decimals(bars) {
            const last = bars.length ? Math.abs(bars[bars.length - 1].close) : 100;
            return last >= 10 ? 2 : last >= 1 ? 4 : 6;
          }

          function fmtPrice(value, digits) {
            return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
          }

          function fmtVolume(value) {
            if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
            if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
            if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K';
            return String(value);
          }

          // Intraday times arrive as exchange wall-clock seconds, so read them as UTC
          function fmtTime(time) {
            if (typeof time === 'string') return time;
            return new Date(time * 1000).toISOString().slice(0, 16).replace('T', ' ');
          }

          // Averages arrive from the server lined up with the bars, null before history begins
          function maPoints(n) {
            const values = data.ma[n] || [];
            return data.bars.map((b, i) => ({ time: b.time, value: values[i] })).filter(p => p.value != null);
          }

          function maColor(n) {
            const palette = THEMES[state.theme].ma;
            return palette[MA_CHOICES.indexOf(n) % palette.length];
          }

          function applyTheme() {
            const t = THEMES[state.theme];
            for (const [key, value] of Object.entries(t)) {
              if (typeof value === 'string') document.documentElement.style.setProperty('--' + key, value);
            }
            $('theme').textContent = state.theme === 'dark' ? 'Light' : 'Dark';
            chart.applyOptions({
              layout: { background: { type: 'solid', color: t.bg }, textColor: t.muted },
              grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
              rightPriceScale: { borderColor: t.border },
              timeScale: { borderColor: t.border },
            });
          }

          function draw() {
            for (const series of [main, volume, ...maSeries]) if (series) chart.removeSeries(series);
            main = volume = null;
            maSeries = [];
            const t = THEMES[state.theme];
            const bars = data.bars;
            const digits = decimals(bars);
            const priceFormat = { type: 'price', precision: digits, minMove: Math.pow(10, -digits) };
            chart.applyOptions({ localization: { priceFormatter: v => fmtPrice(v, digits) } });

            if (state.type === 'line') {
              main = chart.addAreaSeries({
                lineColor: t.line, lineWidth: 2, priceFormat,
                topColor: t.line + '33', bottomColor: t.line + '00',
              });
              main.setData(bars.map(b => ({ time: b.time, value: b.close })));
            } else {
              main = chart.addCandlestickSeries({
                upColor: t.up, downColor: t.down, wickUpColor: t.up, wickDownColor: t.down,
                borderVisible: false, priceFormat,
              });
              main.setData(bars.map(b => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })));
            }

            // Indexes and currencies report no volume, so the pane only shows when there is some
            const hasVolume = bars.some(b => b.volume > 0);
            main.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: hasVolume ? 0.24 : 0.04 } });
            if (hasVolume) {
              volume = chart.addHistogramSeries({
                priceFormat: { type: 'volume' }, priceScaleId: 'volume',
                lastValueVisible: false, priceLineVisible: false,
              });
              volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
              volume.setData(bars.map(b => ({
                time: b.time, value: b.volume, color: (b.close >= b.open ? t.up : t.down) + '55',
              })));
            }

            for (const n of state.ma) {
              const points = maPoints(n);
              if (!points.length) continue;
              const series = chart.addLineSeries({
                color: maColor(n), lineWidth: 1.5, priceFormat,
                priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
              });
              series.setData(points);
              series.maPeriod = n;
              maSeries.push(series);
            }

            chart.timeScale().applyOptions({ timeVisible: data.intraday, secondsVisible: false });
            chart.timeScale().fitContent();
            drawHeader(digits);
            drawLegend(bars.length - 1);
          }

          function drawHeader(digits) {
            const bars = data.bars;
            $('symbol').textContent = INFO.symbol;
            $('name').textContent = [INFO.name, INFO.exchange].filter(Boolean).join(' \\u00b7 ');
            const label = (RANGES.find(r => r[1] === data.period) || [data.period])[0];
            $('span').textContent = label + (INFO.currency ? ' \\u00b7 ' + INFO.currency : '');
            if (!bars.length) return;
            const first = bars[0].close, last = bars[bars.length - 1].close;
            const delta = last - first, pct = first ? delta / first * 100 : 0;
            $('price').textContent = fmtPrice(last, digits);
            $('change').textContent = (delta >= 0 ? '+' : '') + fmtPrice(delta, digits) +
              ' (' + (delta >= 0 ? '+' : '') + pct.toFixed(2) + '%)';
            $('change').className = 'change ' + (delta >= 0 ? 'up' : 'down');
          }

          function fmtMoney(value) {
            try {
              return new Intl.NumberFormat(undefined, {
                style: 'currency', currency: INFO.currency || 'USD', notation: 'compact', maximumFractionDigits: 2,
              }).format(value);
            } catch (err) {
              return fmtVolume(value) + (INFO.currency ? ' ' + INFO.currency : '');
            }
          }

          // Quote stats as of page load; anything Yahoo leaves blank for this asset type is skipped
          function drawStats() {
            const s = INFO.stats || {};
            const num = v => Number(v).toFixed(2);
            const items = [];
            const add = (label, value, cls) => items.push(
              '<div class="stat ' + (cls || '') + '"><span class="label">' + label + '</span>' +
              '<span class="value">' + value + '</span></div>');

            if (s.market_cap) add('Market cap', esc(fmtMoney(s.market_cap)));
            else if (s.net_assets) add('Net assets', esc(fmtMoney(s.net_assets)));
            if (s.pe_ratio) add('P/E', num(s.pe_ratio));
            if (s.forward_pe) add('Fwd P/E', num(s.forward_pe));
            if (s.dividend_yield) add('Div yield', num(s.dividend_yield) + '%');
            if (s.expense_ratio) add('Expense ratio', num(s.expense_ratio) + '%');
            if (s.beta) add('Beta', num(s.beta));
            if (s.volume) add('Volume', fmtVolume(s.volume));
            if (s.avg_volume) add('Avg volume', fmtVolume(s.avg_volume));

            const low = s['52_week_low'], high = s['52_week_high'], price = s.current_price;
            if (low != null && high != null && high > low) {
              const digits = decimals(data.bars);
              const pct = price != null ? Math.min(100, Math.max(0, (price - low) / (high - low) * 100)) : null;
              add('52-week range', fmtPrice(low, digits) +
                '<span class="track">' + (pct != null ? '<span class="dot" style="left:' + pct + '%"></span>' : '') +
                '</span>' + fmtPrice(high, digits), 'range');
            }
            if (s.sector || s.industry) {
              items.push('<div class="stat"><span class="label">Sector</span><span class="value wrap">' +
                esc([s.sector, s.industry].filter(Boolean).join(' \\u00b7 ')) + '</span></div>');
            }
            if (items.length && s.market_time) {
              items.push('<span class="asof">As of ' + esc(new Date(s.market_time * 1000).toLocaleString(undefined, {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
              })) + '</span>');
            }
            $('stats').innerHTML = items.join('');
          }

          function drawLegend(index) {
            const bars = data.bars;
            const bar = bars[index];
            if (!bar) { $('legend').innerHTML = ''; return; }
            const digits = decimals(bars);
            const p = v => fmtPrice(v, digits);
            const parts = ['<span>' + esc(fmtTime(bar.time)) + '</span>'];
            if (state.type === 'line') {
              parts.push('<span>C <b>' + p(bar.close) + '</b></span>');
            } else {
              for (const [k, v] of [['O', bar.open], ['H', bar.high], ['L', bar.low], ['C', bar.close]]) {
                parts.push('<span>' + k + ' <b>' + p(v) + '</b></span>');
              }
            }
            if (bar.volume > 0) parts.push('<span>Vol <b>' + fmtVolume(bar.volume) + '</b></span>');
            for (const series of maSeries) {
              const n = series.maPeriod;
              const value = (data.ma[n] || [])[index];
              if (value == null) continue;
              parts.push('<span style="color:' + maColor(n) + '">MA' + n + ' <b style="color:inherit">' +
                p(value) + '</b></span>');
            }
            $('legend').innerHTML = parts.join('');
          }

          function notice(text, isError) {
            $('notice').textContent = text || '';
            $('notice').className = 'notice' + (text ? ' show' : '') + (isError ? ' error' : '');
          }

          function buildToolbar() {
            $('ranges').innerHTML = RANGES.map(([label, period, interval]) =>
              '<button data-period="' + period + '" data-interval="' + interval + '">' + label + '</button>').join('');
            $('mas').innerHTML = MA_CHOICES.map(n =>
              '<button class="ma" data-ma="' + n + '">MA' + n + '</button>').join('');
            $('ranges').onclick = e => {
              const b = e.target.closest('button');
              if (b) load(b.dataset.period, b.dataset.interval);
            };
            $('types').onclick = e => {
              const b = e.target.closest('button');
              if (!b) return;
              state.type = b.dataset.type;
              draw(); syncToolbar();
            };
            $('mas').onclick = e => {
              const b = e.target.closest('button');
              if (!b) return;
              const n = Number(b.dataset.ma);
              state.ma = state.ma.includes(n) ? state.ma.filter(m => m !== n) : [...state.ma, n].sort((a, z) => a - z);
              draw(); syncToolbar();
            };
            $('theme').onclick = () => {
              state.theme = state.theme === 'dark' ? 'light' : 'dark';
              applyTheme(); draw(); syncToolbar();
            };
          }

          function syncToolbar() {
            for (const b of $('ranges').children) b.classList.toggle('on', b.dataset.period === data.period);
            for (const b of $('types').children) b.classList.toggle('on', b.dataset.type === state.type);
            for (const b of $('mas').children) {
              const n = Number(b.dataset.ma);
              b.classList.toggle('on', state.ma.includes(n));
              b.style.setProperty('--c', maColor(n));
            }
          }

          async function load(period, interval) {
            notice('Loading\\u2026');
            try {
              const r = await fetch('data.json?period=' + encodeURIComponent(period) +
                '&interval=' + encodeURIComponent(interval));
              const next = await r.json();
              if (next.error) throw new Error(next.error);
              data = next;
              notice('');
              draw(); syncToolbar();
            } catch (err) {
              notice(String(err.message || err), true);
            }
          }

          if (STATIC) document.body.classList.add('static');
          chart = LWC.createChart($('chart'), {
            autoSize: true,
            layout: { fontFamily: getComputedStyle(document.body).fontFamily, fontSize: 12 },
            crosshair: { mode: LWC.CrosshairMode.Normal },
            rightPriceScale: { borderVisible: true },
            timeScale: { borderVisible: true, rightOffset: 2 },
            handleScale: !STATIC, handleScroll: !STATIC,
          });
          chart.subscribeCrosshairMove(param => {
            const index = param.logical !== undefined ? Math.round(param.logical) : data.bars.length - 1;
            drawLegend(Math.min(Math.max(index, 0), data.bars.length - 1));
          });
          buildToolbar();
          applyTheme();
          drawStats();
          $('source').href = INFO.stats.yahoo_url;
          $('source').title = 'View ' + INFO.symbol + ' on Yahoo Finance';
          // The chart library draws its own TradingView logo link and rebuilds it when the
          // theme flips; point it at this symbol's page each time it appears
          const linkLogo = () => {
            const logo = document.getElementById('tv-attr-logo');
            if (logo && INFO.tradingview_url && logo.href !== INFO.tradingview_url) {
              logo.href = INFO.tradingview_url;
              logo.title = 'View ' + INFO.symbol + ' on TradingView';
            }
          };
          linkLogo();
          new MutationObserver(linkLogo).observe($('chart'), { childList: true, subtree: true });
          draw();
          syncToolbar();
        </script>
      </body>
    </html>
    """)


def _lookback_start(first: pd.Timestamp, interval: str, bars: int) -> pd.Timestamp:
    """
    A start date roughly `bars` bars of `interval` before `first`.

    Generous on purpose: weekends, holidays and closed hours eat calendar time,
    and surplus bars only cost a slightly bigger download.
    """
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
    if interval in minutes:
        sessions = -(-bars * minutes[interval] // 390)  # 6.5-hour trading days
        return first - pd.Timedelta(days=sessions * 1.6 + 4)
    days = {"1d": 1.6, "1wk": 7.5, "1mo": 31}[interval]
    return first - pd.Timedelta(days=bars * days + 10)


def get_chart_data(
        symbol: str,
        period: str = "6mo",
        interval: str | None = None,
        ma_periods: list[int] | None = None,
    ) -> dict[str, Any]:
    """
    Get OHLCV bars and moving averages shaped for the chart page.

    Moving averages are computed over extra history fetched from before the
    range, so a 200-bar average spans the whole chart rather than starting
    200 bars in. Each average lines up with the bars, null where history ran out.
    """
    interval = interval or DEFAULT_INTERVALS.get(period, "1d")
    ma_periods = sorted(set(ma_periods if ma_periods is not None else CHART_MAS))
    if period not in CHART_PERIODS:
        return {"error": f"Unsupported period: {period}"}
    if interval not in CHART_INTERVALS:
        return {"error": f"Unsupported interval: {interval}"}

    ticker = yf.Ticker(symbol)
    try:
        hist = ticker.history(period=period, interval=interval)
    except Exception as e:
        return {"error": f"Failed to fetch {symbol}: {e}"}
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    if hist.empty:
        return {"error": f"No data found for {symbol} ({period}, {interval})"}

    closes = hist["Close"]
    if ma_periods and period != "max":
        # Intraday history only reaches back so far; averages then start late
        try:
            earlier = ticker.history(start=_lookback_start(hist.index[0], interval, max(ma_periods)),
                                     end=hist.index[0], interval=interval)["Close"].dropna()
            closes = pd.concat([earlier[earlier.index < hist.index[0]], closes])
        except Exception:
            pass
    averages = {
        str(n): [None if pd.isna(v) else round(float(v), 6)
                 for v in closes.rolling(window=n).mean().iloc[-len(hist):]]
        for n in ma_periods
    }

    # 1m ... 1h are intraday; 1mo ends in "o". The chart library labels times
    # in UTC, so intraday bars carry exchange wall-clock time as if it were UTC.
    intraday = interval[-1] in "mh"
    bars = [{
        "time": int(ts.tz_localize(None).timestamp()) if intraday else ts.strftime("%Y-%m-%d"),
        "open": round(float(row["Open"]), 6),
        "high": round(float(row["High"]), 6),
        "low": round(float(row["Low"]), 6),
        "close": round(float(row["Close"]), 6),
        "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
    } for ts, row in hist.iterrows()]

    return {
        "symbol": symbol.upper(),
        "period": period,
        "interval": interval,
        "intraday": intraday,
        "bars": bars,
        "ma": averages,
    }


# Yahoo exchange codes -> TradingView exchange prefixes. TradingView lists
# NYSE Arca funds under AMEX.
TRADINGVIEW_EXCHANGES = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
    "NYQ": "NYSE", "NYS": "NYSE",
    "PCX": "AMEX", "ASE": "AMEX",
}
# Yahoo index symbols -> TradingView's names, which redirect to the right page
TRADINGVIEW_INDEXES = {"^GSPC": "SPX", "^DJI": "DJI", "^IXIC": "IXIC", "^VIX": "VIX", "^RUT": "RUT"}


def tradingview_url(symbol: str, info: dict[str, Any]) -> str:
    """The symbol's page on TradingView, translated from Yahoo's naming."""
    symbol = symbol.upper()
    kind = info.get("quoteType")
    if kind == "INDEX":
        name = TRADINGVIEW_INDEXES.get(symbol, symbol.lstrip("^"))
    elif kind == "CRYPTOCURRENCY":
        name = symbol.replace("-", "")            # BTC-USD -> BTCUSD
    elif kind == "CURRENCY":
        name = symbol.removesuffix("=X")          # EURUSD=X -> EURUSD
    elif kind == "FUTURE":
        name = symbol.removesuffix("=F") + "1!"   # CL=F -> CL1!, the front month
    else:
        name = symbol.replace("-", ".")           # BRK-B -> BRK.B
        prefix = TRADINGVIEW_EXCHANGES.get(info.get("exchange"))
        if prefix:
            name = f"{prefix}-{name}"
    return f"https://www.tradingview.com/symbols/{urllib.parse.quote(name, safe='!.')}/"


def get_chart_info(symbol: str) -> dict[str, Any]:
    """Header and stats strip for the chart page; blanks if Yahoo has none."""
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    stats = quote_from_info(symbol, info)
    return {
        "symbol": symbol.upper(),
        "name": stats["company_name"] or "",
        "exchange": stats["exchange"] or "",
        "currency": stats["currency"] or "",
        "tradingview_url": tradingview_url(symbol, info),
        "stats": stats,
    }


def chart_ma_choices(ma_periods: list[int] | None = None) -> list[int]:
    """The moving averages the page offers: the standard ones plus any from --ma."""
    return sorted(set(CHART_MAS) | set(ma_periods or []))


def _script_json(value: Any) -> str:
    """JSON safe to inline in a <script> block."""
    return json.dumps(value).replace("<", "\\u003c")


def chart_page(
        info: dict[str, Any],
        data: dict[str, Any],
        chart_type: str = "candlestick",
        ma_periods: list[int] | None = None,
        theme: str = "light",
        size: tuple[int, int] | None = None,
    ) -> str:
    """
    Fill the chart page template.

    The first range is inlined so the page draws without a round trip. With
    a size, the page is pinned to that many pixels and the controls hidden,
    for a screenshot.
    """
    ma_periods = ma_periods or []
    screenshot_css = ""
    if size:
        width, height = size
        screenshot_css = (f"#app {{ width: {width}px; height: {height}px; }}\n"
                          "html, body { overflow: hidden; }")
    title = f"{info['symbol']} - stocks.py".replace("&", "&amp;").replace("<", "&lt;")
    return (CHART_PAGE
            .replace("__SCREENSHOT_CSS__", screenshot_css)
            .replace("__TITLE__", title)
            .replace("__INFO__", _script_json(info))
            .replace("__RANGES__", _script_json(CHART_RANGES))
            .replace("__THEMES__", _script_json(CHART_THEMES))
            .replace("__MA_CHOICES__", _script_json(chart_ma_choices(ma_periods)))
            .replace("__STATIC__", _script_json(bool(size)))
            .replace("__STATE__", _script_json({"type": chart_type, "ma": sorted(set(ma_periods)),
                                                "theme": theme}))
            .replace("__DATA__", _script_json(data)))


class _ChartServer(http.server.ThreadingHTTPServer):
    """
    Refuse ports that are already taken, so the free-port fallback runs.

    HTTPServer turns on SO_REUSEADDR, which on Windows lets a second server bind a
    port another process is serving - both listen and the older one keeps the
    traffic. Windows gets an exclusive bind instead.
    """

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _chart_server(
        page: str,
        symbol: str,
        ma_periods: list[int],
        port: int,
    ) -> http.server.ThreadingHTTPServer:
    """Bind a localhost server for the chart page; data.json fetches other ranges live."""
    body_page = page.encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path == "/":
                content_type, body = "text/html; charset=utf-8", body_page
            elif url.path == "/data.json":
                query = urllib.parse.parse_qs(url.query)
                data = get_chart_data(symbol,
                                      period=query.get("period", ["6mo"])[0],
                                      interval=query.get("interval", [None])[0],
                                      ma_periods=ma_periods)
                content_type, body = "application/json", json.dumps(data).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # keep the terminal readable

    try:
        return _ChartServer(("127.0.0.1", port), Handler)
    except OSError as e:
        if port == 0:
            raise RuntimeError(f"Could not start server: {e}")
        print(f"Port {port} unavailable ({e.strerror}), using a free port instead")
        return _ChartServer(("127.0.0.1", 0), Handler)


def serve_chart(
        page: str,
        symbol: str,
        ma_periods: list[int],
        port: int,
        open_browser: bool,
    ) -> None:
    """Serve the chart page on localhost until interrupted."""
    server = _chart_server(page, symbol, ma_periods, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"\nServing {symbol.upper()} chart at {url}")
    print("Press Ctrl+C to stop\n", flush=True)

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        server.server_close()


# Chromium-family browsers that can screenshot headless, checked in order
BROWSER_COMMANDS = [
    "chrome", "google-chrome", "google-chrome-stable",
    "chromium", "chromium-browser", "msedge", "microsoft-edge",
]


def _browser_paths() -> list[str]:
    """Usual install locations on Windows and macOS, which are rarely on PATH."""
    paths = []
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if root:
            paths += [
                os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(root, "Chromium", "Application", "chrome.exe"),
            ]
    paths += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return paths


def find_browser() -> str | None:
    """Locate Chrome, Edge or Chromium. STOCKS_BROWSER overrides the search."""
    override = os.environ.get("STOCKS_BROWSER")
    if override:
        return override
    for command in BROWSER_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return next((path for path in _browser_paths() if os.path.isfile(path)), None)


def screenshot_chart(
        page: str,
        symbol: str,
        ma_periods: list[int],
        path: str,
        size: tuple[int, int],
        wait_ms: int = SCREENSHOT_WAIT_MS,
    ) -> str:
    """
    Render the chart page to a PNG with a headless Chromium browser.

    The page is served on a free localhost port for the duration. Headless
    screenshots fire on a virtual clock, so wait_ms is the page time allowed
    for the chart library to load and draw before the capture.
    """
    browser = find_browser()
    if not browser:
        raise RuntimeError("No Chrome, Edge or Chromium found for --png; "
                           "install one or set STOCKS_BROWSER to its path")

    output = os.path.abspath(path)
    if os.path.exists(output):
        os.remove(output)  # so a stale file can't pass for a fresh capture

    server = _chart_server(page, symbol, ma_periods, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    width, height = size
    # A throwaway profile keeps headless runs clear of an open browser session
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        command = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}",
            f"--screenshot={output}",
            url,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=wait_ms / 1000 + 90)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Browser screenshot failed: {e}") from e
        finally:
            server.shutdown()
            server.server_close()

    if not os.path.isfile(output):
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError("Browser did not write a screenshot"
                           + (": " + " | ".join(detail) if detail else ""))
    return output


def parse_port(value: str) -> int:
    """argparse type for a TCP port, so a bad value is a usage error, not a traceback."""
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port must be 0-65535, got {port}")
    return port


def parse_size(value: str) -> tuple[int, int]:
    """argparse type for WIDTHxHEIGHT image sizes."""
    match = re.match(r"^(\d{2,5})x(\d{2,5})$", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"size must look like 1200x800, got {value!r}")
    return int(match.group(1)), int(match.group(2))


def run_chart(args: argparse.Namespace) -> int:
    """Serve the chart, save a screenshot of it, or print its data."""
    choices = chart_ma_choices(args.ma)
    data = get_chart_data(args.symbol, period=args.period, interval=args.interval,
                          ma_periods=choices)
    if "error" in data:
        print(f"Error: {data['error']}")
        return 1
    info = get_chart_info(args.symbol)
    if args.json:
        print(to_json({**info, **data}))
        return 0
    try:
        if args.png:
            page = chart_page(info, data, args.type, args.ma, args.theme, size=args.size)
            print(f"Chart saved: {screenshot_chart(page, args.symbol, choices, args.png, args.size)}")
        else:
            page = chart_page(info, data, args.type, args.ma, args.theme)
            serve_chart(page, args.symbol, choices, args.port, not args.no_open)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    return 0


# --- News Command ---

def news_time(timestamp: Any) -> str:
    """'Nov 04 2026, 8:34 PM'. Windows strftime has no %-I, so the hour is built by hand."""
    if not isinstance(timestamp, (int, float)):
        return str(timestamp or "")
    published = datetime.fromtimestamp(timestamp)
    return f"{published:%b %d %Y}, {published.hour % 12 or 12}:{published:%M %p}"


def get_news(query: str, count: int = 5) -> dict[str, Any]:
    """Get news articles for a ticker symbol or general search query."""
    try:
        results = yf.Search(query, news_count=count).news or []
    except Exception as e:
        return {"error": f"News fetch failed: {e}"}

    articles = [{
        "title": item.get("title", "No title"),
        "source": item.get("publisher", "Unknown"),
        "pub_date": news_time(item.get("providerPublishTime")),
        "url": item.get("link", ""),
    } for item in results[:count]]
    return {"query": query, "count": len(articles), "articles": articles}


def format_news(data: dict[str, Any]) -> str:
    """Format news articles for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    lines = ["", f"{data['query'].upper()}  Latest News  ({plural(data['count'], 'article')})", RULE]
    if not data["articles"]:
        lines += ["", "No news articles found."]
    for i, article in enumerate(data["articles"], 1):
        lines += ["", f"[{i}] {article['title']}", f"    {article['source']} · {article['pub_date']}"]
        if article["url"]:
            lines.append(f"    {article['url']}")
    lines += ["", RULE, ""]
    return "\n".join(lines)


# --- Recommendations Command ---

# Our consensus keys -> Yahoo's recommendations_summary columns
CONSENSUS_COLUMNS = {
    "strong_buy": "strongBuy", "buy": "buy", "hold": "hold", "sell": "sell", "strong_sell": "strongSell",
}

# Yahoo's upgrades_downgrades Action codes
ACTION_LABELS = {
    "up": "upgraded", "down": "downgraded", "init": "initiated",
    "main": "(maintains)", "reit": "(reiterates)",
}


def target_note(current: Any, prior: Any) -> str:
    """'$355  down from $360', '$250', or '' when there is no price target."""
    if pd.isna(current) or not current:
        return ""
    note = f"${current:.0f}"
    if pd.notna(prior) and prior and prior != current:
        note += f"  {'up' if current > prior else 'down'} from ${prior:.0f}"
    return note


def get_recommendations(symbol: str, history_months: int = 3) -> dict[str, Any]:
    """
    Get analyst consensus and recent rating changes.

    Each source can fail on its own; the other's data is kept and the failure
    is recorded in errors and its *_failed flag.
    """
    ticker = yf.Ticker(symbol)
    data = {
        "symbol": symbol.upper(),
        "errors": [],
        "consensus_failed": False,
        "rating_changes_failed": False,
        "consensus": [],
        "rating_changes": [],
        "history_months": history_months,
    }

    try:
        summary = ticker.recommendations_summary
        for _, row in (summary if summary is not None else pd.DataFrame()).iterrows():
            counts = {key: int(row.get(column, 0)) for key, column in CONSENSUS_COLUMNS.items()}
            data["consensus"].append({"period": row.get("period", ""), **counts,
                                      "total": sum(counts.values())})
    except Exception as e:
        data["consensus_failed"] = True
        data["errors"].append(f"Failed to fetch analyst consensus: {e}")

    try:
        changes = ticker.upgrades_downgrades
        if changes is not None and not changes.empty:
            cutoff = pd.Timestamp.now(tz=changes.index.tz) - pd.DateOffset(months=history_months)
            for date, row in changes[changes.index >= cutoff].sort_index(ascending=False).iterrows():
                action = row.get("Action", "")
                data["rating_changes"].append({
                    "date": date.strftime("%Y-%m-%d"),
                    "firm": row.get("Firm", ""),
                    "from_grade": row.get("FromGrade", ""),
                    "to_grade": row.get("ToGrade", ""),
                    "action_label": ACTION_LABELS.get(action, action),
                    "pt_note": target_note(row.get("currentPriceTarget"), row.get("priorPriceTarget")),
                })
    except Exception as e:
        data["rating_changes_failed"] = True
        data["errors"].append(f"Failed to fetch rating changes: {e}")

    return data


def period_label(period: str) -> str:
    """'0m' -> 'Now', '-1m' -> '-1 Month', '-3m' -> '-3 Months'."""
    if period == "0m":
        return "Now"
    match = re.fullmatch(r"-(\d+)m", period)
    return f"-{plural(int(match.group(1)), 'Month')}" if match else period


def format_recommendations(data: dict[str, Any]) -> str:
    """Format analyst consensus and rating changes for display."""
    lines = ["", f"{data['symbol']}  Analyst Consensus", RULE]
    for error in data.get("errors", []):
        lines += ["", f"Error: {error}"]

    if data["consensus"]:
        lines += [
            "", "CONSENSUS BREAKDOWN", "",
            f"{'Period':<10} {'Strong Buy':>10} {'Buy':>5} {'Hold':>6} {'Sell':>6} {'Strong Sell':>12} {'Total':>7}",
            f"{'-'*10} {'-'*10} {'-'*5} {'-'*6} {'-'*6} {'-'*12} {'-'*7}",
        ]
        for row in data["consensus"]:
            lines.append(f"{period_label(row['period']):<10} {row['strong_buy']:>10} {row['buy']:>5}"
                         f" {row['hold']:>6} {row['sell']:>6} {row['strong_sell']:>12} {row['total']:>7}")
    elif not data.get("consensus_failed"):
        lines += ["", "No consensus data available."]

    lines += ["", f"RECENT RATING CHANGES  (last {plural(data['history_months'], 'month')})", ""]
    for change in data["rating_changes"]:
        grades = f"{change['from_grade'] or '-':<18} -> {change['to_grade'] or '-':<18}"
        target = f"  {change['pt_note']}" if change["pt_note"] else ""
        lines.append(f"{change['date']:<10} {change['firm']:<22} {grades}{target}  {change['action_label']}")
    if not data["rating_changes"] and not data.get("rating_changes_failed"):
        lines.append("No rating changes found in this period.")

    lines += ["", RULE, ""]
    return "\n".join(lines)


# --- Fundamentals Command ---

def _statement_values(statement, metric: str, limit: int = 3) -> list[dict[str, Any]]:
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


def get_fundamentals(symbol: str) -> dict[str, Any]:
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

    entries = [entry for metric in metrics for entry in [metric["ttm"], *metric["annual"]]]
    entries += [metric["latest"] for metric in balance_metrics]
    if not any(entry and entry["value"] is not None for entry in entries):
        return {"error": f"No fundamental data found for {symbol}"}

    return {
        "symbol": symbol.upper(),
        "financials": metrics,
        "balance_sheet": balance_metrics,
    }


def format_fundamentals(data: dict[str, Any]) -> str:
    """Display a compact snapshot, preserving each statement's period labels."""
    if "error" in data:
        return f"Error: {data['error']}"

    def amount(entry):
        if entry is None or entry["value"] is None:
            return "N/A"
        return f'{entry["value"] / 1e9:,.2f}B'

    lines = [
        f"\n{data['symbol']}  Financial Snapshot",
        RULE,
        "Amounts in billions of reported currency; TTM = trailing twelve months.",
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
        lines.append(f"{'Metric':<20}" + "".join(f"{header:>20}" for header in headers))
        for metric in metrics:
            entries = [metric["ttm"], *metric["annual"]]
            lines.append(f"{metric['label']:<20}" + "".join(f"{amount(entry):>20}" for entry in entries))
        lines.append("")

    for metric in data["balance_sheet"]:
        latest = metric["latest"]
        date = latest["period"] if latest else "date unavailable"
        lines.append(f"{metric['label']:<20} {amount(latest):>12}  ({date})")
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
    history_parser.add_argument("--period", "-p", choices=CHART_PERIODS, default="1mo", help="Period (default: 1mo)")
    history_parser.add_argument("--interval", "-i", choices=CHART_INTERVALS, default="1d", help="Interval (default: 1d)")

    # chart command
    chart_parser = subparsers.add_parser("chart", help="Serve an interactive chart on localhost, or save a PNG of it")
    chart_parser.add_argument("symbol", help="Stock ticker symbol")
    chart_parser.add_argument("--period", "-p", choices=CHART_PERIODS, default="6mo", help="Starting period (default: 6mo)")
    chart_parser.add_argument("--interval", "-i", choices=CHART_INTERVALS, help="Bar interval (default: picked for the period)")
    chart_parser.add_argument("--type", "-t", choices=["candlestick", "line"], default="candlestick", help="Chart type (default: candlestick)")
    chart_parser.add_argument("--ma", nargs="+", type=int, default=[], help="Moving averages to start with (e.g. --ma 20 50 200)")
    chart_parser.add_argument("--theme", choices=["light", "dark"], default="light", help="Color theme (default: light)")
    chart_parser.add_argument("--port", type=parse_port, default=CHART_PORT, help=f"Port to serve on (default: {CHART_PORT})")
    chart_parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    chart_parser.add_argument("--png", metavar="FILE", help="Save a screenshot of the chart instead of serving it (needs Chrome, Edge or Chromium)")
    chart_parser.add_argument("--size", type=parse_size, default=DEFAULT_PNG_SIZE, metavar="WxH",
                              help="Screenshot size for --png (default: {}x{})".format(*DEFAULT_PNG_SIZE))
    chart_parser.add_argument("--json", action="store_true", help="Print the chart data as JSON instead of serving it")

    # fundamentals command
    fund_parser = subparsers.add_parser("fundamentals", help="Compact financial snapshot (no scoring)")
    fund_parser.add_argument("symbol", help="Stock ticker symbol (e.g., AAPL)")

    # recommendations command
    rec_parser = subparsers.add_parser("recommendations", help="Analyst consensus and recent rating changes")
    rec_parser.add_argument("symbol", help="Stock ticker symbol (e.g., AAPL)")
    rec_parser.add_argument("--history", "-H", type=int, default=3, help="Months of rating history to show (default: 3)")

    # news command
    news_parser = subparsers.add_parser("news", help="Get latest news for a ticker or search query")
    news_parser.add_argument("query", help="Ticker symbol or search query (e.g., AAPL or 'oil prices')")
    news_parser.add_argument("--count", "-n", type=int, default=5, help="Number of articles (default: 5)")

    # chart has its own --json; for the rest it swaps the formatted text for the data dict
    for command_parser in (quote_parser, search_parser, history_parser, fund_parser, rec_parser, news_parser):
        command_parser.add_argument("--json", action="store_true",
                                    help="Print the data as JSON for agents instead of formatted text")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)
    if args.command == "chart":
        sys.exit(run_chart(args))

    if args.command == "quote":
        data, formatter = get_quote(args.symbol), format_quote
    elif args.command == "search":
        data, formatter = search_ticker(args.query, limit=args.limit), format_search
    elif args.command == "history":
        data, formatter = get_history(args.symbol, period=args.period, interval=args.interval), format_history
    elif args.command == "fundamentals":
        data, formatter = get_fundamentals(args.symbol), format_fundamentals
    elif args.command == "recommendations":
        data, formatter = get_recommendations(args.symbol, history_months=args.history), format_recommendations
    elif args.command == "news":
        data, formatter = get_news(args.query, count=args.count), format_news

    print(to_json(data) if args.json else formatter(data))
    # Any retrieval failure, including a partial one, exits non-zero
    sys.exit(1 if "error" in data or data.get("errors") else 0)


if __name__ == "__main__":
    main()
