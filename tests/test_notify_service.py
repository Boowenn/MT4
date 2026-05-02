from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
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

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmp.cleanup()

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
        self.assertIn("SELL", text)
        self.assertIn("62%", text)
        self.assertIn("medium", text)

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
            json.dumps({"killSwitchActive": True, "killSwitchReason": "daily_loss_limit", "newsBlockActive": True}),
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


if __name__ == "__main__":
    unittest.main()
