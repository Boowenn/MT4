from __future__ import annotations
from typing import Any, Dict, List
DIRECTION_ZH = {"LONG":"买入观察", "SHORT":"卖出观察"}
STATE_ZH = {"WAIT_TRIGGER_CONFIRMATION":"等待二次确认", "BLOCKED":"暂停触发"}

def build_telegram_text(plan: Dict[str, Any], symbol: str | None = None, limit: int = 8) -> str:
    decisions = plan.get("decisions") or []
    if symbol:
        decisions = [item for item in decisions if item.get("symbol") == symbol]
    lines = ["【QuantGod 入场触发实验室】", "", "说明：本消息只做入场触发复核，不会下单、不会平仓、不会撤单、不会修改实盘 preset。", "", "触发状态："]
    for item in decisions[:limit]:
        direction = DIRECTION_ZH.get(str(item.get("direction", "")), str(item.get("direction", "")))
        state = STATE_ZH.get(str(item.get("state", "")), str(item.get("state", "")))
        lines.append(f"- {item.get('symbol')}｜{direction}｜{item.get('timeframe')}｜状态：{state}｜触发分：{item.get('score', 0)}")
        confirmations = item.get("confirmations") or {}
        failed = [name for name, ok in confirmations.items() if not ok]
        if failed: lines.append("  未通过：" + "、".join(failed))
        else: lines.append("  复核：运行快照、快通道、自适应闸门、影子样本均通过")
        reasons = item.get("reasons") or []
        if reasons: lines.append("  原因：" + "；".join(str(x) for x in reasons[:2]))
        if item.get("suggested_wait"): lines.append("  下一步：" + str(item.get("suggested_wait")))
    if not decisions:
        lines.append("- 暂无触发计划，请先运行 build 生成入场触发复核结果。")
    lines.extend(["", "安全边界：", "- 仅建议、只读、影子评估。", "- 不会下单、不会平仓、不会撤单。", "- 不接收 Telegram 交易命令。"])
    return "\n".join(lines)
