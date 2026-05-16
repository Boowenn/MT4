from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.mt5_fastlane.quality import build_quality_report, build_telegram_text
from tools.mt5_fastlane.schema import assert_safe_payload, safety_payload
from tools.run_mt5_fastlane import main as fastlane_main


class Mt5FastLaneTests(unittest.TestCase):
    def test_sample_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fastlane_main(["--runtime-dir", tmp, "--symbols", "USDJPYc", "sample"]), 0)
            report = build_quality_report(tmp, symbols=["USDJPYc"], write=True)
            self.assertTrue(report["heartbeatFound"])
            self.assertEqual(len(report["symbols"]), 1)
            self.assertEqual(report["symbols"][0]["quality"], "FAST")
            self.assertTrue((Path(tmp) / "quality" / "QuantGod_MT5FastLaneQuality.json").exists())

    def test_dashboard_timer_fallback_keeps_evidence_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "QuantGod_MT5_TimerHeartbeat.txt").write_text(
                "localTime=2026.05.16 11:43:33\n"
                "serverTime=2026.05.16 05:43:33\n"
                "refreshIntervalSeconds=5\n",
                encoding="utf-8",
            )
            (root / "QuantGod_Dashboard.json").write_text(
                json.dumps(
                    {
                        "timestamp": "2026.05.16 11:43:41",
                        "watchlist": "USDJPYc",
                        "runtime": {
                            "tradeStatus": "READY",
                            "connected": True,
                            "terminalConnected": True,
                            "tickAgeSeconds": 1,
                        },
                        "market": {"symbol": "USDJPYc", "bid": 158.739, "ask": 158.741, "spread": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            (root / "QuantGod_USDJPYRsiEntryDiagnostics.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.mt5.usdjpy_rsi_entry_diagnostics.v1",
                        "symbol": "USDJPYc",
                        "strategy": "RSI_Reversal",
                        "state": "WAITING_RSI_SIGNAL",
                        "guards": {"spreadPips": 0.2},
                        "rsi": {
                            "rsiClosed1": 44.0,
                            "rsiClosed2": 40.0,
                            "atrClosed1": 0.12,
                            "lowerBand": 158.1,
                            "upperBand": 158.9,
                            "closeClosed1": 158.5,
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_quality_report(tmp, symbols=["USDJPYc"], write=False)

            self.assertTrue(report["heartbeatFound"])
            self.assertTrue(report["heartbeatFresh"])
            self.assertTrue(report["dashboardFallback"])
            self.assertIn("QuantGod_Dashboard.json", report["fallbackSources"])
            self.assertEqual(report["heartbeatSource"], "QuantGod_MT5_TimerHeartbeat.txt")
            self.assertEqual(report["symbols"][0]["quality"], "EA_DASHBOARD_OK")
            self.assertTrue(report["symbols"][0]["dashboardFallback"])
            self.assertEqual(report["symbols"][0]["tickRows"], 3)

    def test_global_symbols_option_survives_subcommand_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fastlane_main(["--runtime-dir", tmp, "--symbols", "EURJPYc", "sample"]), 0)
            report = build_quality_report(tmp, symbols=["EURJPYc"], write=False)
            self.assertEqual(report["symbols"][0]["symbol"], "EURJPYc")

    def test_safety_rejects_secrets_and_execution_flags(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_payload({"token": "x"})
        with self.assertRaises(ValueError):
            assert_safe_payload({"orderSendAllowed": True})
        assert_safe_payload({"safety": safety_payload(), "message": "只读"})

    def test_telegram_text_is_chinese_and_advisory_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fastlane_main(["--runtime-dir", tmp, "--symbols", "USDJPYc", "sample"])
            text = build_telegram_text(build_quality_report(tmp, symbols=["USDJPYc"], write=False))
            self.assertIn("MT5 快通道质量审查", text)
            self.assertIn("不会下单", text)
            self.assertIn("USDJPYc", text)


if __name__ == "__main__":
    unittest.main()
