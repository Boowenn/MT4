"""Thin backward-compatible wrapper around ``tools.notify.messages.render``.

All callers that previously imported ``format_event`` from this module
continue to work unchanged.  The real message generation now lives in
``tools/notify/messages/``.
"""

from __future__ import annotations

from typing import Any

from .messages import render

EVENT_TO_KIND: dict[str, str] = {
    "TEST": "test",
    "TRADE_OPEN": "runtime_event",
    "TRADE_CLOSE": "runtime_event",
    "KILL_SWITCH": "runtime_event",
    "NEWS_BLOCK": "runtime_event",
    "AI_ANALYSIS": "ai_advisory",
    "CONSECUTIVE_LOSS": "runtime_event",
    "DAILY_DIGEST": "daily_digest",
    "GOVERNANCE": "runtime_event",
}


def format_event(event_type: str, data: dict[str, Any] | None = None) -> str:
    """Render a Telegram message for *event_type* using the new message centre.

    Backward-compatible signature — ``send_event`` and other callers
    do not need to change.
    """
    kind = EVENT_TO_KIND.get(
        (event_type or "TEST").upper(), "runtime_event"
    )
    payload = dict(data or {})
    payload.setdefault("_event_type", event_type)
    return render(kind, payload) or ""  # None → "" for old callers
