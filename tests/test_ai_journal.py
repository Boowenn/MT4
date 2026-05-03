from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.ai_journal.kill_switch import apply_signal_kill_switch, evaluate_family
from tools.ai_journal.reader import latest_records, outcome_path
from tools.ai_journal.scorer import score_latest
from tools.ai_journal.telegram_text import ensure_chinese_telegram_text
from tools.ai_journal.writer import record_telegram_advisory


def sample_report(action: str = "BUY", final_action: str = "WATCH_LONG") -> dict:
    return {
        "symbol": "USDJPYc",
        "generatedAt": "2026-05-03T00:00:00Z",
        "timeframes": ["M15", "H1"],
        "snapshot": {
            "source": "hfm_ea_runtime",
            "fallback": False,
            "runtimeFresh": True,
            "runtimeAgeSeconds": 12,
            "current_price": {"bid": 155.10, "ask": 155.12, "last": 155.11, "spread": 0.02},
        },
        "risk": {"risk_level": "medium", "kill_switch_active": False},
        "decision": {"action": action, "confidence": 0.62, "reasoning": "测试建议", "entry_price": 155.11},
        "deepseek_advice": {
            "ok": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "advice": {"verdict": "偏多观察", "planStatus": "等待确认"},
            "validation": {"status": "pass", "reasons": []},
        },
        "advisory_fusion": {
            "finalAction": final_action,
            "agreement": "local_and_deepseek_compatible",
            "notifySeverity": "SIGNAL_REVIEW",
            "evidenceQualityScore": 0.9,
        },
    }


class AiJournalTests(unittest.TestCase):
    def test_record_telegram_advisory_writes_shadow_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = record_telegram_advisory(
                runtime_dir=tmp,
                report=sample_report(),
                delivery={"status": "dry_run", "telegramMessageId": 7},
                message="中文测试消息",
                reason="changed",
                dry_run=True,
                now_iso="2026-05-03T00:01:00Z",
            )
            self.assertTrue(result["ok"])
            rows = latest_records(tmp, limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["shadowSignal"]["direction"], "LONG")
            self.assertFalse(rows[0]["safety"]["orderSendAllowed"])

    def test_score_latest_uses_current_runtime_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "QuantGod_MT5RuntimeSnapshot_USDJPYc.json").write_text(
                json.dumps(
                    {
                        "schema": "quantgod.mt5.runtime_snapshot.v1",
                        "source": "hfm_ea_runtime",
                        "generatedAt": "2026-05-03T04:00:00Z",
                        "symbol": "USDJPYc",
                        "current_price": {"bid": 155.40, "ask": 155.42, "last": 155.41, "spread": 0.02},
                        "safety": {"orderSendAllowed": False, "closeAllowed": False, "cancelAllowed": False},
                    }
                ),
                encoding="utf-8",
            )
            record_telegram_advisory(runtime_dir=tmp, report=sample_report(), message="中文", reason="changed")
            result = score_latest(tmp, limit=10, write=True)
            self.assertEqual(result["scored"], 1)
            self.assertGreater(result["outcomes"][0]["scoreR"], 0)
            self.assertTrue(outcome_path(tmp).exists())

    def test_kill_switch_pauses_weak_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(5):
                outcome = {
                    "schema": "quantgod.ai_advisory_outcome.v1",
                    "recordId": f"r{index}",
                    "symbol": "USDJPYc",
                    "scoredAt": "2026-05-03T04:00:00Z",
                    "horizon": "4h",
                    "elapsedSeconds": 14400,
                    "referencePrice": 155.0,
                    "currentPrice": 154.5,
                    "priceSource": "hfm_ea_runtime",
                    "direction": "LONG",
                    "status": "scored",
                    "directionCorrect": False,
                    "move": -0.5,
                    "movePct": -0.003,
                    "scoreR": -0.7,
                    "classification": "负向",
                    "safety": {"orderSendAllowed": False, "closeAllowed": False, "cancelAllowed": False},
                }
                outcome_path(tmp).parent.mkdir(parents=True, exist_ok=True)
                with outcome_path(tmp).open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(outcome, ensure_ascii=False) + "\n")
            evaluation = evaluate_family(tmp, "USDJPYc", "LONG")
            self.assertTrue(evaluation["pause"])
            gated = apply_signal_kill_switch(sample_report(), runtime_dir=tmp, now_iso="2026-05-03T05:00:00Z")
            self.assertEqual(gated["advisory_fusion"]["finalAction"], "PAUSED")
            self.assertEqual(gated["decision"]["action"], "HOLD")
            self.assertIn("暂停", gated["deepseek_advice"]["advice"]["verdict"])

    def test_telegram_text_normalizes_english_operational_terms(self) -> None:
        text = "融合审查：finalAction=WATCH_LONG；validator=pass；agreement=local_and_deepseek_compatible；advisoryOnly=true | KillSwitch False"
        out = ensure_chinese_telegram_text(text)
        self.assertIn("最终动作=偏多观察", out)
        self.assertIn("校验=通过", out)
        self.assertIn("仅建议=是", out)
        self.assertNotIn("finalAction=", out)
        self.assertNotIn("WATCH_LONG", out)


if __name__ == "__main__":
    unittest.main()
