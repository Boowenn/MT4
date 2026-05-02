from __future__ import annotations

import unittest

from tools.notify.event_formatter import format_event


class NotifyFormatterTests(unittest.TestCase):
    def test_ai_analysis_message_is_structured(self) -> None:
        text = format_event(
            "AI_ANALYSIS",
            {
                "symbol": "EURUSDc",
                "action": "HOLD",
                "confidence": 0.35,
                "risk": "medium_high",
                "note": "Wait for NFP",
            },
        )
        self.assertIn("EURUSDc", text)
        self.assertIn("HOLD", text)
        self.assertIn("35%", text)
        self.assertIn("medium_high", text)

    def test_trade_messages_escape_html(self) -> None:
        text = format_event("TEST", {"message": "<script>alert(1)</script>"})
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_all_required_phase2_events_have_messages(self) -> None:
        events = [
            "TRADE_OPEN",
            "TRADE_CLOSE",
            "KILL_SWITCH",
            "NEWS_BLOCK",
            "AI_ANALYSIS",
            "CONSECUTIVE_LOSS",
            "DAILY_DIGEST",
        ]
        for event in events:
            with self.subTest(event=event):
                self.assertGreater(len(format_event(event, {"symbol": "EURUSDc", "message": "ok"})), 10)


if __name__ == "__main__":
    unittest.main()
