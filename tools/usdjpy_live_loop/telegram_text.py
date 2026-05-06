from __future__ import annotations

from typing import Any

from .schema import bool_zh, direction_zh, entry_mode_zh


def live_loop_to_chinese_text(payload: dict[str, Any]) -> str:
    top = payload.get("topLiveEligiblePolicy") or payload.get("topPolicy") or {}
    shadow = payload.get("topShadowPolicy") or {}
    preset = payload.get("preset") or {}
    runtime = payload.get("runtime") or {}
    lines = [
        "【QuantGod USDJPY 实盘 EA 闭环】",
        "",
        f"结论：{payload.get('stateZh', '未知')}",
        f"实盘路线：{payload.get('liveRouteZh', '仅 RSI 买入路线')}",
        "",
        "当前优先策略：",
        f"- 策略：{top.get('strategy', 'UNKNOWN')}",
        f"- 方向：{direction_zh(top.get('direction'))}",
        f"- 状态：{entry_mode_zh(top.get('entryMode'))}",
        f"- 建议仓位：{float(top.get('recommendedLot') or 0):.2f} / 上限 {float(top.get('maxLot') or payload.get('maxEaPositions') or 2):.2f}",
        "",
        "现场证据：",
        f"- 运行快照：{bool_zh(runtime.get('ready'))}",
        f"- preset 恢复：{bool_zh(preset.get('ready'))}",
        f"- RSI 买入路线：{'已恢复' if preset.get('rsiBuyRoutePreserved') else '未确认'}",
        f"- EA 自动仓位上限：{payload.get('maxEaPositions', 2)}；人工仓位不计入政策判断",
    ]
    if shadow and shadow != top:
        lines.extend([
            "",
            "影子研究第一名：",
            f"- {shadow.get('strategy', 'UNKNOWN')}｜{direction_zh(shadow.get('direction'))}｜{entry_mode_zh(shadow.get('entryMode'))}",
            "- 影子第一名只用于研究，不会抢占实盘 RSI 买入路线。",
        ])
    why = payload.get("whyNoEntry") or []
    if why:
        lines.extend(["", "为什么没有入场："])
        lines.extend(f"- {item}" for item in why[:6])
    actions = payload.get("nextActions") or []
    if actions:
        lines.extend(["", "下一步自动动作："])
        lines.extend(f"- {item}" for item in actions[:5])
    lines.extend([
        "",
        "安全边界：",
        "- 本消息只说明现有 MT5 EA 是否具备恢复条件。",
        "- 工具不会下单、不会平仓、不会撤单、不会修改 preset。",
    ])
    return "\n".join(lines)
