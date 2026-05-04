"""Renderer for the ``ai_advisory`` message kind.

Triggered by the Phase 2 "AI 分析并推送" button
(``POST /api/notify/mt5-ai-monitor/run``).

Returns **None** when the decision action is HOLD — the caller must
skip the push, not the renderer.
"""

from __future__ import annotations

from typing import Any, Optional

from ._shared import (
    chinese_action,
    chinese_risk,
    fmt_pct,
    fmt_time_tokyo,
    safe_truncate,
)


def render_ai_advisory(payload: dict[str, Any]) -> Optional[str]:
    """Render a local AI advisory message.

    Returns:
        ``str`` for BUY/SELL; ``None`` for HOLD (meaning "do not push").
    """
    decision = payload.get("decision") or {}
    # Backward-compat: accept root-level action/confidence/risk as fallback
    # (used by _event_payload_from_analysis in notify_service.py)
    action = str(
        decision.get("action")
        or payload.get("action")
        or "HOLD"
    ).upper()

    # HOLD → suppress push
    if action == "HOLD":
        return None

    # ── resolve fields (decision.* first, then root-level fallback) ──
    symbol = str(payload.get("symbol") or "UNKNOWN")
    timeframe = str(
        payload.get("timeframe")
        or _primary_tf(payload)
        or "M15"
    )
    confidence = (
        decision.get("confidence")
        or payload.get("confidence")
        or 0
    )
    grade = safe_truncate(
        decision.get("signalGrade") or _infer_grade(decision, payload), 20, "B 级"
    )
    risk_raw = payload.get("risk")
    risk_val = (
        risk_raw.get("risk_level")
        if isinstance(risk_raw, dict)
        else risk_raw
    )
    risk = chinese_risk(decision.get("risk") or risk_val)

    entry = (
        decision.get("entryZone")
        or _format_entry(decision)
        or str(payload.get("entry") or "--")
    )
    sl = decision.get("stopLoss") or decision.get("sl") or payload.get("stopLoss") or "--"
    sl_pips = decision.get("stopLossPips") or payload.get("stopLossPips")
    targets = decision.get("targets") or payload.get("targets") or []
    rr = decision.get("riskReward") or payload.get("riskReward") or "--"
    invalidation = safe_truncate(
        decision.get("invalidation")
        or payload.get("note")
        or payload.get("reasoning"),
        80,
        "无明确失效条件",
    )

    direction = chinese_action(action)

    sl_line = (
        f"止损位：{sl}（{sl_pips} 点）" if sl_pips else f"止损位：{sl}"
    )
    targets_line = (
        "目标位：" + " / ".join(str(t) for t in targets[:3])
        if targets
        else "目标位：--"
    )

    lines = [
        f"\U0001f3af AI 实盘建议 — {symbol} {timeframe}",
        f"方向：{direction}｜置信度 {fmt_pct(confidence)}",
        f"信号等级：{grade}｜风险：{risk}",
        "",
        f"入场区间：{entry}",
        sl_line,
        targets_line,
        f"盈亏比：{rr}",
        "",
        f"失效条件：{invalidation}",
        f"仅作建议，不执行交易｜东京时间 {fmt_time_tokyo()}",
    ]
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------


def _primary_tf(payload: dict[str, Any]) -> Optional[str]:
    tfs = payload.get("timeframes") or []
    return tfs[0] if tfs else None


def _infer_grade(decision: dict[str, Any], payload: dict[str, Any] | None = None) -> str:
    conf = decision.get("confidence") or (payload or {}).get("confidence")
    try:
        c = float(conf)  # type: ignore[arg-type]
        if c <= 1:
            c *= 100
        if c >= 75:
            return "A 级"
        if c >= 60:
            return "B 级"
        return "C 级"
    except (TypeError, ValueError):
        return "B 级"


def _format_entry(decision: dict[str, Any]) -> str:
    entry = decision.get("entry") or decision.get("price")
    if entry is None:
        return "--"
    spread = decision.get("entrySpread") or 0
    if spread:
        return f"{entry} ± {spread}"
    return str(entry)
