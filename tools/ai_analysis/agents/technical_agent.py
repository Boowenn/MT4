from __future__ import annotations

from statistics import mean
from typing import Any

from ..llm_client import LLMClientError
from .base_agent import BaseAgent, as_float, clamp, utc_now_iso


class TechnicalAgent(BaseAgent):
    name = "technical"
    required_fields = (
        "agent",
        "symbol",
        "trend",
        "indicators",
        "key_levels",
        "signal_strength",
        "direction",
        "reasoning",
    )

    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._llm_json(context)
            return self._validate_or_raise(response)
        except Exception as error:
            if not self.use_fallback_on_error:
                raise
            return self._fallback(context, error)

    def _fallback(self, snapshot: dict[str, Any], error: Exception | None = None) -> dict[str, Any]:
        symbol = str(snapshot.get("symbol") or snapshot.get("brokerSymbol") or "UNKNOWN")
        tf_keys = {
            "m15": "kline_m15",
            "h1": "kline_h1",
            "h4": "kline_h4",
            "d1": "kline_d1",
        }
        trend: dict[str, str] = {}
        trend_scores: list[int] = []
        for tf, key in tf_keys.items():
            bars = _bars(snapshot.get(key))
            tf_trend, tf_score = _trend_for_bars(bars)
            trend[tf] = tf_trend
            trend_scores.append(tf_score)
        score_sum = sum(trend_scores)
        if score_sum >= 2:
            consensus = "bullish"
            direction = "bullish"
        elif score_sum <= -2:
            consensus = "bearish"
            direction = "bearish"
        elif score_sum > 0:
            consensus = "mixed_bullish"
            direction = "neutral_bullish"
        elif score_sum < 0:
            consensus = "mixed_bearish"
            direction = "neutral_bearish"
        else:
            consensus = "mixed_neutral"
            direction = "neutral"
        trend["consensus"] = consensus

        h1_bars = _bars(snapshot.get("kline_h1")) or _bars(snapshot.get("kline_m15"))
        closes = [bar["close"] for bar in h1_bars]
        rsi = _rsi(closes[-80:]) if len(closes) >= 15 else None
        short_ema = _ema(closes, 9)
        long_ema = _ema(closes, 21)
        ma_signal = "none"
        if len(closes) >= 22:
            prev_short = _ema(closes[:-1], 9)
            prev_long = _ema(closes[:-1], 21)
            if prev_short is not None and prev_long is not None and short_ema is not None and long_ema is not None:
                if prev_short <= prev_long and short_ema > long_ema:
                    ma_signal = "golden_cross"
                elif prev_short >= prev_long and short_ema < long_ema:
                    ma_signal = "death_cross"
        resistance, support = _key_levels(h1_bars)
        strength = clamp(0.25 + 0.15 * abs(score_sum))
        if ma_signal in {"golden_cross", "death_cross"}:
            strength = clamp(strength + 0.15)
        if rsi is not None and (rsi >= 70 or rsi <= 30):
            strength = clamp(strength + 0.1)

        report = {
            "agent": self.name,
            "symbol": symbol,
            "timestamp": utc_now_iso(),
            "model": self.model or self.llm.default_model,
            "timeframes_analyzed": ["M15", "H1", "H4", "D1"],
            "trend": trend,
            "indicators": {
                "ma_cross": {"signal": ma_signal, "tf": "H1", "bars_ago": 0 if ma_signal != "none" else None},
                "rsi": {"h1": round(rsi, 2) if rsi is not None else None, "zone": _rsi_zone(rsi)},
                "macd": {"h1_histogram": None, "divergence": "not_evaluated_fallback"},
                "bollinger": {"h1_position": "not_evaluated_fallback", "squeeze": None},
            },
            "key_levels": {"resistance": resistance, "support": support},
            "signal_strength": round(strength, 3),
            "direction": direction,
            "reasoning": "Fallback technical summary from local OHLC bars; LLM output unavailable or invalid.",
            "cost_usd": 0.0,
            "fallback": True,
        }
        if error:
            report["fallback_error"] = str(error)
        return report


def _bars(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, float]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        close = as_float(item.get("close"), 0.0)
        if close <= 0:
            continue
        rows.append(
            {
                "open": as_float(item.get("open"), close),
                "high": as_float(item.get("high"), close),
                "low": as_float(item.get("low"), close),
                "close": close,
            }
        )
    return rows


def _trend_for_bars(bars: list[dict[str, float]]) -> tuple[str, int]:
    closes = [bar["close"] for bar in bars]
    if len(closes) < 21:
        return "neutral", 0
    short = _ema(closes, 9)
    long = _ema(closes, 21)
    recent_slope = closes[-1] - closes[max(0, len(closes) - 10)]
    if short is None or long is None:
        return "neutral", 0
    threshold = max(abs(long) * 0.0005, 1e-9)
    if short > long + threshold and recent_slope >= 0:
        return "bullish", 1
    if short < long - threshold and recent_slope <= 0:
        return "bearish", -1
    return "neutral", 0


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    current = mean(values[:period])
    for value in values[period:]:
        current = value * alpha + current * (1 - alpha)
    return current


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for prev, cur in zip(values[-period - 1 : -1], values[-period:]):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _rsi_zone(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 70:
        return "overbought"
    if value <= 30:
        return "oversold"
    return "neutral"


def _key_levels(bars: list[dict[str, float]]) -> tuple[list[float], list[float]]:
    if not bars:
        return [], []
    recent = bars[-60:]
    highs = sorted({round(bar["high"], 5) for bar in recent}, reverse=True)
    lows = sorted({round(bar["low"], 5) for bar in recent})
    return highs[:2], lows[:2]
