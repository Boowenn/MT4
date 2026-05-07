from __future__ import annotations

from typing import Any, Dict


def news_gate_to_chinese_text(news_gate: Dict[str, Any]) -> str:
    mode = news_gate.get("mode") or "SOFT"
    risk = news_gate.get("riskLevel") or "UNKNOWN"
    action = "硬阻断" if news_gate.get("hardBlock") else "不阻断"
    lot = news_gate.get("lotMultiplier", 1.0)
    reason = news_gate.get("reasonZh") or "新闻风险已记录。"
    return "\n".join([
        "新闻门禁：",
        f"- 模式：{mode}",
        f"- 风险：{risk}",
        f"- 处理：{action}",
        f"- 仓位倍率：{lot}",
        f"- 说明：{reason}",
    ])

