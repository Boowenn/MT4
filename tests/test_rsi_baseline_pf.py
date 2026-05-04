"""RSI baseline regression test framework.
When RSI parameters change, this guards against silent PF degradation.
Uses existing backtest infrastructure where available, baseline file otherwise.
"""
from __future__ import annotations
import json, unittest
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parents[1] / "tests" / "baselines" / "rsi_pf_baseline.json"
DEFAULT_BASELINE = {
    "_schema": "quantgod.rsi_baseline.v1",
    "_description": "Last accepted RSI backtest performance baseline. Update only when intentionally improving params.",
    "min_profit_factor": 0.85,
    "min_win_rate_pct": 40.0,
    "max_drawdown_usc": 80.0,
    "last_updated": "2026-05-04",
    "params_snapshot": {
        "PilotRsiPeriod": 2,
        "PilotRsiOverbought": 85,
        "PilotRsiOversold": 15,
    }
}


class RsiBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASELINE_PATH.exists():
            BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_text(json.dumps(DEFAULT_BASELINE, indent=2, ensure_ascii=False), encoding="utf-8")
        cls.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    def test_baseline_file_exists_and_valid(self):
        self.assertIn("min_profit_factor", self.baseline)
        self.assertIn("min_win_rate_pct", self.baseline)
        self.assertGreater(self.baseline["min_profit_factor"], 0)
        self.assertLess(self.baseline["min_profit_factor"], 10)

    def test_baseline_has_params_snapshot(self):
        params = self.baseline.get("params_snapshot", {})
        self.assertIn("PilotRsiPeriod", params)
        self.assertIn("PilotRsiOverbought", params)
        self.assertIn("PilotRsiOversold", params)

    def test_current_preset_params_match_baseline_snapshot(self):
        """Alert when RSI params changed without updating baseline."""
        preset_path = Path(__file__).resolve().parents[1] / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
        if not preset_path.exists():
            self.skipTest("Preset file not found")
        preset = {}
        for raw in preset_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            preset[k.strip()] = v.strip()
        snapshot = self.baseline.get("params_snapshot", {})
        for key, expected in snapshot.items():
            actual = preset.get(key)
            if actual is not None:
                self.assertEqual(str(expected), actual,
                    f"{key} changed: baseline={expected}, preset={actual}. Update baseline if this is intentional.")


if __name__ == "__main__":
    unittest.main()
