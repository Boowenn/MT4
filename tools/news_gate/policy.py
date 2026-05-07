from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .schema import ENTRY_BLOCKED, ENTRY_OPPORTUNITY, ENTRY_STANDARD, NEWS_RISK_HARD, NEWS_RISK_SOFT, NEWS_RISK_UNKNOWN


def _round_lot(value: float, step: float, min_lot: float, max_lot: float) -> float:
    if value <= 0:
        return 0.0
    steps = round(value / step)
    return round(max(min_lot, min(max_lot, steps * step)), 2)


def apply_news_gate_to_live_policy(
    *,
    entry_mode: str,
    allowed: bool,
    recommended_lot: float,
    strictness: str,
    reasons: List[str],
    news_gate: Dict[str, Any],
    min_lot: float,
    max_lot: float,
    step: float,
) -> Tuple[str, bool, float, str, List[str]]:
    risk = str(news_gate.get("riskLevel") or "").upper()
    updated_reasons = list(reasons)
    if news_gate.get("hardBlock") or risk == NEWS_RISK_HARD:
        updated_reasons.append(news_gate.get("reasonZh") or "高冲击新闻窗口，暂停 live。")
        return ENTRY_BLOCKED, False, 0.0, "BLOCKED_HIGH_IMPACT_NEWS", updated_reasons
    if risk == NEWS_RISK_SOFT:
        if entry_mode == ENTRY_STANDARD and news_gate.get("stageDowngrade", True):
            entry_mode = ENTRY_OPPORTUNITY
            strictness = "NEWS_SOFT_STAGE_DOWNGRADED"
            updated_reasons.append("普通新闻风险：标准入场降为机会入场。")
        multiplier = float(news_gate.get("lotMultiplier") or 1.0)
        recommended_lot = _round_lot(recommended_lot * multiplier, step, min_lot, max_lot)
        updated_reasons.append(news_gate.get("reasonZh") or "普通新闻风险只降仓，不阻断。")
    elif risk == NEWS_RISK_UNKNOWN:
        multiplier = float(news_gate.get("lotMultiplier") or 1.0)
        recommended_lot = _round_lot(recommended_lot * multiplier, step, min_lot, max_lot)
        updated_reasons.append(news_gate.get("reasonZh") or "新闻源未知：不阻断，只轻微降仓。")
    return entry_mode, allowed, recommended_lot, strictness, updated_reasons

