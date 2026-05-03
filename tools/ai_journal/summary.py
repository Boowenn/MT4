"""Chinese summary helpers for AI advisory journal."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from pathlib import Path
from typing import Any

from .reader import latest_outcomes, latest_records
from .schema import SUMMARY_SCHEMA, safety_payload, utc_now_iso


def _score_values(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            if row.get("scoreR") is not None:
                values.append(float(row["scoreR"]))
        except (TypeError, ValueError):
            continue
    return values


def summarize(runtime_dir: str | Path, *, limit: int = 100) -> dict[str, Any]:
    records = latest_records(runtime_dir, limit=limit)
    outcomes = [row for row in latest_outcomes(runtime_dir, limit=limit) if row.get("status") == "scored"]
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        by_symbol[str(outcome.get("symbol") or "UNKNOWN")].append(outcome)
    symbol_rows: list[dict[str, Any]] = []
    for symbol, rows in sorted(by_symbol.items()):
        scores = _score_values(rows)
        wins = [row for row in rows if row.get("directionCorrect")]
        symbol_rows.append(
            {
                "symbol": symbol,
                "samples": len(rows),
                "wins": len(wins),
                "hitRate": round(len(wins) / len(rows), 4) if rows else None,
                "averageScoreR": round(mean(scores), 4) if scores else None,
                "state": "建议暂停" if scores and mean(scores) < -0.25 else "继续观察",
            }
        )
    total_scores = _score_values(outcomes)
    return {
        "schema": SUMMARY_SCHEMA,
        "ok": True,
        "generatedAt": utc_now_iso(),
        "runtimeDir": str(Path(runtime_dir).expanduser().resolve()),
        "records": len(records),
        "scoredOutcomes": len(outcomes),
        "hitRate": round(sum(1 for row in outcomes if row.get("directionCorrect")) / len(outcomes), 4) if outcomes else None,
        "averageScoreR": round(mean(total_scores), 4) if total_scores else None,
        "symbols": symbol_rows,
        "safety": safety_payload(),
    }


def chinese_summary_text(payload: dict[str, Any]) -> str:
    rows = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
    lines = [
        "〖QuantGod AI 建议复盘〗",
        f"样本数：{payload.get('records', 0)}；已评分：{payload.get('scoredOutcomes', 0)}",
        f"总体命中率：{payload.get('hitRate') if payload.get('hitRate') is not None else '暂无'}",
        f"平均影子 R：{payload.get('averageScoreR') if payload.get('averageScoreR') is not None else '暂无'}",
        "",
        "〖品种表现〗",
    ]
    if not rows:
        lines.append("暂无可评分样本。")
    for row in rows[:12]:
        lines.append(
            f"{row.get('symbol')}：样本 {row.get('samples')}；胜率 {row.get('hitRate')}；平均影子 R {row.get('averageScoreR')}；状态 {row.get('state')}"
        )
    lines.extend(
        [
            "",
            "〖边界〗",
            "本复盘只评估历史观察建议，不会下单、平仓、撤单或修改实盘参数。",
        ]
    )
    return "\n".join(lines)
