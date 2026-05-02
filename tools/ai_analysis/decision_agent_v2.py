"""DecisionAgent V2 fallback logic for debate-aware AI reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class DecisionAgentV2:
    name = "decision_v2"

    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        bull = context.get("bull_case") or {}
        bear = context.get("bear_case") or {}
        risk = context.get("risk") or {}
        technical = context.get("technical") or {}
        bull_conv = float(bull.get("conviction") or 0.0)
        bear_conv = float(bear.get("conviction") or 0.0)
        risk_level = str(risk.get("risk_level") or "medium").lower()
        kill = bool(risk.get("kill_switch_active"))
        action = "HOLD"
        confidence = max(bull_conv, bear_conv, 0.25)
        if not kill and risk_level not in {"high", "critical"}:
            if bull_conv >= bear_conv + 0.18 and bull_conv >= 0.45:
                action = "BUY"
            elif bear_conv >= bull_conv + 0.18 and bear_conv >= 0.45:
                action = "SELL"
        if kill or risk_level in {"high", "critical"}:
            action = "HOLD"
            confidence = max(confidence, 0.65)
        return {
            "agent": self.name,
            "timestamp": utc_now(),
            "action": action,
            "confidence": round(min(0.95, confidence), 3),
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward_ratio": None,
            "position_size_suggestion": "0.01",
            "debate_summary": {
                "bull_conviction": round(bull_conv, 3),
                "bear_conviction": round(bear_conv, 3),
                "bull_thesis": bull.get("thesis"),
                "bear_thesis": bear.get("thesis"),
            },
            "key_factors": [
                f"Bull conviction {bull_conv:.2f}",
                f"Bear conviction {bear_conv:.2f}",
                f"Risk level {risk_level}",
                f"Technical direction {technical.get('direction') or technical.get('trend', {}).get('consensus', 'unknown')}",
            ],
            "reasoning": "DecisionAgent V2 combines Technical/Risk/News/Sentiment evidence plus Bull/Bear debate. It remains advisory only.",
            "governance_evidence": {
                "advisoryOnly": True,
                "supports_action": action != "HOLD",
                "note": "V2 debate evidence for Governance review only; cannot promote/demote/execute.",
            },
            "total_cost_usd": 0.0,
        }
