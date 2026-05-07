from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List


def summarize_trades(trades: List[Dict[str, Any]], equity_curve: List[float]) -> Dict[str, Any]:
    profits = [float(item.get("profitR", 0.0)) for item in trades]
    wins = [item for item in profits if item > 0]
    losses = [item for item in profits if item < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_r = sum(profits)
    max_drawdown = _max_drawdown(equity_curve)
    mfe_values = [float(item.get("mfeR", 0.0)) for item in trades]
    capture_values = [
        max(0.0, min(1.0, float(item.get("profitR", 0.0)) / float(item.get("mfeR", 1.0))))
        for item in trades
        if float(item.get("mfeR", 0.0)) > 0
    ]
    return {
        "netR": round(net_r, 4),
        "netPips": round(sum(float(item.get("profitPips", 0.0)) for item in trades), 3),
        "profitFactor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else (round(gross_profit, 4) if gross_profit > 0 else 0.0),
        "winRate": round((len(wins) / len(profits)) * 100.0, 2) if profits else 0.0,
        "maxDrawdownR": round(max_drawdown, 4),
        "sharpe": round(_sharpe(profits), 4),
        "sortino": round(_sortino(profits), 4),
        "tradeCount": len(trades),
        "avgR": round(statistics.mean(profits), 4) if profits else 0.0,
        "medianR": round(statistics.median(profits), 4) if profits else 0.0,
        "lossStreak": _max_loss_streak(profits),
        "profitCaptureRatio": round(statistics.mean(capture_values), 4) if capture_values else 0.0,
        "maxAdverseR": round(min((float(item.get("maeR", 0.0)) for item in trades), default=0.0), 4),
        "maxFavorableR": round(max(mfe_values, default=0.0), 4),
    }


def _max_drawdown(equity: List[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return abs(worst)


def _sharpe(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    stdev = statistics.pstdev(values)
    if stdev <= 0:
        return 0.0
    return statistics.mean(values) / stdev * math.sqrt(len(values))


def _sortino(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    downside = [min(0.0, value) for value in values]
    downside_dev = statistics.pstdev(downside)
    if downside_dev <= 0:
        return 0.0
    return statistics.mean(values) / downside_dev * math.sqrt(len(values))


def _max_loss_streak(values: List[float]) -> int:
    streak = 0
    worst = 0
    for value in values:
        if value < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst

