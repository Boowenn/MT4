"""Chinese-only Telegram text normalization for QuantGod advisory messages."""

from __future__ import annotations

import re
from typing import Any

ACTION_MAP = {
    "WATCH_LONG": "偏多观察",
    "WATCH_SHORT": "偏空观察",
    "PAUSED": "暂停",
    "HOLD": "观望",
    "BUY": "偏多观察",
    "SELL": "偏空观察",
    "LONG": "偏多",
    "SHORT": "偏空",
    "NONE": "无方向",
}

TOKEN_REPLACEMENTS = [
    ("finalAction=", "最终动作="),
    ("validator=", "校验="),
    ("agreement=", "一致性="),
    ("advisoryOnly=true", "仅建议=是"),
    ("advisoryOnly=false", "仅建议=否"),
    ("telegram push-only", "Telegram 只推送"),
    ("Telegram push-only", "Telegram 只推送"),
    ("AI advisory-only", "AI 仅建议"),
    ("advisory-only", "仅建议"),
    ("read-only", "只读"),
    ("live preset", "实盘参数"),
    ("KillSwitch", "熔断"),
    ("Kill Switch", "熔断"),
    ("true", "是"),
    ("false", "否"),
    ("True", "是"),
    ("False", "否"),
    ("unknown", "未知"),
    ("UNKNOWN", "未知"),
    ("bid", "买价"),
    ("ask", "卖价"),
    ("source", "来源"),
    ("fallback", "回退"),
    ("runtimeFresh", "运行快照新鲜"),
    ("DeepSeek", "深度求索"),
    ("Fusion", "融合审查"),
    ("local_and_deepseek_compatible", "本地与深度求索兼容"),
    ("local_deepseek_conflict", "本地与深度求索冲突"),
    ("pass", "通过"),
    ("unknown", "未知"),
    ("changed", "证据变化"),
    ("force", "手动强制复核"),
    ("first_seen", "首次发现"),
    ("interval_elapsed", "定时复核"),
]


def chinese_action(value: Any) -> str:
    return ACTION_MAP.get(str(value or "").upper(), str(value or "未知"))


def chinese_gate_summary(report: dict[str, Any]) -> str:
    gate = report.get("ai_journal_gate") if isinstance(report.get("ai_journal_gate"), dict) else {}
    status = str(gate.get("status") or "pass")
    if status == "paused":
        evaluation = gate.get("evaluation") if isinstance(gate.get("evaluation"), dict) else {}
        return (
            "AI复盘闸门：暂停；"
            f"原因：{gate.get('reasonZh') or '近期影子样本表现为负'}；"
            f"样本：{evaluation.get('samples', '暂无')}；"
            f"胜率：{evaluation.get('hitRate', '暂无')}；"
            f"平均影子R：{evaluation.get('averageScoreR', '暂无')}；"
            f"恢复时间：{gate.get('pausedUntil') or '等待冷却结束'}"
        )
    if status == "pass":
        evaluation = gate.get("evaluation") if isinstance(gate.get("evaluation"), dict) else {}
        return (
            "AI复盘闸门：通过；"
            f"样本：{evaluation.get('samples', 0)}；"
            f"胜率：{evaluation.get('hitRate', '暂无')}；"
            f"平均影子R：{evaluation.get('averageScoreR', '暂无')}"
        )
    return "AI复盘闸门：暂不适用；当前仅记录观察样本。"


def ensure_chinese_telegram_text(text: str) -> str:
    """Normalize known English operational terms into Chinese before Telegram push.

    Symbols, timestamps, model identifiers, and URLs are left untouched. This is
    intended for human-facing message text, not for machine JSON payloads.
    """
    out = str(text or "")
    # Convert bracket action tags first, e.g. [WATCH_LONG] / [HOLD].
    for raw, label in ACTION_MAP.items():
        out = re.sub(rf"\[{re.escape(raw)}\]", f"[{label}]", out)
        out = re.sub(rf"\b{re.escape(raw)}\b", label, out)
    for old, new in TOKEN_REPLACEMENTS:
        out = out.replace(old, new)
    # Normalize common boolean / status fragments that appear in fusion audit lines.
    out = re.sub(r"最终动作=([A-Z_]+)", lambda m: "最终动作=" + chinese_action(m.group(1)), out)
    out = re.sub(r"方向: ([A-Z_]+)", lambda m: "方向：" + chinese_action(m.group(1)), out)
    out = out.replace(" | ", "；")
    out = out.replace(" : ", "：")
    out = out.replace(": ", "：")
    return out
