from __future__ import annotations

from statistics import mean
from typing import Any, Dict, Iterable, List


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _values(events: Iterable[Dict[str, Any]], key: str) -> List[float]:
    values: List[float] = []
    for event in events:
        value = _float(event.get(key))
        if value is not None:
            values.append(value)
    return values


def loss_streak(events: List[Dict[str, Any]]) -> int:
    longest = current = 0
    for value in _values(events, "scoreR"):
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def summarize(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    score = _values(events, "scoreR")
    mae = _values(events, "maeR")
    mfe = _values(events, "mfeR")
    return {
        "sampleCount": len(events),
        "scoredSampleCount": len(score),
        "netR": round(sum(score), 4) if score else 0.0,
        "avgR": round(mean(score), 4) if score else None,
        "maxAdverseR": round(min(mae), 4) if mae else None,
        "maxFavorableR": round(max(mfe), 4) if mfe else None,
        "winRate": round(sum(1 for value in score if value > 0) / len(score) * 100, 2) if score else None,
        "lossStreak": loss_streak(events),
    }


def compare(candidate: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    candidate_adverse = candidate.get("maxAdverseR")
    baseline_adverse = baseline.get("maxAdverseR")
    adverse_delta = None
    if candidate_adverse is not None and baseline_adverse is not None:
        adverse_delta = round(float(candidate_adverse) - float(baseline_adverse), 4)
    return {
        **candidate,
        "baselineNetR": baseline.get("netR", 0.0),
        "netRDelta": round(float(candidate.get("netR") or 0.0) - float(baseline.get("netR") or 0.0), 4),
        "sampleCountDelta": int(candidate.get("sampleCount") or 0) - int(baseline.get("sampleCount") or 0),
        "maxAdverseDeltaR": adverse_delta,
    }

