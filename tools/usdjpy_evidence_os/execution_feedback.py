from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .io_utils import append_jsonl_unique, load_json, read_jsonl_tail, utc_now_iso, write_json
from .schema import (
    AGENT_VERSION,
    FOCUS_SYMBOL,
    SAFETY_BOUNDARY,
    execution_feedback_ledger_path,
    execution_feedback_path,
)


def build_execution_feedback(runtime_dir: Path, write: bool = True) -> Dict[str, Any]:
    rows = _collect_rows(runtime_dir)
    normalized = _dedupe_feedback(
        [_normalize_row(index, row, source) for index, (row, source) in enumerate(rows, start=1)]
    )
    report = {
        "ok": True,
        "schema": "quantgod.live_execution_quality_report.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "sampleCount": len(normalized),
        "metrics": _metrics(normalized),
        "qualityGates": _quality_gates(normalized),
        "recentFeedback": normalized[-20:],
        "reasonZh": "执行反馈统一审计 EA trade event、成交、拒单、滑点、延迟和 policy 偏离；不会下单。",
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        if normalized:
            append_jsonl_unique(execution_feedback_ledger_path(runtime_dir), normalized, "feedbackId")
        write_json(execution_feedback_path(runtime_dir), report)
    return report


def _collect_rows(runtime_dir: Path) -> List[Tuple[Dict[str, Any], str]]:
    rows: List[Tuple[Dict[str, Any], str]] = []
    trade_events = runtime_dir / "QuantGod_RuntimeTradeEvents.jsonl"
    rows.extend((row, trade_events.name) for row in read_jsonl_tail(trade_events, 500))
    live_loop_ledger = runtime_dir / "live" / "QuantGod_USDJPYLiveLoopLedger.csv"
    if live_loop_ledger.exists():
        rows.extend((row, live_loop_ledger.name) for row in _read_csv(live_loop_ledger))
    for name in (
        "QuantGod_TradeJournal.csv",
        "QuantGod_TradeEventLinks.csv",
        "QuantGod_TradeOutcomeLabels.csv",
        "QuantGod_USDJPYEADryRunDecisionLedger.csv",
    ):
        path = runtime_dir / name
        if path.exists():
            rows.extend((row, path.name) for row in _read_csv(path))
    adaptive_dry_run = runtime_dir / "adaptive" / "QuantGod_USDJPYEADryRunDecisionLedger.csv"
    if adaptive_dry_run.exists():
        rows.extend((row, adaptive_dry_run.name) for row in _read_csv(adaptive_dry_run))
    for path in runtime_dir.glob("QuantGod_CloseHistory*.csv"):
        rows.extend((row, path.name) for row in _read_csv(path))
    if not rows:
        status = load_json(runtime_dir / "live" / "QuantGod_USDJPYLiveLoopStatus.json")
        if status:
            rows.append((status, "QuantGod_USDJPYLiveLoopStatus.json"))
    return rows


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _normalize_row(index: int, row: Dict[str, Any], source: str) -> Dict[str, Any]:
    symbol = _first(row, "symbol", "Symbol") or FOCUS_SYMBOL
    expected_price = _num(_first(row, "expectedPrice", "entryPrice", "EntryPrice", "openPrice"))
    fill_price = _num(_first(row, "fillPrice", "price", "Price", "exitPrice", "ClosePrice"))
    slippage_pips = _num(_first(row, "slippagePips", "SlippagePips"))
    if slippage_pips == 0.0 and expected_price and fill_price:
        slippage_pips = round((fill_price - expected_price) / 0.01, 4)
    retcode = _first(row, "retcode", "Retcode", "retCode")
    reject_reason = _reject_reason(row, retcode)
    feedback_id = _feedback_id(index, row, source)
    return {
        "schema": "quantgod.live_execution_feedback.v1",
        "feedbackId": feedback_id,
        "createdAt": utc_now_iso(),
        "symbol": symbol,
        "policyId": _first(row, "policyId", "intentId", "status", "Status") or "USDJPY_LIVE_LOOP",
        "strategyId": _first(row, "strategyId", "strategy", "Strategy") or "RSI_Reversal",
        "entrySignalTime": _first(row, "entrySignalTime", "createdAt", "timestamp", "time", "Time"),
        "orderSendTime": _first(row, "orderSendTime", "generatedAt", "sendTime"),
        "fillTime": _first(row, "fillTime", "CloseTime", "exitTime"),
        "expectedPrice": expected_price,
        "fillPrice": fill_price,
        "slippagePips": slippage_pips,
        "spreadAtEntry": _num(_first(row, "spreadAtEntry", "spreadPoints", "Spread", "spread")),
        "latencyMs": _num(_first(row, "latencyMs", "LatencyMs")),
        "retcode": retcode,
        "rejectReason": reject_reason,
        "exitReason": _first(row, "exitReason", "ExitReason"),
        "profitR": _num(_first(row, "profitR", "ProfitR")),
        "mfeR": _num(_first(row, "mfeR", "MfeR")),
        "maeR": _num(_first(row, "maeR", "MaeR")),
        "source": source,
        "sourceKeys": sorted(row.keys())[:20],
        "safety": dict(SAFETY_BOUNDARY),
    }


def _metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    slippage = [abs(float(row["slippagePips"])) for row in rows if row.get("slippagePips")]
    rejects = [row for row in rows if row.get("rejectReason")]
    fills = [row for row in rows if row.get("fillPrice") and not row.get("rejectReason")]
    latency = [float(row["latencyMs"]) for row in rows if row.get("latencyMs")]
    profits = [float(row.get("profitR") or 0.0) for row in rows]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    policy_mismatch = [
        row
        for row in rows
        if str(row.get("policyId") or "").upper() in {"EVIDENCE_MISSING", "BLOCKED"}
        and (row.get("fillPrice") or row.get("retcode"))
    ]
    return {
        "feedbackRows": len(rows),
        "fillCount": len(fills),
        "rejectCount": len(rejects),
        "rejectRatePct": round((len(rejects) / len(rows) * 100.0), 2) if rows else 0.0,
        "avgAbsSlippagePips": round(sum(slippage) / len(slippage), 4) if slippage else 0.0,
        "maxAbsSlippagePips": round(max(slippage), 4) if slippage else 0.0,
        "avgLatencyMs": round(sum(latency) / len(latency), 2) if latency else 0.0,
        "netR": round(sum(profits), 4),
        "winRatePct": round(len(wins) / (len(wins) + len(losses)) * 100.0, 2) if wins or losses else 0.0,
        "policyMismatchCount": len(policy_mismatch),
        "feedbackQuality": _feedback_quality(len(rows), len(fills), len(rejects)),
    }


def _quality_gates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metrics = _metrics(rows)
    return [
        {
            "name": "slippage",
            "status": "PASS" if float(metrics["avgAbsSlippagePips"]) <= 0.8 else "WARN",
            "reasonZh": "平均滑点处于可接受范围" if float(metrics["avgAbsSlippagePips"]) <= 0.8 else "平均滑点偏高，需要降仓或限制触发窗口",
        },
        {
            "name": "reject_rate",
            "status": "PASS" if float(metrics["rejectRatePct"]) <= 15.0 else "WARN",
            "reasonZh": "拒单率正常" if float(metrics["rejectRatePct"]) <= 15.0 else "拒单率偏高，需要检查 EA 与券商执行",
        },
        {
            "name": "policy_mismatch",
            "status": "PASS" if int(metrics["policyMismatchCount"]) == 0 else "WARN",
            "reasonZh": "未发现 policy 与执行明显偏离" if int(metrics["policyMismatchCount"]) == 0 else "发现 policy 阻断态仍有执行痕迹，需要复盘",
        },
    ]


def _dedupe_feedback(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        key = row.get("feedbackId")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


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


def _feedback_quality(rows: int, fills: int, rejects: int) -> str:
    if rows >= 30 and fills:
        return "HIGH"
    if rows >= 10 or fills or rejects:
        return "MEDIUM"
    if rows:
        return "LOW"
    return "MISSING"


def _reject_reason(row: Dict[str, Any], retcode: Any) -> str:
    explicit = _first(row, "rejectReason", "mainBlocker", "reason", "Reason")
    if explicit:
        return str(explicit)
    code = str(retcode or "").strip()
    if not code or code in {"0", "10009", "10008"}:
        return ""
    return f"MT5_RETCODE_{code}"


def _feedback_id(index: int, row: Dict[str, Any], source: str) -> str:
    raw = "|".join(
        str(_first(row, key) or "")
        for key in (
            "ticket",
            "Ticket",
            "order",
            "deal",
            "intentId",
            "policyId",
            "generatedAt",
            "time",
            "Time",
            "CloseTime",
        )
    )
    seed = f"{source}|{raw}|{index if not raw.strip('|') else ''}"
    return "USDJPY-FEEDBACK-" + hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]
