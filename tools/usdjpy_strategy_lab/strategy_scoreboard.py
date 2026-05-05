from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Any, Dict, Iterable, List, Tuple

from .data_loader import load_evidence_rows
from .schema import (
    DEFAULT_STRATEGIES,
    DIRECTIONS,
    FOCUS_SYMBOL,
    RouteScore,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PAUSED,
    STATUS_RUNNABLE,
    STATUS_WATCH_ONLY,
    assert_no_secret_or_execution_flags,
    utc_now_iso,
)


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo))


def _loss_streak(values: List[float]) -> int:
    streak = 0
    for value in reversed(values):
        if value < 0:
            streak += 1
        else:
            break
    return streak


def _score(sample_count: int, win_rate: float, avg_r: float, profit_factor: float, capture: float, loss_streak: int) -> float:
    score = 0.0
    score += min(sample_count, 30) / 30 * 15
    score += win_rate * 35
    score += max(-1.0, min(1.0, avg_r / 5.0)) * 20 + 10
    score += min(profit_factor, 3.0) / 3.0 * 15
    score += max(0.0, min(1.0, capture)) * 15
    score -= min(loss_streak, 5) * 5
    return round(max(0.0, min(100.0, score)), 2)


def _classify(sample_count: int, win_rate: float, avg_r: float, profit_factor: float, loss_streak: int, min_samples: int) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if sample_count < min_samples:
        reasons.append(f"样本不足：{sample_count}/{min_samples}")
        return STATUS_INSUFFICIENT_DATA, reasons
    if loss_streak >= 4:
        reasons.append(f"连续亏损 {loss_streak} 条，暂停该方向")
        return STATUS_PAUSED, reasons
    if win_rate < 0.38:
        reasons.append(f"胜率过低：{win_rate:.1%}")
        return STATUS_PAUSED, reasons
    if avg_r < -0.25:
        reasons.append(f"平均结果为负：{avg_r:.2f}")
        return STATUS_PAUSED, reasons
    if win_rate >= 0.52 and avg_r > 0 and profit_factor >= 1.05:
        reasons.append("近期样本为正，可进入 USDJPY 策略候选")
        return STATUS_RUNNABLE, reasons
    reasons.append("表现未恶化，但仍需影子观察")
    return STATUS_WATCH_ONLY, reasons


def build_strategy_scoreboard(runtime_dir, *, min_samples: int = 5) -> Dict[str, Any]:
    rows = load_evidence_rows(runtime_dir)
    buckets: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        strategy = row.get("strategy") or "UNKNOWN_STRATEGY"
        direction = row.get("direction") if row.get("direction") in DIRECTIONS else "UNKNOWN"
        regime = row.get("regime") or "UNKNOWN"
        timeframe = row.get("timeframe") or "UNKNOWN"
        if strategy == "UNKNOWN_STRATEGY" or direction == "UNKNOWN":
            continue
        buckets[(strategy, direction, regime, timeframe)].append(row)

    routes: List[RouteScore] = []
    for (strategy, direction, regime, timeframe), items in buckets.items():
        pnl = [float(item.get("pnl") or 0.0) for item in items]
        mfe = [max(0.0, float(item.get("mfe") or 0.0)) for item in items]
        mae = [max(0.0, float(item.get("mae") or 0.0)) for item in items]
        positive = [value for value in pnl if value > 0]
        negative = [abs(value) for value in pnl if value < 0]
        sample_count = len(pnl)
        wins = len(positive)
        win_rate = wins / sample_count if sample_count else 0.0
        avg_r = sum(pnl) / sample_count if sample_count else 0.0
        profit_factor = (sum(positive) / sum(negative)) if negative and sum(negative) > 0 else (999.0 if positive else 0.0)
        mfe_p50 = _percentile(mfe, 0.50)
        mfe_p70 = _percentile(mfe, 0.70)
        mae_p70 = _percentile(mae, 0.70)
        capture = (sum(max(0.0, value) for value in pnl) / sum(mfe)) if sum(mfe) > 0 else 0.0
        loss_streak = _loss_streak(pnl)
        status, reasons = _classify(sample_count, win_rate, avg_r, profit_factor, loss_streak, min_samples)
        score = _score(sample_count, win_rate, avg_r, profit_factor if profit_factor != 999.0 else 3.0, capture, loss_streak)
        routes.append(RouteScore(
            symbol=FOCUS_SYMBOL,
            strategy=strategy,
            direction=direction,
            regime=regime,
            timeframe=timeframe,
            sampleCount=sample_count,
            winRate=round(win_rate, 4),
            avgR=round(avg_r, 4),
            avgPips=round(avg_r, 4),
            profitFactor=round(min(profit_factor, 999.0), 4),
            mfeP50=round(mfe_p50, 4),
            mfeP70=round(mfe_p70, 4),
            maeP70=round(mae_p70, 4),
            mfeCaptureRate=round(capture, 4),
            lossStreak=loss_streak,
            status=status,
            score=score,
            reasons=reasons,
        ))

    if not routes:
        for strategy in DEFAULT_STRATEGIES:
            for direction in DIRECTIONS:
                routes.append(RouteScore(
                    symbol=FOCUS_SYMBOL,
                    strategy=strategy,
                    direction=direction,
                    status=STATUS_INSUFFICIENT_DATA,
                    reasons=["没有找到 USDJPY 专用样本，必须先积累影子结果"],
                ))

    routes.sort(key=lambda item: (item.status != STATUS_RUNNABLE, -item.score, item.strategy, item.direction))
    payload = {
        "schema": "quantgod.usdjpy_strategy_scoreboard.v1",
        "generatedAt": utc_now_iso(),
        "focusOnly": True,
        "symbol": FOCUS_SYMBOL,
        "minSamples": min_samples,
        "routeCount": len(routes),
        "routes": [route.to_dict() for route in routes],
        "safety": {
            "readOnlyDataPlane": True,
            "advisoryOnly": True,
            "dryRunOnly": True,
            "orderSendAllowed": False,
            "livePresetMutationAllowed": False,
        },
    }
    assert_no_secret_or_execution_flags(payload)
    return payload
