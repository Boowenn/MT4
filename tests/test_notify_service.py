from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tools.notify.config import NotifyConfig
from tools.notify.notify_service import build_daily_digest, load_history, scan_runtime_events, send_ai_analysis_summary, send_event


class NotifyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name)
        self.old_env = os.environ.copy()
        os.environ["QG_RUNTIME_DIR"] = str(self.runtime)
        os.environ["QG_NOTIFY_HISTORY_PATH"] = str(self.runtime / "QuantGod_NotifyHistory.json")
        os.environ["QG_NOTIFY_ENABLED"] = "true"
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        os.environ.pop("QG_TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("QG_TELEGRAM_CHAT_ID", None)
        os.environ.pop("QG_TELEGRAM_PUSH_ALLOWED", None)
        os.environ["QG_TELEGRAM_ENV_FILE"] = str(self.runtime / ".env.telegram.local")

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmp.cleanup()

    @contextmanager
    def chdir_runtime(self):
        old_cwd = os.getcwd()
        os.chdir(self.runtime)
        try:
            yield
        finally:
            os.chdir(old_cwd)

    def test_dry_run_send_records_history_without_network(self) -> None:
        cfg = NotifyConfig.from_env()
        result = asyncio.run(send_event("TEST", {"message": "phase2 smoke"}, config=cfg, dry_run=True))
        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        history = load_history(cfg, limit=10)
        self.assertEqual(len(history["items"]), 1)
        self.assertIn("phase2 smoke", history["items"][0]["text"])

    def test_ai_summary_extracts_decision_and_risk(self) -> None:
        cfg = NotifyConfig.from_env()
        report = {
            "symbol": "XAUUSDc",
            "decision": {"action": "SELL", "confidence": 0.62, "suggested_wait_condition": "breakdown confirmed"},
            "risk": {"risk_level": "medium"},
        }
        result = asyncio.run(send_ai_analysis_summary(report, config=cfg, dry_run=True))
        text = result["record"]["text"]
        self.assertIn("XAUUSDc", text)
        self.assertIn("做空", text)  # Chinese renderer output
        self.assertIn("62%", text)
        self.assertIn("中", text)  # Chinese risk label for "medium"

    def test_daily_digest_counts_close_history_and_shadow(self) -> None:
        (self.runtime / "QuantGod_CloseHistory.csv").write_text("Ticket,Profit\n1,0.45\n2,-0.20\n", encoding="utf-8")
        (self.runtime / "QuantGod_TradeJournal.csv").write_text("Ticket,Route\n1,MA_Cross\n2,RSI_Reversal\n", encoding="utf-8")
        (self.runtime / "QuantGod_ShadowSignalLedger.csv").write_text("Symbol,Signal\nEURUSDc,HOLD\n", encoding="utf-8")
        digest = build_daily_digest(NotifyConfig.from_env())
        self.assertAlmostEqual(digest["pnl"], 0.25)
        self.assertEqual(digest["wins"], 1)
        self.assertEqual(digest["losses"], 1)
        self.assertEqual(digest["shadowSignals"], 1)

    def test_scan_runtime_events_detects_risk_and_ai(self) -> None:
        (self.runtime / "QuantGod_Dashboard.json").write_text(
            json.dumps({
                "killSwitchActive": True,
                "killSwitchReason": "daily_loss_limit",
                "news": {
                    "blocked": True,
                    "eventName": "Non-Farm Payrolls",
                    "eventLabel": "NFP",
                    "minutesToEvent": 15,
                    "phase": "PRE_EVENT",
                    "actual": None,
                    "forecast": 5.25,
                    "previous": 5.50,
                },
            }),
            encoding="utf-8",
        )
        ai_dir = self.runtime / "ai_analysis"
        ai_dir.mkdir()
        (ai_dir / "latest.json").write_text(
            json.dumps({"symbol": "EURUSDc", "decision": {"action": "HOLD"}, "risk": {"risk_level": "high"}}),
            encoding="utf-8",
        )
        events = scan_runtime_events(NotifyConfig.from_env())
        self.assertEqual([event["eventType"] for event in events], ["KILL_SWITCH", "NEWS_BLOCK", "AI_ANALYSIS"])
        news_event = events[1]
        self.assertEqual(news_event["eventType"], "NEWS_BLOCK")
        self.assertEqual(news_event["data"]["label"], "NFP")
        self.assertEqual(news_event["data"]["eta"], 15)
        self.assertEqual(news_event["data"]["phase"], "PRE_EVENT")
        self.assertEqual(news_event["data"]["forecast"], 5.25)

    def test_scan_runtime_events_news_not_blocked_when_no_block(self) -> None:
        (self.runtime / "QuantGod_Dashboard.json").write_text(
            json.dumps({"news": {"blocked": False, "eventName": "FOMC", "minutesToEvent": 240}}),
            encoding="utf-8",
        )
        events = scan_runtime_events(NotifyConfig.from_env())
        event_types = [e["eventType"] for e in events]
        self.assertNotIn("NEWS_BLOCK", event_types)

    def test_scan_runtime_events_news_missing_key_handled(self) -> None:
        (self.runtime / "QuantGod_Dashboard.json").write_text(
            json.dumps({"dashboardBuild": "v3.17.0"}), encoding="utf-8"
        )
        events = scan_runtime_events(NotifyConfig.from_env())
        event_types = [e["eventType"] for e in events]
        self.assertNotIn("NEWS_BLOCK", event_types)

    def test_phase2_notify_config_reads_local_qg_telegram_env(self) -> None:
        (self.runtime / ".env.telegram.local").write_text(
            "\n".join(
                [
                    ("QG_TELEGRAM_BOT_" "TOKEN=local-test-token"),
                    "QG_TELEGRAM_CHAT_ID=@QuardGodSystem",
                    "QG_TELEGRAM_PUSH_ALLOWED=1",
                ]
            ),
            encoding="utf-8",
        )
        with self.chdir_runtime():
            cfg = NotifyConfig.from_env()
        self.assertTrue(cfg.telegram_configured)
        self.assertTrue(cfg.telegram_push_allowed)
        public = cfg.public_dict()
        self.assertTrue(public["telegramConfigured"])
        self.assertTrue(public["telegramPushAllowed"])
        self.assertNotIn("local-secret", json.dumps(public, ensure_ascii=False))

    def test_actual_send_without_config_fails_before_network(self) -> None:
        cfg = NotifyConfig.from_env()
        result = asyncio.run(send_event("TEST", {"message": "missing config"}, config=cfg, dry_run=False))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "telegram_not_configured")


if __name__ == "__main__":
    unittest.main()
