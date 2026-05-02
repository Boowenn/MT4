"""Phase 3 NewsAgent for QuantGod AI Analysis V2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class NewsAgent:
    name = "news"

    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        news = snapshot.get("news") or snapshot.get("calendar") or {}
        events = news.get("events") if isinstance(news, dict) else None
        events = events if isinstance(events, list) else []
        high = [e for e in events if str(e.get("impact") or e.get("severity") or "").lower() in {"high", "red", "critical"}]
        active_block = bool(news.get("active") or news.get("blocked") or news.get("news_block_active")) if isinstance(news, dict) else False
        risk_level = "high" if active_block or high else "low"
        bias = "neutral"
        if high:
            bias = "event_risk"
        return {
            "agent": self.name,
            "timestamp": _now(),
            "risk_level": risk_level,
            "macro_bias": bias,
            "active_news_block": active_block,
            "events_considered": len(events),
            "high_impact_events": high[:5],
            "reasoning": "High-impact event risk detected" if risk_level == "high" else "No high-impact news evidence found in local snapshot",
            "cost_usd": 0.0,
        }
