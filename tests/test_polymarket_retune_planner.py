import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_polymarket_retune_planner.py"
SPEC = importlib.util.spec_from_file_location("build_polymarket_retune_planner", MODULE_PATH)
planner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(planner)


class PolymarketRetunePlannerTests(unittest.TestCase):
    def test_copy_trading_review_scales_shadow_pnl_to_real_cash(self):
        recommendation = planner.build_recommendation({
            "experimentKey": "politics_copy_archive_shadow_v1",
            "marketScope": "politics",
            "signalSource": "copy",
            "closed": 220,
            "wins": 120,
            "losses": 100,
            "grossWin": 132.0,
            "grossLoss": -110.0,
            "realizedPnl": 22.0,
            "profitFactor": 1.2,
            "winRatePct": 54.55,
        })

        review = planner.copy_trading_review([recommendation], {
            "accountCash": 7.1,
            "bankroll": 15.0,
        })

        simulation = review["capitalSimulation"]
        self.assertTrue(review["active"])
        self.assertTrue(simulation["restoreLiveReviewEligible"])
        self.assertGreater(simulation["cashScaledPnlUSDC"], 0)
        self.assertEqual(simulation["accountCashUSDC"], 7.1)
        self.assertIn("Telegram signals", [item["source"] for item in review["sourceToolkit"]])
        self.assertFalse(review["iterationPlan"]["retuneRequired"])

    def test_copy_trading_review_emits_all_market_retune_plan_when_weak(self):
        recommendation = planner.build_recommendation({
            "experimentKey": "sports_copy_archive_shadow_v1",
            "marketScope": "sports",
            "signalSource": "copy",
            "closed": 179,
            "wins": 89,
            "losses": 90,
            "grossWin": 232.0821,
            "grossLoss": -236.3137,
            "realizedPnl": -4.2316,
            "profitFactor": 0.9821,
            "winRatePct": 49.72,
        })

        review = planner.copy_trading_review([recommendation], {
            "accountCash": 7.1,
            "bankroll": 15.0,
        })

        plan = review["iterationPlan"]
        self.assertEqual(review["status"], "COPY_TRADING_RETUNE_REQUIRED")
        self.assertIn("全市场模块", review["summary"])
        self.assertIn("politics", plan["copyUniverse"])
        self.assertIn("crypto", plan["copyUniverse"])
        self.assertTrue(any(item["key"] == "copy_archive_all_market_whitelist_v2" for item in plan["candidateVariants"]))
        self.assertIn("cash_scaled_pnl_not_positive", plan["capitalResult"]["blockers"])


if __name__ == "__main__":
    unittest.main()
