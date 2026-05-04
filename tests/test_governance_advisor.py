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


class CandidateActionTests(unittest.TestCase):
    """candidate_action — decides candidate promotion readiness."""

    def test_insufficient_sample_keeps_iterating(self):
        action, tone, blockers = governance.candidate_action({"horizonRows": 5, "winRatePct": 60, "avgSignedPips": 5})
        self.assertEqual(action, "KEEP_SIM_ITERATE")
        self.assertIn("sample_lt_20", blockers)

    def test_win_rate_lt_45_returns_retune(self):
        action, tone, blockers = governance.candidate_action({"horizonRows": 25, "winRatePct": 40, "avgSignedPips": -2})
        self.assertEqual(action, "RETUNE_SIM")
        self.assertEqual(tone, "conflict")
        self.assertIn("win_rate_lt_55", blockers)

    def test_win_rate_below_55_keeps_iterating(self):
        action, tone, blockers = governance.candidate_action({"horizonRows": 30, "winRatePct": 50, "avgSignedPips": 1})
        self.assertEqual(action, "KEEP_SIM_ITERATE")
        self.assertIn("win_rate_lt_55", blockers)

    def test_avg_pips_not_positive_blocks_promotion(self):
        action, tone, blockers = governance.candidate_action({"horizonRows": 30, "winRatePct": 58, "avgSignedPips": -1})
        self.assertEqual(action, "KEEP_SIM_ITERATE")
        self.assertIn("avg_signed_pips_not_positive", blockers)

    def test_all_green_returns_promotion_review(self):
        action, tone, blockers = governance.candidate_action({"horizonRows": 25, "winRatePct": 60, "avgSignedPips": 10})
        self.assertEqual(action, "PROMOTION_REVIEW")
        self.assertEqual(tone, "supported")
        self.assertEqual(blockers, [])

    def test_none_candidate_returns_collect(self):
        action, tone, blockers = governance.candidate_action(None)
        self.assertEqual(action, "KEEP_SIM_COLLECT")
        self.assertIn("candidate outcome sample is not ready", blockers)


class LiveActionTests(unittest.TestCase):
    """live_action — decides whether to KEEP/DEMOTE live routes."""

    def test_trades_lt_3_returns_watch_with_blocker(self):
        action, tone, blockers = governance.live_action({"closedTrades": 1}, None)
        self.assertEqual(action, "KEEP_LIVE_WATCH")
        self.assertIn("live_forward_sample_lt_3", blockers)

    def test_consecutive_losses_ge_2_demotes(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 10, "consecutiveLosses": 2, "netProfitUSC": -5, "profitFactor": 0.8}, None
        )
        self.assertEqual(action, "DEMOTE_REVIEW")
        self.assertEqual(tone, "conflict")
        self.assertIn("consecutive_losses_ge_2", blockers)

    def test_consecutive_losses_3_demotes(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 15, "consecutiveLosses": 3, "netProfitUSC": -10, "profitFactor": 0.5}, None
        )
        self.assertEqual(action, "DEMOTE_REVIEW")

    def test_pf_lt_1_and_net_negative_demotes(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 10, "consecutiveLosses": 0, "netProfitUSC": -3, "profitFactor": 0.7}, None
        )
        self.assertEqual(action, "DEMOTE_REVIEW")
        self.assertIn("profit_factor_lt_1", blockers)

    def test_low_win_rate_watches(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 20, "consecutiveLosses": 0, "netProfitUSC": 5, "profitFactor": 1.2, "winRatePct": 40}, None
        )
        self.assertEqual(action, "KEEP_LIVE_WATCH")
        self.assertIn("win_rate_lt_45", blockers)

    def test_floating_drawdown_adds_watch_blocker(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 10, "profitFactor": 1.3, "winRatePct": 55}, {"floatingProfitUSC": -1.5}
        )
        self.assertIn("open_position_drawdown_watch", blockers)

    def test_all_green_returns_keep_live(self):
        action, tone, blockers = governance.live_action(
            {"closedTrades": 20, "consecutiveLosses": 0, "netProfitUSC": 10, "profitFactor": 1.5, "winRatePct": 60}, None
        )
        self.assertEqual(action, "KEEP_LIVE")
        self.assertEqual(tone, "supported")
        self.assertEqual(blockers, [])

    def test_empty_live_returns_watch(self):
        action, tone, blockers = governance.live_action(None, None)
        self.assertEqual(action, "KEEP_LIVE_WATCH")
        self.assertIn("live_forward_sample_lt_3", blockers)


