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


if __name__ == "__main__":
    unittest.main()
