from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Any

from .schema import PolicyThresholds

def _consecutive_losses(items: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(items):
        if row.get("scoreR", 0.0) < 0:
            count += 1
        else:
            break
    return count

def _status_for(samples: int, win_rate: float, avg_r: float, consecutive_losses: int, thresholds: PolicyThresholds) -> tuple[str, str, float]:
    if samples < thresholds.min_samples:
        return "INSUFFICIENT_DATA", "样本不足，仅允许观察复核", 0.0
    if avg_r <= thresholds.pause_avg_score_r:
        return "PAUSED", "近期平均影子收益为负，暂停该方向建议", 0.0
    if win_rate < thresholds.pause_win_rate:
        return "PAUSED", "近期胜率低于暂停阈值，暂停该方向建议", 0.0
    if consecutive_losses >= thresholds.max_consecutive_losses:
        return "PAUSED", "连续负向样本过多，暂停该方向建议", 0.0
    if samples >= thresholds.active_min_samples and win_rate >= thresholds.min_win_rate and avg_r >= thresholds.min_avg_score_r:
        return "ACTIVE_SHADOW_OK", "影子样本通过，允许继续观察", min(1.5, max(0.1, 0.5 + avg_r))
    return "WATCH_ONLY", "样本未达主动标准，仅保留观察", 0.25

def score_routes(observations: list[dict[str, Any]], thresholds: PolicyThresholds) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for obs in observations:
        direction = obs.get("direction", "FLAT")
        if direction == "FLAT":
            continue
        key = (
            str(obs.get("symbol") or "UNKNOWN"),
            str(obs.get("strategy") or "UNKNOWN"),
            direction,
            str(obs.get("regime") or "UNKNOWN"),
        )
        groups[key].append(obs)

    scored: list[dict[str, Any]] = []
    for (symbol, strategy, direction, regime), items in sorted(groups.items()):
        samples = len(items)
        wins = sum(1 for item in items if item.get("scoreR", 0.0) > 0)
        win_rate = wins / samples if samples else 0.0
        avg_r = mean(float(item.get("scoreR", 0.0)) for item in items) if items else 0.0
        median_r = median(float(item.get("scoreR", 0.0)) for item in items) if items else 0.0
        avg_mfe = mean(abs(float(item.get("mfe", 0.0))) for item in items) if items else 0.0
        avg_mae = mean(abs(float(item.get("mae", 0.0))) for item in items) if items else 0.0
        consecutive_losses = _consecutive_losses(items)
        status, reason, risk_multiplier = _status_for(samples, win_rate, avg_r, consecutive_losses, thresholds)
        scored.append({
            "symbol": symbol,
            "strategy": strategy,
            "direction": direction,
            "directionLabel": "买入观察" if direction == "LONG" else "卖出观察",
            "regime": regime,
            "samples": samples,
            "wins": wins,
            "losses": samples - wins,
            "winRate": round(win_rate, 4),
            "avgScoreR": round(avg_r, 4),
            "medianScoreR": round(median_r, 4),
            "avgMfe": round(avg_mfe, 4),
            "avgMae": round(avg_mae, 4),
            "consecutiveLosses": consecutive_losses,
            "state": status,
            "riskMultiplier": round(risk_multiplier, 4),
            "reason": reason,
        })
    scored.sort(key=lambda row: (row["state"] == "PAUSED", -row["avgScoreR"], -row["winRate"], row["symbol"]))
    return scored

def best_route_for_symbol(scored_routes: list[dict[str, Any]], symbol: str, direction: str | None = None) -> dict[str, Any] | None:
    routes = [r for r in scored_routes if str(r.get("symbol", "")).upper() == symbol.upper()]
    if direction:
        routes = [r for r in routes if r.get("direction") == direction]
    if not routes:
        return None
    allowed = [r for r in routes if r.get("state") in {"ACTIVE_SHADOW_OK", "WATCH_ONLY"}]
    source = allowed or routes
    return sorted(source, key=lambda r: (r.get("state") != "ACTIVE_SHADOW_OK", -float(r.get("avgScoreR", 0)), -float(r.get("winRate", 0))))[0]
