from __future__ import annotations

from html import escape
from typing import Any


def _first(data: dict[str, Any], *keys: str, default: str = "--") -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _fmt_num(value: Any, digits: int = 2, prefix: str = "", suffix: str = "") -> str:
    try:
        number = float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return "--"
    sign = "+" if number > 0 and not prefix else ""
    return f"{prefix}{sign}{number:.{digits}f}{suffix}"


def _html(text: Any) -> str:
    return escape(str(text), quote=False)


def format_event(event_type: str, data: dict[str, Any] | None = None) -> str:
    payload = data or {}
    event = str(event_type or "TEST").upper()

    if event == "TEST":
        message = _first(payload, "message", "text", default="QuantGod notification test")
        return f"🧪 <b>QuantGod Test</b>\n{_html(message)}"

    if event == "TRADE_OPEN":
        symbol = _first(payload, "symbol", "Symbol")
        side = _first(payload, "side", "direction", "type").upper()
        lots = _first(payload, "lots", "volume", default="0.01")
        price = _first(payload, "price", "entry", "entry_price")
        sl = _first(payload, "sl", "stop_loss", "stopLoss")
        tp = _first(payload, "tp", "take_profit", "takeProfit")
        route = _first(payload, "route", "strategy")
        return f"🟢 <b>{_html(symbol)} {side}</b> {lots} @ {_html(price)} | SL: {_html(sl)} TP: {_html(tp)} | Route: {_html(route)}"

    if event == "TRADE_CLOSE":
        symbol = _first(payload, "symbol", "Symbol")
        pips = _fmt_num(_first(payload, "pips", "Pips", default="0"), digits=1, suffix=" pips")
        pnl = _fmt_num(_first(payload, "pnl", "profit", "Profit", default="0"), digits=2, prefix="$")
        duration = _first(payload, "duration", "Duration", default="--")
        return f"🔴 <b>{_html(symbol)} CLOSE</b> {pips} | {pnl} | Duration: {_html(duration)}"

    if event == "KILL_SWITCH":
        reason = _first(payload, "reason", "Reason", default="unknown")
        pnl = _fmt_num(_first(payload, "pnl", "dailyPnl", "daily_pnl", default="0"), digits=2, prefix="$")
        return f"⛔ <b>Kill Switch ACTIVE</b>: {_html(reason)} | PnL: {pnl}"

    if event == "NEWS_BLOCK":
        label = _first(payload, "label", "event", "title", default="tracked event")
        eta = _first(payload, "eta", "minutes", "minutesToEvent", default="--")
        return f"📰 <b>News Block</b>: {_html(label)} in {_html(eta)}min | Pre-block active"

    if event == "AI_ANALYSIS":
        symbol = _first(payload, "symbol", "Symbol")
        action = _first(payload, "action", "decision", default="HOLD").upper()
        confidence = _first(payload, "confidence", default="0")
        risk = _first(payload, "risk", "riskLevel", "risk_level", default="unknown")
        note = _first(payload, "note", "reasoning", "suggested_wait_condition", default="analysis complete")
        try:
            conf_text = f"{float(confidence) * 100:.0f}%" if float(confidence) <= 1 else f"{float(confidence):.0f}%"
        except (TypeError, ValueError):
            conf_text = str(confidence)
        return f"🤖 <b>{_html(symbol)} AI</b>: {action} ({_html(conf_text)}) | Risk: {_html(risk)} | {_html(note)}"

    if event == "CONSECUTIVE_LOSS":
        losses = _first(payload, "losses", "count", default="--")
        cooldown = _first(payload, "cooldown", "cooldownMinutes", default="--")
        return f"⚠️ <b>Consecutive loss pause</b>: {_html(losses)} losses | Cooldown: {_html(cooldown)}min"

    if event == "DAILY_DIGEST":
        pnl = _fmt_num(_first(payload, "pnl", "dailyPnl", default="0"), digits=2, prefix="$")
        wins = _first(payload, "wins", default="0")
        losses = _first(payload, "losses", default="0")
        routes = _first(payload, "routes", "routeSummary", default="routes: --")
        shadow = _first(payload, "shadowSignals", "shadow", default="0")
        return f"📊 <b>Daily</b>: {pnl} | {wins}W/{losses}L | {_html(routes)} | Shadow: {_html(shadow)} signals"

    if event == "GOVERNANCE":
        route = _first(payload, "route", "Route", default="all")
        action = _first(payload, "action", "Action", default="review")
        reason = _first(payload, "reason", "Reason", default="governance evidence updated")
        return f"🛡️ <b>Governance</b> {_html(route)}: {_html(action)} | {_html(reason)}"

    summary = _first(payload, "summary", "message", "text", default="event received")
    return f"ℹ️ <b>{_html(event)}</b>\n{_html(summary)}"
