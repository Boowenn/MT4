from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.autonomous_lifecycle.cent_account_rules import cent_account_config
from tools.autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
from tools.autonomous_lifecycle.mt5_shadow_lane import build_mt5_shadow_lane
from tools.autonomous_lifecycle.polymarket_shadow_lane import build_polymarket_shadow_lane
from tools.daily_autopilot_v2.orchestrator import run_daily_autopilot_cycle
from tools.daily_autopilot_v2.report import build_daily_autopilot_v2
from tools.usdjpy_strategy_lab.schema import DEFAULT_STRATEGIES
from tools.usdjpy_walk_forward.selector import sample_walk_forward_runtime


class AutonomousLifecycleTests(unittest.TestCase):
    def test_builds_three_lane_lifecycle_without_trade_rights(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            sample_walk_forward_runtime(runtime, overwrite=True)

            payload = build_autonomous_lifecycle(runtime, write=True)

            self.assertEqual(payload["symbol"], "USDJPYc")
            self.assertEqual(payload["lanes"]["live"]["strategy"], "RSI_Reversal")
            self.assertEqual(payload["lanes"]["live"]["direction"], "LONG")
            self.assertFalse(payload["safety"]["orderSendAllowed"])
            self.assertFalse(payload["safety"]["liveMutationAllowed"])
            self.assertFalse(payload["safety"]["polymarketRealMoneyAllowed"])
            self.assertIn("mt5Shadow", payload["lanes"])
            self.assertIn("polymarketShadow", payload["lanes"])
            self.assertTrue((runtime / "agent" / "QuantGod_AutonomousLifecycle.json").exists())
            self.assertTrue((runtime / "agent" / "QuantGod_MT5ShadowStrategyRanking.json").exists())
            self.assertTrue((runtime / "agent" / "QuantGod_PolymarketShadowLane.json").exists())

    def test_mt5_shadow_lane_keeps_all_default_strategies_in_simulation_pool(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)

            payload = build_mt5_shadow_lane(runtime)

            self.assertEqual(payload["lane"], "MT5_SHADOW")
            self.assertFalse(payload["safety"]["liveEligible"])
            self.assertEqual(set(payload["strategyPool"]), set(DEFAULT_STRATEGIES))
            route_strategies = {row["strategy"] for row in payload["routes"]}
            self.assertTrue(set(DEFAULT_STRATEGIES).issubset(route_strategies))

    def test_polymarket_lane_is_never_real_money(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)

            payload = build_polymarket_shadow_lane(runtime)

            self.assertEqual(payload["lane"], "POLYMARKET_SHADOW")
            self.assertFalse(payload["safety"]["walletIntegrationAllowed"])
            self.assertFalse(payload["safety"]["polymarketRealMoneyAllowed"])
            self.assertFalse(payload["safety"]["polymarketOrderAllowed"])

    def test_cent_account_config_caps_max_lot_at_two(self) -> None:
        cfg = cent_account_config()

        self.assertEqual(cfg["accountMode"], "cent")
        self.assertLessEqual(cfg["maxLot"], 2.0)
        self.assertTrue(cfg["centAccountAcceleration"])

    def test_daily_autopilot_v2_summarizes_three_lanes_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            sample_walk_forward_runtime(runtime, overwrite=True)

            payload = build_daily_autopilot_v2(runtime, write=True)

            self.assertEqual(payload["symbol"], "USDJPYc")
            self.assertIn("morningPlan", payload)
            self.assertIn("eveningReview", payload)
            self.assertIn("dailyTodo", payload)
            self.assertIn("dailyReview", payload)
            self.assertIn("nextPhaseTodos", payload)
            self.assertTrue(payload["dailyTodo"]["completedByAgent"])
            self.assertTrue(payload["dailyReview"]["completedByAgent"])
            self.assertTrue(payload["dailyTodo"]["requiresAutonomousGovernance"])
            self.assertEqual(payload["agentVersion"], "v2.6")
            self.assertIn("strategyJsonTodo", payload["dailyTodo"])
            self.assertIn("gaEvolutionTodo", payload["dailyTodo"])
            self.assertIn("telegramGatewayTodo", payload["dailyTodo"])
            self.assertTrue(payload["nextPhaseTodos"]["completedByAgent"])
            self.assertEqual(payload["nextPhaseTodos"]["strategyJsonTodo"]["status"], "COMPLETED_BY_AGENT")
            self.assertEqual(payload["nextPhaseTodos"]["gaEvolutionTodo"]["status"], "COMPLETED_BY_AGENT")
            self.assertEqual(payload["nextPhaseTodos"]["telegramGatewayTodo"]["status"], "COMPLETED_BY_AGENT")
            self.assertNotIn("requiresManualReview", payload["dailyTodo"])
            self.assertNotIn("requiresManualReview", payload["dailyReview"])
            self.assertIn("mt5Shadow", payload["lanes"])
            self.assertIn("polymarketShadow", payload["lanes"])
            self.assertFalse(payload["safety"]["orderSendAllowed"])
            self.assertFalse(payload["safety"]["polymarketRealMoneyAllowed"])
            self.assertTrue((runtime / "agent" / "QuantGod_DailyAutopilotV2.json").exists())

    def test_daily_autopilot_v2_runs_agent_cycle_and_records_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            repo_root = Path(__file__).resolve().parents[1]

            run = run_daily_autopilot_cycle(
                runtime,
                repo_root=repo_root,
                write=True,
                bootstrap_samples=True,
            )
            payload = build_daily_autopilot_v2(runtime, repo_root=repo_root, write=True)

            self.assertTrue(run["ok"])
            self.assertEqual(run["status"], "COMPLETED_BY_AGENT")
            self.assertGreaterEqual(run["completedStepCount"], 7)
            self.assertEqual(run["failedStepCount"], 0)
            self.assertIn("orchestrationRun", payload)
            self.assertEqual(payload["orchestrationRun"]["status"], "COMPLETED_BY_AGENT")
            self.assertTrue((runtime / "agent" / "QuantGod_DailyAutopilotV2RunLatest.json").exists())
            self.assertTrue((runtime / "agent" / "QuantGod_DailyAutopilotV2RunLedger.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
