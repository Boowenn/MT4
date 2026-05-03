from __future__ import annotations

import unittest

from tools.ai_analysis.advisory_fusion import compact_fusion_payload, fuse_advisory_report
from tools.ai_analysis.deepseek_validator import validate_deepseek_advice


def base_report(*, fallback: bool = False, runtime_fresh: bool = True, action: str = "HOLD", kill_switch: bool = False) -> dict:
    return {
        "ok": True,
        "schema": "quantgod.ai_analysis.v2",
        "generatedAt": "2026-05-03T00:00:00Z",
        "symbol": "USDJPYc",
        "timeframes": ["M15", "H1", "H4", "D1"],
        "snapshot": {
            "source": "hfm_ea_runtime",
            "fallback": fallback,
            "runtimeFresh": runtime_fresh,
            "runtimeAgeSeconds": 12,
            "current_price": {"bid": 155.1, "ask": 155.12, "last": 155.11, "spread": 0.02},
        },
        "technical": {"direction": "bullish" if action == "BUY" else "neutral"},
        "risk": {"risk_level": "medium", "kill_switch_active": kill_switch, "tradeable": True, "factors": []},
        "news": {"risk_level": "low"},
        "sentiment": {"bias": "neutral"},
        "bull_case": {"thesis": "bull thesis", "conviction": 0.4},
        "bear_case": {"thesis": "bear thesis", "conviction": 0.3},
        "decision": {"action": action, "confidence": 0.62, "reasoning": "local decision"},
        "safety": {"advisoryOnly": True, "orderSendAllowed": False},
    }


def good_deepseek(verdict: str = "观望，不开新仓") -> dict:
    return {
        "ok": True,
        "status": "ok",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "advice": {
            "headline": "等待确认",
            "verdict": verdict,
            "signalGrade": "观察级",
            "confidencePct": "62%",
            "marketSummary": "运行证据有效，但仍需复核。",
            "technicalSummary": "趋势中性偏多。",
            "bullCase": "多头需要突破确认。",
            "bearCase": "空头需要跌破支撑确认。",
            "newsRisk": "暂无重大新闻阻断。",
            "sentimentPositioning": "情绪中性。",
            "planStatus": "仅观察，等待程序风控确认。",
            "entryZone": "不生成，等待确认。",
            "targets": ["不生成", "不生成", "不生成"],
            "defense": "不生成",
            "riskReward": "未评估",
            "positionAdvice": "不构成下单建议。",
            "invalidation": "证据不足时继续观望。",
            "watchPoints": ["等待 runtimeFresh", "确认点差正常"],
            "riskNotes": ["只读 advisory-only", "Telegram push-only"],
            "executionBoundary": "仅建议，不执行交易。",
        },
    }


class DeepSeekValidatorTests(unittest.TestCase):
    def test_fallback_snapshot_forces_observation_advice(self) -> None:
        report = base_report(fallback=True, runtime_fresh=False, action="BUY")
        payload = good_deepseek("偏多观察")
        payload["advice"]["entryZone"] = "155.10 附近买入"
        result = validate_deepseek_advice(report, payload)
        self.assertEqual(result["status"], "downgraded")
        self.assertIn("fallback_snapshot", result["reasons"])
        advice = result["effectiveAdvice"]
        self.assertEqual(advice["verdict"], "观望，不开新仓")
        self.assertIn("暂停", advice["planStatus"])
        self.assertEqual(advice["targets"], ["不生成", "不生成", "不生成"])

    def test_execution_language_is_rejected_even_when_runtime_is_fresh(self) -> None:
        report = base_report(fallback=False, runtime_fresh=True, action="BUY")
        payload = good_deepseek("偏多")
        payload["advice"]["positionAdvice"] = "立即市价买入并加杠杆"
        result = validate_deepseek_advice(report, payload)
        self.assertEqual(result["status"], "downgraded")
        self.assertIn("execution_language_detected", result["reasons"])
        self.assertEqual(result["effectiveAdvice"]["verdict"], "观望，不开新仓")

    def test_local_and_deepseek_direction_conflict_forces_hold(self) -> None:
        report = base_report(fallback=False, runtime_fresh=True, action="BUY")
        payload = good_deepseek("偏空观察，等待确认")
        result = validate_deepseek_advice(report, payload)
        self.assertEqual(result["status"], "downgraded")
        self.assertIn("local_deepseek_conflict", result["reasons"])
        fused = fuse_advisory_report({**report, "deepseek_advice": payload})
        self.assertEqual(fused["advisory_fusion"]["finalAction"], "HOLD")

    def test_valid_runtime_and_compatible_deepseek_can_watch_long(self) -> None:
        report = base_report(fallback=False, runtime_fresh=True, action="BUY")
        payload = good_deepseek("偏多观察，等待程序风控确认")
        result = validate_deepseek_advice(report, payload)
        self.assertEqual(result["status"], "pass")
        fused = fuse_advisory_report({**report, "deepseek_advice": payload})
        self.assertEqual(fused["advisory_fusion"]["finalAction"], "WATCH_LONG")
        compact = compact_fusion_payload(fused)
        self.assertEqual(compact["validatorStatus"], "pass")
        self.assertIn("advisory-only", compact["executionBoundary"])

    def test_missing_deepseek_degrades_but_keeps_safety_flags_false(self) -> None:
        report = base_report(fallback=False, runtime_fresh=True, action="HOLD")
        fused = fuse_advisory_report({**report, "deepseek_advice": {"ok": False, "status": "missing_api_key"}})
        self.assertEqual(fused["advisory_fusion"]["finalAction"], "HOLD")
        self.assertFalse(fused["advisory_fusion"]["safety"]["orderSendAllowed"])
        self.assertFalse(fused["advisory_fusion"]["safety"]["telegramCommandExecutionAllowed"])


if __name__ == "__main__":
    unittest.main()
