import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_daily_autopilot.py"
SPEC = importlib.util.spec_from_file_location("run_daily_autopilot", MODULE_PATH)
autopilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(autopilot)

REVIEW_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_daily_review.py"
REVIEW_SPEC = importlib.util.spec_from_file_location("build_daily_review", REVIEW_MODULE_PATH)
daily_review = importlib.util.module_from_spec(REVIEW_SPEC)
assert REVIEW_SPEC.loader is not None
REVIEW_SPEC.loader.exec_module(daily_review)

POLY_GOV_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_polymarket_auto_governance.py"
TOOLS_DIR = str(POLY_GOV_MODULE_PATH.parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
POLY_GOV_SPEC = importlib.util.spec_from_file_location("build_polymarket_auto_governance", POLY_GOV_MODULE_PATH)
poly_governance = importlib.util.module_from_spec(POLY_GOV_SPEC)
assert POLY_GOV_SPEC.loader is not None
POLY_GOV_SPEC.loader.exec_module(poly_governance)


class DailyAutopilotTests(unittest.TestCase):
    def test_run_step_passes_env_overrides_without_order_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = autopilot.run_step(
                "env_probe",
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['QG_RUNTIME_DIR']); print(os.environ['QG_MAC_RUNTIME_SOURCE'])",
                ],
                tmp_path,
                env_overrides={
                    "QG_RUNTIME_DIR": str(tmp_path / "runtime"),
                    "QG_MAC_RUNTIME_SOURCE": "local",
                },
            )

            self.assertEqual(result["status"], "OK")
            self.assertIn(str(tmp_path / "runtime"), result["stdoutTail"])
            self.assertIn("local", result["stdoutTail"])

    def test_mac_wrappers_are_valid_bash(self):
        repo_root = MODULE_PATH.parents[1]
        env = {**os.environ, "QG_MAC_RUNTIME_SOURCE": "local"}
        result = subprocess.run(
            ["bash", "-n", "tools/run_mac_daily_autopilot.sh", "tools/run_mac_polymarket_readonly_cycle.sh"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mt5_permission_log_is_not_triage_when_current_dashboard_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            mt5_root = Path(tmp) / "MetaTrader 5"
            runtime_dir = mt5_root / "MQL5" / "Files"
            logs_dir = mt5_root / "MQL5" / "Logs"
            runtime_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            (logs_dir / "20260501.log").write_text(
                "pilot order failed: retcode=10017 comment=Trade disabled\n"
                "trading has been disabled - investor mode\n",
                encoding="utf-8",
            )
            (runtime_dir / "QuantGod_Dashboard.json").write_text(json.dumps({
                "runtime": {
                    "tradeStatus": "READY",
                    "tradeAllowed": True,
                    "terminalTradeAllowed": True,
                    "programTradeAllowed": True,
                    "accountTradeAllowed": True,
                    "accountExpertTradeAllowed": True,
                    "focusSymbolTradeAllowed": True,
                    "tradePermissionBlocker": "",
                }
            }), encoding="utf-8")

            risk = daily_review.mt5_terminal_risk(runtime_dir, datetime(2026, 5, 1, tzinfo=timezone.utc))

            self.assertGreater(risk["investorModeCount"], 0)
            self.assertGreater(risk["orderSendFailureCount"], 0)
            self.assertTrue(risk["currentTradePermissionRecovered"])
            self.assertFalse(risk["requiresCodexReview"])

    def test_frontend_reads_daily_artifacts_through_api_first(self):
        api_source = (MODULE_PATH.parents[1] / "frontend" / "src" / "services" / "api.js").read_text(encoding="utf-8")

        self.assertIn("fetchJsonFirst(['/api/daily-review', '/QuantGod_DailyReview.json'])", api_source)
        self.assertIn("fetchJsonFirst(['/api/daily-autopilot', '/QuantGod_DailyAutopilot.json'])", api_source)

    def test_dashboard_server_exposes_daily_readonly_routes(self):
        server_source = (MODULE_PATH.parents[1] / "Dashboard" / "dashboard_server.js").read_text(encoding="utf-8")

        self.assertIn("'/api/daily-review'", server_source)
        self.assertIn("'/api/daily-autopilot'", server_source)
        self.assertIn("dailyReviewName", server_source)

    def test_daily_pnl_negative_is_resolved_when_rsi_sell_side_is_blocked(self):
        daily_pnl = daily_review.close_history_summary([
            {
                "CloseTime": "2026.04.29 09:00",
                "Strategy": "RSI_Reversal",
                "Type": "SELL",
                "NetProfit": "-0.70",
            },
            {
                "CloseTime": "2026.04.29 15:00",
                "Strategy": "RSI_Reversal",
                "Type": "SELL",
                "NetProfit": "-0.55",
            },
        ])
        governance = {
            "routeDecisions": [{
                "key": "RSI_Reversal",
                "sidePolicy": {"sellLiveAllowed": False},
            }]
        }

        self.assertTrue(daily_review.daily_pnl_resolved_by_policy(daily_pnl, governance))

        governance["routeDecisions"][0]["sidePolicy"]["sellLiveAllowed"] = True
        self.assertFalse(daily_review.daily_pnl_resolved_by_policy(daily_pnl, governance))

    def test_daily_pnl_uses_requested_review_day_even_without_trades(self):
        daily_pnl = daily_review.close_history_summary([
            {
                "CloseTime": "2026.04.29 09:00",
                "Strategy": "RSI_Reversal",
                "Type": "SELL",
                "NetProfit": "-0.70",
            }
        ], "2026-04-30")

        self.assertEqual(daily_pnl["date"], "2026-04-30")
        self.assertEqual(daily_pnl["closedTrades"], 0)
        self.assertEqual(daily_pnl["netUSC"], 0)
        self.assertEqual(daily_pnl["byStrategy"], [])

    def test_param_action_queue_marks_window_wait_as_scheduled(self):
        scheduler = {
            "selectedTasks": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "routeKey": "MA_Cross",
                "score": 1.074,
                "resultStatus": "CONFIG_ONLY_WAIT_REPORT",
            }]
        }
        auto_tester = {
            "summary": {"canRunTerminal": False},
            "gate": {"blockers": ["outside_strategy_tester_window"]},
        }

        queue = daily_review.param_action_queue(scheduler, auto_tester, 5)

        self.assertEqual(queue[0]["state"], "WAIT_GUARD")
        self.assertEqual(queue[0]["guardClass"], "WAIT_TESTER_WINDOW")
        self.assertEqual(queue[0]["statusLabel"], "SCHEDULED_TESTER_WINDOW")
        self.assertIn("nextWindowLabel", queue[0])
        self.assertFalse(queue[0]["livePresetMutationAllowed"])

    def test_frontend_renders_scheduled_tester_window_copy(self):
        source = (MODULE_PATH.parents[1] / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")

        self.assertIn("今日已排队", source)
        self.assertIn("SCHEDULED_TESTER_WINDOW", source)
        self.assertIn("paramTodoStatusLabel(row)", source)
        self.assertIn("Polymarket 亏损复盘", source)
        self.assertIn("mt5.value.dailyReview?.polymarket?.dailyReview", source)
        self.assertIn("const mt5ActionQueueItems", source)
        self.assertIn("const polymarketActionQueueItems", source)
        self.assertIn("const todayTodoItems", source)
        self.assertIn("routeLaneMetricText(route, row)", source)
        self.assertIn("后验 ${first(outcome.horizonRows", source)
        self.assertIn("{{ lane.metricText }}", source)
        self.assertIn("...mt5ActionQueueItems.value.slice(0, 3)", source)
        self.assertIn("...polymarketActionQueueItems.value.slice(0, 2)", source)

    def test_mt5_status_cards_do_not_truncate_evidence_text(self):
        source = (MODULE_PATH.parents[1] / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".mt5-radar-board .dense-radar", source)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", source)
        self.assertIn(".page-mt5 .micro-metric span", source)
        self.assertIn(".page-mt5 .trade-metric-grid b", source)
        self.assertIn("overflow-wrap: anywhere;", source)
        self.assertIn("text-overflow: clip;", source)

    def test_polymarket_global_loss_copy_explains_risk_isolation(self):
        state, action, risk, next_test = poly_governance.classify_decision(
            92.0,
            False,
            ["SIM_SAMPLE_LT_MIN"],
            ["GLOBAL_LOSS_QUARANTINE", "EXECUTED_PF_BELOW_1"],
            type("Args", (), {"demote_score": 35.0, "keep_shadow_score": 58.0, "promotion_review_score": 78.0})(),
        )

        self.assertEqual(state, "QUARANTINE_NO_PROMOTION")
        self.assertEqual(risk, "high")
        self.assertIn("进入隔离", action)
        self.assertIn("风险隔离", next_test)
        self.assertIn("复盘亏损来源", next_test)
        self.assertNotIn("修复亏损来源", next_test)

    def test_polymarket_daily_review_builds_loss_todos(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "QuantGod_PolymarketResearch.json").write_text(json.dumps({
                "summary": {
                    "executed": {"closed": 24, "winRatePct": 4.17, "profitFactor": 0.0145, "realizedPnl": -9.9841},
                    "shadow": {"closed": 383, "winRatePct": 36.29, "profitFactor": 0.7055, "realizedPnl": -159.3266},
                },
                "recentJournalGroups": [{
                    "experimentKey": "sports_edge_filter_shadow_v1",
                    "marketScope": "sports",
                    "entryStatus": "live_blocked_shadow",
                    "signalSource": "autonomous",
                    "closed": 62,
                    "wins": 12,
                    "losses": 50,
                    "winRatePct": 19.35,
                    "profitFactor": 0.3956,
                    "realizedPnl": -58.0649,
                    "avgPnl": -0.9365,
                }],
                "recentExperimentGroups": [{
                    "experimentKey": "sports_edge_filter_shadow_v1",
                    "closed": 62,
                    "wins": 12,
                    "losses": 50,
                    "winRatePct": 19.35,
                    "profitFactor": 0.3956,
                    "realizedPnl": -58.0649,
                    "avgPnl": -0.9365,
                }],
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketAutoGovernance.json").write_text(json.dumps({
                "globalBlockers": ["GLOBAL_LOSS_QUARANTINE", "EXECUTED_PF_BELOW_1"],
                "summary": {"quarantine": 46, "autoCanaryEligible": 0},
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketDryRunOutcomeWatcher.json").write_text(json.dumps({
                "summary": {"wouldExit": 4, "stopLoss": 2, "trailingExit": 2},
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketExecutionGate.json").write_text(json.dumps({
                "summary": {"canBet": 0, "blocked": 24},
            }), encoding="utf-8")

            review = daily_review.polymarket_daily_review(runtime)

            self.assertTrue(review["summary"]["lossQuarantine"])
            self.assertEqual(review["summary"]["todoCount"], 4)
            self.assertEqual(review["actionQueue"][0]["type"], "POLY_LOSS_SOURCE_REVIEW")
            self.assertFalse(review["safety"]["walletWriteAllowed"])
            self.assertEqual(review["topLossSources"][0]["experimentKey"], "sports_edge_filter_shadow_v1")

    def test_daily_review_ledger_schema_upgrade_preserves_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "review.csv"
            ledger.write_text("A,B\nold_a,old_b\nnew_a,new_b,new_c\n", encoding="utf-8")

            daily_review.append_csv(ledger, {"A": "tail_a", "B": "tail_b", "C": "tail_c"}, ["A", "B", "C"])
            rows = list(__import__("csv").DictReader(ledger.read_text(encoding="utf-8").splitlines()))

            self.assertEqual(rows[0], {"A": "old_a", "B": "old_b", "C": ""})
            self.assertEqual(rows[1], {"A": "new_a", "B": "new_b", "C": "new_c"})
            self.assertEqual(rows[2], {"A": "tail_a", "B": "tail_b", "C": "tail_c"})

    def test_autopilot_ledger_schema_upgrade_preserves_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "autopilot.csv"
            ledger.write_text("A,B\nold_a,old_b\nnew_a,new_b,new_c\n", encoding="utf-8")

            autopilot.append_csv(ledger, {"A": "tail_a", "B": "tail_b", "C": "tail_c"}, ["A", "B", "C"])
            rows = list(__import__("csv").DictReader(ledger.read_text(encoding="utf-8").splitlines()))

            self.assertEqual(rows[0], {"A": "old_a", "B": "old_b", "C": ""})
            self.assertEqual(rows[1], {"A": "new_a", "B": "new_b", "C": "new_c"})
            self.assertEqual(rows[2], {"A": "tail_a", "B": "tail_b", "C": "tail_c"})


if __name__ == "__main__":
    unittest.main()
