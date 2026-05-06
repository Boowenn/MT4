from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.automation_chain.runner import AutomationChainRunner
from tools.automation_chain.telegram_text import build_automation_telegram_text


class AutomationChainTest(unittest.TestCase):
    def test_status_fail_closed_when_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = AutomationChainRunner(Path.cwd(), tmp, ["USDJPYc"], python_bin="python")
            status = runner.build_status()
            self.assertEqual(status["state"], "NOT_RUN")
            self.assertIn("尚未运行", status["stateZh"])
            self.assertFalse(status["safety"]["orderSendAllowed"])

    def test_policy_summary_detects_opportunity_and_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "adaptive").mkdir(parents=True)
            (runtime / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json").write_text(json.dumps({
                "strategies": [
                    {"symbol": "USDJPYc", "direction": "LONG", "entryMode": "OPPORTUNITY_ENTRY", "allowed": True, "recommendedLot": 0.7, "reason": "核心安全通过"},
                    {"symbol": "USDJPYc", "direction": "SHORT", "entryMode": "BLOCKED", "allowed": False, "recommendedLot": 0, "reasons": ["方向负期望", "运行快照通过"]},
                ]
            }, ensure_ascii=False), encoding="utf-8")
            runner = AutomationChainRunner(Path.cwd(), runtime, ["USDJPYc"], python_bin="python")
            summary = runner._summarize_policy(runner._policy_file())
            self.assertEqual(summary["opportunityCount"], 1)
            self.assertEqual(summary["blockedCount"], 1)
            self.assertEqual(summary["opportunities"][0]["entryModeZh"], "机会入场")
            self.assertIn("方向负期望", summary["blocked"][0]["reason"])

    def test_blocked_reasons_filter_positive_evidence(self):
        runner = AutomationChainRunner(Path.cwd(), "runtime", ["USDJPYc"], python_bin="python")
        reasons = runner._actionable_blockers(["USDJPY 运行快照可用", "运行快照通过", "快通道质量未通过：DEGRADED"])
        self.assertEqual(reasons, ["快通道质量未通过：DEGRADED"])

    def test_chain_steps_use_usdjpy_live_loop_as_source_of_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = AutomationChainRunner(Path.cwd(), tmp, ["USDJPYc"], python_bin="python")
            commands = "\n".join(" ".join(step.command) for step in runner.build_steps(send=True))
            self.assertIn("run_usdjpy_strategy_lab.py", commands)
            self.assertIn("run_usdjpy_live_loop.py", commands)
            self.assertIn("dry-run", commands)
            self.assertNotIn("run_auto_execution_policy.py", commands)

    def test_telegram_text_is_chinese_and_safe(self):
        report = {
            "stateZh": "阻断：证据不完整",
            "symbols": ["USDJPYc"],
            "singleSourceOfTruth": "USDJPY_LIVE_LOOP",
            "generatedAt": "2099-01-01T00:00:00Z",
            "steps": [{"labelZh": "P3-7 快通道质量", "ok": False, "summaryZh": "缺少质量文件"}],
            "missingEvidence": ["缺少 P3-7 快通道质量证据"],
            "blockedReasons": ["缺少运行快照"],
            "policySummary": {"opportunities": [], "blocked": []},
            "topLiveEligiblePolicy": {"strategy": "RSI_Reversal", "direction": "LONG", "entryMode": "OPPORTUNITY_ENTRY", "recommendedLot": 0.12},
            "dryRunDecision": {"decision": "本应机会入场", "strategy": "RSI_Reversal", "direction": "LONG"},
        }
        text = build_automation_telegram_text(report)
        self.assertIn("【QuantGod USDJPY 自动化闭环巡检】", text)
        self.assertIn("主状态来源", text)
        self.assertIn("不会下单", text)
        self.assertNotIn("OrderSend", text)


if __name__ == "__main__":
    unittest.main()
