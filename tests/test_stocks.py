"""Offline regression tests for factual financial reports."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch, PropertyMock, Mock

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "stocks", Path(__file__).resolve().parents[1] / "skills" / "stocks" / "scripts" / "stocks.py"
)
stocks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stocks)


class FundamentalsTests(unittest.TestCase):
    def ticker(self):
        annual_dates = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
        return Mock(
            income_stmt=pd.DataFrame(
                [[9e9, None, 7e9], [1e9, 2e9, 3e9], [4e9, 3e9, 2e9]],
                index=["Total Revenue", "Net Income Common Stockholders", "Net Income"],
                columns=annual_dates,
            ),
            cashflow=pd.DataFrame(
                [[2e9]], index=["Free Cash Flow"], columns=pd.to_datetime(["2025-09-30"])
            ),
            balance_sheet=pd.DataFrame(
                [[1e9], [3e9]], index=["Cash And Cash Equivalents", "Total Debt"],
                columns=pd.to_datetime(["2025-09-30"]),
            ),
            ttm_income_stmt=pd.DataFrame(
                [[10e9]], index=["Total Revenue"], columns=pd.to_datetime(["2026-03-31"])
            ),
            ttm_cashflow=pd.DataFrame(),
        )

    def test_snapshot_preserves_dates_missing_values_and_exact_metrics(self):
        with patch.object(stocks.yf, "Ticker", return_value=self.ticker()):
            data = stocks.get_fundamentals("test")
        revenue = data["financials"][0]
        self.assertEqual(revenue["annual"][1], {"period": "2024-12-31", "value": None})
        self.assertEqual(data["financials"][3]["annual"][0]["value"], 4e9)
        output = stocks.format_fundamentals(data)
        self.assertIn("2026-03-31", output)
        self.assertIn("2025-09-30", output)
        self.assertIn("N/A", output)
        self.assertNotIn("Score", output)
        self.assertEqual(json.loads(stocks.to_json(data)), data)
        self.assertNotIn("total_score", data)
        self.assertFalse(hasattr(stocks, "score_fundamentals"))

    def test_fetch_failure_is_explicit_and_json_stays_json(self):
        ticker = self.ticker()
        type(ticker).income_stmt = PropertyMock(side_effect=RuntimeError("offline"))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_fundamentals("test")
        self.assertIn("offline", data["error"])
        self.assertEqual(json.loads(stocks.to_json(data)), data)

    def test_cli_fundamentals_failure_exits_nonzero_with_json_error(self):
        with patch.object(stocks, "get_fundamentals", return_value={"error": "offline"}), \
             patch("sys.argv", ["stocks.py", "fundamentals", "TEST", "--json"]), \
             patch("builtins.print") as output:
            with self.assertRaises(SystemExit) as exc:
                stocks.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(json.loads(output.call_args.args[0]), {"error": "offline"})

    def test_empty_statements_are_an_error(self):
        ticker = Mock(**{name: pd.DataFrame() for name in [
            "income_stmt", "cashflow", "balance_sheet", "ttm_income_stmt", "ttm_cashflow"
        ]})
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            self.assertIn("error", stocks.get_fundamentals("test"))


class RecommendationsTests(unittest.TestCase):
    def ticker(self):
        return Mock(
            recommendations_summary=pd.DataFrame([{
                "period": "0m", "strongBuy": 7, "buy": 3, "hold": 0, "sell": 0, "strongSell": 0
            }]),
            upgrades_downgrades=pd.DataFrame(
                [{"Firm": "Example", "FromGrade": "Hold", "ToGrade": "Buy", "Action": "up"}],
                index=pd.DatetimeIndex([pd.Timestamp.now(tz="America/New_York")]),
            ),
        )

    def test_counts_without_generated_verdict_and_timezone_aware_changes(self):
        with patch.object(stocks.yf, "Ticker", return_value=self.ticker()):
            data = stocks.get_recommendations("test")
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["consensus"][0]["total"], 10)
        self.assertNotIn("label", data["consensus"][0])
        self.assertEqual(len(data["rating_changes"]), 1)
        self.assertEqual(len(data["rating_changes"][0]["date"]), 10)
        output = stocks.format_recommendations(data)
        self.assertNotIn("Verdict", output)
        output.encode("cp1252")  # Works on default Windows console encoding.

    def test_partial_failure_keeps_consensus_and_does_not_claim_no_changes(self):
        ticker = self.ticker()
        type(ticker).upgrades_downgrades = PropertyMock(side_effect=RuntimeError("offline"))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_recommendations("test")
        output = stocks.format_recommendations(data)
        self.assertIn("CONSENSUS BREAKDOWN", output)
        self.assertIn("Failed to fetch rating changes: offline", output)
        self.assertNotIn("No rating changes found", output)

    def test_consensus_failure_keeps_rating_changes(self):
        ticker = self.ticker()
        type(ticker).recommendations_summary = PropertyMock(side_effect=RuntimeError("offline"))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_recommendations("test")
        self.assertTrue(data["consensus_failed"])
        self.assertEqual(len(data["rating_changes"]), 1)
        self.assertNotIn("No consensus data available", stocks.format_recommendations(data))

    def test_cli_reports_failure_exit_status(self):
        with patch.object(stocks, "get_recommendations", return_value={
            "symbol": "TEST", "consensus": [], "rating_changes": [], "history_months": 3,
            "errors": ["offline"], "consensus_failed": True, "rating_changes_failed": True,
        }), patch("sys.argv", ["stocks.py", "recommendations", "TEST"]), patch("builtins.print"):
            with self.assertRaises(SystemExit) as exc:
                stocks.main()
        self.assertEqual(exc.exception.code, 1)


class QuoteTests(unittest.TestCase):
    def test_50_and_200_day_averages_come_from_yahoo(self):
        closes = pd.DataFrame({"Close": [100.0] * 30})
        ticker = Mock(info={"regularMarketPrice": 110.0, "fiftyDayAverage": 105.0,
                            "twoHundredDayAverage": 120.0},
                      history=Mock(return_value=closes))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            quote = stocks.get_quote("test")
        ma = quote["moving_averages"]
        self.assertEqual(ma["SMA_50"]["value"], 105.0)
        self.assertEqual(ma["SMA_200"], {"value": 120.0, "position": "below", "distance_pct": -8.33})
        self.assertEqual(ma["SMA_20"]["value"], 100.0)
        self.assertIn("EMA_21", ma)

    def test_dividend_yield_is_already_a_percentage(self):
        ticker = Mock(info={"regularMarketPrice": 110.0, "dividendYield": 0.33},
                      history=Mock(return_value=pd.DataFrame({"Close": []})))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            output = stocks.format_quote(stocks.get_quote("test"))
        self.assertIn("Dividend Yield:   0.33%", output)


class PartialBarTests(unittest.TestCase):
    """Yahoo can return today's bar with volume but no prices yet."""

    def bars(self):
        index = pd.date_range("2026-10-01", periods=25, freq="D")
        frame = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                              "Volume": 1000}, index=index)
        frame.iloc[-1, :4] = None
        return frame

    def test_quote_sma_20_ignores_the_partial_bar(self):
        ticker = Mock(info={"regularMarketPrice": 110.0}, history=Mock(return_value=self.bars()))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            quote = stocks.get_quote("test")
        self.assertEqual(quote["moving_averages"]["SMA_20"]["value"], 100.0)
        self.assertNotRegex(stocks.format_quote(quote), r"\bnan\b")
        self.assertEqual(quote["yahoo_url"], "https://finance.yahoo.com/quote/TEST/")

    def test_history_drops_the_partial_bar(self):
        with patch.object(stocks.yf, "Ticker", return_value=Mock(history=Mock(return_value=self.bars()))):
            data = stocks.get_history("test")
        self.assertEqual(data["count"], 24)
        self.assertNotIn("nan", stocks.format_history(data))


