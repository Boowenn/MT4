from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent, as_float, clamp, last_close, utc_now_iso


class DecisionAgent(BaseAgent):
    name = "decision"
    required_fields = (
        "agent",
        "action",
        "confidence",
        "entry_price",
        "stop_loss",
        "take_profit",
        "risk_reward_ratio",
        "position_size_suggestion",
        "reasoning",
        "key_factors",
        "governance_evidence",
        "total_cost_usd",
    )

    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._llm_json(context, max_tokens=3072)
            response["total_cost_usd"] = as_float(
                response.get("total_cost_usd"),
                _sum_costs(context),
            )
            return self._validate_or_raise(response)
        except Exception as error:
            if not self.use_fallback_on_error:
                raise
            return self._fallback(context, error)

    def _fallback(self, context: dict[str, Any], error: Exception | None = None) -> dict[str, Any]:
        technical = context.get("technical") or {}
        risk = context.get("risk") or {}
        snapshot = context.get("snapshot") or {}
        risk_score = as_float(risk.get("risk_score"), 1.0)
        tradeable = bool(risk.get("tradeable", False)) and not bool(risk.get("kill_switch_active", False))
        direction = str(technical.get("direction") or "neutral").lower()
        signal_strength = as_float(technical.get("signal_strength"), 0.0)
        action = "HOLD"
        if tradeable and risk_score < 0.65 and signal_strength >= 0.55:
            if "bullish" in direction:
                action = "BUY"
            elif "bearish" in direction:
                action = "SELL"
        confidence = clamp((signal_strength * 0.65) + ((1 - risk_score) * 0.35))
        price = last_close(snapshot)
        stop_loss = take_profit = risk_reward = None
        if action in {"BUY", "SELL"} and price:
            levels = technical.get("key_levels") or {}
            supports = [as_float(item) for item in levels.get("support", []) if as_float(item) > 0]
            resistances = [as_float(item) for item in levels.get("resistance", []) if as_float(item) > 0]
            if action == "BUY":
                stop_loss = min(supports) if supports else round(price * 0.995, 5)
                take_profit = max(resistances) if resistances else round(price * 1.01, 5)
            else:
                stop_loss = max(resistances) if resistances else round(price * 1.005, 5)
                take_profit = min(supports) if supports else round(price * 0.99, 5)
            loss = abs(price - stop_loss)
            reward = abs(take_profit - price)
            risk_reward = round(reward / loss, 3) if loss > 0 else None
        key_factors = [
            f"technical_direction={direction}",
            f"signal_strength={signal_strength:.2f}",
            f"risk_score={risk_score:.2f}",
            "AI output is advisory only; no order path is invoked.",
        ]
        report = {
            "agent": self.name,
            "timestamp": utc_now_iso(),
            "model": self.model or self.llm.default_model,
            "action": action,
            "confidence": round(confidence, 3),
            "entry_price": round(price, 5) if action in {"BUY", "SELL"} and price else None,
            "stop_loss": round(stop_loss, 5) if isinstance(stop_loss, (int, float)) else None,
            "take_profit": round(take_profit, 5) if isinstance(take_profit, (int, float)) else None,
            "risk_reward_ratio": risk_reward,
            "position_size_suggestion": "0.01" if action in {"BUY", "SELL"} else "0.00",
            "reasoning": "Fallback decision summary: hold unless technical confluence is strong and local risk is low.",
            "key_factors": key_factors,
            "suggested_wait_condition": None if action in {"BUY", "SELL"} else "Wait for stronger confluence and no active risk blockers.",
            "governance_evidence": {
                "route": "AI_ANALYSIS_ADVISORY",
                "supports_action": action != "HOLD",
                "advisory_only": True,
                "cannot_override_kill_switch": True,
                "note": "Governance may read this as extra evidence only; it must not promote/demote or execute by itself.",
            },
            "total_cost_usd": _sum_costs(context),
            "fallback": True,
        }
        if error:
            report["fallback_error"] = str(error)
        return report


def _sum_costs(context: dict[str, Any]) -> float:
    total = 0.0
    for key in ("technical", "risk"):
        value = context.get(key) or {}
        if isinstance(value, dict):
            total += as_float(value.get("cost_usd"), 0.0)
    return round(total, 6)
