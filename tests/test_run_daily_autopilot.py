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
TOOLS_DIR = str(MODULE_PATH.parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
SPEC = importlib.util.spec_from_file_location("run_daily_autopilot", MODULE_PATH)
autopilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(autopilot)

REVIEW_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_daily_review.py"
REVIEW_SPEC = importlib.util.spec_from_file_location("build_daily_review", REVIEW_MODULE_PATH)
daily_review = importlib.util.module_from_spec(REVIEW_SPEC)
assert REVIEW_SPEC.loader is not None
REVIEW_SPEC.loader.exec_module(daily_review)

GUARD_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "auto_tester_window_guard.py"
GUARD_SPEC = importlib.util.spec_from_file_location("auto_tester_window_guard", GUARD_MODULE_PATH)
auto_tester_guard = importlib.util.module_from_spec(GUARD_SPEC)
assert GUARD_SPEC.loader is not None
GUARD_SPEC.loader.exec_module(auto_tester_guard)

AUTO_TESTER_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_param_lab_auto_tester_window.py"
AUTO_TESTER_SPEC = importlib.util.spec_from_file_location("run_param_lab_auto_tester_window", AUTO_TESTER_MODULE_PATH)
auto_tester_window = importlib.util.module_from_spec(AUTO_TESTER_SPEC)
assert AUTO_TESTER_SPEC.loader is not None
AUTO_TESTER_SPEC.loader.exec_module(auto_tester_window)

POLY_GOV_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_polymarket_auto_governance.py"
POLY_GOV_SPEC = importlib.util.spec_from_file_location("build_polymarket_auto_governance", POLY_GOV_MODULE_PATH)
poly_governance = importlib.util.module_from_spec(POLY_GOV_SPEC)
assert POLY_GOV_SPEC.loader is not None
POLY_GOV_SPEC.loader.exec_module(poly_governance)

POLY_RESEARCH_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_polymarket_research_bridge.py"
POLY_RESEARCH_SPEC = importlib.util.spec_from_file_location("build_polymarket_research_bridge", POLY_RESEARCH_MODULE_PATH)
poly_research = importlib.util.module_from_spec(POLY_RESEARCH_SPEC)
assert POLY_RESEARCH_SPEC.loader is not None
sys.modules[POLY_RESEARCH_SPEC.name] = poly_research
POLY_RESEARCH_SPEC.loader.exec_module(poly_research)

PARAM_RUN_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_param_lab.py"
PARAM_RUN_SPEC = importlib.util.spec_from_file_location("run_param_lab", PARAM_RUN_MODULE_PATH)
param_runner = importlib.util.module_from_spec(PARAM_RUN_SPEC)
assert PARAM_RUN_SPEC.loader is not None
PARAM_RUN_SPEC.loader.exec_module(param_runner)

PARAM_COLLECT_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "collect_param_lab_results.py"
PARAM_COLLECT_SPEC = importlib.util.spec_from_file_location("collect_param_lab_results", PARAM_COLLECT_MODULE_PATH)
param_collect = importlib.util.module_from_spec(PARAM_COLLECT_SPEC)
assert PARAM_COLLECT_SPEC.loader is not None
PARAM_COLLECT_SPEC.loader.exec_module(param_collect)


class DailyAutopilotTests(unittest.TestCase):
    def test_daily_autopilot_uses_bounded_daily_tester_range(self):
        now = datetime.fromisoformat("2026-05-02T00:25:00+09:00")

        self.assertEqual(autopilot.daily_tester_date_range(now, 2), ("2026.04.30", "2026.05.02"))
        self.assertEqual(autopilot.daily_tester_date_range(now, 99), ("2026.04.18", "2026.05.02"))
        self.assertEqual(autopilot.daily_tester_timeout_seconds(120), 300)
        self.assertEqual(autopilot.daily_tester_timeout_seconds(99999), 3600)

    def test_auto_tester_runner_command_forwards_daily_bounds_and_timeout(self):
        args = type("Args", (), {
            "repo_root": str(MODULE_PATH.parents[1]),
            "runtime_dir": "/tmp/runtime",
            "max_tasks": 1,
            "rank_mode": "route-balanced",
            "login": "186054398",
            "server": "HFMarketsGlobal-Live12",
            "max_live_snapshot_age_minutes": 30,
            "from_date": "2026.04.30",
            "to_date": "2026.05.02",
            "terminal_timeout_seconds": 900,
            "route": [],
            "candidate_id": [],
            "allow_outside_window": False,
        })()

        command = auto_tester_window.command_for_runner(
            args,
            run_terminal=True,
            lock_path=Path("/tmp/runtime/QuantGod_AutoTesterWindow.lock.json"),
            plan_path=Path("/tmp/runtime/QuantGod_AutoTesterWindowExecutorPlan.json"),
            hfm_root=Path("/tmp/isolated_tester"),
        )

        self.assertIn("--from-date", command)
        self.assertIn("2026.04.30", command)
        self.assertIn("--to-date", command)
        self.assertIn("2026.05.02", command)
        self.assertIn("--terminal-timeout-seconds", command)
        self.assertIn("900", command)

    def test_agent_artifacts_turn_missing_html_into_parsed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "QuantGod_TradeJournal.csv").write_text(
                "DealTicket,PositionId,EventType,Side,Symbol,Lots,Price,GrossProfit,Commission,Swap,NetProfit,EventTime,Strategy,Source,Regime,RegimeTimeframe,Comment\n",
                encoding="utf-8",
            )
            (artifact_dir / "QuantGod_CloseHistory.csv").write_text(
                "ExitTicket,PositionId,Type,Symbol,Lots,OpenTime,CloseTime,DurationMinutes,OpenPrice,ClosePrice,GrossProfit,Commission,Swap,NetProfit,Strategy,Source,EntryRegime,ExitRegime,RegimeTimeframe,Comment\n",
                encoding="utf-8",
            )
            (artifact_dir / "QuantGod_Dashboard.json").write_text(
                json.dumps({"runtime": {"tradeStatus": "READY", "executionEnabled": True, "readOnlyMode": False}, "account": {"balance": 10000.0}}),
                encoding="utf-8",
            )

            metrics = param_runner.parse_agent_artifacts(
                artifact_dir,
                {
                    "reportExists": False,
                    "parseStatus": "REPORT_MISSING",
                    "closedTrades": None,
                    "netProfit": None,
                    "profitFactor": None,
                    "winRate": None,
                },
            )

        self.assertTrue(metrics["reportExists"])
        self.assertTrue(metrics["testerEvidenceExists"])
        self.assertEqual(metrics["parseStatus"], "PARSED_AGENT_ARTIFACTS")
        self.assertEqual(metrics["closedTrades"], 0)
        self.assertEqual(metrics["sampleStatus"], "NO_TRADES_IN_TEST_WINDOW")

    def test_collector_reuses_agent_metrics_from_status(self):
        task = {
            "metrics": {
                "reportExists": True,
                "testerEvidenceExists": True,
                "parseStatus": "PARSED_AGENT_ARTIFACTS",
                "closedTrades": 0,
                "netProfit": 0.0,
            }
        }

        metrics = param_collect.reusable_task_metrics(task)
        score, grade, readiness, blockers = param_collect.score_result(metrics, min_trades=10)

        self.assertEqual(metrics["parseStatus"], "PARSED_AGENT_ARTIFACTS")
        self.assertEqual(grade, "C")
        self.assertEqual(readiness, "NEEDS_MORE_EVIDENCE")
        self.assertIn("trades_lt_min", blockers)

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
        self.assertIn("buildDailyTesterBounds", server_source)
        self.assertIn("'--terminal-timeout-seconds'", server_source)
        self.assertIn("'--from-date'", server_source)
        self.assertIn(
            "build_polymarket_research_bridge.py",
            (MODULE_PATH.parents[1] / "tools" / "run_mac_polymarket_readonly_cycle.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "build_polymarket_retune_planner.py",
            (MODULE_PATH.parents[1] / "tools" / "run_mac_polymarket_readonly_cycle.sh").read_text(encoding="utf-8"),
        )

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

    def test_param_action_queue_marks_terminal_nonzero_as_codex_triage(self):
        scheduler = {
            "selectedTasks": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "routeKey": "MA_Cross",
                "score": 1.074,
                "resultStatus": "REPORT_MISSING_AFTER_RUN",
            }]
        }
        auto_tester = {
            "summary": {"canRunTerminal": True},
            "gate": {"blockers": []},
        }
        run_recovery = {
            "candidateDrilldown": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "riskLevel": "red",
                "riskReason": "terminal_nonzero",
                "latestStopReason": "terminal_nonzero",
                "terminalNonzeroCount": 1,
                "terminalExitCodes": [191],
                "failureReasons": {
                    "terminal_exit_nonzero": 1,
                    "report_missing_after_run": 1,
                },
            }]
        }

        queue = daily_review.param_action_queue(scheduler, auto_tester, 5, run_recovery)

        self.assertEqual(queue[0]["state"], "NEEDS_CODEX_TRIAGE")
        self.assertEqual(queue[0]["guardClass"], "RUN_RECOVERY_RED")
        self.assertEqual(queue[0]["statusLabel"], "TERMINAL_EXIT_NONZERO")
        self.assertIn("terminal_exit_191", queue[0]["blockers"])
        self.assertEqual(queue[0]["recovery"]["riskLevel"], "red")
        self.assertFalse(queue[0]["livePresetMutationAllowed"])

    def test_param_action_queue_treats_synced_account_context_as_window_wait(self):
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
        run_recovery = {
            "candidateDrilldown": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "riskLevel": "yellow",
                "riskReason": "account_context_synced_retry_ready",
                "latestStopReason": "account_context_synced_retry_ready",
                "terminalNonzeroCount": 3,
                "terminalExitCodes": [191],
            }]
        }

        queue = daily_review.param_action_queue(scheduler, auto_tester, 5, run_recovery)

        self.assertEqual(queue[0]["state"], "WAIT_GUARD")
        self.assertEqual(queue[0]["guardClass"], "WAIT_TESTER_WINDOW")
        self.assertEqual(queue[0]["statusLabel"], "ACCOUNT_CONTEXT_SYNCED_RETRY_READY")
        self.assertFalse(queue[0]["livePresetMutationAllowed"])

    def test_param_action_queue_marks_latest_parsed_agent_evidence_done(self):
        scheduler = {
            "selectedTasks": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "routeKey": "MA_Cross",
                "score": 1.074,
                "resultStatus": "REPORT_MISSING_AFTER_RUN",
            }]
        }
        auto_tester = {
            "summary": {"canRunTerminal": True},
            "gate": {"blockers": []},
        }
        run_recovery = {
            "candidateDrilldown": [{
                "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                "riskLevel": "green",
                "riskReason": "parsed_latest",
                "latestState": "parsed",
                "latestStopReason": "parsed_latest",
            }]
        }

        queue = daily_review.param_action_queue(scheduler, auto_tester, 5, run_recovery)

        self.assertEqual(queue[0]["state"], "DONE")
        self.assertFalse(queue[0]["livePresetMutationAllowed"])

    def test_daily_tester_budget_suppresses_new_backlog_after_today_run(self):
        now = datetime.fromisoformat("2026-05-02T04:05:00+09:00")
        param_status = {
            "generatedAtIso": "2026-05-01T18:32:59+00:00",
            "summary": {
                "runAttemptedCount": 5,
                "reportParsedCount": 5,
                "agentEvidenceParsedCount": 5,
                "selectedTaskCount": 5,
            },
        }

        completed = daily_review.daily_tester_completed_count(param_status, now, 5)

        self.assertEqual(completed, 5)

    def test_daily_iteration_flags_polymarket_loss_quarantine_for_codex(self):
        poly = {
            "dailyReview": {
                "summary": {
                    "lossQuarantine": True,
                    "executedProfitFactor": 0.0145,
                    "shadowProfitFactor": 0.7055,
                    "quarantineCount": 45,
                },
                "topLossSources": [{
                    "experimentKey": "sports_edge_filter_shadow_v1",
                    "profitFactor": 0.3956,
                    "winRatePct": 19.35,
                    "realizedPnl": -58.0649,
                }],
                "retuneSources": [{
                    "experimentKey": "sports_edge_filter_shadow_v1",
                }],
            }
        }
        iteration = daily_review.daily_iteration_review(
            {"date": "2026-05-01", "closedTrades": 2, "netUSC": 3.54},
            [],
            poly,
            {"requiresCodexReview": False},
            5,
        )
        codex = daily_review.codex_review_queue(
            {"date": "2026-05-01", "closedTrades": 2, "netUSC": 3.54, "requiresReview": False},
            [],
            [],
            {},
            {},
            {},
            {"workerStatus": "OK"},
            {"requiresCodexReview": False},
            iteration,
        )

        self.assertEqual(iteration["status"], "ITERATION_REQUIRED")
        self.assertTrue(iteration["codexFollowupRequired"])
        self.assertTrue(iteration["codeIterationQueue"])
        self.assertTrue(iteration["strategyIterationQueue"])
        self.assertTrue(codex["required"])
        self.assertEqual(codex["reasons"][-1]["code"], "DAILY_ITERATION_ACTIONABLE_FINDINGS")

    def test_completion_report_explains_finished_todos_and_recommendations(self):
        poly = {
            "dailyReview": {
                "summary": {
                    "lossQuarantine": True,
                    "executedProfitFactor": 0.0145,
                    "shadowProfitFactor": 0.7055,
                    "quarantineCount": 45,
                },
                "topLossSources": [{
                    "experimentKey": "sports_edge_filter_shadow_v1",
                    "profitFactor": 0.3956,
                    "winRatePct": 19.35,
                    "realizedPnl": -58.0649,
                }],
            }
        }
        param_status = {
            "tasks": [{
                "candidateId": "BB_Triple_EURUSDc_bb_outer_band_strict_v2",
                "routeKey": "BB_Triple",
                "symbol": "EURUSDc",
                "status": "PARSED_AGENT_ARTIFACTS",
                "score": -7.745,
            }]
        }
        param_results = {
            "results": [{
                "candidateId": "BB_Triple_EURUSDc_bb_outer_band_strict_v2",
                "grade": "C",
                "promotionReadiness": "NEEDS_MORE_EVIDENCE",
                "metrics": {
                    "reportExists": True,
                    "parseStatus": "PARSED_AGENT_ARTIFACTS",
                    "closedTrades": 0,
                    "sampleStatus": "NO_TRADES_IN_TEST_WINDOW",
                },
            }]
        }
        iteration = {"iterationRequired": True}

        report = daily_review.build_completion_report(
            "2026-05-01",
            {"closedTrades": 2, "netUSC": 3.54, "requiresReview": False},
            param_status,
            param_results,
            [{"candidateId": "MA_Cross_EURUSDc_ma_slower_confirmation"}],
            [],
            poly,
            iteration,
        )

        self.assertEqual(report["status"], "ITERATION_REQUIRED")
        self.assertEqual(report["summary"]["testerParsedCount"], 1)
        self.assertEqual(report["summary"]["testerNoTradeCount"], 1)
        self.assertGreaterEqual(report["summary"]["recommendationCount"], 3)
        self.assertIn("不能作为升实盘证据", report["testerReports"][0]["effect"])
        self.assertTrue(any(item["scope"] == "Polymarket" for item in report["recommendations"]))
        self.assertFalse(report["safety"]["orderSendAllowed"])

    def test_daily_closeout_window_keeps_todos_on_same_local_day(self):
        now = datetime.fromisoformat("2026-05-02T00:25:00+09:00")
        plan = daily_review.tester_window_plan(now)

        self.assertTrue(plan["openNow"])
        self.assertTrue(plan["dueToday"])
        self.assertEqual(plan["nextWindowLabel"], "2026-05-02 00:00-02:30 JST")

    def test_auto_tester_guard_allows_daily_closeout_window(self):
        now = datetime.fromisoformat("2026-05-01T15:25:00+00:00")
        window = auto_tester_guard.regular_tester_window(now)

        self.assertTrue(window["ok"])
        self.assertEqual(window["blockers"], [])
        self.assertIn("Daily closeout 00:00-02:30 JST", window["windowLabel"])

    def test_tester_guard_accepts_wine_archive_report_paths(self):
        path = auto_tester_guard.path_from_tester_text(
            r"Z:\Users\bowen\Desktop\Quard\QuantGod\archive\param-lab\runs\run\reports\EURUSDc\x.html"
        )

        self.assertEqual(
            str(path),
            "/Users/bowen/Desktop/Quard/QuantGod/archive/param-lab/runs/run/reports/EURUSDc/x.html",
        )

    def test_auto_tester_retry_allows_fixed_missing_tester_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "run" / "configs" / "x.ini"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "[Common]\nLogin=186054398\nServer=HFMarketsGlobal-Live12\n\n[Tester]\nExpert=QuantGod_MultiStrategy.ex5\n",
                encoding="ascii",
            )
            status_path = root / "run" / "QuantGod_ParamLabStatus.json"
            status_path.write_text(json.dumps({
                "taskStatus": [{
                    "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                    "configPath": str(config_path),
                }]
            }), encoding="utf-8")
            scheduler = {
                "selectedTasks": [{
                    "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                    "routeKey": "MA_Cross",
                    "strategy": "MA_Cross",
                    "variant": "ma_control_tight_exit",
                }]
            }
            recovery = {
                "candidateDrilldown": [{
                    "candidateId": "MA_Cross_EURUSDc_ma_control_tight_exit",
                    "riskLevel": "red",
                    "riskReason": "terminal_nonzero",
                    "latestStatusPath": str(status_path),
                }]
            }

            effective, controls = auto_tester_window.apply_executor_controls(
                scheduler=scheduler,
                recovery=recovery,
                budget_policy={"defaultRouteBudget": 1},
                max_tasks=1,
                enforce_retry_drilldown=True,
                enforce_budget=True,
            )

        self.assertEqual(controls["redSkippedCount"], 0)
        self.assertEqual(len(effective["selectedTasks"]), 1)
        self.assertEqual(effective["selectedTasks"][0]["retryOverride"], "PREVIOUS_TESTER_CONFIG_MISSING_TESTER_LOGIN_FIXED")

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
        self.assertIn("今日已完成，等待明日刷新", source)
        self.assertIn("每日迭代结论", source)
        self.assertIn("dailyArtifact.dailyIteration", source)
        self.assertIn("待办处理报告", source)
        self.assertIn("completionReport", source)
        self.assertIn("每日待办处理报告", source)
        self.assertIn("const actionQueueItems = computed(() => [\n  ...mt5ActionQueueItems.value,\n  ...polymarketActionQueueItems.value", source)
        self.assertNotIn("...paramVisibleTasks.value.slice(0, 5).map((row) => ({", source)
        self.assertIn("routeLaneMetricText(route, row)", source)
        self.assertIn("后验 ${first(outcome.horizonRows", source)
        self.assertIn("{{ lane.metricText }}", source)
        self.assertIn("shadowResearchUniverse", source)
        self.assertIn("实盘 universe", source)
        self.assertIn("模拟 universe", source)
        self.assertIn("mt5UniverseCards", source)
        self.assertIn("...mt5ActionQueueItems.value.slice(0, 3)", source)
        self.assertIn("...polymarketActionQueueItems.value.slice(0, 2)", source)
        self.assertIn("dailyTesterTodoMode", source)
        self.assertIn("每日待办短窗口", source)
        self.assertIn("vue_paramlab_daily_todo", source)
        self.assertIn("testerLookbackDays: 2", source)

    def test_mt5_status_cards_do_not_truncate_evidence_text(self):
        source = (MODULE_PATH.parents[1] / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".mt5-radar-board .dense-radar", source)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", source)
        self.assertIn(".page-mt5 .micro-metric span", source)
        self.assertIn(".page-mt5 .trade-metric-grid b", source)
        self.assertIn(".universe-strip", source)
        self.assertIn(".universe-card strong", source)
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

    def test_polymarket_daily_review_builds_loss_todos_when_evidence_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "QuantGod_PolymarketResearch.json").write_text(json.dumps({
                "generatedAtIso": "2026-04-28T00:00:00+00:00",
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

    def test_polymarket_daily_review_hides_completed_fresh_retune_cycle(self):
        now = daily_review.utc_now().isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "QuantGod_PolymarketResearch.json").write_text(json.dumps({
                "generatedAtIso": now,
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
            (runtime / "QuantGod_PolymarketRetunePlanner.json").write_text(json.dumps({
                "generatedAtIso": now,
                "status": "OK",
                "decision": "SHADOW_ONLY_RETUNE_NO_BETTING",
                "recommendationCounts": {"total": 3, "red": 1, "yellow": 2},
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketAutoGovernance.json").write_text(json.dumps({
                "generatedAt": now,
                "globalBlockers": ["GLOBAL_LOSS_QUARANTINE", "EXECUTED_PF_BELOW_1"],
                "summary": {"quarantine": 46, "autoCanaryEligible": 0},
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketDryRunOutcomeWatcher.json").write_text(json.dumps({
                "generatedAtIso": now,
                "summary": {"wouldExit": 4, "stopLoss": 2, "trailingExit": 2},
            }), encoding="utf-8")
            (runtime / "QuantGod_PolymarketExecutionGate.json").write_text(json.dumps({
                "generatedAt": now,
                "summary": {"canBet": 0, "blocked": 24},
            }), encoding="utf-8")

            review = daily_review.polymarket_daily_review(runtime)

            self.assertEqual(review["status"], "DONE_HIDE_UNTIL_NEXT_REFRESH")
            self.assertTrue(review["summary"]["lossQuarantine"])
            self.assertEqual(review["summary"]["todoCount"], 0)
            self.assertGreaterEqual(review["summary"]["completedCount"], 4)
            self.assertEqual(review["actionQueue"], [])
            self.assertEqual(review["completedActionQueue"][0]["state"], "DONE")

    def test_polymarket_research_replays_archived_snapshot_from_history_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "history.sqlite"
            con = __import__("sqlite3").connect(db_path)
            con.execute(
                "CREATE TABLE qd_polymarket_research_snapshots "
                "(generated_at TEXT, raw_json TEXT)"
            )
            con.execute(
                "INSERT INTO qd_polymarket_research_snapshots VALUES (?, ?)",
                (
                    "2026-05-01T18:06:59+00:00",
                    json.dumps({
                        "mode": "POLYMARKET_READ_ONLY_RESEARCH_BRIDGE",
                        "status": "OK",
                        "summary": {
                            "executed": {"closed": 0, "profitFactor": None},
                            "shadow": {"closed": 0, "profitFactor": None},
                        },
                    }),
                ),
            )
            con.execute(
                "INSERT INTO qd_polymarket_research_snapshots VALUES (?, ?)",
                (
                    "2026-04-28T10:57:30+00:00",
                    json.dumps({
                        "mode": "POLYMARKET_READ_ONLY_RESEARCH_BRIDGE",
                        "status": "OK",
                        "summary": {
                            "executed": {"closed": 24, "profitFactor": 0.0145},
                            "shadow": {"closed": 383, "profitFactor": 0.7055},
                        },
                        "source": {"dbPath": "D:/polymarket/copybot.db"},
                    }),
                ),
            )
            con.commit()
            con.close()

            snapshot = poly_research.build_snapshot(Path(tmp), db_path, 14, 5, skip_account_snapshot=True)

            self.assertEqual(snapshot["status"], "OK_ARCHIVED_SNAPSHOT")
            self.assertEqual(snapshot["summary"]["executed"]["closed"], 24)
            self.assertEqual(snapshot["summary"]["shadow"]["profitFactor"], 0.7055)
            self.assertTrue(snapshot["source"]["archiveReplay"])

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