class FormattingTests(unittest.TestCase):
    def test_every_consensus_month_gets_a_label(self):
        rows = [{"period": p, "strong_buy": 1, "buy": 1, "hold": 1, "sell": 0, "strong_sell": 0, "total": 3}
                for p in ["0m", "-1m", "-2m", "-3m"]]
        output = stocks.format_recommendations({
            "symbol": "TEST", "errors": [], "consensus": rows, "rating_changes": [], "history_months": 3,
        })
        for label in ["Now", "-1 Month ", "-2 Months", "-3 Months"]:
            self.assertIn(label, output)
        self.assertNotIn("-3m", output)

    def test_rating_actions_and_price_targets(self):
        self.assertEqual(stocks.ACTION_LABELS["reit"], "(reiterates)")
        self.assertEqual(stocks.ACTION_LABELS["init"], "initiated")
        self.assertEqual(stocks.target_note(355.0, 360.0), "$355  down from $360")
        self.assertEqual(stocks.target_note(250.0, float("nan")), "$250")
        self.assertEqual(stocks.target_note(float("nan"), 300.0), "")

    def test_quote_shows_fund_size_and_costs(self):
        output = stocks.format_quote({"symbol": "SPY", "sector": None, "industry": None,
                                      "net_assets": 809216114688, "expense_ratio": 0.0945})
        self.assertIn("Net Assets:       $809,216,114,688", output)
        self.assertIn("Expense Ratio:    0.09%", output)
        self.assertNotIn("Market Cap", output)
        self.assertIn("Sector:           N/A", output)
        self.assertNotIn("None", output)

    def test_stocks_keep_market_cap(self):
        output = stocks.format_quote({"symbol": "AAPL", "market_cap": 5e12, "net_assets": None})
        self.assertIn("Market Cap:       $5,000,000,000,000", output)
        self.assertNotIn("Net Assets", output)
        self.assertNotIn("Expense Ratio", output)

    def test_json_flag_prints_the_data_with_nan_as_null(self):
        data = {"symbol": "TEST", "count": 1, "results": [{"symbol": "T", "price": float("nan")}]}
        for command in (["search", "test"], ["quote", "TEST"], ["news", "test"]):
            getter = {"search": "search_ticker", "quote": "get_quote", "news": "get_news"}[command[0]]
            with patch.object(stocks, getter, return_value=data), \
                 patch("sys.argv", ["stocks.py", *command, "--json"]), \
                 patch("builtins.print") as output:
                with self.assertRaises(SystemExit) as exc:
                    stocks.main()
            self.assertEqual(exc.exception.code, 0)
            self.assertEqual(json.loads(output.call_args.args[0])["results"][0]["price"], None)

    def test_news_times_are_readable_on_every_platform(self):
        published = int(pd.Timestamp("2026-11-04 09:05").timestamp())
        item = {"title": "t", "publisher": "p", "link": "", "providerPublishTime": published}
        with patch.object(stocks.yf, "Search", return_value=Mock(news=[item])):
            data = stocks.get_news("test")
        self.assertRegex(data["articles"][0]["pub_date"], r"^[A-Z][a-z]{2} \d{2} \d{4}, \d{1,2}:\d{2} [AP]M$")


