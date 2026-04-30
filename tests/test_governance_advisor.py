import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_governance_advisor.py"
SPEC = importlib.util.spec_from_file_location("build_governance_advisor", MODULE_PATH)
governance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(governance)


class GovernanceAdvisorTests(unittest.TestCase):
    def test_rsi_sell_losses_do_not_demote_buy_live_side(self):
        live = governance.summarize_live_forward([
            {
                "Source": "EA",
                "Strategy": "RSI_Reversal",
                "Type": "BUY",
                "NetProfit": "0.80",
                "CloseTime": "2026.04.28 08:00",
            },
            {
                "Source": "EA",
                "Strategy": "RSI_Reversal",
                "Type": "BUY",
                "NetProfit": "0.70",
                "CloseTime": "2026.04.28 09:00",
            },
            {
                "Source": "EA",
                "Strategy": "RSI_Reversal",
                "Type": "SELL",
                "NetProfit": "-0.50",
                "CloseTime": "2026.04.29 07:00",
            },
            {
                "Source": "EA",
                "Strategy": "RSI_Reversal",
                "Type": "SELL",
                "NetProfit": "-0.60",
                "CloseTime": "2026.04.29 09:00",
            },
        ])["RSI_Reversal"]

        action, tone, blockers, side_policy = governance.rsi_live_action(live, {})

        self.assertEqual(action, "KEEP_LIVE_WATCH")
        self.assertEqual(tone, "waiting")
        self.assertIn("sell_side_demoted_after_loss_review", blockers)
        self.assertEqual(side_policy["liveAllowed"], ["BUY"])
        self.assertEqual(side_policy["liveBlocked"], ["SELL"])
        self.assertFalse(side_policy["sellLiveAllowed"])
        self.assertGreater(live["sideBreakdown"]["BUY"]["netProfitUSC"], 0)
        self.assertLess(live["sideBreakdown"]["SELL"]["netProfitUSC"], 0)


if __name__ == "__main__":
    unittest.main()
