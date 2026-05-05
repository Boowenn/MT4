from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from ai_analysis.deepseek_mt5_advisor import (  # noqa: E402
    DeepSeekAdvisorConfig,
    DeepSeekMt5Advisor,
    anthropic_messages_url,
    chat_completions_url,
    load_deepseek_config,
    sanitize_report_for_deepseek,
    uses_anthropic_gateway,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class DeepSeekMt5AdvisorTests(unittest.TestCase):
    def sample_report(self) -> dict:
        return {
            "symbol": "USDJPYc",
            "generatedAt": "2026-05-03T00:00:00Z",
            "timeframes": ["M15", "H1"],
            "snapshot": {
                "source": "hfm_ea_runtime",
                "fallback": False,
                "runtimeFresh": True,
                "runtimeAgeSeconds": 10,
                "current_price": {"bid": 155.1, "ask": 155.12, "last": 155.11, "spread": 0.02},
                "open_positions": [{"ticket": "SHOULD_NOT_LEAK", "login": "SHOULD_NOT_LEAK"}],
            },
            "technical": {"direction": "neutral", "trend": {}, "indicators": {}, "key_levels": {}},
            "risk": {"risk_level": "medium", "kill_switch_active": False, "factors": []},
            "news": {"risk_level": "low", "reasoning": "No block"},
            "sentiment": {"bias": "neutral"},
            "bull_case": {"thesis": "Bull thesis", "conviction": 0.4},
            "bear_case": {"thesis": "Bear thesis", "conviction": 0.2},
            "decision": {"action": "HOLD", "confidence": 0.5},
        }

    def test_sanitized_payload_excludes_account_identifiers(self) -> None:
        sanitized = sanitize_report_for_deepseek(self.sample_report())
        raw = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn("SHOULD_NOT_LEAK", raw)
        self.assertNotIn("ticket", raw)
        self.assertIn("USDJPYc", raw)

    def test_load_config_reads_local_env_without_printing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.deepseek.local"
            env.write_text(
                "QG_MT5_AI_DEEPSEEK_ENABLED=1\n"
                "DEEPSEEK_API_KEY=sk-test-secret\n"
                "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
                "DEEPSEEK_MODEL=deepseek-v4-pro\n",
                encoding="utf-8",
            )
            config = load_deepseek_config(repo_root=tmp, env_file=env, environ={})
        self.assertTrue(config.enabled)
        self.assertEqual(config.api_key, "sk-test-secret")
        self.assertEqual(config.model, "deepseek-v4-pro")

    def test_mt5_specific_model_env_overrides_general_deepseek_model(self) -> None:
        config = load_deepseek_config(
            environ={
                "DEEPSEEK_API_KEY": "sk-test",
                "DEEPSEEK_MODEL": "deepseek-v4-pro",
                "QG_MT5_AI_DEEPSEEK_MODEL": "deepseek-v4-flash",
            }
        )
        self.assertEqual(config.model, "deepseek-v4-flash")

    def test_advisor_parses_deepseek_json_advice(self) -> None:
        content = {
            "headline": "证据有效但方向不够强，先观察。",
            "verdict": "观望，不开新仓",
            "signalGrade": "观察级",
            "confidencePct": "62%",
            "marketSummary": "价格横盘，点差正常。",
            "technicalSummary": "短线中性。",
            "bullCase": "突破后才考虑。",
            "bearCase": "跌破支撑转弱。",
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
        }
        payload = {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}

        def opener(request, timeout):
            self.assertIn("/chat/completions", request.full_url)
            body = json.loads(request.data.decode("utf-8"))
            raw = json.dumps(body, ensure_ascii=False)
            self.assertNotIn("SHOULD_NOT_LEAK", raw)
            return FakeResponse(payload)

        advisor = DeepSeekMt5Advisor(
            DeepSeekAdvisorConfig(enabled=True, api_key="sk-test", model="deepseek-v4-pro"),
            opener=opener,
        )
        result = advisor.analyze(self.sample_report())
        self.assertTrue(result["ok"])
        self.assertEqual(result["advice"]["verdict"], "观望，不开新仓")
        self.assertEqual(result["advice"]["targets"], ["不生成", "不生成", "不生成"])

    def test_advisor_supports_anthropic_gateway_response(self) -> None:
        content = {
            "headline": "DeepSeek 已分析，继续观察。",
            "verdict": "观望，不开新仓",
            "signalGrade": "观察级",
            "confidencePct": "60%",
            "marketSummary": "价格横盘。",
            "technicalSummary": "方向中性。",
            "bullCase": "等待突破。",
            "bearCase": "等待跌破。",
            "newsRisk": "暂无。",
            "sentimentPositioning": "中性。",
            "planStatus": "暂停，仅允许观察复核",
            "entryZone": "不生成",
            "targets": ["不生成", "不生成", "不生成"],
            "defense": "不生成",
            "riskReward": "未评估",
            "positionAdvice": "不构成下单建议",
            "invalidation": "证据不足",
            "watchPoints": ["看快照", "看点差"],
            "riskNotes": ["不追单", "不绕过风控"],
            "executionBoundary": "仅建议。",
        }
        payload = {"content": [{"type": "thinking", "thinking": "hidden"}, {"type": "text", "text": json.dumps(content, ensure_ascii=False)}]}

        def opener(request, timeout):
            self.assertIn("/anthropic/v1/messages", request.full_url)
            self.assertIn("anthropic-version", {k.lower(): v for k, v in request.header_items()})
            body = json.loads(request.data.decode("utf-8"))
            self.assertIn("system", body)
            self.assertNotIn("response_format", body)
            return FakeResponse(payload)

        advisor = DeepSeekMt5Advisor(
            DeepSeekAdvisorConfig(
                enabled=True,
                api_key="sk-test",
                base_url="https://api.deepseek.com/anthropic",
                model="deepseek-v4-pro",
            ),
            opener=opener,
        )
        result = advisor.analyze(self.sample_report())
        self.assertTrue(result["ok"])
        self.assertEqual(result["advice"]["headline"], "DeepSeek 已分析，继续观察。")

    def test_normalize_advice_joins_scalar_list_fields(self) -> None:
        content = {
            "entryZone": ["待复核", "等待新鲜证据"],
            "targets": ["不生成", "不生成", "不生成"],
        }
        payload = {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}

        def opener(request, timeout):
            return FakeResponse(payload)

        advisor = DeepSeekMt5Advisor(
            DeepSeekAdvisorConfig(enabled=True, api_key="sk-test", model="deepseek-v4-flash"),
            opener=opener,
        )
        result = advisor.analyze(self.sample_report())
        self.assertEqual(result["advice"]["entryZone"], "待复核；等待新鲜证据")

    def test_non_json_deepseek_reply_becomes_observation_only(self) -> None:
        payload = {"choices": [{"message": {"content": "技术面偏中性，建议继续观察，等待更清晰信号。"}}]}

        def opener(request, timeout):
            return FakeResponse(payload)

        advisor = DeepSeekMt5Advisor(
            DeepSeekAdvisorConfig(enabled=True, api_key="sk-test", model="deepseek-v4-flash"),
            opener=opener,
        )
        result = advisor.analyze(self.sample_report())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok_text_fallback")
        self.assertEqual(result["advice"]["verdict"], "观望，不开新仓")
        self.assertEqual(result["advice"]["entryZone"], "不生成")
        self.assertIn("非结构化", result["advice"]["headline"])

    def test_gateway_url_helpers(self) -> None:
        self.assertTrue(uses_anthropic_gateway("https://api.deepseek.com/anthropic"))
        self.assertEqual(anthropic_messages_url("https://api.deepseek.com/anthropic"), "https://api.deepseek.com/anthropic/v1/messages")
        self.assertEqual(chat_completions_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")


if __name__ == "__main__":
    unittest.main()