class TradingViewUrlTests(unittest.TestCase):
    def test_yahoo_symbols_map_to_tradingview_pages(self):
        cases = [
            ("AAPL", {"quoteType": "EQUITY", "exchange": "NMS"}, "NASDAQ-AAPL"),
            ("BRK-B", {"quoteType": "EQUITY", "exchange": "NYQ"}, "NYSE-BRK.B"),
            ("SPY", {"quoteType": "ETF", "exchange": "PCX"}, "AMEX-SPY"),
            ("^GSPC", {"quoteType": "INDEX"}, "SPX"),
            ("BTC-USD", {"quoteType": "CRYPTOCURRENCY"}, "BTCUSD"),
            ("EURUSD=X", {"quoteType": "CURRENCY"}, "EURUSD"),
            ("CL=F", {"quoteType": "FUTURE"}, "CL1!"),
            ("XYZ", {}, "XYZ"),
        ]
        for symbol, info, page in cases:
            self.assertEqual(stocks.tradingview_url(symbol, info),
                             f"https://www.tradingview.com/symbols/{page}/")


class ChartTests(unittest.TestCase):
    def ticker(self, index):
        rows = [[10.0, 11.0, 9.0, 10.5, 1000], [None, None, None, None, None], [10.5, 12.0, 10.0, 11.5, None]]
        return Mock(history=Mock(return_value=pd.DataFrame(
            rows, index=index, columns=["Open", "High", "Low", "Close", "Volume"]
        )))

    def test_daily_bars_use_dates_and_drop_empty_rows(self):
        index = pd.DatetimeIndex(["2026-11-02", "2026-11-03", "2026-11-04"], tz="America/New_York")
        with patch.object(stocks.yf, "Ticker", return_value=self.ticker(index)):
            data = stocks.get_chart_data("test", period="6mo")
        self.assertEqual(data["interval"], "1d")
        self.assertFalse(data["intraday"])
        self.assertEqual([b["time"] for b in data["bars"]], ["2026-11-02", "2026-11-04"])
        self.assertEqual(data["bars"][1]["volume"], 0)

    def test_intraday_bars_carry_exchange_wall_clock(self):
        index = pd.DatetimeIndex(["2026-11-03 09:30", "2026-11-03 09:35", "2026-11-03 09:40"],
                                 tz="America/New_York")
        with patch.object(stocks.yf, "Ticker", return_value=self.ticker(index)):
            data = stocks.get_chart_data("test", period="1d")
        self.assertEqual(data["interval"], "5m")
        self.assertTrue(data["intraday"])
        self.assertEqual(data["bars"][0]["time"], int(pd.Timestamp("2026-11-03 09:30", tz="UTC").timestamp()))

    def test_moving_averages_use_history_before_the_range(self):
        index = pd.date_range("2026-11-02", periods=3, freq="D", tz="America/New_York")
        bars = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": [4.0, 5.0, 6.0],
                             "Volume": 0}, index=index)
        earlier = pd.DataFrame({"Close": [1.0, 2.0, 3.0]},
                               index=pd.date_range("2026-10-30", periods=3, freq="D", tz="America/New_York"))
        ticker = Mock(history=Mock(side_effect=[bars, earlier]))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_chart_data("test", period="6mo", ma_periods=[3, 10])
        self.assertEqual(data["ma"]["3"], [3.0, 4.0, 5.0])  # first bar averages 2, 3, 4
        self.assertEqual(data["ma"]["10"], [None, None, None])
        self.assertLess(ticker.history.call_args_list[1].kwargs["start"], index[0])

    def test_lookback_failure_still_charts(self):
        index = pd.DatetimeIndex(["2026-11-02", "2026-11-03", "2026-11-04"], tz="America/New_York")
        ticker = self.ticker(index)
        ticker.history.side_effect = [ticker.history.return_value, RuntimeError("too far back")]
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_chart_data("test", period="5d", ma_periods=[2])
        self.assertEqual(data["ma"]["2"], [None, 11.0])

    def test_unsupported_period_is_an_error(self):
        self.assertIn("error", stocks.get_chart_data("test", period="7y"))

    def test_page_inlines_data_without_breaking_out_of_script(self):
        info = {"symbol": "TEST", "name": "</script><b>x", "exchange": "", "currency": "USD"}
        data = {"symbol": "TEST", "period": "6mo", "interval": "1d", "intraday": False, "bars": []}
        page = stocks.chart_page(info, data, size=(800, 600))
        self.assertNotIn("</script><b>", page)
        self.assertNotIn("__", page.split("<script>")[1])
        self.assertIn("width: 800px", page)


if __name__ == "__main__":
    unittest.main()
