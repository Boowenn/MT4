from __future__ import annotations

from pathlib import Path
from typing import Any

from .stability import build_report, read_report


def build_text(runtime_dir: Path, *, refresh: bool = False) -> str:
    report = build_report(Path(runtime_dir), write=True) if refresh else read_report(Path(runtime_dir))
    lines = [
        "【QuantGod GA 多代稳定性】",
        "",
        f"状态：{report.get('status', 'UNKNOWN')} / {report.get('stabilityGrade', 'UNKNOWN')}",
        f"可用性：{report.get('evidenceUsability', 'UNKNOWN')}",
        f"代数：{report.get('generationCount', 0)}",
        f"候选：{report.get('candidateCount', 0)}",
        f"精英：{report.get('eliteCount', 0)}",
        f"墓园：{report.get('graveyardCount', 0)}",
        f"Lineage：节点 {report.get('lineageNodeCount', 0)} / 边 {report.get('lineageEdgeCount', 0)} / 深度 {report.get('lineageDepth', 0)}",
        "",
    ]
    fitness = report.get("fitnessSummary") if isinstance(report.get("fitnessSummary"), dict) else {}
    if fitness:
        lines.extend(
            [
                "Fitness：",
                f"- 样本：{fitness.get('count', 0)}",
                f"- 最佳：{fitness.get('max')}",
                f"- 平均：{fitness.get('avg')}",
                "",
            ]
        )
    blockers = report.get("blockers") or []
    if blockers:
        lines.append("阻断：")
        for blocker in blockers[:8]:
            lines.append(f"- {blocker}")
        lines.append("")
    recommendations = report.get("recommendationsZh") or []
    if recommendations:
        lines.append("建议：")
        for item in recommendations[:8]:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend(
        [
            "安全边界：",
            "- GA 多代稳定性只用于生产证据验证。",
            "- 不下单、不平仓、不撤单、不修改 MT5 live preset。",
            "- GA 候选不会直接进入实盘。",
        ]
    )
    return "\n".join(lines)
