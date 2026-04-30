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


if __name__ == "__main__":
    unittest.main()
