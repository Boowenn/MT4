"""Bull-side debate agent for AI Analysis V2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_bull_points(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    technical = evidence.get("technical") or {}
    trend = technical.get("trend") or {}
    direction = str(technical.get("direction") or trend.get("consensus") or "").lower()
    if "bull" in direction or "buy" in direction:
        points.append({"source": "technical", "point": f"Technical direction has bullish evidence: {direction}", "weight": 0.35})
    sentiment = evidence.get("sentiment") or {}
    if str(sentiment.get("bias") or "").lower() == "bullish":
        points.append({"source": "sentiment", "point": "Sentiment score is bullish", "weight": 0.2})
    news = evidence.get("news") or {}
    if str(news.get("risk_level") or "").lower() in {"low", "medium"}:
        points.append({"source": "news", "point": "No blocking high-impact news risk", "weight": 0.15})
    risk = evidence.get("risk") or {}
    if risk.get("tradeable") is True or str(risk.get("risk_level") or "").lower() in {"low", "medium"}:
        points.append({"source": "risk", "point": "Risk layer does not block trading", "weight": 0.2})
    return points


class BullAgent:
    name = "bull"

    async def argue(self, evidence: dict[str, Any]) -> dict[str, Any]:
        points = _extract_bull_points(evidence)
        conviction = min(0.9, sum(float(p.get("weight") or 0.0) for p in points))
        thesis = "Bull case is weak; wait for clearer upside evidence."
        if conviction >= 0.45:
            thesis = "Bull case: upside continuation is plausible if risk gates remain open."
        return {
            "agent": self.name,
            "timestamp": _now(),
            "thesis": thesis,
            "evidence": points,
            "counter_risks": ["higher-timeframe conflict", "news/event risk", "low conviction if signal strength remains weak"],
            "conviction": round(conviction, 3),
            "reasoning": "BullAgent only argues a case for DecisionAgent; it cannot trigger orders.",
        }
