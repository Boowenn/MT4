import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_mt5_entry_blockers.py"
SPEC = importlib.util.spec_from_file_location("build_mt5_entry_blockers", MODULE_PATH)
entry_blockers = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(entry_blockers)


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Mt5EntryBlockerTests(unittest.TestCase):
    def test_fresh_dashboard_and_shadow_signal_rows_explain_entry_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            dashboard = runtime / entry_blockers.DASHBOARD_NAME
            dashboard.write_text(
                json.dumps(
                    {
                        "timestamp": "2026.05.05 14:34:50",
                        "runtime": {
                            "localTime": "2026.05.05 14:34:50",
                            "tradeStatus": "READY",
                            "executionEnabled": True,
                            "readOnlyMode": False,
                            "pilotStartupEntryGuardActive": False,
                        },
                        "news": {"blocked": False, "status": "IDLE"},
                        "openTrades": [],
                        "pendingOrders": [],
                    }
                ),
                encoding="utf-8",
            )
            now = datetime.fromisoformat("2026-05-05T05:35:00+00:00")
            os.utime(dashboard, (now.timestamp() - 10, now.timestamp() - 10))
            write_csv(
                runtime / entry_blockers.SHADOW_SIGNAL_NAME,
                [
                    "EventId",
                    "LabelTimeLocal",
                    "LabelTimeServer",
                    "EventBarTime",
                    "Symbol",
                    "Strategy",
                    "Timeframe",
                    "SignalStatus",
                    "SignalDirection",
                    "SignalScore",
                    "Regime",
                    "Blocker",
                    "ExecutionAction",
                    "ReferencePrice",
                    "SpreadPips",
                    "NewsStatus",
                    "Reason",
                ],
                [
                    ["a", "2026.05.05 09:15:00", "", "", "USDJPY", "MA_Cross", "M15", "SESSION_BLOCK", "NONE", 0, "TREND", "SESSION", "BLOCKED", 155.1, 1.2, "IDLE", "outside session"],
                    ["b", "2026.05.05 10:15:00", "", "", "USDJPY", "MA_Cross", "M15", "WAIT_SIGNAL", "NONE", 0, "RANGE", "NO_SIGNAL", "OBSERVED", 155.2, 1.1, "IDLE", "waiting"],
                    ["c", "2026.05.04 10:15:00", "", "", "USDJPY", "MA_Cross", "M15", "NEWS_BLOCK", "NONE", 0, "RANGE", "NEWS_BLOCK", "BLOCKED", 155.2, 1.1, "PRE_BLOCK", "old day"],
                ],
            )

            payload = entry_blockers.build_report(runtime, now=now, target_date_jst="2026-05-05")

            self.assertEqual(payload["summary"]["status"], "ENTRY_BLOCKERS_OBSERVED")
            self.assertTrue(payload["evidence"]["dashboardFresh"])
            self.assertTrue(payload["currentState"]["usable"])
            self.assertEqual(payload["currentState"]["tradeStatus"], "READY")
            self.assertEqual(payload["summary"]["signalRows"], 2)
            self.assertEqual(payload["summary"]["blockedRows"], 1)
            self.assertEqual(payload["summary"]["observedRows"], 1)
            self.assertEqual(payload["summary"]["sessionBlocks"], 1)
            self.assertEqual(payload["summary"]["waitSignalRows"], 1)
            self.assertEqual(payload["summary"]["topBlocker"], "SESSION")

    def test_stale_dashboard_is_not_used_as_current_live_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            dashboard = runtime / entry_blockers.DASHBOARD_NAME
            dashboard.write_text(
                json.dumps(
                    {
                        "timestamp": "2026.05.03 00:00:00",
                        "runtime": {
                            "localTime": "2026.05.03 00:00:00",
                            "tradeStatus": "AUTO_PAUSED",
                            "pilotStartupEntryGuardActive": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            now = datetime.fromisoformat("2026-05-05T05:35:00+00:00")
            os.utime(dashboard, (now.timestamp() - 7200, now.timestamp() - 7200))

            payload = entry_blockers.build_report(runtime, now=now, target_date_jst="2026-05-05")

            self.assertEqual(payload["summary"]["status"], "EVIDENCE_STALE_DASHBOARD")
            self.assertFalse(payload["evidence"]["dashboardFresh"])
            self.assertFalse(payload["currentState"]["usable"])
            self.assertNotIn("tradeStatus", payload["currentState"])
            self.assertEqual(payload["summary"]["recommendation"], "REFRESH_LIVE_DASHBOARD_BEFORE_TUNING")

    def test_fresh_dashboard_diagnostics_explain_current_wait_when_ledger_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            dashboard = runtime / entry_blockers.DASHBOARD_NAME
            dashboard.write_text(
                json.dumps(
                    {
                        "timestamp": "2026.05.05 14:34:50",
                        "runtime": {"localTime": "2026.05.05 14:34:50", "tradeStatus": "READY"},
                        "diagnostics": {
                            "MA_Cross": {"status": "ROUTE_DISABLED", "runtimeLabel": "OFF", "reason": "MA disabled"},
                            "RSI_Reversal": {"status": "WAIT_BAR", "runtimeLabel": "ON", "reason": "Waiting for next H1 bar"},
                            "BB_Triple": {"status": "WAIT_BAR", "runtimeLabel": "CAND", "reason": "Waiting for next H1 bar"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            now = datetime.fromisoformat("2026-05-05T05:35:00+00:00")
            os.utime(dashboard, (now.timestamp() - 10, now.timestamp() - 10))

            payload = entry_blockers.build_report(runtime, now=now, target_date_jst="2026-05-05")

            self.assertEqual(payload["summary"]["status"], "CURRENT_DIAGNOSTICS_OBSERVED")
            self.assertEqual(payload["summary"]["signalRows"], 0)
            self.assertEqual(payload["summary"]["diagnosticRows"], 3)
            self.assertEqual(payload["summary"]["topDiagnosticStatus"], "WAIT_BAR")
            self.assertEqual(payload["summary"]["recommendation"], "WAIT_FOR_NEXT_BAR_OR_ADD_BAR_WAIT_TELEMETRY_BEFORE_TUNING")
            self.assertEqual(payload["breakdown"]["currentDiagnostics"]["byStatus"][0]["status"], "WAIT_BAR")


if __name__ == "__main__":
    unittest.main()
