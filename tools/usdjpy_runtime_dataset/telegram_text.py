from __future__ import annotations

from typing import Any, Dict


def _line_value(value: Any, fallback: str = "—") -> str:
    return fallback if value in (None, "") else str(value)


def evolution_to_chinese_text(payload: Dict[str, Any]) -> str:
    dataset = payload.get("dataset") if isinstance(payload.get("dataset"), dict) else {}
    replay = payload.get("replay") if isinstance(payload.get("replay"), dict) else {}
    tuning = payload.get("tuning") if isinstance(payload.get("tuning"), dict) else {}
    proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else {}
    ds = dataset.get("summary", {}) if isinstance(dataset.get("summary"), dict) else {}
    rp = replay.get("summary", {}) if isinstance(replay.get("summary"), dict) else {}
    tn = tuning.get("summary", {}) if isinstance(tuning.get("summary"), dict) else {}
    lines = [
        "【QuantGod USDJPY 自学习闭环】",
        "",
        f"数据集：样本 {_line_value(ds.get('sampleCount'), '0')}，RSI 准入 {_line_value(ds.get('readySignalCount'), '0')}，实盘入场 {_line_value(ds.get('actualEntryCount'), '0')}",
        f"回放：错失机会 {_line_value(rp.get('missedOpportunityCount'), '0')}，过早出场 {_line_value(rp.get('earlyExitCount'), '0')}，合理阻断 {_line_value(rp.get('reasonableBlockCount'), '0')}",
        f"参数候选：{_line_value(tn.get('candidateCount'), '0')} 个；提案：{proposal.get('statusZh') or proposal.get('status') or '未生成'}",
        "",
        "边界：只读复盘，不下单、不平仓、不撤单、不自动修改实盘 preset。",
    ]
    return "\n".join(lines)

