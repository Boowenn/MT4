from __future__ import annotations

from typing import Any, Dict


def build_telegram_text(report: Dict[str, Any]) -> str:
    symbol = report.get("symbol", "UNKNOWN")
    direction = {"LONG": "买入观察", "SHORT": "卖出观察"}.get(str(report.get("direction", "")).upper(), str(report.get("direction", "")))
    decision = report.get("decisionZh") or report.get("decision") or "阻断"
    lines = [
        "【QuantGod 实盘试点安全锁】",
        "",
        f"品种：{symbol}",
        f"方向：{direction}",
        f"结论：{decision}",
        "",
        "前置检查：",
    ]
    for check in report.get("checks", [])[:18]:
        passed = bool(check.get("passed"))
        status = "通过" if passed else "未通过"
        detail = "通过" if passed else check.get("detail")
        lines.append(f"- {check.get('name')}：{status}｜{detail}")
    reasons = report.get("reasons") or []
    if reasons:
        lines.extend(["", "阻断/说明："])
        for reason in reasons[:8]:
            lines.append(f"- {reason}")
    envelope = report.get("pilotEnvelope") or {}
    lines.extend([
        "",
        "试点边界：",
        f"- 最大手数：{envelope.get('maxLot', '未设置')}",
        f"- 日内最多次数：{envelope.get('maxDailyTrades', '未设置')}",
        f"- 日内最大亏损R：{envelope.get('maxDailyLossR', '未设置')}",
        "",
        "安全边界：",
        "- 本工具不会下单、不会平仓、不会撤单、不会修改订单。",
        "- 不会修改实盘 preset，不会写 MT5 OrderRequest。",
        "- 不接收 Telegram 交易命令，不开放 webhook 执行入口。",
    ])
    return "\n".join(lines)
