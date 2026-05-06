from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.adaptive_policy.policy_engine import build_adaptive_policy
from tools.adaptive_policy.telegram_text import build_policy_telegram_text

class AdaptivePolicyTests(unittest.TestCase):
    def _runtime(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="qg_adaptive_policy_"))
        (root / "journal").mkdir(parents=True, exist_ok=True)
        snapshot = {
            "schema": "quantgod.mt5.runtime_snapshot.v1",
            "source": "hfm_ea_runtime",
            "generatedAt": "2099-01-01T00:00:00Z",
            "symbol": "USDJPYc",
            "fallback": False,
            "runtimeAgeSeconds": 1,
            "current_price": {"bid": 155.10, "ask": 155.12, "spread": 0.02, "timeIso": "2099-01-01T00:00:00Z"},
            "safety": {"readOnly": True, "orderSendAllowed": False}
        }
        (root / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json").write_text(json.dumps(snapshot), encoding="utf-8")
        with (root / "ShadowCandidateOutcomeLedger.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "strategy", "direction", "regime", "scoreR", "mfe", "mae", "spread"])
            writer.writeheader()
            for _ in range(7):
                writer.writerow({"symbol": "USDJPYc", "strategy": "RSI_Reversal", "direction": "BUY", "regime": "TREND_EXP_DOWN", "scoreR": "0.35", "mfe": "1.2", "mae": "0.4", "spread": "0.02"})
            for _ in range(7):
                writer.writerow({"symbol": "USDJPYc", "strategy": "RSI_Reversal", "direction": "SELL", "regime": "RANGE", "scoreR": "-0.40", "mfe": "0.2", "mae": "1.1", "spread": "0.02"})
        with (root / "QuantGod_StrategyEvaluationReport.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "ATR", "ADX", "BBWidth"])
            writer.writeheader()
            writer.writerow({"symbol": "USDJPYc", "ATR": "1.0", "ADX": "20", "BBWidth": "0.01"})
        return root

    def test_scores_buy_active_and_sell_paused(self):
        runtime = self._runtime()
        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=True)
        routes = policy["routes"]
        buy = [r for r in routes if r["direction"] == "LONG"][0]
        sell = [r for r in routes if r["direction"] == "SHORT"][0]
        self.assertEqual(buy["state"], "ACTIVE_SHADOW_OK")
        self.assertEqual(sell["state"], "PAUSED")
        self.assertGreater(buy["winRate"], 0.9)

    def test_entry_gate_and_sltp_plan_are_written(self):
        runtime = self._runtime()
        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=True)
        self.assertTrue((runtime / "adaptive" / "QuantGod_AdaptivePolicy.json").exists())
        self.assertTrue((runtime / "adaptive" / "QuantGod_DynamicEntryGate.json").exists())
        self.assertTrue((runtime / "adaptive" / "QuantGod_DynamicSLTPPlan.json").exists())
        self.assertTrue(policy["entryGates"][0]["runtimeFresh"])
        self.assertFalse(policy["entryGates"][0]["fallback"])

    def test_entry_gate_blocks_abnormally_wide_spread_against_history(self):
        runtime = self._runtime()
        snapshot_path = runtime / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["current_price"]["spread"] = 0.20
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=False)
        spread_check = [item for item in policy["entryGates"][0]["checks"] if item["name"] == "点差"][0]

        self.assertFalse(spread_check["passed"])
        self.assertIn("历史中位点差", spread_check["reason"])

    def test_entry_gate_blocks_degraded_fastlane_quality(self):
        runtime = self._runtime()
        quality_dir = runtime / "quality"
        quality_dir.mkdir(parents=True, exist_ok=True)
        (quality_dir / "QuantGod_MT5FastLaneQuality.json").write_text(json.dumps({
            "schema": "quantgod.mt5.fast_lane_quality.v1",
            "heartbeatFresh": True,
            "heartbeatAgeSeconds": 1,
            "symbols": [{
                "symbol": "USDJPYc",
                "quality": "DEGRADED",
                "tickAgeSeconds": 20,
                "indicatorAgeSeconds": 30,
                "spreadPoints": 2.0,
            }],
            "safety": {"readOnlyDataPlane": True, "orderSendAllowed": False},
        }), encoding="utf-8")

        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=False)
        fastlane_check = [item for item in policy["entryGates"][0]["checks"] if item["name"] == "快通道"][0]

        self.assertFalse(fastlane_check["passed"])
        self.assertFalse(policy["entryGates"][0]["passed"])
        self.assertIn("快通道降级", fastlane_check["reason"])

    def test_empty_fastlane_uses_fresh_hfm_dashboard_fallback(self):
        runtime = self._runtime()
        (runtime / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json").unlink()
        (runtime / "QuantGod_StrategyEvaluationReport.csv").write_text(
            "ReportTimeLocal,Symbol,Strategy,ATRPips,ADX,BBWidthPips,TickAgeSeconds,SpreadPips\n"
            "2026.05.06 14:00:00,USDJPYc,RSI_Reversal,0,0,0,0,2.6\n",
            encoding="utf-8",
        )
        (runtime / "QuantGod_Dashboard.json").write_text(json.dumps({
            "watchlist": "USDJPYc",
            "runtime": {"tradeStatus": "READY", "executionEnabled": True, "readOnlyMode": False, "tickAgeSeconds": 0},
            "market": {"symbol": "USDJPYc", "bid": 155.71, "ask": 155.74, "spread": 0.02},
        }), encoding="utf-8")
        quality_dir = runtime / "quality"
        quality_dir.mkdir(parents=True, exist_ok=True)
        (quality_dir / "QuantGod_MT5FastLaneQuality.json").write_text(json.dumps({
            "schema": "quantgod.mt5.fastlane.quality.v1",
            "heartbeatFound": False,
            "heartbeatFresh": False,
            "symbols": [{"symbol": "USDJPYc", "quality": "DEGRADED", "tickRows": 0, "tickAgeSeconds": None, "indicatorAgeSeconds": None}],
        }), encoding="utf-8")

        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=False)
        gate = policy["entryGates"][0]
        checks = {item["name"]: item for item in gate["checks"]}

        self.assertTrue(gate["passed"])
        self.assertEqual(gate["snapshotSource"], "hfm_ea_dashboard")
        self.assertIn("Dashboard", checks["快通道"]["reason"])
        self.assertIn("降级", checks["指标"]["reason"])

    def test_telegram_text_is_chinese_and_read_only(self):
        runtime = self._runtime()
        policy = build_adaptive_policy(runtime, symbols=["USDJPYc"], write=False)
        text = build_policy_telegram_text(policy)
        self.assertIn("自适应策略审查", text)
        self.assertIn("买入观察", text)
        self.assertIn("暂停", text)
        self.assertIn("不会下单", text)
        self.assertNotIn("orderSendAllowed=true", text)

if __name__ == "__main__":
    unittest.main()
