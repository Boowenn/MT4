"""Renderer for the ``daily_digest`` message kind.

Triggered by ``POST /api/notify/daily-digest`` (Phase 2 "发送每日摘要" button).
Produces a compact 3-6 line daily recap with slash-separated information density.
"""

from __future__ import annotations

from typing import Any

from ._shared import fmt_date, fmt_money, fmt_pct, safe_truncate


def render_daily_digest(payload: dict[str, Any]) -> str:
    """Produce a compact daily recap message.

    Visual identity: 📊 prefix, slash-separated values, no colon-indented labels.
    """
    pnl = fmt_money(payload.get("pnl") or payload.get("dailyPnl") or 0)
    wins = payload.get("wins") or 0
    losses = payload.get("losses") or 0
    total = int(wins) + int(losses)
    win_rate = f"{fmt_pct(int(wins) / total * 100 if total else 0, 1)}" if total else "--"
    routes = safe_truncate(payload.get("routes") or payload.get("routeSummary") or "routes: --", 80, "--")
    shadow_signals = payload.get("shadowSignals") or payload.get("shadow") or 0
    pending = payload.get("shadowPending") or 0
    confirmed = payload.get("shadowConfirmed") or 0
    risk_events = payload.get("riskEvents") or 0
    max_dd = fmt_money(payload.get("maxDrawdown") or 0)

    shadow_line = ""
    if pending or confirmed:
        shadow_line = f"\n影子信号：{shadow_signals} 条（待评估 {pending} / 已确认 {confirmed}）"
    else:
        shadow_line = f"\n影子信号：{shadow_signals} 条"

    risk_line = ""
    if risk_events:
        risk_line = f"\n风险事件：{risk_events}"
    else:
        risk_line = "\n风险事件：0"

    dd_line = ""
    max_dd_val = payload.get("maxDrawdown")
    if max_dd_val is not None and str(max_dd_val).strip():
        dd_time = safe_truncate(payload.get("maxDrawdownTime") or "", 30, "")
        time_suffix = f" {dd_time}" if dd_time and dd_time != "--" else ""
        dd_line = f"\n最大回撤：{max_dd}{time_suffix}"

    lines = [
        f"\U0001f4ca 今日复盘 — {fmt_date()}",
        f"盈亏：{pnl}｜胜负：{wins} 胜 / {losses} 负（{win_rate}）",
        f"活跃路由：{routes}",
        shadow_line.strip(),
        risk_line.strip(),
        dd_line.strip() if dd_line.strip() else "",
    ]
    return "\n".join(line for line in lines if line)
