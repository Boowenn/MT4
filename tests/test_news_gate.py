from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.news_gate.classifier import classify_news_gate
from tools.news_gate.config import NewsGateConfig
from tools.news_gate.policy import apply_news_gate_to_live_policy
from tools.news_gate.schema import ENTRY_BLOCKED, ENTRY_OPPORTUNITY, ENTRY_STANDARD
from tools.usdjpy_bar_replay.market_clock import classify_gates


class NewsGateTests(unittest.TestCase):
    def test_soft_news_does_not_hard_block_and_reduces_lot(self) -> None:
        decision = classify_news_gate(
            {"news": {"blocked": True, "eventName": "Retail sales", "impact": "medium"}},
            NewsGateConfig(mode="SOFT", softLotMultiplier=0.5),
        )
        self.assertEqual(decision["riskLevel"], "SOFT")
        self.assertFalse(decision["hardBlock"])

        entry_mode, allowed, lot, strictness, reasons = apply_news_gate_to_live_policy(
            entry_mode=ENTRY_STANDARD,
            allowed=True,
            recommended_lot=0.48,
            strictness="STANDARD_ALL_CORE_AND_TACTICAL_PASS",
            reasons=[],
            news_gate=decision,
            min_lot=0.01,
            max_lot=2.0,
            step=0.01,
        )
        self.assertEqual(entry_mode, ENTRY_OPPORTUNITY)
        self.assertTrue(allowed)
        self.assertEqual(lot, 0.24)
        self.assertEqual(strictness, "NEWS_SOFT_STAGE_DOWNGRADED")
        self.assertIn("不阻断", " ".join(reasons))

    def test_high_impact_news_still_blocks_live(self) -> None:
        decision = classify_news_gate(
            {"news": {"blocked": True, "eventName": "FOMC rate decision", "impact": "high"}},
            NewsGateConfig(mode="SOFT"),
        )
        self.assertEqual(decision["riskLevel"], "HARD")
        self.assertTrue(decision["hardBlock"])

        entry_mode, allowed, lot, strictness, _ = apply_news_gate_to_live_policy(
            entry_mode=ENTRY_OPPORTUNITY,
            allowed=True,
            recommended_lot=0.1,
            strictness="RELAXED_ONE_MISSING_CONFIRMATION",
            reasons=[],
            news_gate=decision,
            min_lot=0.01,
            max_lot=2.0,
            step=0.01,
        )
        self.assertEqual(entry_mode, ENTRY_BLOCKED)
        self.assertFalse(allowed)
        self.assertEqual(lot, 0.0)
        self.assertEqual(strictness, "BLOCKED_HIGH_IMPACT_NEWS")

    def test_unknown_news_source_does_not_block(self) -> None:
        decision = classify_news_gate({}, NewsGateConfig(mode="SOFT", unknownLotMultiplier=0.75))
        self.assertEqual(decision["riskLevel"], "UNKNOWN")
        self.assertFalse(decision["hardBlock"])
        self.assertEqual(decision["lotMultiplier"], 0.75)

    def test_replay_hard_gate_only_keeps_high_impact_news_hard(self) -> None:
        soft = classify_gates({"blockReason": "NEWS_BLOCK ordinary commentary", "raw": {"newsAllowed": False, "newsImpact": "medium"}})
        hard = classify_gates({"blockReason": "NEWS_BLOCK BOJ rate decision", "raw": {"newsAllowed": False, "newsImpact": "high"}})
        self.assertTrue(soft["hardGatePass"])
        self.assertEqual(soft["newsRiskLevel"], "SOFT")
        self.assertFalse(hard["hardGatePass"])
        self.assertIn("HIGH_IMPACT_NEWS", hard["hardBlockers"])


if __name__ == "__main__":
    unittest.main()

