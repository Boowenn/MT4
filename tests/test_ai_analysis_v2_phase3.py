from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from tools.ai_analysis.agents.bear_agent import BearAgent
from tools.ai_analysis.agents.bull_agent import BullAgent
from tools.ai_analysis.analysis_service_v2 import AnalysisServiceV2, phase3_ai_safety
from tools.ai_analysis.memory.vector_store import LocalVectorMemory


class AiAnalysisV2Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["QG_RUNTIME_DIR"] = self.tmp.name
        os.environ["AI_ANALYSIS_HISTORY_DIR"] = str(Path(self.tmp.name) / "ai_analysis")

    def test_bull_bear_cases_have_conviction(self):
        evidence = {
            "technical": {"direction": "bullish"},
            "risk": {"risk_level": "medium", "tradeable": True},
            "news": {"risk_level": "low"},
            "sentiment": {"bias": "bearish"},
        }
        bull = asyncio.run(BullAgent().argue(evidence))
        bear = asyncio.run(BearAgent().argue(evidence))
        self.assertEqual(bull["agent"], "bull")
        self.assertEqual(bear["agent"], "bear")
        self.assertGreaterEqual(bull["conviction"], 0)
        self.assertGreaterEqual(bear["conviction"], 0)

    def test_memory_store_query_status(self):
        memory = LocalVectorMemory(Path(self.tmp.name) / "memory.jsonl")
        memory.store_case(symbol="EURUSDc", report={"decision": {"action": "HOLD", "reasoning": "NFP risk"}}, tags=["NFP"])
        cases = memory.query(symbol="EURUSDc", conditions=["NFP", "risk"], top_k=3)
        self.assertTrue(cases)
        self.assertEqual(memory.status()["case_count"], 1)

    def test_analysis_service_v2_report_safety_and_governance_evidence(self):
        service = AnalysisServiceV2(runtime_dir=self.tmp.name)
        report = asyncio.run(service.run_analysis("EURUSDc", ["M15", "H1"]))
        self.assertTrue(report["ok"])
        self.assertIn("bull_case", report)
        self.assertIn("bear_case", report)
        self.assertFalse(report["safety"]["orderSendAllowed"])
        evidence = Path(self.tmp.name) / "QuantGod_AIAnalysisEvidenceV2.json"
        self.assertTrue(evidence.exists())
        self.assertFalse(phase3_ai_safety()["canOverrideKillSwitch"])
