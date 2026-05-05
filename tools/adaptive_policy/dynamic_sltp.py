from __future__ import annotations

from statistics import median
from typing import Any

from .schema import PolicyThresholds

def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * pct))
    return float(ordered[max(0, min(index, len(ordered) - 1))])

def build_dynamic_sltp_plan(
    scored_route: dict[str, Any] | None,
    observations: list[dict[str, Any]],
    thresholds: PolicyThresholds,
    symbol: str | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    if scored_route:
        symbol = symbol or scored_route.get("symbol")
        direction = direction or scored_route.get("direction")
    relevant = [
        obs for obs in observations
        if (not symbol or str(obs.get("symbol", "")).upper() == str(symbol).upper())
        and (not direction or obs.get("direction") == direction)
    ][-thresholds.max_plan_records:]

    mfes = [abs(float(obs.get("mfe", 0.0))) for obs in relevant if abs(float(obs.get("mfe", 0.0))) > 0]
    maes = [abs(float(obs.get("mae", 0.0))) for obs in relevant if abs(float(obs.get("mae", 0.0))) > 0]
    scores = [float(obs.get("scoreR", 0.0)) for obs in relevant]

    if not relevant:
        basis = "样本不足，使用保守 ATR 倍数模板"
    else:
        basis = "基于近期 MFE/MAE 影子样本"

    stop_basis = _percentile(maes, 0.70) or 1.35
    tp1 = _percentile(mfes, 0.50) or 0.70
    tp2 = _percentile(mfes, 0.70) or 1.20
    tp3 = _percentile(mfes, 0.85) or 1.80
    avg_score = sum(scores) / len(scores) if scores else 0.0

    risk_mode = "保守"
    if scored_route and scored_route.get("state") == "ACTIVE_SHADOW_OK" and avg_score > thresholds.min_avg_score_r:
        risk_mode = "标准观察"
    if scored_route and scored_route.get("state") == "PAUSED":
        risk_mode = "暂停"

    return {
        "symbol": symbol or "UNKNOWN",
        "direction": direction or "FLAT",
        "directionLabel": "买入观察" if direction == "LONG" else "卖出观察" if direction == "SHORT" else "观望",
        "riskMode": risk_mode,
        "sampleCount": len(relevant),
        "basis": basis,
        "initialStop": {
            "label": "初始止损建议",
            "value": round(stop_basis, 4),
            "unit": "shadow_move_or_atr_multiple",
            "description": "取近期 MAE 七成分位或 ATR 保守倍数，仍仅为人工复核参考",
        },
        "targets": [
            {"name": "第一目标", "value": round(tp1, 4), "description": "近期 MFE 中位数"},
            {"name": "第二目标", "value": round(tp2, 4), "description": "近期 MFE 七成分位"},
            {"name": "第三目标", "value": round(tp3, 4), "description": "近期 MFE 八五分位"},
        ],
        "trailing": {
            "breakevenAtR": 0.70,
            "protectAtR": 1.20,
            "givebackPct": 0.45,
            "description": "达到 0.7R 后保护本金；达到 1.2R 后使用波动跟踪；MFE 回撤过大时保护利润",
        },
        "timeStop": {
            "m15Bars": 4,
            "h1Bars": 3,
            "description": "超过指定 bar 数仍无正向 MFE，则降级为观望复核",
        },
        "advisoryOnly": True,
    }
