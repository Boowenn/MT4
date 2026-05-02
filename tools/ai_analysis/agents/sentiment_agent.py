"""Phase 3 SentimentAgent for QuantGod AI Analysis V2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SentimentAgent:
    name = "sentiment"

    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        sentiment = snapshot.get("sentiment") or {}
        if not isinstance(sentiment, dict):
            sentiment = {}
        cot = sentiment.get("cot") or sentiment.get("cot_bias") or "unknown"
        volatility = sentiment.get("volatility") or sentiment.get("vix") or "unknown"
        positioning = sentiment.get("positioning") or sentiment.get("retail_positioning") or "unknown"
        score = float(sentiment.get("score") or 0.0)
        if score > 0.2:
            bias = "bullish"
        elif score < -0.2:
            bias = "bearish"
        else:
            bias = "neutral"
        return {
            "agent": self.name,
            "timestamp": _now(),
            "bias": bias,
            "score": round(score, 3),
            "inputs": {"cot": cot, "volatility": volatility, "positioning": positioning},
            "confidence": 0.25 if not sentiment else min(0.75, 0.35 + abs(score)),
            "reasoning": "Sentiment is derived from local snapshot fields; missing fields default to neutral.",
            "cost_usd": 0.0,
        }
