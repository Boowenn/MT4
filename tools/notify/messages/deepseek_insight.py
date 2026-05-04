"""Renderer for the ``deepseek_insight`` message kind.

Triggered by the Phase 1 "自动分析并推送 Telegram" button
(``POST /api/ai-analysis/deepseek-telegram/run``).

Returns **None** when the decision action is HOLD — the caller must
skip the push, not the renderer.

Distinct from ``ai_advisory``:
- 🤖 prefix instead of 🎯
- Extra "模型推理摘要" / "新闻与情绪" paragraphs
- Model attribution line at the bottom
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


def render_deepseek_insight(payload: dict[str, Any]) -> Optional[str]:
    """Render a DeepSeek-powered insight message.

    Returns:
        ``str`` for BUY/SELL; ``None`` for HOLD (meaning "do not push").
    """
    decision = payload.get("decision") or {}
    action = str(decision.get("action") or "HOLD").upper()

    # HOLD → suppress push
    if action == "HOLD":
        return None

    # ── resolve fields ──────────────────────────────────────────────
    symbol = str(payload.get("symbol") or "UNKNOWN")
    timeframe = str(
        payload.get("timeframe")
        or (_primary_tf(payload))
        or "M15"
    )
    confidence = decision.get("confidence") or 0
    grade = safe_truncate(
        decision.get("signalGrade") or _infer_grade(decision), 20, "B 级"
    )
    risk_raw = payload.get("risk")
    risk_val = (
        risk_raw.get("risk_level")
        if isinstance(risk_raw, dict)
        else risk_raw
    )
    risk = chinese_risk(decision.get("risk") or risk_val)

    # DeepSeek-specific enriched sections
    ds_advice = payload.get("deepseek_advice") or {}
    advice = ds_advice.get("advice") if isinstance(ds_advice.get("advice"), dict) else {}
    model = str(ds_advice.get("model") or advice.get("model") or "deepseek-v4-flash")

    market_summary = safe_truncate(
        advice.get("marketSummary")
        or advice.get("headline")
        or "技术面与基本面综合分析",
        150,
    )
    bull_case = safe_truncate(
        advice.get("bullCase") or "多方证据待确认", 160
    )
    bear_case = safe_truncate(
        advice.get("bearCase") or "空方证据待确认", 160
    )

    entry = decision.get("entryZone") or _format_entry(decision)
    sl = decision.get("stopLoss") or decision.get("sl") or "--"
    sl_pips = decision.get("stopLossPips")
    targets = decision.get("targets") or []
    rr = decision.get("riskReward") or "--"
    invalidation = safe_truncate(
        decision.get("invalidation"), 80, "无明确失效条件"
    )

    news_risk = safe_truncate(
        advice.get("newsRisk") or "暂无高影响事件", 130
    )
    sentiment_positioning = safe_truncate(
        advice.get("sentimentPositioning") or "数据不足", 130
    )

    direction = chinese_action(action)

    sl_line = (
        f"止损：{sl}（{sl_pips} 点）" if sl_pips else f"止损：{sl}"
    )
    targets_line = (
        " / ".join(str(t) for t in targets[:3])
        if targets
        else "--"
    )

    lines = [
        f"\U0001f916 DeepSeek 深度研判 — {symbol}",
        f"方向：{direction}｜置信度 {fmt_pct(confidence)}",
        f"信号等级：{grade}｜风险：{risk}",
        "",
        "【市场摘要】",
        market_summary,
        "",
        "【多空辩论】",
        f"\U0001f53c 多方：{bull_case}",
        f"\U0001f53d 空方：{bear_case}",
        "",
        "【交易计划】",
        f"入场：{entry}",
        sl_line,
        f"目标：{targets_line}",
        f"盈亏比：{rr}",
        f"失效：{invalidation}",
        "",
        "【新闻与情绪】",
        news_risk,
        sentiment_positioning,
        "",
        "仅作研判，不执行交易",
        f"分析模型：{model}｜东京时间 {fmt_time_tokyo()}",
    ]
    return "\n".join(lines)


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------


def _primary_tf(payload: dict[str, Any]) -> Optional[str]:
    tfs = payload.get("timeframes") or []
    return tfs[0] if tfs else None


def _infer_grade(decision: dict[str, Any]) -> str:
    conf = decision.get("confidence")
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
