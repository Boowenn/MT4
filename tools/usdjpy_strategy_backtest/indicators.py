from __future__ import annotations

from typing import Iterable, List, Optional, Tuple


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


def sma_values(values: Iterable[float], period: int) -> List[Optional[float]]:
    data = [float(item) for item in values]
    output: List[Optional[float]] = [None for _ in data]
    if period <= 0:
        return output
    running = 0.0
    for index, value in enumerate(data):
        running += value
        if index >= period:
            running -= data[index - period]
        if index >= period - 1:
            output[index] = running / period
    return output


def ema_values(values: Iterable[float], period: int) -> List[Optional[float]]:
    data = [float(item) for item in values]
    output: List[Optional[float]] = [None for _ in data]
    if period <= 0 or not data:
        return output
    alpha = 2.0 / (period + 1.0)
    ema = data[0]
    for index, value in enumerate(data):
        ema = (value * alpha) + (ema * (1.0 - alpha))
        if index >= period - 1:
            output[index] = ema
    return output


def bollinger_bands(values: Iterable[float], period: int = 20, deviations: float = 2.0) -> List[Tuple[Optional[float], Optional[float], Optional[float]]]:
    data = [float(item) for item in values]
    output: List[Tuple[Optional[float], Optional[float], Optional[float]]] = [(None, None, None) for _ in data]
    if period <= 1:
        return output
    for index in range(period - 1, len(data)):
        window = data[index - period + 1 : index + 1]
        mid = sum(window) / period
        variance = sum((item - mid) ** 2 for item in window) / period
        stdev = variance ** 0.5
        output[index] = (mid - deviations * stdev, mid, mid + deviations * stdev)
    return output


def macd_values(values: Iterable[float], fast: int = 12, slow: int = 26, signal: int = 9) -> List[Tuple[Optional[float], Optional[float], Optional[float]]]:
    data = [float(item) for item in values]
    fast_ema = ema_values(data, fast)
    slow_ema = ema_values(data, slow)
    macd_line: List[Optional[float]] = []
    for fast_value, slow_value in zip(fast_ema, slow_ema):
        macd_line.append(None if fast_value is None or slow_value is None else fast_value - slow_value)
    signal_input = [0.0 if item is None else item for item in macd_line]
    signal_line = ema_values(signal_input, signal)
    output: List[Tuple[Optional[float], Optional[float], Optional[float]]] = []
    for macd_value, signal_value in zip(macd_line, signal_line):
        hist = None if macd_value is None or signal_value is None else macd_value - signal_value
        output.append((macd_value, signal_value, hist))
    return output


def atr_values(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float], period: int = 14) -> List[Optional[float]]:
    high_values = [float(item) for item in highs]
    low_values = [float(item) for item in lows]
    close_values = [float(item) for item in closes]
    output: List[Optional[float]] = [None for _ in close_values]
    true_ranges: List[float] = []
    for index, close in enumerate(close_values):
        if index == 0:
            tr = high_values[index] - low_values[index]
        else:
            previous_close = close_values[index - 1]
            tr = max(
                high_values[index] - low_values[index],
                abs(high_values[index] - previous_close),
                abs(low_values[index] - previous_close),
            )
        true_ranges.append(tr)
        if index == period - 1:
            output[index] = sum(true_ranges[-period:]) / period
        elif index >= period and output[index - 1] is not None:
            output[index] = ((output[index - 1] * (period - 1)) + tr) / period
    return output
