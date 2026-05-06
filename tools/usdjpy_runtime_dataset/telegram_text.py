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
    unit = replay.get("unitPolicy") if isinstance(replay.get("unitPolicy"), dict) else {}
    scenarios = replay.get("scenarioComparisons") if isinstance(replay.get("scenarioComparisons"), list) else []
    scenario_lines = []
    for item in scenarios:
        if not isinstance(item, dict) or item.get("scenario") == "current":
            continue
        delta = item.get("netRDelta")
        verdict = item.get("verdict") or "待验证"
        if delta is None:
            scenario_lines.append(f"- {item.get('labelZh') or item.get('scenario')}：需要补 bar/tick 回放，结论 {verdict}")
        else:
            scenario_lines.append(f"- {item.get('labelZh') or item.get('scenario')}：估算 {delta}R，结论 {verdict}")
    lines = [
        "【QuantGod USDJPY 自学习闭环】",
        "",
        f"数据集：样本 {_line_value(ds.get('sampleCount'), '0')}，RSI 准入 {_line_value(ds.get('readySignalCount'), '0')}，实盘入场 {_line_value(ds.get('actualEntryCount'), '0')}",
        f"回放：错失机会 {_line_value(rp.get('missedOpportunityCount'), '0')}，过早出场 {_line_value(rp.get('earlyExitCount'), '0')}，合理阻断 {_line_value(rp.get('reasonableBlockCount'), '0')}",
        f"后验证据：可评估 {_line_value(rp.get('posteriorReadyCount'), '0')}，缺 R 倍数 {_line_value(rp.get('missingExitRCount'), '0')}",
        f"参数候选：{_line_value(tn.get('candidateCount'), '0')} 个；提案：{proposal.get('statusZh') or proposal.get('status') or '未生成'}",
        "",
        "回放对比：" if scenario_lines else "回放对比：暂无可比较候选",
        *scenario_lines[:3],
        f"计量口径：主口径 {unit.get('primary') or 'R'}，辅助口径 {unit.get('secondary') or 'pips'}；USC 只作账面参考。",
        "",
        "边界：只读复盘，不下单、不平仓、不撤单、不自动修改实盘 preset。",
    ]
    return "\n".join(lines)
