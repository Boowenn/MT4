"""Phase 3 NewsAgent for QuantGod AI Analysis V2.

Trusts EA economic calendar outputs — EA is the ground truth for news blocking.
NewsAgent only translates EA data for AI consumption; it does NOT re-judge impact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class NewsAgent:
    name = "news"

    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        news = snapshot.get("news") or {}
        if not isinstance(news, dict):
            news = {}

        blocked = bool(news.get("blocked") or news.get("active"))
        has_event = bool(news.get("eventName") or news.get("eventCode"))
        minutes_to = int(news.get("minutesToEvent") or 0)
        minutes_since = int(news.get("minutesSinceEvent") or 0)
        phase = str(news.get("phase") or "").upper()

        # Trust EA's judgment — don't re-evaluate impact
        if blocked:
            risk_level = "high"
            bias = "event_risk"
        elif has_event and 0 < minutes_to <= 60:
            risk_level = "medium"
            bias = "event_risk"
        elif has_event:
            risk_level = "low"
            bias = "neutral"
        else:
            risk_level = "low"
            bias = "neutral"

        current_event = None
        if has_event:
            current_event = {
                "name": news.get("eventName"),
                "label": news.get("eventLabel"),
                "code": news.get("eventCode"),
                "minutes_to": minutes_to,
                "minutes_since": minutes_since,
                "phase": phase,
                "actual": news.get("actual"),
                "forecast": news.get("forecast"),
                "previous": news.get("previous"),
            }

        if blocked:
            reasoning = news.get("reason") or "EA has identified news block active"
        elif has_event:
            reasoning = news.get("reason") or f"{minutes_to} minutes to next USD event"
        else:
            reasoning = "EA economic calendar shows no near-term USD events"

        return {
            "agent": self.name,
            "timestamp": _now(),
            "risk_level": risk_level,
            "macro_bias": bias,
            "active_news_block": blocked,
            "events_considered": 1 if has_event else 0,
            "high_impact_events": [current_event] if risk_level in ("high", "medium") and current_event else [],
            "current_event": current_event,
            "reasoning": reasoning,
            "cost_usd": 0.0,
        }