class SummarizeProfitRowsTests(unittest.TestCase):
    """summarize_profit_rows — basic statistics from closed trades."""

    def test_mixed_wins_and_losses(self):
        rows = [
            {"NetProfit": "1.0", "CloseTime": "2026.05.01 08:00"},
            {"NetProfit": "-0.5", "CloseTime": "2026.05.01 09:00"},
            {"NetProfit": "0.8", "CloseTime": "2026.05.01 10:00"},
        ]
        result = governance.summarize_profit_rows(rows)
        self.assertEqual(result["closedTrades"], 3)
        self.assertEqual(result["wins"], 2)
        self.assertEqual(result["losses"], 1)
        self.assertAlmostEqual(result["netProfitUSC"], 1.3)
        self.assertAlmostEqual(result["winRatePct"], 66.67, places=1)
        self.assertEqual(result["consecutiveLosses"], 0)

    def test_consecutive_losses_at_end(self):
        rows = [
            {"NetProfit": "0.5", "CloseTime": "2026.05.01 08:00"},
            {"NetProfit": "-0.3", "CloseTime": "2026.05.01 09:00"},
            {"NetProfit": "-0.4", "CloseTime": "2026.05.01 10:00"},
        ]
        result = governance.summarize_profit_rows(rows)
        self.assertEqual(result["consecutiveLosses"], 2)

    def test_all_wins(self):
        rows = [
            {"NetProfit": "1.0", "CloseTime": "2026.05.01 08:00"},
            {"NetProfit": "0.5", "CloseTime": "2026.05.01 09:00"},
        ]
        result = governance.summarize_profit_rows(rows)
        self.assertEqual(result["consecutiveLosses"], 0)
        self.assertEqual(result["wins"], 2)
        self.assertEqual(result["losses"], 0)


class RsiSidePolicyTests(unittest.TestCase):
    """rsi_side_policy — BUY live, SELL blocked after loss review."""

    def test_sell_blocked_buy_allowed(self):
        policy = governance.rsi_side_policy({
            "sideBreakdown": {
                "BUY": {"netProfitUSC": 1.5, "closedTrades": 5},
                "SELL": {"netProfitUSC": -2.0, "closedTrades": 3},
            }
        })
        self.assertEqual(policy["liveAllowed"], ["BUY"])
        self.assertEqual(policy["liveBlocked"], ["SELL"])
        self.assertFalse(policy["sellLiveAllowed"])

    def test_both_positive_still_blocks_sell_by_policy(self):
        """RSI policy always blocks SELL regardless of performance."""
        policy = governance.rsi_side_policy({
            "sideBreakdown": {
                "BUY": {"netProfitUSC": 1.0},
                "SELL": {"netProfitUSC": 2.0},
            }
        })
        self.assertFalse(policy["sellLiveAllowed"])


class DominantLossSideTests(unittest.TestCase):
    """dominant_loss_side — identifies which side is losing."""

    def test_sell_is_dominant_loser(self):
        result = governance.dominant_loss_side({
            "BUY": {"netProfitUSC": 1.0},
            "SELL": {"netProfitUSC": -3.0},
        })
        self.assertEqual(result, "SELL")

    def test_no_losses_returns_empty(self):
        result = governance.dominant_loss_side({
            "BUY": {"netProfitUSC": 1.0},
            "SELL": {"netProfitUSC": 0.5},
        })
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
