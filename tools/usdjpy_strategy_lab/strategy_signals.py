from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .data_loader import _get, read_all_csv, to_float, to_direction
from .schema import (
    FOCUS_SYMBOL,
    NEW_USDJPY_STRATEGIES,
    READ_ONLY_SAFETY,
    STRATEGY_DISPLAY_NAMES,
    assert_no_secret_or_execution_flags,
    is_focus_symbol,
    normalize_symbol,
    utc_now_iso,
)


def _candidate_direction(row: Dict[str, Any]) -> str:
    direction = to_direction(_get(row, "CandidateDirection", "direction", "SignalDirection", "side", default="UNKNOWN"))
    return direction


def _candidate_route(row: Dict[str, Any]) -> str:
    return str(_get(row, "CandidateRoute", "strategy", "Strategy", "route", default="")).strip()


def build_candidate_signals(runtime_dir: Path, *, limit: int = 50) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for row in read_all_csv(runtime_dir, "QuantGod_ShadowCandidateLedger.csv", "ShadowCandidateLedger.csv"):
        symbol = normalize_symbol(_get(row, "Symbol", "symbol", default=FOCUS_SYMBOL))
        route = _candidate_route(row)
        if not is_focus_symbol(symbol) or route not in NEW_USDJPY_STRATEGIES:
            continue
        rows.append({
            "eventId": _get(row, "EventId", "id", default=""),
            "symbol": FOCUS_SYMBOL,
            "strategy": route,
            "strategyName": STRATEGY_DISPLAY_NAMES.get(route, route),
            "timeframe": _get(row, "Timeframe", "timeframe", default="M15"),
            "direction": _candidate_direction(row),
            "score": to_float(_get(row, "CandidateScore", "score", default=0.0)),
            "regime": _get(row, "Regime", "regime", default="UNKNOWN"),
            "referencePrice": to_float(_get(row, "ReferencePrice", "price", default=0.0)),
            "spreadPips": to_float(_get(row, "SpreadPips", "spread", default=0.0)),
            "eventBarTime": _get(row, "EventBarTime", "time", default=""),
            "labelTimeLocal": _get(row, "LabelTimeLocal", "LabelTimeServer", default=""),
            "trigger": _get(row, "Trigger", "trigger", default=""),
            "reason": _get(row, "Reason", "reason", default="影子策略候选"),
        })
    rows = rows[-max(1, limit):]
    rows.reverse()
    payload = {
        "schema": "quantgod.usdjpy_strategy_signals.v1",
        "generatedAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "count": len(rows),
        "signals": rows,
        "safety": dict(READ_ONLY_SAFETY),
    }
    assert_no_secret_or_execution_flags(payload)
    return payload
