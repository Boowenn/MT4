import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tools.usdjpy_strategy_lab.data_loader import sample_runtime
from tools.usdjpy_strategy_lab.data_loader import focus_runtime_snapshot
from tools.usdjpy_strategy_lab.policy_builder import _build_spread_gate, build_usdjpy_policy
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
            self.assertEqual(policy["accountLanePolicy"]["usdAccountOpportunityEntryMode"], "PAPER_MIRROR_ONLY")
            self.assertTrue(policy["accountLanePolicy"]["polymarketLogicUnchanged"])
            self.assertGreaterEqual(policy["standardEntryCount"] + policy["opportunityEntryCount"], 1)
            self.assertGreaterEqual(policy["evidence"]["candidateSignalCount"], 1)
            output = runtime / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json"
            self.assertTrue(output.exists())
            self.assertFalse((runtime / "adaptive" / "QuantGod_AutoExecutionPolicy.json").exists())
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

    def test_live_dashboard_snapshot_can_back_risk_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            dashboard = runtime / "QuantGod_Dashboard.json"
            dashboard.write_text(
                json.dumps({
                    "timestamp": "2026.05.06 01:40:21",
                    "watchlist": FOCUS_SYMBOL,
                    "runtime": {
                        "tradeStatus": "READY",
                        "executionEnabled": True,
                        "readOnlyMode": False,
                        "tickAgeSeconds": 0,
                    },
                    "market": {"bid": 157.762, "ask": 157.788, "spread": 2.6},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            snapshot = focus_runtime_snapshot(runtime)
            self.assertIsNotNone(snapshot)
            self.assertLess(snapshot["runtimeAgeSeconds"], 30)
            risk = build_risk_check(runtime)
            self.assertEqual(risk["status"], "PASS")

    def test_minute_old_dashboard_snapshot_stays_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            dashboard = runtime / "QuantGod_Dashboard.json"
            dashboard.write_text(
                json.dumps({
                    "timestamp": "2026.05.06 01:40:21",
                    "watchlist": FOCUS_SYMBOL,
                    "runtime": {
                        "tradeStatus": "READY",
                        "executionEnabled": True,
                        "readOnlyMode": False,
                        "tickAgeSeconds": 0,
                    },
                    "market": {"bid": 157.762, "ask": 157.788, "spread": 2.6},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            old_time = time.time() - 60
            os.utime(dashboard, (old_time, old_time))
            snapshot = focus_runtime_snapshot(runtime)
            self.assertIsNotNone(snapshot)
            self.assertGreater(snapshot["runtimeAgeSeconds"], 30)
            self.assertTrue(snapshot["runtimeFresh"])
            risk = build_risk_check(runtime)
            self.assertEqual(risk["status"], "PASS")

    def test_fastlane_fast_state_is_accepted_by_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            quality_path = runtime / "quality" / "QuantGod_MT5FastLaneQuality.json"
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["quality"] = "FAST"
            quality["symbols"][0]["quality"] = "FAST"
            quality_path.write_text(json.dumps(quality, ensure_ascii=False), encoding="utf-8")
            policy = build_usdjpy_policy(runtime)
            self.assertTrue(policy["evidence"]["fastlaneOk"])
            self.assertFalse(any("快通道质量未通过：FAST" in "；".join(item["reasons"]) for item in policy["strategies"]))

    def test_dashboard_fastlane_fallback_is_degraded_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "quality" / "QuantGod_MT5FastLaneQuality.json").unlink()
            policy = build_usdjpy_policy(runtime)
            self.assertTrue(policy["evidence"]["fastlaneOk"])
            self.assertTrue(any("快通道质量降级可用" in "；".join(item["reasons"]) for item in policy["strategies"]))

    def test_empty_fastlane_exporter_falls_back_to_fresh_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "QuantGod_Dashboard.json").write_text(
                json.dumps({
                    "watchlist": FOCUS_SYMBOL,
                    "runtime": {"tradeStatus": "READY", "executionEnabled": True, "readOnlyMode": False, "tickAgeSeconds": 0},
                    "market": {"bid": 155.92, "ask": 155.95, "spread": 3.0},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            quality_path = runtime / "quality" / "QuantGod_MT5FastLaneQuality.json"
            quality_path.write_text(
                json.dumps({
                    "schema": "quantgod.mt5.fastlane.quality.v1",
                    "heartbeatFound": False,
                    "quality": "DEGRADED",
                    "symbols": [{"symbol": FOCUS_SYMBOL, "quality": "DEGRADED", "tickRows": 0, "tickAgeSeconds": None, "indicatorAgeSeconds": None}],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            policy = build_usdjpy_policy(runtime)
            self.assertTrue(policy["evidence"]["fastlaneOk"])
            self.assertTrue(any("HFM EA Dashboard 新鲜快照" in "；".join(item["reasons"]) for item in policy["strategies"]))

    def test_stale_degraded_fastlane_exporter_falls_back_to_fresh_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "QuantGod_Dashboard.json").write_text(
                json.dumps({
                    "watchlist": FOCUS_SYMBOL,
                    "runtime": {"tradeStatus": "READY", "executionEnabled": True, "readOnlyMode": False, "tickAgeSeconds": 2},
                    "market": {"bid": 155.92, "ask": 155.95, "spread": 3.0},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            quality_path = runtime / "quality" / "QuantGod_MT5FastLaneQuality.json"
            quality_path.write_text(
                json.dumps({
                    "schema": "quantgod.mt5.fastlane.quality.v1",
                    "heartbeatFound": True,
                    "heartbeatFresh": False,
                    "heartbeatAgeSeconds": 120,
                    "heartbeatFreshLimitSeconds": 90,
                    "quality": "DEGRADED",
                    "symbols": [{
                        "symbol": FOCUS_SYMBOL,
                        "quality": "DEGRADED",
                        "tickRows": 3,
                        "tickAgeSeconds": 2,
                        "indicatorAgeSeconds": 39,
                        "checks": [
                            {"name": "tick_fast_lane", "passed": False, "reason": "tick年龄=9秒"},
                            {"name": "indicator_lane", "passed": False},
                            {"name": "tick_rows", "passed": True},
                            {"name": "spread", "passed": True},
                        ],
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            policy = build_usdjpy_policy(runtime)
            self.assertTrue(policy["evidence"]["fastlaneOk"])
            self.assertTrue(any("HFM EA Dashboard 新鲜快照" in "；".join(item["reasons"]) for item in policy["strategies"]))

    def test_entry_trigger_decisions_shape_is_accepted_by_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            trigger_path = runtime / "adaptive" / "QuantGod_EntryTriggerPlan.json"
            trigger_path.write_text(
                json.dumps({
                    "schema": "quantgod.entry_trigger_lab.v1",
                    "decisions": [
                        {"symbol": FOCUS_SYMBOL, "direction": "LONG", "state": "WAIT_TRIGGER_CONFIRMATION", "score": 0.88, "reasons": []},
                        {"symbol": FOCUS_SYMBOL, "direction": "SHORT", "state": "BLOCKED", "score": 0.2, "reasons": ["方向近期负期望"]},
                    ],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")
            self.assertNotIn("缺少 USDJPY 入场触发计划", "；".join(rsi_long["reasons"]))
            self.assertIn(rsi_long["entryMode"], {ENTRY_STANDARD, ENTRY_OPPORTUNITY})
            self.assertEqual(rsi_long["hardGateStatus"], "PASS")
            self.assertGreaterEqual(rsi_long["signalQuorum"], 2)

    def test_soft_stale_runtime_downgrades_instead_of_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            snapshot_path = runtime / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json"
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["runtimeAgeSeconds"] = 60
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")

            self.assertEqual(policy["evidence"]["runtimeFreshnessTier"], "SOFT_STALE")
            self.assertEqual(rsi_long["entryMode"], ENTRY_OPPORTUNITY)
            self.assertTrue(rsi_long["allowed"])
            self.assertEqual(rsi_long["entryStrictness"], "RUNTIME_SOFT_STALE_STAGE_DOWNGRADED")

    def test_hard_stale_runtime_blocks_even_when_signals_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            snapshot_path = runtime / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json"
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["runtimeAgeSeconds"] = 120
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")

            self.assertEqual(policy["evidence"]["runtimeFreshnessTier"], "HARD_STALE")
            self.assertEqual(rsi_long["hardGateStatus"], "BLOCKED")
            self.assertEqual(rsi_long["entryMode"], ENTRY_BLOCKED)
            self.assertFalse(rsi_long["allowed"])

    def test_missing_trigger_needs_rsi_diagnostic_before_opportunity_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "adaptive" / "QuantGod_EntryTriggerPlan.json").unlink()

            missing_policy = build_usdjpy_policy(runtime)
            missing_rsi = next(item for item in missing_policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")
            self.assertEqual(missing_rsi["entryMode"], "WATCH_ONLY")
            self.assertFalse(missing_rsi["allowed"])
            self.assertEqual(missing_rsi["entryStrictness"], "WATCH_ONLY_TRIGGER_MISSING_NO_RSI_DIAGNOSTIC")

            (runtime / "QuantGod_USDJPYRsiEntryDiagnostics.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.mt5.usdjpy_rsi_entry_diagnostics.v1",
                        "symbol": "USDJPYc",
                        "strategy": "RSI_Reversal",
                        "direction": "LONG",
                        "state": "READY_BUY_SIGNAL",
                        "guards": {"spreadAllowed": True, "sessionOpen": True},
                        "rsi": {"signalReady": True, "signalDirection": "BUY"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ready_policy = build_usdjpy_policy(runtime)
            ready_rsi = next(item for item in ready_policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")
            self.assertEqual(ready_rsi["entryMode"], ENTRY_OPPORTUNITY)
            self.assertTrue(ready_rsi["allowed"])
            self.assertTrue(ready_rsi["signalComponents"]["triggerSignal"])

    def test_two_of_three_quorum_allows_opportunity_without_extra_indicator_and(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "adaptive" / "QuantGod_EntryTriggerPlan.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.entry_trigger_lab.v1",
                        "decisions": [
                            {
                                "symbol": FOCUS_SYMBOL,
                                "direction": "LONG",
                                "state": "BLOCKED",
                                "score": 0.35,
                                "reasons": ["战术确认暂缺，但不是硬风控"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")

            self.assertEqual(rsi_long["signalQuorum"], 2)
            self.assertEqual(rsi_long["entryMode"], ENTRY_OPPORTUNITY)
            self.assertTrue(rsi_long["allowed"])

    def test_soft_wide_spread_downgrades_cent_opportunity_instead_of_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "QuantGod_USDJPYRsiEntryDiagnostics.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.mt5.usdjpy_rsi_entry_diagnostics.v1",
                        "symbol": "USDJPYc",
                        "strategy": "RSI_Reversal",
                        "direction": "LONG",
                        "state": "SPREAD_BLOCK",
                        "summary": "点差超过 EA 入场限制，等待点差回落。",
                        "guards": {
                            "sessionOpen": True,
                            "spreadAllowed": False,
                            "spreadPips": 2.3,
                            "maxSpreadPips": 2.2,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")

            self.assertEqual(policy["spreadGate"]["tier"], "SOFT_WIDE")
            self.assertEqual(policy["accountLanePolicy"]["softWideSpreadUsdMode"], "PAPER_MIRROR_ONLY")
            self.assertEqual(rsi_long["hardGateStatus"], "PASS")
            self.assertEqual(rsi_long["entryMode"], ENTRY_OPPORTUNITY)
            self.assertTrue(rsi_long["allowed"])
            self.assertLessEqual(rsi_long["recommendedLot"], 0.10)
            self.assertIn("点差轻微偏宽", "；".join(rsi_long["reasons"]))

    def test_hard_wide_spread_still_blocks_all_live_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "QuantGod_USDJPYRsiEntryDiagnostics.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.mt5.usdjpy_rsi_entry_diagnostics.v1",
                        "symbol": "USDJPYc",
                        "strategy": "RSI_Reversal",
                        "direction": "LONG",
                        "state": "SPREAD_BLOCK",
                        "guards": {
                            "sessionOpen": True,
                            "spreadAllowed": False,
                            "spreadPips": 3.1,
                            "maxSpreadPips": 2.2,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            policy = build_usdjpy_policy(runtime)
            rsi_long = next(item for item in policy["strategies"] if item["strategy"] == "RSI_Reversal" and item["direction"] == "LONG")

            self.assertEqual(policy["spreadGate"]["tier"], "HARD_WIDE")
            self.assertTrue(policy["spreadGate"]["hardBlock"])
            self.assertEqual(rsi_long["hardGateStatus"], "BLOCKED")
            self.assertEqual(rsi_long["entryMode"], ENTRY_BLOCKED)
            self.assertFalse(rsi_long["allowed"])

    def test_missing_spread_gate_blocks_when_no_reliable_spread_exists(self):
        spread_gate = _build_spread_gate({}, {})

        self.assertEqual(spread_gate["tier"], "UNKNOWN")
        self.assertTrue(spread_gate["hardBlock"])
        self.assertEqual(spread_gate["action"], "BLOCK")

    def test_live_rsi_buy_uses_direction_sltp_when_shadow_pool_blocks_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            (runtime / "adaptive" / "QuantGod_DynamicSLTPCalibration.json").unlink()
            (runtime / "adaptive" / "QuantGod_DynamicSLTPPlan.json").write_text(
                json.dumps({
                    "schema": "quantgod.adaptive_policy.v1",
                    "dynamicSltpPlans": [{
                        "symbol": FOCUS_SYMBOL,
                        "direction": "LONG",
                        "riskMode": "保守",
                        "initialStop": {"value": 3.2},
                        "targets": [{"value": 4.8}, {"value": 6.1}],
                        "trailing": {"breakevenAtR": 0.9, "protectAtR": 1.4},
                        "timeStop": {"m15Bars": 6},
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            (runtime / "adaptive" / "QuantGod_EntryTriggerPlan.json").write_text(
                json.dumps({
                    "schema": "quantgod.entry_trigger_lab.v1",
                    "decisions": [{
                        "symbol": FOCUS_SYMBOL,
                        "direction": "LONG",
                        "state": "BLOCKED",
                        "score": 0.88,
                        "reasons": ["影子样本不足或近期表现弱，样本数=105"],
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            policy = build_usdjpy_policy(runtime)
            self.assertIsNotNone(policy["topLiveEligiblePolicy"])
            self.assertEqual(policy["topLiveEligiblePolicy"]["strategy"], "RSI_Reversal")
            self.assertEqual(policy["topLiveEligiblePolicy"]["direction"], "LONG")
            self.assertIn(policy["topLiveEligiblePolicy"]["entryMode"], {ENTRY_STANDARD, ENTRY_OPPORTUNITY})
            self.assertTrue(any("方向级计划可用" in reason for reason in policy["topLiveEligiblePolicy"]["reasons"]))

    def test_shadow_top_policy_cannot_override_rsi_buy_live_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            sample_runtime(runtime, overwrite=True)
            ledger = runtime / "ShadowCandidateOutcomeLedger.csv"
            with ledger.open("a", encoding="utf-8") as handle:
                for idx in range(8):
                    handle.write(f"USDJPYc,MA_Cross,LONG,TREND_EXP_UP,M15,{8 + idx * 0.1:.1f},10.0,1.0\n")
            sltp_path = runtime / "adaptive" / "QuantGod_DynamicSLTPCalibration.json"
            sltp = json.loads(sltp_path.read_text(encoding="utf-8"))
            sltp["plans"].append({
                "symbol": FOCUS_SYMBOL,
                "strategy": "MA_Cross",
                "direction": "LONG",
                "status": "CALIBRATED",
                "initialStopPips": 3.0,
                "target1Pips": 5.0,
            })
            sltp_path.write_text(json.dumps(sltp, ensure_ascii=False), encoding="utf-8")
            policy = build_usdjpy_policy(runtime)
            self.assertEqual(policy["topShadowPolicy"]["strategy"], "MA_Cross")
            self.assertEqual(policy["topLiveEligiblePolicy"]["strategy"], "RSI_Reversal")
            self.assertEqual(policy["topLiveEligiblePolicy"]["direction"], "LONG")
            self.assertEqual(policy["topPolicy"], policy["topLiveEligiblePolicy"])

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
