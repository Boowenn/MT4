from __future__ import annotations

from typing import Any

STATE_CN = {
    "CALIBRATED": "已校准",
    "WATCH_ONLY": "仅观察",
    "INSUFFICIENT_DATA": "样本不足",
    "PAUSED": "暂停",
}


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def build_telegram_text(payload: dict[str, Any], symbol: str | None = None, limit: int = 6) -> str:
    plans = payload.get("plans", [])
    if symbol:
        plans = [p for p in plans if p.get("symbol") == symbol]
    lines = [
        "【QuantGod 动态止盈止损校准】",
        "",
        f"生成时间：{payload.get('generatedAt', '-')}",
        f"样本组数：{len(plans)}",
        "",
        "校准结论：",
    ]
    if not plans:
        lines.append("- 暂无可用样本；仅记录，不生成方向建议。")
    for plan in plans[:limit]:
        targets = plan.get("targets", {})
        lines.append(
            "- "
            f"{plan.get('symbol')}｜{plan.get('strategy')}｜{plan.get('directionText')}｜{plan.get('regime')}｜"
            f"状态：{STATE_CN.get(plan.get('state'), plan.get('state'))}｜"
            f"样本：{plan.get('sampleCount')}｜胜率：{float(plan.get('winRate', 0))*100:.1f}%｜"
            f"初始止损：{_fmt(plan.get('initialStop'))}｜目标：{_fmt(targets.get('tp1'))}/{_fmt(targets.get('tp2'))}/{_fmt(targets.get('tp3'))}"
        )
        lines.append(f"  原因：{plan.get('reason')}")
    paused = sum(1 for p in plans if p.get("state") == "PAUSED")
    calibrated = sum(1 for p in plans if p.get("state") == "CALIBRATED")
    lines.extend([
        "",
        "风险提示：",
        f"- 已校准方向：{calibrated}；暂停方向：{paused}",
        "- 动态止盈止损只用于影子评估和人工复核。",
        "- 不会下单、不会平仓、不会撤单、不会修改实盘 preset。",
    ])
    return "\n".join(lines)
