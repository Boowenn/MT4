from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from mt5_runtime_bridge.reader import RuntimeBridgeReader
from mt5_runtime_bridge.schema import build_sample_snapshot, validate_runtime_snapshot


class Mt5RuntimeBridgeTests(unittest.TestCase):
    def test_sample_snapshot_validates_and_has_read_only_safety(self) -> None:
        snapshot = build_sample_snapshot("USDJPYc")
        validation = validate_runtime_snapshot(snapshot, expected_symbol="USDJPYc")
        self.assertTrue(validation["ok"], validation)
        self.assertTrue(snapshot["safety"]["readOnly"])
        self.assertFalse(snapshot["safety"]["orderSendAllowed"])
        self.assertFalse(snapshot["safety"]["telegramCommandExecutionAllowed"])

    def test_reader_returns_runtime_payload_not_mock_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            reader = RuntimeBridgeReader(tmp_dir, max_age_seconds=0)
            reader.write_sample_files(["USDJPYc"], overwrite=True)
            payload = reader.collect_for_ai_snapshot("USDJPYc", ["M15", "H1"])
            self.assertFalse(payload["fallback"])
            self.assertEqual(payload["source"], "hfm_ea_runtime")
            self.assertTrue(payload["runtimeFresh"])
            self.assertIn("kline_m15", payload)
            self.assertIn("current_price", payload)

    def test_schema_rejects_credential_like_keys_and_trade_flags(self) -> None:
        snapshot = build_sample_snapshot("USDJPYc")
        snapshot["apiToken"] = "must-not-exist"
        snapshot["safety"]["orderSendAllowed"] = True
        validation = validate_runtime_snapshot(snapshot, expected_symbol="USDJPYc")
        self.assertFalse(validation["ok"])
        joined = ";".join(validation["errors"])
        self.assertIn("forbidden_credential_like_keys", joined)
        self.assertIn("unsafe_truthy_flag:orderSendAllowed", joined)

    def test_cli_sample_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli = ROOT / "tools" / "run_mt5_runtime_bridge.py"
            sample = subprocess.run(
                [sys.executable, str(cli), "sample", "--runtime-dir", tmp_dir, "--symbols", "USDJPYc", "--overwrite"],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertIn("QuantGod_MT5RuntimeSnapshot_USDJPYc.json", sample.stdout)
            status = subprocess.run(
                [sys.executable, str(cli), "status", "--runtime-dir", tmp_dir, "--symbols", "USDJPYc", "--max-age-seconds", "0"],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(status.stdout)
            self.assertTrue(payload["runtimeFound"])
            self.assertEqual(payload["freshSymbols"], 1)

    def test_market_data_collector_prefers_runtime_when_mt5_python_unavailable(self) -> None:
        from ai_analysis.market_data_collector import MarketDataCollector

        with tempfile.TemporaryDirectory() as tmp_dir:
            RuntimeBridgeReader(tmp_dir, max_age_seconds=0).write_sample_files(["USDJPYc"], overwrite=True)
            with mock.patch.dict(os.environ, {"QG_MT5_RUNTIME_MAX_AGE_SECONDS": "0"}, clear=False):
                snapshot = MarketDataCollector(runtime_dir=tmp_dir).collect_sync("USDJPYc", ["M15"])
            self.assertFalse(snapshot["fallback"])
            self.assertEqual(snapshot["source"], "hfm_ea_runtime")
            self.assertTrue(snapshot["runtimeFresh"])
            self.assertIn("kline_m15", snapshot)
            self.assertNotEqual(snapshot["kline_m15"][0].get("source"), "mock_fallback")

    def test_dashboard_embedded_runtime_uses_hfm_gmt_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dashboard = {
                "timestamp": "2026.05.04 20:00:00",
                "runtime": {"gmtTime": "2026.05.04 11:00:00", "localTime": "2026.05.04 20:00:00"},
                "symbols": [
                    {
                        "symbol": "USDJPYc",
                        "bid": 157.09,
                        "ask": 157.12,
                        "spread": 3.0,
                        "tradeMode": "FULL",
                    }
                ],
            }
            path = Path(tmp_dir) / "QuantGod_Dashboard.json"
            path.write_text(json.dumps(dashboard), encoding="utf-8")
            reader = RuntimeBridgeReader(tmp_dir, max_age_seconds=0)
            payload = reader.collect_for_ai_snapshot("USDJPYc", ["M15"])

            self.assertFalse(payload["fallback"], payload)
            self.assertEqual(payload["source"], "dashboard_runtime")
            self.assertTrue(payload["runtimeFresh"])
            self.assertEqual(payload["current_price"]["timeIso"], "2026.05.04 11:00:00")


if __name__ == "__main__":
    unittest.main()
