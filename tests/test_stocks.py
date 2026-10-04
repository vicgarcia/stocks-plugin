"""Offline regression tests for factual financial reports."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch, PropertyMock, Mock

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "stocks", Path(__file__).resolve().parents[1] / "scripts" / "stocks.py"
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
        self.assertEqual(json.loads(stocks.format_fundamentals(data, as_json=True)), data)
        self.assertNotIn("total_score", data)
        self.assertFalse(hasattr(stocks, "score_fundamentals"))

    def test_fetch_failure_is_explicit_and_json_stays_json(self):
        ticker = self.ticker()
        type(ticker).income_stmt = PropertyMock(side_effect=RuntimeError("offline"))
        with patch.object(stocks.yf, "Ticker", return_value=ticker):
            data = stocks.get_fundamentals("test")
        self.assertIn("offline", data["error"])
        self.assertEqual(json.loads(stocks.format_fundamentals(data, as_json=True)), data)

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


if __name__ == "__main__":
    unittest.main()
