from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from .io_utils import append_jsonl, load_json, utc_now_iso, write_json
from .schema import (
    AGENT_VERSION,
    FOCUS_SYMBOL,
    SAFETY_BOUNDARY,
    execution_feedback_ledger_path,
    execution_feedback_path,
)


def build_execution_feedback(runtime_dir: Path, write: bool = True) -> Dict[str, Any]:
    rows = _collect_rows(runtime_dir)
    normalized = [_normalize_row(index, row) for index, row in enumerate(rows, start=1)]
    report = {
        "ok": True,
        "schema": "quantgod.live_execution_quality_report.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "sampleCount": len(normalized),
        "metrics": _metrics(normalized),
        "recentFeedback": normalized[-20:],
        "reasonZh": "执行反馈只用于审计滑点、拒单、延迟和 EA 是否偏离 policy；不会下单。",
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        if normalized:
            append_jsonl(execution_feedback_ledger_path(runtime_dir), normalized)
        write_json(execution_feedback_path(runtime_dir), report)
    return report


def _collect_rows(runtime_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    live_loop_ledger = runtime_dir / "live" / "QuantGod_USDJPYLiveLoopLedger.csv"
    if live_loop_ledger.exists():
        rows.extend(_read_csv(live_loop_ledger))
    for path in runtime_dir.glob("QuantGod_CloseHistory*.csv"):
        rows.extend(_read_csv(path))
    if not rows:
        status = load_json(runtime_dir / "live" / "QuantGod_USDJPYLiveLoopStatus.json")
        if status:
            rows.append(status)
    return rows


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _normalize_row(index: int, row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "quantgod.live_execution_feedback.v1",
        "feedbackId": f"USDJPY-FEEDBACK-{index:05d}",
        "createdAt": utc_now_iso(),
        "symbol": _first(row, "symbol", "Symbol") or FOCUS_SYMBOL,
        "policyId": _first(row, "policyId", "intentId", "status", "Status") or "USDJPY_LIVE_LOOP",
        "strategyId": _first(row, "strategyId", "strategy", "Strategy") or "RSI_Reversal",
        "entrySignalTime": _first(row, "entrySignalTime", "createdAt", "timestamp", "time", "Time"),
        "fillTime": _first(row, "fillTime", "CloseTime", "exitTime"),
        "expectedPrice": _num(_first(row, "expectedPrice", "entryPrice", "EntryPrice")),
        "fillPrice": _num(_first(row, "fillPrice", "price", "Price", "exitPrice")),
        "slippagePips": _num(_first(row, "slippagePips", "SlippagePips")),
        "latencyMs": _num(_first(row, "latencyMs", "LatencyMs")),
        "rejectReason": _first(row, "rejectReason", "mainBlocker", "reason", "Reason"),
        "exitReason": _first(row, "exitReason", "ExitReason"),
        "profitR": _num(_first(row, "profitR", "ProfitR")),
        "mfeR": _num(_first(row, "mfeR", "MfeR")),
        "maeR": _num(_first(row, "maeR", "MaeR")),
        "sourceKeys": sorted(row.keys())[:20],
        "safety": dict(SAFETY_BOUNDARY),
    }


def _metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    slippage = [abs(float(row["slippagePips"])) for row in rows if row.get("slippagePips")]
    rejects = [row for row in rows if row.get("rejectReason")]
    profits = [float(row.get("profitR") or 0.0) for row in rows]
    return {
        "feedbackRows": len(rows),
        "rejectCount": len(rejects),
        "avgAbsSlippagePips": round(sum(slippage) / len(slippage), 4) if slippage else 0.0,
        "netR": round(sum(profits), 4),
    }


def _first(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in {None, ""}:
            return row[key]
    return None


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
