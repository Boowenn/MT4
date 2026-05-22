from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.usdjpy_spread_gate_audit import (
    backfill_tokyo_h4_shadow_candidate_ledger,
    backfill_tokyo_h4_shadow_candidate_outcome_ledger,
    build_spread_gate_impact_audit,
)


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

    def test_backfill_writes_deduped_tokyo_h4_candidate_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            rows = [
                {
                    "generatedAtLocal": "2026.05.18 09:00:00",
                    "generatedAtServer": "2026.05.18 00:00:00",
                    "symbol": "USDJPYc",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "shadowResearchSpreadAllowed": True,
                    "spreadPips": 2.2,
                    "bid": 155.120,
                    "ask": 155.142,
                    "h4Pullback": {
                        "signalTimeframe": "M15",
                        "eventBarTime": "2026.05.18 08:45:00",
                        "signalDirection": 1,
                        "score": 70,
                    },
                    "tokyoRange": {"signalDirection": 0},
                },
                {
                    "generatedAtLocal": "2026.05.18 09:01:00",
                    "generatedAtServer": "2026.05.18 00:01:00",
                    "symbol": "USDJPYc",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "shadowResearchSpreadAllowed": True,
                    "spreadPips": 2.2,
                    "bid": 155.121,
                    "ask": 155.143,
                    "h4Pullback": {
                        "signalTimeframe": "M15",
                        "eventBarTime": "2026.05.18 08:45:00",
                        "signalDirection": 1,
                        "score": 70,
                    },
                    "tokyoRange": {"signalDirection": 0},
                },
                {
                    "generatedAtLocal": "2026.05.18 12:15:00",
                    "generatedAtServer": "2026.05.18 03:15:00",
                    "symbol": "USDJPYc",
                    "sessionOpen": True,
                    "newsBlocked": False,
                    "shadowResearchSpreadAllowed": True,
                    "spreadPips": 2.5,
                    "bid": 155.300,
                    "ask": 155.325,
                    "h4Pullback": {"signalDirection": 0},
                    "tokyoRange": {
                        "timeframe": "M15",
                        "eventBarTime": "2026.05.18 12:00:00",
                        "signalDirection": -1,
                        "score": 74,
                    },
                },
            ]
            (runtime / "QuantGod_StrategyJsonEAShadowEvaluationLedger.jsonl").write_text(
                "\n".join(json.dumps(item) for item in rows) + "\n",
                encoding="utf-8",
            )

            report = backfill_tokyo_h4_shadow_candidate_ledger(
                runtime,
                start_date_jst="2026-05-18",
                end_date_jst="2026-05-18",
                write=True,
            )

            ledger = runtime / "QuantGod_ShadowCandidateLedger.csv"
            text = ledger.read_text(encoding="utf-8")
            self.assertEqual(report["appendedCandidateRows"], 2)
            self.assertIn("USDJPY_H4_TREND_PULLBACK", text)
            self.assertIn("USDJPY_TOKYO_RANGE_BREAKOUT", text)
            self.assertIn("Strategy JSON H4 Pullback shadow signal", text)

            second = backfill_tokyo_h4_shadow_candidate_ledger(
                runtime,
                start_date_jst="2026-05-18",
                end_date_jst="2026-05-18",
                write=True,
            )
            self.assertEqual(second["appendedCandidateRows"], 0)
            self.assertEqual(second["skipped"].get("alreadyPresent"), 2)

    def test_backfill_writes_tokyo_h4_candidate_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "QuantGod_ShadowCandidateLedger.csv").write_text(
                "EventId,LabelTimeLocal,LabelTimeServer,EventBarTime,Symbol,CandidateRoute,Timeframe,CandidateDirection,CandidateScore,Regime,ReferencePrice,SpreadPips,NewsStatus,Trigger,Reason\n"
                "H4-1,2026.05.18 09:00:00,2026.05.18 00:00:00,2026.05.18 08:45:00,USDJPYc,USDJPY_H4_TREND_PULLBACK,M15,BUY,70.0,STRATEGY_JSON_SHADOW,155.100,2.2,CLEAR,trigger,reason\n"
                "TOKYO-1,2026.05.18 12:15:00,2026.05.18 03:15:00,2026.05.18 12:00:00,USDJPYc,USDJPY_TOKYO_RANGE_BREAKOUT,M15,SELL,74.0,STRATEGY_JSON_SHADOW,155.300,2.2,CLEAR,trigger,reason\n",
                encoding="utf-8",
            )
            kline_dir = runtime / "backtest" / "exported_klines"
            kline_dir.mkdir(parents=True)
            (kline_dir / "QuantGod_USDJPYc_M15_rates.csv").write_text(
                "epoch,timestamp,open,high,low,close,tick_volume,spread,real_volume\n"
                "1,2026.05.18 08:45:00,155.10,155.15,155.05,155.12,1,22,0\n"
                "2,2026.05.18 09:00:00,155.12,155.20,155.10,155.18,1,22,0\n"
                "3,2026.05.18 09:15:00,155.18,155.22,155.16,155.20,1,22,0\n"
                "4,2026.05.18 09:30:00,155.20,155.24,155.18,155.22,1,22,0\n"
                "5,2026.05.18 12:00:00,155.30,155.31,155.20,155.24,1,22,0\n"
                "6,2026.05.18 12:15:00,155.24,155.26,155.10,155.12,1,22,0\n"
                "7,2026.05.18 12:30:00,155.12,155.15,155.00,155.04,1,22,0\n"
                "8,2026.05.18 12:45:00,155.04,155.08,154.96,155.00,1,22,0\n",
                encoding="utf-8",
            )

            report = backfill_tokyo_h4_shadow_candidate_outcome_ledger(
                runtime,
                start_date_jst="2026-05-18",
                end_date_jst="2026-05-18",
                write=True,
            )

            outcome = runtime / "QuantGod_ShadowCandidateOutcomeLedger.csv"
            text = outcome.read_text(encoding="utf-8")
            self.assertEqual(report["appendedOutcomeRows"], 6)
            self.assertIn("USDJPY_H4_TREND_PULLBACK", text)
            self.assertIn("USDJPY_TOKYO_RANGE_BREAKOUT", text)
            self.assertIn("WIN", text)


if __name__ == "__main__":
    unittest.main()
