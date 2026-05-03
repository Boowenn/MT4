"""Score shadow outcomes for QuantGod AI advisory records."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .price_probe import current_price_from_runtime
from .reader import append_jsonl, latest_outcomes, latest_records, outcome_path
from .schema import OUTCOME_SCHEMA, safety_payload, utc_now_iso, validate_record


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_seconds(start: Any, end: Any | None = None) -> int | None:
    start_dt = _parse_time(start)
    if not start_dt:
        return None
    end_dt = _parse_time(end) or datetime.now(timezone.utc)
    return max(0, int((end_dt - start_dt).total_seconds()))


def _directional_move(direction: str, reference: float, current: float) -> float:
    if direction == "LONG":
        return current - reference
    if direction == "SHORT":
        return reference - current
    return 0.0


def _risk_unit(reference: float, spread: float | None) -> float:
    # A conservative shadow scoring unit. We prefer observed spread when it is
    # meaningful; otherwise use 0.2% of reference price. This is not a real TP/SL.
    candidates = []
    if spread is not None and spread > 0:
        candidates.append(spread * 3.0)
    if reference > 0:
        candidates.append(abs(reference) * 0.002)
    return max(max(candidates or [1.0]), 1e-9)


def score_record(record: dict[str, Any], *, runtime_dir: str | Path, horizon: str = "4h", now_iso: str | None = None) -> dict[str, Any]:
    symbol = str(record.get("symbol") or "UNKNOWN")
    shadow = record.get("shadowSignal") if isinstance(record.get("shadowSignal"), dict) else {}
    snapshot = record.get("snapshot") if isinstance(record.get("snapshot"), dict) else {}
    direction = str(shadow.get("direction") or "NONE").upper()
    reference = _num(shadow.get("referencePrice") or snapshot.get("referencePrice"))
    price = current_price_from_runtime(runtime_dir, symbol)
    current = _num(price.get("mid"))
    now = now_iso or utc_now_iso()
    elapsed = _elapsed_seconds(record.get("generatedAt"), now)
    outcome = {
        "schema": OUTCOME_SCHEMA,
        "recordId": record.get("recordId"),
        "symbol": symbol,
        "scoredAt": now,
        "horizon": horizon,
        "elapsedSeconds": elapsed,
        "referencePrice": reference,
        "currentPrice": current,
        "priceSource": price.get("source") or "unknown",
        "direction": direction,
        "status": "pending",
        "directionCorrect": None,
        "move": None,
        "movePct": None,
        "scoreR": None,
        "classification": "待观察",
        "safety": safety_payload(),
    }
    if direction not in {"LONG", "SHORT"}:
        outcome.update({"status": "not_actionable", "classification": "观望样本"})
    elif reference is None or current is None:
        outcome.update({"status": "missing_price", "classification": "缺少价格"})
    else:
        move = _directional_move(direction, reference, current)
        unit = _risk_unit(reference, _num(snapshot.get("spread")))
        score_r = move / unit
        move_pct = (move / reference) if reference else None
        outcome.update(
            {
                "status": "scored",
                "directionCorrect": move > 0,
                "move": move,
                "movePct": move_pct,
                "scoreR": round(score_r, 4),
                "classification": "正向" if move > 0 else "负向" if move < 0 else "持平",
            }
        )
    validate_record(outcome)
    return outcome


def score_latest(runtime_dir: str | Path, *, limit: int = 50, horizon: str = "4h", write: bool = True) -> dict[str, Any]:
    records = latest_records(runtime_dir, limit=limit)
    outcomes = [score_record(record, runtime_dir=runtime_dir, horizon=horizon) for record in records]
    if write:
        for outcome in outcomes:
            append_jsonl(outcome_path(runtime_dir), outcome)
    scored = [item for item in outcomes if item.get("status") == "scored"]
    wins = [item for item in scored if item.get("directionCorrect")]
    losses = [item for item in scored if item.get("directionCorrect") is False]
    score_values = [float(item["scoreR"]) for item in scored if item.get("scoreR") is not None]
    return {
        "ok": True,
        "mode": "QUANTGOD_AI_ADVISORY_JOURNAL_SCORE",
        "runtimeDir": str(Path(runtime_dir).expanduser().resolve()),
        "horizon": horizon,
        "records": len(records),
        "scored": len(scored),
        "wins": len(wins),
        "losses": len(losses),
        "hitRate": round(len(wins) / len(scored), 4) if scored else None,
        "averageScoreR": round(mean(score_values), 4) if score_values else None,
        "outcomes": outcomes,
        "outcomePath": str(outcome_path(runtime_dir)),
        "safety": safety_payload(),
    }


def scored_outcomes_for_symbol(runtime_dir: str | Path, symbol: str, *, limit: int = 100) -> list[dict[str, Any]]:
    outcomes = latest_outcomes(runtime_dir, limit=limit)
    return [item for item in outcomes if item.get("status") == "scored" and str(item.get("symbol") or "") == symbol]
