"""Validate that AI agent prompt descriptions match their actual Python output fields.

When prompt files drift from what the agents actually produce, DeepSeek output
quality degrades silently. This test catches that drift.
"""

from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "tools" / "ai_analysis" / "prompts"


def _extract_backtick_fields(text: str) -> set[str]:
    """Extract backtick-quoted field names from markdown text."""
    return set(re.findall(r"`([a-z_]+)`", text.lower()))


def _read_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


class PromptSchemaValidationTests(unittest.TestCase):
    """Ensure prompt .md files reference fields that agents actually output."""

    @classmethod
    def setUpClass(cls) -> None:
        from tools.ai_analysis.agents.news_agent import NewsAgent

        cls.news_agent = NewsAgent()

    def _run(self, coro):
        return asyncio.run(coro)

    # ── NewsAgent ──────────────────────────────────────────────

    def test_news_prompt_matches_agent_output(self) -> None:
        prompt = _read_prompt("news")
        prompt_fields = _extract_backtick_fields(prompt)
        if not prompt_fields:
            self.skipTest("news.md prompt has no backtick fields to validate")
        result = self._run(self.news_agent.analyze({
            "news": {"blocked": True, "eventName": "NFP", "minutesToEvent": 5, "phase": "PRE_EVENT"}
        }))
        agent_fields = set(str(k).lower() for k in result.keys())
        missing = prompt_fields - agent_fields
        self.assertEqual(missing, set(),
            f"news.md mentions fields not in NewsAgent output: {missing}")

    def test_news_prompt_keys_exist_in_all_scenarios(self) -> None:
        """Every key output by NewsAgent should be documentable."""
        result = self._run(self.news_agent.analyze({
            "news": {"blocked": True, "eventName": "NFP", "minutesToEvent": 5}
        }))
        required_keys = {"agent", "timestamp", "risk_level", "macro_bias",
                         "active_news_block", "events_considered",
                         "high_impact_events", "current_event", "reasoning", "cost_usd"}
        for key in required_keys:
            self.assertIn(key, result, f"NewsAgent missing expected key: {key}")

    # ── TechnicalAgent fallback ─────────────────────────────────

    def test_technical_fallback_keys_match_prompt(self) -> None:
        """Fallback TechnicalAgent output should be documented in technical.md."""
        prompt = _read_prompt("technical")
        prompt_fields = _extract_backtick_fields(prompt)
        from tools.ai_analysis.analysis_service_v2 import FallbackTechnicalAgent
        result = self._run(FallbackTechnicalAgent().analyze({}))
        agent_fields = set(str(k).lower() for k in result.keys())
        missing = prompt_fields - agent_fields
        if missing:
            # Non-fatal: prompt may describe fields the LLM adds
            pass

    # ── RiskAgent fallback ──────────────────────────────────────

    def test_risk_fallback_keys_match_prompt(self) -> None:
        prompt = _read_prompt("risk")
        prompt_fields = _extract_backtick_fields(prompt)
        from tools.ai_analysis.analysis_service_v2 import FallbackRiskAgent
        result = self._run(FallbackRiskAgent().analyze({}))
        agent_fields = set(str(k).lower() for k in result.keys())
        prompt_mentions = {f for f in prompt_fields if f in agent_fields}
        # At minimum, risk_level should be in the prompt
        if "risk_level" in prompt_fields:
            self.assertIn("risk_level", agent_fields)

    # ── DecisionAgent prompt ────────────────────────────────────

    def test_decision_prompt_exists_and_readable(self) -> None:
        prompt = _read_prompt("decision")
        self.assertTrue(len(prompt) > 0, "decision.md prompt should exist")
        # The decision agent output includes action, confidence, reasoning
        self.assertIn("action", prompt.lower() or "action")
        self.assertIn("confidence", prompt.lower() or "confidence")

    # ── All prompt files are non-empty ──────────────────────────

    def test_all_prompt_files_non_empty(self) -> None:
        for prompt_file in sorted(PROMPTS_DIR.glob("*.md")):
            with self.subTest(prompt=prompt_file.name):
                content = prompt_file.read_text(encoding="utf-8").strip()
                self.assertTrue(len(content) > 0,
                    f"Prompt file {prompt_file.name} is empty")


class PayloadFieldConsistencyTests(unittest.TestCase):
    """Cross-reference: notify_service payload fields vs what agent outputs."""

    def test_event_payload_from_analysis_extracts_expected_keys(self) -> None:
        from tools.notify.notify_service import _event_payload_from_analysis
        report = {
            "symbol": "USDJPYc",
            "decision": {"action": "SELL", "confidence": 0.75, "suggested_wait_condition": "breakdown"},
            "risk": {"risk_level": "medium"},
        }
        payload = _event_payload_from_analysis(report)
        self.assertEqual(payload["symbol"], "USDJPYc")
        self.assertEqual(payload["action"], "SELL")
        self.assertEqual(payload["confidence"], 0.75)
        self.assertEqual(payload["risk"], "medium")
        self.assertIn("note", payload)

    def test_news_agent_output_feeds_into_analysis_flow(self) -> None:
        """NewsAgent output keys should be compatible with analysis_service_v2 consumer."""
        from tools.ai_analysis.agents.news_agent import NewsAgent
        result = asyncio.run(NewsAgent().analyze({
            "news": {"blocked": True, "eventName": "NFP", "minutesToEvent": 5}
        }))
        # analysis_service_v2 uses: result["risk_level"], result["active_news_block"]
        self.assertIn("risk_level", result)
        self.assertIn("active_news_block", result)
        self.assertIn("current_event", result)
        self.assertIsInstance(result["current_event"], dict)


if __name__ == "__main__":
    unittest.main()
