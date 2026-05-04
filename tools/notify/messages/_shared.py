"""Shared formatting utilities for all message renderers.

Centralizes Chinese-localised formatting primitives so every renderer
gets consistent money / percentage / pip / time representations without
copy-pasting the same helper functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape as _html_escape

TOKYO = timezone(timedelta(hours=9))

_ACTION_ZH: dict[str, str] = {
    "BUY": "做多",
    "SELL": "做空",
    "HOLD": "观望",
    "LONG": "做多",
    "SHORT": "做空",
    "CLOSE_BUY": "平多",
    "CLOSE_SELL": "平空",
}

_RISK_ZH: dict[str, str] = {
    "low": "低",
    "medium": "中",
    "medium_high": "中高",
    "high": "高",
    "critical": "极高",
    "unknown": "未知",
}


def chinese_action(value: object) -> str:
    """Map BUY/SELL/HOLD to Chinese labels."""
    return _ACTION_ZH.get(str(value or "").upper(), str(value or "未知"))


def chinese_risk(value: object) -> str:
    """Map low/medium/high/critical to Chinese labels."""
    return _RISK_ZH.get(str(value or "").lower(), str(value or "未知"))


def fmt_money(value: object, prefix: str = "$", sign: bool = True) -> str:
    """Format a monetary amount.

    When *sign* is True positive numbers get a leading ``+``.
    """
    try:
        n = float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return "--"
    s = "+" if (sign and n > 0) else ""
    return f"{s}{prefix}{n:,.2f}"


def fmt_pct(value: object, digits: int = 0) -> str:
    """Format a probability (0-1) or percentage (0-100) value."""
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "--"
    if 0 <= n <= 1:
        n *= 100
    return f"{n:.{digits}f}%"


def fmt_pips(value: object, digits: int = 1) -> str:
    """Format a pip value with sign."""
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "--"
    return f"{n:+.{digits}f} 点"


def fmt_time_tokyo(iso_value: object = None) -> str:
    """Return current Tokyo time as ``HH:MM``.

    If *iso_value* is given, convert that ISO-8601 timestamp to Tokyo time.
    """
    if iso_value is None:
        dt = datetime.now(TOKYO)
    else:
        try:
            dt = datetime.fromisoformat(
                str(iso_value).replace("Z", "+00:00")
            ).astimezone(TOKYO)
        except (ValueError, TypeError):
            dt = datetime.now(TOKYO)
    return dt.strftime("%H:%M")


def fmt_date() -> str:
    """Return today's date in Tokyo time as ``YYYY-MM-DD``."""
    return datetime.now(TOKYO).strftime("%Y-%m-%d")


def safe_truncate(value: object, limit: int, fallback: str = "--") -> str:
    """Truncate text to *limit* characters, appending ``…`` if needed."""
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def html_escape(value: object) -> str:
    """HTML-escape a string."""
    return _html_escape(str(value), quote=False)
