"""Renderer for the ``test`` message kind.

Triggered by ``POST /api/notify/test`` — a simple 1-2 line channel
connectivity test message.
"""

from __future__ import annotations

from typing import Any

from ._shared import fmt_time_tokyo, safe_truncate


def render_test(payload: dict[str, Any]) -> str:
    """Produce a short Telegram channel-test message.

    Returns:
        Always a non-empty string (test messages are never suppressed).
    """
    message = safe_truncate(
        payload.get("message") or payload.get("text") or "QuantGod notification test",
        200,
        fallback="QuantGod 通道连接正常",
    )
    lines = [
        "\U0001f9ea QuantGod 通道测试",
        f"{message}｜东京时间 {fmt_time_tokyo()}",
    ]
    return "\n".join(lines)
