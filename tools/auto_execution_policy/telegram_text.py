from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .schema import zh_direction, zh_entry_mode


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_telegram_text(document: Dict[str, Any], symbol_filter: str | None = None, limit: int = 8) -> str:
    rows: List[Dict[str, Any]] = list(document.get("policies", []))
    if symbol_filter:
        rows = [row for row in rows if row.get("symbol") == symbol_filter]
    lines: List[str] = [
        "【QuantGod 自动执行策略调参】",
        "",
        "说明：本消息用于EA自动交易策略参数复核；它不会下单、不会平仓、不会撤单、不会修改实盘 preset。",
        "",
        "策略结论：",
    ]
    if not rows:
        lines.append("- 暂无策略行，默认阻断。")
    for row in rows[:limit]:
        mode = zh_entry_mode(row.get("entryMode"))
        direction = zh_direction(row.get("direction"))
        symbol = row.get("symbol", "未知品种")
        lot = row.get("recommendedLot", 0)
        score = row.get("score", 0)
        reason = row.get("reason", "无原因")
        lines.append(
            f"- {symbol}｜{direction}｜状态：{mode}｜评分：{_fmt(score)}｜建议仓位：{_fmt(lot)}｜原因：{reason}"
        )
        blockers = row.get("blockers") or []
        warnings = row.get("warnings") or []
        for blocker in blockers[:2]:
            lines.append(f"  - 阻断原因：{blocker}")
        for warning in warnings[:2]:
            lines.append(f"  - 注意：{warning}")
        if row.get("entryMode") != "BLOCKED":
            lines.append(
                f"  - 出场参数：模式={row.get('exitMode')}，保本延后={row.get('breakevenDelayR')}R，移动止损启动={row.get('trailStartR')}R，时间止损={row.get('timeStopBars')}根K线"
            )
    summary = document.get("summary", {})
    lines.extend([
        "",
        "汇总：",
        f"- 标准入场：{summary.get('standardEntries', 0)}",
        f"- 机会入场：{summary.get('opportunityEntries', 0)}",
        f"- 阻断：{summary.get('blocked', 0)}",
        "",
        "仓位规则：最大仓位可以设为2，但实际建议仓位按风险预算、机会等级和评分计算；机会入场只允许小仓试探。",
        "",
        "安全边界：",
        "- 不会下单、不会平仓、不会撤单。",
        "- 不会修改订单SL/TP，不会写MT5 OrderRequest。",
        "- 不接收Telegram交易命令，不开放webhook执行入口。",
    ])
    return "\n".join(lines)
