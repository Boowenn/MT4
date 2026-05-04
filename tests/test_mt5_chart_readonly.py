from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.mt5_chart_readonly import (
    build_kline_payload,
    build_shadow_signals_payload,
    build_trades_payload,
)


class Mt5ChartReadOnlyTests(unittest.TestCase):
    def test_kline_endpoint_is_read_only_and_has_bars(self):
        payload = build_kline_payload("EURUSDc", "H1", 20)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["endpoint"], "kline")
        self.assertEqual(payload["symbol"], "EURUSDc")
        self.assertEqual(payload["timeframe"], "H1")
        self.assertEqual(len(payload["bars"]), 20)
        self.assertTrue(payload["safety"]["readOnly"])
        self.assertFalse(payload["safety"]["orderSendAllowed"])
        self.assertFalse(payload["safety"]["mutatesMt5"])

    def test_trades_endpoint_reads_runtime_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "QuantGod_TradeJournal.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Symbol", "Strategy", "Type", "OpenTimeIso", "OpenPrice", "Ticket"])
                writer.writeheader()
                writer.writerow(
                    {
                        "Symbol": "EURUSDc",
                        "Strategy": "MA_Cross",
                        "Type": "BUY",
                        "OpenTimeIso": datetime.now(timezone.utc).isoformat(),
                        "OpenPrice": "1.105",
                        "Ticket": "1001",
                    }
                )
            payload = build_trades_payload("EURUSDc", days=30, runtime_dir=root)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["route"], "MA_Cross")
        self.assertEqual(payload["items"][0]["side"], "BUY")
        self.assertEqual(payload["items"][0]["price"], 1.105)

    def test_shadow_signals_endpoint_reads_runtime_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "QuantGod_ShadowSignalLedger.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Symbol", "Route", "Side", "Signal", "EventTimeIso", "Price"])
                writer.writeheader()
                writer.writerow(
                    {
                        "Symbol": "EURUSDc",
                        "Route": "MA_Cross",
                        "Side": "SELL",
                        "Signal": "blocked_news",
                        "EventTimeIso": datetime.now(timezone.utc).isoformat(),
                        "Price": "1.107",
                    }
                )
            payload = build_shadow_signals_payload("EURUSDc", days=7, runtime_dir=root)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["signal"], "blocked_news")
        self.assertEqual(payload["items"][0]["side"], "SELL")

    def test_shadow_signals_skip_rows_without_valid_time_and_parse_label_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "QuantGod_ShadowCandidateLedger.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "EventId",
                        "LabelTimeLocal",
                        "Symbol",
                        "CandidateRoute",
                        "CandidateDirection",
                        "CandidateScore",
                        "ReferencePrice",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "EventId": "missing-time",
                        "LabelTimeLocal": "",
                        "Symbol": "EURUSDc",
                        "CandidateRoute": "BB_TRIPLE_SHADOW",
                        "CandidateDirection": "UNKNOWN",
                    }
                )
                writer.writerow(
                    {
                        "EventId": "valid-local-time",
                        "LabelTimeLocal": datetime.now(timezone.utc).strftime("%Y.%m.%d %H:%M:%S"),
                        "Symbol": "EURUSDc",
                        "CandidateRoute": "BB_TRIPLE_SHADOW",
                        "CandidateDirection": "BUY",
                        "CandidateScore": "0.71",
                        "ReferencePrice": "1.107",
                    }
                )
            payload = build_shadow_signals_payload("EURUSDc", days=7, runtime_dir=root)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "valid-local-time")
        self.assertEqual(payload["items"][0]["route"], "BB_TRIPLE_SHADOW")
        self.assertEqual(payload["items"][0]["side"], "BUY")
        self.assertNotIn("1970", payload["items"][0]["timeIso"])


if __name__ == "__main__":
    unittest.main()
