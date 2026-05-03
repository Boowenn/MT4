from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_mt5_ai_telegram_monitor as monitor


def sample_report(symbol: str = "USDJPYc") -> dict:
    return {
        "ok": True,
        "symbol": symbol,
        "generatedAt": "2026-05-03T00:00:00Z",
        "snapshot": {
            "source": "runtime_files",
            "fallback": False,
            "current_price": {"bid": 155.12, "ask": 155.14},
            "open_positions": [],
        },
        "technical": {"direction": "neutral"},
        "risk": {"risk_level": "medium", "kill_switch_active": False},
        "decision": {
            "action": "HOLD",
            "confidence": 0.64,
            "reasoning": "Advisory only.",
            "key_factors": ["Risk level medium", "Technical direction neutral"],
        },
    }


class FakeAnalysisService:
    def __init__(self, runtime_dir=None):
        self.runtime_dir = runtime_dir

    async def run_analysis(self, symbol, timeframes):
        report = sample_report(symbol)
        report["timeframes"] = timeframes
        return report


class Mt5AiTelegramMonitorTests(unittest.TestCase):
    def test_safety_blocks_trading_and_commands(self) -> None:
        safety = monitor.monitor_safety()
        self.assertTrue(safety["advisoryOnly"])
        self.assertFalse(safety["orderSendAllowed"])
        self.assertFalse(safety["telegramCommandExecutionAllowed"])
        self.assertFalse(safety["livePresetMutationAllowed"])

    def test_advisory_message_declares_read_only_boundary(self) -> None:
        text = monitor.build_advisory_message(sample_report(), reason="changed")
        self.assertIn("MT5 AI 监听", text)
        self.assertIn("只读监听", text)
        self.assertIn("不会下单", text)

    def test_dedupe_waits_for_unchanged_signature(self) -> None:
        report = sample_report()
        sig = monitor.event_signature(report)
        state = {
            "symbols": {
                "USDJPYc": {
                    "signature": sig,
                    "lastNotifiedAt": "2026-05-03T00:00:00Z",
                }
            }
        }
        ok, reason = monitor.should_notify(
            state,
            symbol="USDJPYc",
            signature=sig,
            now_epoch=1777766405,
            min_interval_seconds=60,
            force=False,
        )
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("dedup_wait_"))

    def test_scan_once_defaults_to_dry_run_and_writes_runtime_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = monitor.build_parser().parse_args(
                [
                    "scan-once",
                    "--symbols",
                    "USDJPYc",
                    "--runtime-dir",
                    tmp_dir,
                    "--env-file",
                    str(Path(tmp_dir) / ".env.telegram.local"),
                    "--min-interval-seconds",
                    "0",
                ]
            )
            env_file = Path(tmp_dir) / ".env.telegram.local"
            env_file.write_text(
                "QG_TELEGRAM_BOT_TOKEN=123456:ABCDEF\n"
                "QG_TELEGRAM_CHAT_ID=@QuardGod\n"
                "QG_TELEGRAM_PUSH_ALLOWED=0\n"
                "QG_TELEGRAM_COMMANDS_ALLOWED=0\n",
                encoding="utf-8",
            )
            with mock.patch.object(monitor, "AnalysisServiceV2", FakeAnalysisService):
                payload = asyncio.run(monitor.scan_once(args))
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dryRun"])
            self.assertEqual(payload["summary"]["notifications"], 1)
            latest = Path(tmp_dir) / "QuantGod_MT5AiTelegramMonitorLatest.json"
            state = Path(tmp_dir) / "QuantGod_MT5AiTelegramMonitorState.json"
            self.assertTrue(latest.exists())
            self.assertTrue(state.exists())
            self.assertEqual(json.loads(state.read_text())["symbols"]["USDJPYc"]["status"], "dry_run")


if __name__ == "__main__":
    unittest.main()
