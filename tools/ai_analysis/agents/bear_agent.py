"""Bear-side debate agent for AI Analysis V2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_bear_points(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    technical = evidence.get("technical") or {}
    trend = technical.get("trend") or {}
    direction = str(technical.get("direction") or trend.get("consensus") or "").lower()
    if "bear" in direction or "sell" in direction:
        points.append({"source": "technical", "point": f"Technical direction has bearish evidence: {direction}", "weight": 0.35})
    sentiment = evidence.get("sentiment") or {}
    if str(sentiment.get("bias") or "").lower() == "bearish":
        points.append({"source": "sentiment", "point": "Sentiment score is bearish", "weight": 0.2})
    news = evidence.get("news") or {}
    if str(news.get("risk_level") or "").lower() in {"high", "critical"} or news.get("active_news_block"):
        points.append({"source": "news", "point": "High-impact news risk supports defensive/short-bias caution", "weight": 0.25})
    risk = evidence.get("risk") or {}
    if risk.get("kill_switch_active") or str(risk.get("risk_level") or "").lower() in {"medium_high", "high", "critical"}:
        points.append({"source": "risk", "point": "Risk layer raises caution or blocks trading", "weight": 0.3})
    return points


class BearAgent:
    name = "bear"

    async def argue(self, evidence: dict[str, Any]) -> dict[str, Any]:
        points = _extract_bear_points(evidence)
        conviction = min(0.9, sum(float(p.get("weight") or 0.0) for p in points))
        thesis = "Bear case is weak; no strong downside evidence."
        if conviction >= 0.45:
            thesis = "Bear case: downside or defensive HOLD is justified by current evidence."
        return {
            "agent": self.name,
            "timestamp": _now(),
            "thesis": thesis,
            "evidence": points,
            "counter_risks": ["oversold bounce", "bullish lower-timeframe reversal", "bear case fades if news risk clears"],
            "conviction": round(conviction, 3),
            "reasoning": "BearAgent only argues a case for DecisionAgent; it cannot trigger orders.",
        }
