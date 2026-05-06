from __future__ import annotations

from typing import Any, Dict


def _fmt(value: Any, fallback: str = "—") -> str:
    return fallback if value in (None, "") else str(value)


def autonomous_agent_to_chinese_text(payload: Dict[str, Any]) -> str:
    decision = payload.get("promotionDecision") if isinstance(payload.get("promotionDecision"), dict) else {}
    patch = payload.get("currentPatch") if isinstance(payload.get("currentPatch"), dict) else {}
    rollback = patch.get("rollback") if isinstance(patch.get("rollback"), dict) else {}
    candidates = decision.get("candidates") if isinstance(decision.get("candidates"), list) else []
    lines = [
        "【USDJPY 自主治理 Agent】",
        "",
        f"当前阶段：{_fmt(payload.get('stageZh') or payload.get('stage'))}",
        f"自动 patch：{'允许写入受控 patch' if payload.get('patchAllowed') else '未放行'}",
        "审批模式：无需人工审批；必须通过机器硬风控与自动回滚。",
        "",
        "候选参数：",
    ]
    if candidates:
        for item in candidates[:4]:
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            lines.append(
                f"- {_fmt(item.get('labelZh') or item.get('variant'))}：{_fmt(item.get('autonomousStageZh'))}，"
                f"净变化 {_fmt(summary.get('netRDelta'), '0')}R"
            )
    else:
        lines.append("- 暂无候选，等待回放样本。")
    blockers = rollback.get("hardBlockers") if isinstance(rollback.get("hardBlockers"), list) else []
    lines.extend(["", "硬风控："])
    if blockers:
        lines.extend(f"- {item}" for item in blockers[:5])
    else:
        lines.append("- 当前未触发硬回滚。")
    lines.extend([
        "",
        "底线：USDJPY-only；Polymarket 永远 shadow-only；DeepSeek 只解释；Telegram 不接交易命令；不会改源码或 live preset。",
    ])
    return "\n".join(lines)
