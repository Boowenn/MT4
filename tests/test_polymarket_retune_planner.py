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

        review = planner.copy_trading_review(
            [recommendation],
            {
                "accountCash": 7.1,
                "bankroll": 15.0,
            },
            {},
            {},
        )

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

        review = planner.copy_trading_review(
            [recommendation],
            {
                "accountCash": 7.1,
                "bankroll": 15.0,
            },
            {},
            {},
        )

        plan = review["iterationPlan"]
        self.assertEqual(review["status"], "COPY_TRADING_RETUNE_REQUIRED")
        self.assertEqual(review["operatorStatusLabel"], "Agent 已生成跟单重调方案")
        self.assertEqual(review["agentRetuneStatus"], "RETUNE_PLAN_READY_SHADOW_ONLY")
        self.assertTrue(review["completedByAgent"])
        self.assertTrue(plan["completedByAgent"])
        self.assertIn("全市场模块", review["summary"])
        self.assertIn("politics", plan["copyUniverse"])
        self.assertIn("crypto", plan["copyUniverse"])
        self.assertTrue(any(item["key"] == "copy_archive_all_market_whitelist_v2" for item in plan["candidateVariants"]))
        self.assertIn("结算样本不少于 200 笔", plan["acceptanceCriteriaZh"])
        self.assertIn("cash_scaled_pnl_not_positive", plan["capitalResult"]["blockers"])

    def test_active_copy_discovery_reports_failed_replay_instead_of_write_next(self):
        review = planner.copy_discovery_active_review(
            {
                "summary": {"rankedTraders": 30, "eligibleTraders": 28},
                "traders": [{"userName": "leader", "copyScore": 100, "closedStats": {"closed": 50}}],
                "shadowCandidates": [{"slug": "market"}],
                "walletRiskPolicy": {
                    "realWalletExecutionAllowed": False,
                    "walletWriteAllowed": False,
                    "orderSendAllowed": False,
                    "validation": {
                        "shadowReplay": {
                            "present": True,
                            "passed": False,
                            "samples": 39,
                            "profitFactor": 0.5486,
                            "netPnlUSDC": -2.3562,
                        },
                        "walkForward": {
                            "present": True,
                            "passed": False,
                            "batches": 3,
                            "passRatePct": 0,
                        },
                    },
                },
            },
            {},
        )

        self.assertEqual(review["status"], "COPY_TRADER_REPLAY_BLOCKED_SHADOW_ONLY")
        self.assertEqual(review["primaryAction"], "KEEP_COPY_TRADER_SHADOW_REPLAY")
        self.assertIn("Telegram 跟单信号已写入", review["iterationPlan"]["nextAction"])

    def test_active_copy_discovery_collects_more_when_walk_forward_not_full_pass(self):
        review = planner.copy_discovery_active_review(
            {
                "summary": {"rankedTraders": 30, "eligibleTraders": 28},
                "traders": [{"userName": "leader", "copyScore": 100, "closedStats": {"closed": 50}}],
                "shadowCandidates": [{"slug": "market"}],
                "walletRiskPolicy": {
                    "realWalletExecutionAllowed": False,
                    "walletWriteAllowed": False,
                    "orderSendAllowed": False,
                    "runtimePreflight": {"blockers": ["private_key_env_missing"]},
                    "validation": {
                        "shadowReplay": {"present": True, "passed": True, "samples": 39, "profitFactor": 1.3},
                        "walkForward": {"present": True, "passed": True, "batches": 3, "passRatePct": 67},
                    },
                },
            },
            {},
        )

        self.assertEqual(review["status"], "COPY_TRADER_VALIDATED_COLLECT_MORE_BEFORE_RUNTIME")
        self.assertEqual(review["primaryAction"], "KEEP_BUCKETED_REPLAY_COLLECTING")
        self.assertIn("暂不配置真钱 runtime", review["iterationPlan"]["nextAction"])

    def test_active_copy_discovery_reports_runtime_blockers_after_full_walk_forward_passes(self):
        review = planner.copy_discovery_active_review(
            {
                "summary": {"rankedTraders": 30, "eligibleTraders": 28},
                "traders": [{"userName": "leader", "copyScore": 100, "closedStats": {"closed": 50}}],
                "shadowCandidates": [{"slug": "market"}],
                "walletRiskPolicy": {
                    "realWalletExecutionAllowed": False,
                    "walletWriteAllowed": False,
                    "orderSendAllowed": False,
                    "runtimePreflight": {"blockers": ["private_key_env_missing"]},
                    "validation": {
                        "shadowReplay": {"present": True, "passed": True, "samples": 39, "profitFactor": 1.3},
                        "walkForward": {"present": True, "passed": True, "batches": 3, "passRatePct": 100},
                    },
                },
            },
            {},
        )

        self.assertEqual(review["status"], "COPY_TRADER_VALIDATED_RUNTIME_BLOCKED")
        self.assertEqual(review["primaryAction"], "CONFIGURE_ISOLATED_CLOB_RUNTIME")
        self.assertIn("private_key_env_missing", review["iterationPlan"]["nextAction"])


if __name__ == "__main__":
    unittest.main()
