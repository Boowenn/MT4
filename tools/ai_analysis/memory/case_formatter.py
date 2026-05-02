"""Formatting helpers for AI Analysis V2 memory cases."""

from __future__ import annotations


def format_cases(cases: list[dict]) -> str:
    if not cases:
        return "No similar historical cases available."
    lines = []
    for idx, case in enumerate(cases, 1):
        summary = case.get("report", {}).get("summary", {})
        lines.append(
            f"{idx}. {case.get('symbol')} similarity={case.get('similarity', 0):.2f} "
            f"action={summary.get('action', 'unknown')} note={str(summary.get('reasoning', ''))[:180]}"
        )
    return "\n".join(lines)
