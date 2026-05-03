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
            "runtimeFresh": True,
            "runtimeAgeSeconds": 12,
            "current_price": {"bid": 155.12, "ask": 155.14},
            "open_positions": [],
        },
        "technical": {
            "direction": "neutral",
            "trend": {"m15": "neutral", "h1": "neutral", "h4": "neutral", "d1": "neutral"},
            "indicators": {"ma_cross": {"signal": "none"}, "rsi": {"h1": 51.2, "zone": "neutral"}},
            "key_levels": {"support": [154.9], "resistance": [155.8]},
        },
        "risk": {
            "risk_level": "medium",
            "kill_switch_active": False,
            "factors": [{"severity": "low", "detail": "No active local risk blocker found in fallback inputs."}],
        },
        "news": {"risk_level": "low", "reasoning": "No high-impact news evidence."},
        "sentiment": {"bias": "neutral", "reasoning": "Local sentiment is neutral."},
        "bull_case": {"thesis": "Bull case waits for a cleaner breakout.", "conviction": 0.31},
        "bear_case": {"thesis": "Bear case is limited by current range conditions.", "conviction": 0.29},
        "decision": {
            "action": "HOLD",
            "confidence": 0.64,
            "reasoning": "Advisory only.",
            "key_factors": ["Risk level medium", "Technical direction neutral"],
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward_ratio": None,
            "position_size_suggestion": "0.01",
            "debate_summary": {
                "bull_conviction": 0.31,
                "bear_conviction": 0.29,
                "bull_thesis": "Bull case waits for a cleaner breakout.",
                "bear_thesis": "Bear case is limited by current range conditions.",
            },
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
        self.assertIn("【QuantGod MT5 智能监控报告】", text)
        self.assertIn("【一、报告信息】", text)
        self.assertIn("【二、行情与账户快照】", text)
        self.assertIn("【三、盘面结构】", text)
        self.assertIn("【四、智能综合评分】", text)
        self.assertIn("【五、多空推演】", text)
        self.assertIn("【六、交易计划】", text)
        self.assertIn("【七、风险明细】", text)
        self.assertIn("【八、执行与风控边界】", text)
        self.assertIn("观望，不开新仓", text)
        self.assertIn("不会下单", text)
        self.assertNotIn("HOLD", text)
        self.assertNotIn("Bid", text)
        self.assertNotIn("Kill Switch", text)
        self.assertNotIn("EA/gate", text)
        self.assertNotIn("live preset", text)

    def test_advisory_message_localizes_buy_plan(self) -> None:
        report = sample_report()
        report["decision"]["action"] = "BUY"
        report["decision"]["entry_price"] = 155.12
        report["decision"]["stop_loss"] = 154.72
        report["decision"]["take_profit"] = 155.92
        report["decision"]["risk_reward_ratio"] = 2.0
        text = monitor.build_advisory_message(report, reason="force")
        self.assertIn("方向：偏多观察，等待程序风控确认", text)
        self.assertIn("入场区间：等待程序风控门禁确认后才考虑做多", text)
        self.assertIn("防守位置：154.72", text)
        self.assertIn("目标三：155.92", text)
        self.assertIn("触发原因：手动强制复核", text)

    def test_advisory_message_blocks_plan_when_evidence_is_fallback(self) -> None:
        report = sample_report()
        report["snapshot"]["fallback"] = True
        report["snapshot"]["runtimeFresh"] = False
        report["snapshot"]["source"] = "mt5_python_unavailable"
        report["decision"]["action"] = "BUY"
        text = monitor.build_advisory_message(report, reason="force")
        self.assertIn("信号等级：数据复核级", text)
        self.assertIn("数据质量不足，本条只做系统复核，不允许据此入场。", text)
        self.assertIn("计划状态：暂停，仅允许观察复核。", text)
        self.assertIn("入场区间：不生成", text)

    def test_advisory_message_prefers_deepseek_advice(self) -> None:
        report = sample_report()
        report["deepseek_advice"] = {
            "ok": True,
            "status": "ok",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "advice": {
                "headline": "大模型判断证据不够强，继续等待。",
                "verdict": "观望，不开新仓",
                "signalGrade": "观察级",
                "confidencePct": "61%",
                "marketSummary": "价格横盘，点差正常。",
                "technicalSummary": "短线中性，缺少突破。",
                "bullCase": "突破压力后才有做多价值。",
                "bearCase": "跌破支撑后转弱。",
                "newsRisk": "暂无高影响新闻。",
                "sentimentPositioning": "情绪中性。",
                "planStatus": "暂停，仅允许观察复核",
                "entryZone": "不生成",
                "targets": ["不生成", "不生成", "不生成"],
                "defense": "不生成",
                "riskReward": "未评估",
                "positionAdvice": "不构成下单建议",
                "invalidation": "证据转弱继续观望",
                "watchPoints": ["等待新鲜证据", "观察支撑压力"],
                "riskNotes": ["不追单", "不绕过风控"],
                "executionBoundary": "仅建议，不执行交易。",
            },
        }
        text = monitor.build_advisory_message(report, reason="changed")
        self.assertIn("分析来源：DeepSeek 大模型研判", text)
        self.assertIn("一句话结论：大模型判断证据不够强，继续等待。", text)
        self.assertIn("技术总结：短线中性，缺少突破。", text)
        self.assertIn("计划状态：暂停，仅允许观察复核", text)

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
                    "--no-deepseek",
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
