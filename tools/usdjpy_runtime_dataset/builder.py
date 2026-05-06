from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from tools.usdjpy_strategy_lab.data_loader import (
        _write_json,
        fastlane_quality,
        focus_runtime_snapshot,
        first_json,
        is_focus_symbol,
        read_all_csv,
        to_direction,
        to_float,
    )
    from tools.usdjpy_strategy_lab.schema import normalize_strategy_name
except ModuleNotFoundError:  # pragma: no cover - CLI entrypoint runs from tools/
    from usdjpy_strategy_lab.data_loader import (
        _write_json,
        fastlane_quality,
        focus_runtime_snapshot,
        first_json,
        is_focus_symbol,
        read_all_csv,
        to_direction,
        to_float,
    )
    from usdjpy_strategy_lab.schema import normalize_strategy_name

from .schema import FOCUS_SYMBOL, READ_ONLY_SAFETY, SCHEMA_DATASET, utc_now_iso


def _pick(row: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        value = lower.get(key.lower())
        if value not in (None, ""):
            return value
    return default


def _symbol(row: Dict[str, Any]) -> str:
    return str(_pick(row, "symbol", "Symbol", "品种", default=FOCUS_SYMBOL) or FOCUS_SYMBOL)


def _is_usdjpy_row(row: Dict[str, Any]) -> bool:
    return is_focus_symbol(_symbol(row)) or "USDJPY" in json.dumps(row, ensure_ascii=False).upper()


def _sample_from_csv(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    direction = to_direction(_pick(row, "direction", "side", "type", "orderType", "方向"))
    profit = to_float(_pick(row, "profit", "netUSC", "pnl", "profitUSC", "NetUSC", "净值"), 0.0)
    blocker = str(_pick(row, "blocker", "blockReason", "reason", "status", "event", "label", "说明", default="")).strip()
    entered = str(_pick(row, "didEnter", "entered", "event", "type", default="")).upper() in {"1", "TRUE", "ENTRY", "OPEN"}
    if source == "close_history":
        entered = True
    ready = "READY" in blocker.upper() or str(_pick(row, "readyBuySignal", "rsiBuySignal", default="")).lower() == "true"
    return {
        "source": source,
        "timestamp": _pick(row, "timestamp", "time", "Time", "closeTime", "openTime", "generatedAtIso"),
        "symbol": FOCUS_SYMBOL,
        "strategy": normalize_strategy_name(_pick(row, "strategy", "route", "routeKey", "strategyName", default="UNKNOWN")),
        "direction": direction,
        "status": _pick(row, "status", "state", "event", "label"),
        "blockReason": blocker,
        "didEnter": bool(entered),
        "wouldEnter": bool(ready or "WOULD" in blocker.upper()),
        "profitUSC": profit,
        "mfeR": to_float(_pick(row, "mfeR", "MFER", "mfe", "maxFavorableR"), 0.0),
        "maeR": to_float(_pick(row, "maeR", "MAER", "mae", "maxAdverseR"), 0.0),
        "exitReason": _pick(row, "exitReason", "closeReason", "reason"),
        "raw": row,
    }


def _diagnostic_sample(runtime_dir: Path) -> Dict[str, Any] | None:
    diag = first_json(runtime_dir, "QuantGod_USDJPYRsiEntryDiagnostics.json") or {}
    if not diag:
        dashboard = focus_runtime_snapshot(runtime_dir) or {}
        diag = dashboard.get("usdJpyRsiEntryDiagnostics") if isinstance(dashboard.get("usdJpyRsiEntryDiagnostics"), dict) else {}
    if not diag:
        return None
    status = str(diag.get("status") or diag.get("conclusion") or "").upper()
    blockers = diag.get("mainBlockers") if isinstance(diag.get("mainBlockers"), list) else []
    return {
        "source": "rsi_entry_diagnostics",
        "timestamp": diag.get("generatedAtIso") or diag.get("timestamp"),
        "symbol": FOCUS_SYMBOL,
        "strategy": "RSI_Reversal",
        "direction": "LONG",
        "status": status or "UNKNOWN",
        "blockReason": "; ".join(str(item) for item in blockers) or diag.get("message") or "",
        "didEnter": False,
        "wouldEnter": status == "READY_BUY_SIGNAL" or bool(diag.get("rsiBuySignal")),
        "profitUSC": 0.0,
        "mfeR": 0.0,
        "maeR": 0.0,
        "exitReason": "",
        "raw": diag,
    }


def _collect_samples(runtime_dir: Path) -> List[Dict[str, Any]]:
    sources = [
        ("close_history", ("QuantGod_CloseHistory.csv", "QuantGod_CloseHistoryLedger.csv", "QuantGod_MT5CloseHistory.csv")),
        ("trade_journal", ("QuantGod_TradeJournal.csv", "QuantGod_MT5TradeJournal.csv", "QuantGod_TradeJournalLedger.csv")),
        ("entry_blockers", ("QuantGod_EntryBlockers.csv", "QuantGod_MT5EntryBlockers.csv", "QuantGod_EntryBlockerLedger.csv")),
        ("shadow_outcomes", ("ShadowCandidateOutcomeLedger.csv", "QuantGod_ShadowCandidateOutcomeLedger.csv")),
        ("strategy_report", ("QuantGod_StrategyEvaluationReport.csv",)),
    ]
    samples: List[Dict[str, Any]] = []
    for source, names in sources:
        for row in read_all_csv(runtime_dir, *names):
            if _is_usdjpy_row(row):
                samples.append(_sample_from_csv(row, source))
    diag = _diagnostic_sample(runtime_dir)
    if diag:
        samples.insert(0, diag)
    return samples


def _blocker_counter(samples: Iterable[Dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for sample in samples:
        text = str(sample.get("blockReason") or sample.get("status") or "").upper()
        if not text:
            continue
        for token in ("SESSION", "SPREAD", "NEWS", "COOLDOWN", "STARTUP", "WAIT", "ROUTE_DISABLED", "NO_CROSS", "KILL"):
            if token in text:
                counter[token] += 1
    return counter


def build_runtime_dataset(runtime_dir: Path, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    samples = _collect_samples(runtime_dir)
    blockers = _blocker_counter(samples)
    close_trades = [sample for sample in samples if sample.get("source") == "close_history"]
    decision_samples = [sample for sample in samples if sample.get("source") != "close_history"]
    ready = [sample for sample in samples if sample.get("wouldEnter")]
    entered = [sample for sample in samples if sample.get("didEnter")]
    net_usc = round(sum(to_float(sample.get("profitUSC"), 0.0) for sample in close_trades), 4)
    live_loop = first_json(runtime_dir, "QuantGod_USDJPYLiveLoopStatus.json") or {}
    policy = first_json(runtime_dir, "QuantGod_USDJPYAutoExecutionPolicy.json") or {}
    fastlane = fastlane_quality(runtime_dir)
    dataset_dir = runtime_dir / "datasets" / "usdjpy"
    payload = {
        "ok": True,
        "schema": SCHEMA_DATASET,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "runtimeDir": str(runtime_dir),
        "datasetDir": str(dataset_dir),
        "safety": READ_ONLY_SAFETY,
        "summary": {
            "sampleCount": len(samples),
            "decisionSampleCount": len(decision_samples),
            "readySignalCount": len(ready),
            "actualEntryCount": len(entered),
            "blockedCount": sum(blockers.values()),
            "closeTradeCount": len(close_trades),
            "netUSC": net_usc,
            "blockerCounts": dict(blockers.most_common()),
            "fastlaneQuality": fastlane.get("quality"),
            "liveLoopState": live_loop.get("state"),
            "topLiveEligiblePolicy": (policy.get("topLiveEligiblePolicy") or {}).get("strategy"),
            "topShadowPolicy": (policy.get("topShadowPolicy") or {}).get("strategy"),
        },
        "latest": {
            "runtime": focus_runtime_snapshot(runtime_dir) or {},
            "fastlane": fastlane,
            "liveLoop": live_loop,
            "policy": policy,
        },
        "samples": samples[:500],
    }
    if write:
        _write_json(dataset_dir / "QuantGod_USDJPYRuntimeDataset.json", payload)
        jsonl = dataset_dir / "QuantGod_USDJPYDecisionSamples.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in samples) + ("\n" if samples else ""), encoding="utf-8")
    return payload
