import json
import tempfile
import unittest
from pathlib import Path

from tools.usdjpy_strategy_lab.data_loader import sample_runtime
from tools.usdjpy_strategy_lab.data_loader import focus_runtime_snapshot
from tools.usdjpy_strategy_lab.policy_builder import build_usdjpy_policy
from tools.usdjpy_strategy_lab.dry_run_bridge import build_dry_run_decision
from tools.usdjpy_strategy_lab.schema import FOCUS_SYMBOL, ENTRY_STANDARD, ENTRY_OPPORTUNITY, ENTRY_BLOCKED
from tools.usdjpy_strategy_lab.strategy_catalog import build_strategy_catalog
from tools.usdjpy_strategy_lab.strategy_signals import build_candidate_signals
from tools.usdjpy_strategy_lab.strategy_scoreboard import build_strategy_scoreboard
from tools.usdjpy_strategy_lab.risk_governor import build_risk_check
from tools.usdjpy_strategy_lab.backtest_plan_builder import build_backtest_plan
from tools.usdjpy_strategy_lab.backtest_importer import import_backtest_results, load_imported_backtests
from tools.usdjpy_strategy_lab.telegram_text import policy_to_chinese_text


class USDJPYStrategyLabTests(unittest.TestCase):
    def test_sample_builds_usdjpy_only_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            policy = build_usdjpy_policy(runtime, write=True)
            self.assertEqual(policy["symbol"], FOCUS_SYMBOL)
            self.assertEqual(policy["allowedSymbols"], [FOCUS_SYMBOL])
            self.assertTrue(policy["policyConstraints"]["rsiLiveRoutePreserved"])
            self.assertIn("strategyCatalogVersion", policy)
            self.assertTrue(policy["focusOnly"])
            self.assertGreaterEqual(policy["standardEntryCount"] + policy["opportunityEntryCount"], 1)
            self.assertGreaterEqual(policy["evidence"]["candidateSignalCount"], 1)
            output = runtime / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json"
            self.assertTrue(output.exists())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["symbol"], FOCUS_SYMBOL)
            regimes = {item["regime"] for item in policy["strategies"]}
            self.assertNotIn("0.6", regimes)
            self.assertIn("RANGE", regimes)

    def test_non_focus_rows_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            ledger = runtime / "ShadowCandidateOutcomeLedger.csv"
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write("EURUSDc,RSI_Reversal,LONG,RANGE,M15,100,100,1\n")
            scoreboard = build_strategy_scoreboard(runtime)
            self.assertTrue(all(route["symbol"] == FOCUS_SYMBOL for route in scoreboard["routes"]))
            text = policy_to_chinese_text(build_usdjpy_policy(runtime))
            self.assertIn("仅 USDJPYc", text)
            self.assertIn("其他品种：已忽略", text)

    def test_missing_core_evidence_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            # Only sample ledger, no runtime snapshot and no fastlane quality.
            (runtime / "ShadowCandidateOutcomeLedger.csv").write_text(
                "symbol,strategy,direction,regime,timeframe,pips,mfePips,maePips\n"
                "USDJPYc,RSI_Reversal,LONG,TREND_EXP_DOWN,M15,3,5,1\n"
                "USDJPYc,RSI_Reversal,LONG,TREND_EXP_DOWN,M15,2,4,1\n"
                "USDJPYc,RSI_Reversal,LONG,TREND_EXP_DOWN,M15,2,4,1\n"
                "USDJPYc,RSI_Reversal,LONG,TREND_EXP_DOWN,M15,2,4,1\n"
                "USDJPYc,RSI_Reversal,LONG,TREND_EXP_DOWN,M15,2,4,1\n",
                encoding="utf-8",
            )
            policy = build_usdjpy_policy(runtime)
            self.assertEqual(policy["standardEntryCount"], 0)
            self.assertEqual(policy["opportunityEntryCount"], 0)
            self.assertGreater(policy["blockedCount"], 0)
            self.assertTrue(any("缺少 USDJPY 运行快照" in "；".join(item["reasons"]) for item in policy["strategies"]))

    def test_non_focus_runtime_snapshot_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json").unlink()
            (runtime / "QuantGod_Dashboard.json").write_text(
                json.dumps({"symbol": "EURUSDc", "fallback": False, "runtimeFresh": True}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertIsNone(focus_runtime_snapshot(runtime))
            policy = build_usdjpy_policy(runtime)
            self.assertEqual(policy["standardEntryCount"], 0)
            self.assertEqual(policy["opportunityEntryCount"], 0)

    def test_dry_run_writes_no_execution_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            decision = build_dry_run_decision(runtime, write=True)
            self.assertIn(decision["entryMode"], {ENTRY_STANDARD, ENTRY_OPPORTUNITY, ENTRY_BLOCKED})
            self.assertFalse(decision["safety"]["orderSendAllowed"])
            self.assertTrue((runtime / "adaptive" / "QuantGod_USDJPYEADryRunDecision.json").exists())

    def test_strategy_factory_catalog_and_signals_are_shadow_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            catalog = build_strategy_catalog()
            keys = {item["key"] for item in catalog["catalog"]}
            self.assertIn("USDJPY_TOKYO_RANGE_BREAKOUT", keys)
            self.assertIn("USDJPY_NIGHT_REVERSION_SAFE", keys)
            self.assertIn("USDJPY_H4_TREND_PULLBACK", keys)
            self.assertTrue(all(item["shadowTradingOnly"] for item in catalog["catalog"]))
            self.assertTrue(all(item["orderSendAllowed"] is False for item in catalog["catalog"]))
            signals = build_candidate_signals(runtime, limit=10)
            self.assertGreaterEqual(signals["count"], 3)
            self.assertTrue(all(signal["strategy"].startswith("USDJPY_") for signal in signals["signals"]))

    def test_backtest_plan_and_risk_check_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            plan = build_backtest_plan(runtime)
            self.assertEqual(len(plan["plans"]), 3)
            self.assertTrue(all(item["dryRunOnly"] for item in plan["plans"]))
            risk = build_risk_check(runtime)
            self.assertEqual(risk["status"], "PASS")
            self.assertFalse(risk["safety"]["orderSendAllowed"])

    def test_import_backtest_results_are_usdjpy_only_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            source = runtime / "tester_results.csv"
            source.write_text(
                "symbol,strategy,timeframe,trades,profitFactor,winRate,netProfit,maxDrawdown\n"
                "USDJPYc,USDJPY_TOKYO_RANGE_BREAKOUT,M15,86,1.26,54.2,18.5,7.1\n"
                "EURUSDc,USDJPY_TOKYO_RANGE_BREAKOUT,M15,90,2.0,60,22,5\n"
                "USDJPYc,UNKNOWN,M15,10,1.0,50,0,1\n",
                encoding="utf-8",
            )
            result = import_backtest_results(runtime, source)
            self.assertTrue(result["ok"])
            self.assertEqual(result["acceptedRows"], 1)
            self.assertFalse(result["imports"][0]["safety"]["orderSendAllowed"])
            self.assertEqual(result["imports"][0]["strategy"], "USDJPY_TOKYO_RANGE_BREAKOUT")
            imported = load_imported_backtests(runtime)
            self.assertEqual(imported["count"], 1)
            self.assertEqual(imported["imports"][0]["status"], "PROMOTABLE")


if __name__ == "__main__":
    unittest.main()
