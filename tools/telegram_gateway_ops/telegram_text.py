from __future__ import annotations

from typing import Any, Dict


def gateway_ops_to_chinese_text(status: Dict[str, Any]) -> str:
    delivery = status.get("deliveryObservability") if isinstance(status.get("deliveryObservability"), dict) else {}
    lines = [
        "【QuantGod Telegram Gateway 运维复盘】",
        f"状态：{status.get('statusZh') or status.get('status', 'UNKNOWN')}",
        f"队列：{status.get('queuedCount', 0)}",
        f"待投递：{status.get('pendingCount', 0)}",
        f"真实发送：{status.get('actualSentCount', 0)}",
        f"去重 / 限频抑制：{status.get('suppressedCount', 0)}",
        f"失败：{status.get('failedCount', 0)}",
        f"最近 topic：{status.get('lastTopic') or '无'}",
        f"投递状态：{delivery.get('stateZh') or '等待新报告'}",
        "",
        "按 topic 待投递：",
    ]
    pending_by_topic = status.get("pendingByTopic") if isinstance(status.get("pendingByTopic"), dict) else {}
    if pending_by_topic:
        for topic, count in sorted(pending_by_topic.items()):
            lines.append(f"- {topic}: {count}")
    else:
        lines.append("- 暂无待投递 topic")
    lines.extend(
        [
            "",
            "安全边界：Telegram Gateway 只做 push-only 观测、排队、去重、限频和 ledger；",
            "不接收 Telegram 命令，不下单、不平仓、不撤单、不修改 MT5 live preset。",
        ]
    )
    return "\n".join(lines)
