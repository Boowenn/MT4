from __future__ import annotations

from typing import Iterable, List, Optional


def rsi_values(closes: Iterable[float], period: int) -> List[Optional[float]]:
    """Return Wilder RSI values aligned with the input close series."""
    values = [float(item) for item in closes]
    if period < 2 or len(values) <= period:
        return [None for _ in values]

    output: List[Optional[float]] = [None for _ in values]
    gains: List[float] = []
    losses: List[float] = []
    for index in range(1, period + 1):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    output[period] = _rsi(avg_gain, avg_loss)

    for index in range(period + 1, len(values)):
        delta = values[index] - values[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        output[index] = _rsi(avg_gain, avg_loss)
    return output


def _rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs_value = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs_value))

