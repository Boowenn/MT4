from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.usdjpy_spread_gate_audit import build_spread_gate_impact_audit


class USDJPYSpreadGateAuditTests(unittest.TestCase):
    def test_threshold_impact_dedupes_shadow_opportunities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            kline_dir = runtime / "backtest" / "exported_klines"
            kline_dir.mkdir(parents=True)
            (kline_dir / "QuantGod_USDJPYc_M1_rates.csv").write_text(
                "epoch,timestamp,open,high,low,close,tick_volume,spread,real_volume\n"
                "1,2026.05.18 00:00:00,1,1,1,1,1,20,0\n"
                "2,2026.05.18 00:01:00,1,1,1,1,1,22,0\n"
                "3,2026.05.18 00:02:00,1,1,1,1,1,25,0\n",
                encoding="utf-8",
            )
            rows = [
                {
                    "generatedAtLocal": "2026.05.18 09:00:00",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "spreadPips": 2.2,
                    "h4Pullback": {
                        "eventBarTime": "2026.05.18 08:45:00",
                        "signalDirection": 1,
                        "score": 70,
                    },
                    "tokyoRange": {"signalDirection": 0},
                },
                {
                    "generatedAtLocal": "2026.05.18 09:01:00",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "spreadPips": 2.2,
                    "h4Pullback": {
                        "eventBarTime": "2026.05.18 08:45:00",
                        "signalDirection": 1,
                        "score": 70,
                    },
                    "tokyoRange": {"signalDirection": 0},
                },
                {
                    "generatedAtLocal": "2026.05.18 10:00:00",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "spreadPips": 2.5,
                    "h4Pullback": {"signalDirection": 0},
                    "tokyoRange": {
                        "eventBarTime": "2026.05.18 09:45:00",
                        "signalDirection": -1,
                        "score": 70,
                    },
                },
            ]
            (runtime / "QuantGod_StrategyJsonEAShadowEvaluationLedger.jsonl").write_text(
                "\n".join(json.dumps(item) for item in rows) + "\n",
                encoding="utf-8",
            )

            report = build_spread_gate_impact_audit(
                runtime,
                start_date_jst="2026-05-18",
                end_date_jst="2026-05-18",
                thresholds=(2.0, 2.2, 2.5),
                include_promotion_review=False,
                write=True,
            )

            by_threshold = report["shadowEvaluationImpact"]["byThreshold"]
            self.assertEqual(by_threshold[0]["thresholdPips"], 2.0)
            self.assertEqual(by_threshold[0]["m1PassRows"], 1)
            self.assertEqual(by_threshold[1]["uniqueOpportunityCount"], 1)
            self.assertEqual(by_threshold[2]["uniqueOpportunityCount"], 2)
            self.assertEqual(report["microLiveDecision"]["recommendation"], "KEEP_LIVE_CAP_2_0")
            self.assertTrue((runtime / "replay" / "usdjpy" / "QuantGod_USDJPYSpreadGateImpactAudit.json").exists())
            self.assertFalse(report["safety"]["livePresetMutationAllowed"])


if __name__ == "__main__":
    unittest.main()
