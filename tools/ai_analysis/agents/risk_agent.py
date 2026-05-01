from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent, as_float, clamp, utc_now_iso


class RiskAgent(BaseAgent):
    name = "risk"
    required_fields = (
        "agent",
        "risk_score",
        "risk_level",
        "factors",
        "kill_switch_active",
        "position_exposure",
        "tradeable",
        "reasoning",
    )

    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._llm_json(context, max_tokens=3072)
            return self._validate_or_raise(response)
        except Exception as error:
            if not self.use_fallback_on_error:
                raise
            return self._fallback(context, error)

    def _fallback(self, snapshot: dict[str, Any], error: Exception | None = None) -> dict[str, Any]:
        factors: list[dict[str, str]] = []
        score = 0.15
        kill_active = _kill_switch_active(snapshot.get("kill_switch_status"))
        if kill_active:
            score += 0.65
            factors.append(
                {
                    "factor": "kill_switch_active",
                    "severity": "critical",
                    "detail": "One or more exported kill-switch flags are active.",
                }
            )
        news = snapshot.get("news_filter_status") or snapshot.get("news") or {}
        if isinstance(news, dict) and _truthy(news.get("blockActive") or news.get("blocked") or news.get("preBlockActive")):
            score += 0.3
            factors.append(
                {
                    "factor": "news_block",
                    "severity": "high",
                    "detail": str(news.get("nextEvent") or news.get("reason") or "News filter is active."),
                }
            )
        consecutive = snapshot.get("consecutive_loss_state") or {}
        if isinstance(consecutive, dict) and _truthy(consecutive.get("cooldownActive") or consecutive.get("paused")):
            score += 0.25
            factors.append(
                {
                    "factor": "consecutive_loss_cooldown",
                    "severity": "high",
                    "detail": "Consecutive-loss cooldown is active.",
                }
            )
        daily_pnl = as_float(snapshot.get("daily_pnl"), 0.0)
        if daily_pnl < 0:
            score += min(0.2, abs(daily_pnl) / 100.0)
            factors.append(
                {
                    "factor": "negative_daily_pnl",
                    "severity": "medium",
                    "detail": f"Daily realized PnL is negative: {daily_pnl:.2f}.",
                }
            )
        positions = snapshot.get("open_positions") or []
        position_count = len(positions) if isinstance(positions, list) else 0
        if position_count >= 3:
            score += 0.18
            factors.append(
                {
                    "factor": "open_position_count",
                    "severity": "medium",
                    "detail": f"{position_count} open positions are already present.",
                }
            )
        if not factors:
            factors.append(
                {
                    "factor": "baseline",
                    "severity": "low",
                    "detail": "No active local risk blocker found in fallback inputs.",
                }
            )
        score = clamp(score)
        level = _risk_level(score)
        tradeable = not kill_active and score < 0.85
        report = {
            "agent": self.name,
            "timestamp": utc_now_iso(),
            "model": self.model or self.llm.default_model,
            "risk_score": round(score, 3),
            "risk_level": level,
            "factors": factors,
            "kill_switch_active": kill_active,
            "position_exposure": _position_exposure(position_count),
            "tradeable": tradeable,
            "reasoning": "Fallback risk summary from local dashboard/runtime state; LLM output unavailable or invalid.",
            "cost_usd": 0.0,
            "fallback": True,
        }
        if error:
            report["fallback_error"] = str(error)
        return report


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "active", "blocked", "on"}


def _kill_switch_active(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key).lower()
            if "kill" in name or "pause" in name or "blocked" in name:
                if _truthy(item):
                    return True
            if isinstance(item, dict) and _kill_switch_active(item):
                return True
    if isinstance(value, list):
        return any(_kill_switch_active(item) for item in value)
    return False


def _risk_level(score: float) -> str:
    if score >= 0.9:
        return "critical"
    if score >= 0.75:
        return "high"
    if score >= 0.55:
        return "medium_high"
    if score >= 0.3:
        return "medium"
    return "low"


def _position_exposure(count: int) -> str:
    if count >= 5:
        return "high"
    if count >= 3:
        return "medium_high"
    if count >= 1:
        return "low"
    return "none"
