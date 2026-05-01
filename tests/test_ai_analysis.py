from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from tools.ai_analysis.analysis_service import AnalysisService
from tools.ai_analysis.config import AIAnalysisConfig
from tools.ai_analysis.llm_client import LLMClient, LLMClientError
from tools.ai_analysis.market_data_collector import MarketDataCollector, READ_ONLY_SAFETY


class FakeLLM:
    default_model = "fake/model"

    async def chat(self, system_prompt, user_message, model=None, temperature=0.2, max_tokens=4096, response_format="json"):
        if "TechnicalAgent" in system_prompt:
            return {
                "agent": "technical",
                "symbol": "EURUSDc",
                "timestamp": "2026-04-30T14:30:00Z",
                "model": model or self.default_model,
                "timeframes_analyzed": ["M15", "H1", "H4", "D1"],
                "trend": {"m15": "bullish", "h1": "bullish", "h4": "neutral", "d1": "neutral", "consensus": "mixed_bullish"},
                "indicators": {"ma_cross": {"signal": "golden_cross", "tf": "M15", "bars_ago": 2}},
                "key_levels": {"resistance": [1.12], "support": [1.1]},
                "signal_strength": 0.72,
                "direction": "bullish",
                "reasoning": "mock technical",
                "cost_usd": 0.001,
            }
        if "RiskAgent" in system_prompt:
            return {
                "agent": "risk",
                "timestamp": "2026-04-30T14:30:00Z",
                "model": model or self.default_model,
                "risk_score": 0.25,
                "risk_level": "low",
                "factors": [{"factor": "baseline", "severity": "low", "detail": "ok"}],
                "kill_switch_active": False,
                "position_exposure": "none",
                "tradeable": True,
                "reasoning": "mock risk",
                "cost_usd": 0.001,
            }
        return {
            "agent": "decision",
            "timestamp": "2026-04-30T14:30:00Z",
            "model": model or self.default_model,
            "action": "BUY",
            "confidence": 0.66,
            "entry_price": 1.105,
            "stop_loss": 1.1,
            "take_profit": 1.12,
            "risk_reward_ratio": 3.0,
            "position_size_suggestion": "0.01",
            "reasoning": "mock decision",
            "key_factors": ["mock"],
            "suggested_wait_condition": None,
            "governance_evidence": {
                "route": "AI_ANALYSIS_ADVISORY",
                "supports_action": True,
                "advisory_only": True,
                "cannot_override_kill_switch": True,
            },
            "total_cost_usd": 0.002,
        }


class AIAnalysisTests(unittest.TestCase):
    def test_llm_json_parser_accepts_fenced_json(self):
        parsed = LLMClient.parse_json_content('```json\n{"agent":"technical"}\n```')
        self.assertEqual(parsed["agent"], "technical")

    def test_llm_requires_api_key_for_real_request(self):
        client = LLMClient(api_key="", max_retries=0)
        with self.assertRaises(LLMClientError):
            client._request_with_retries({"messages": []})

    def test_market_collector_mock_snapshot_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = AIAnalysisConfig(runtime_dir=Path(tmp), history_dir=Path(tmp) / "ai", mock_mode=True)
            snapshot = MarketDataCollector(config).collect_sync("EURUSDc", ["M15", "H1"])
        self.assertEqual(snapshot["symbol"], "EURUSDc")
        self.assertEqual(snapshot["safety"], READ_ONLY_SAFETY)
        self.assertFalse(snapshot["safety"]["orderSendAllowed"])
        self.assertIn("kline_m15", snapshot)
        self.assertIn("kline_h1", snapshot)

    def test_analysis_service_writes_latest_history_and_governance_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AIAnalysisConfig(
                runtime_dir=root / "runtime",
                history_dir=root / "ai_analysis",
                mock_mode=True,
                openrouter_api_key="",
            )
            service = AnalysisService(config=config, llm=FakeLLM())
            report = asyncio.run(service.run_analysis("EURUSDc", ["M15", "H1", "H4", "D1"]))

            self.assertEqual(report["mode"], "QUANTGOD_AI_ANALYSIS_FULL_REPORT_V1")
            self.assertEqual(report["decision"]["action"], "BUY")
            self.assertFalse(report["safety"]["canExecuteTrade"])
            self.assertTrue((config.history_dir / "latest.json").exists())
            evidence_path = config.runtime_dir / "QuantGod_AIAnalysisEvidence.json"
            self.assertTrue(evidence_path.exists())
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["mode"], "QUANTGOD_AI_ANALYSIS_EVIDENCE_V1")
            self.assertTrue(evidence["advisoryOnly"])
            self.assertFalse(evidence["safety"]["canExecuteTrade"])
            self.assertEqual(service.latest()["id"], report["id"])
            self.assertEqual(len(service.history("EURUSDc", limit=5)), 1)


if __name__ == "__main__":
    unittest.main()
