from __future__ import annotations

from statistics import mean, median
from typing import Any, Dict, Iterable, List

from .schema import (
    CONCLUSION_LIVE_CONFIG_ELIGIBLE,
    CONCLUSION_REJECTED,
    CONCLUSION_SHADOW_ONLY,
    CONCLUSION_TESTER_ONLY,
)


def _values(events: Iterable[Dict[str, Any]], key: str) -> List[float]:
    values: List[float] = []
    for event in events:
        value = event.get(key)
        try:
            if value is not None:
                values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def loss_streak(events: List[Dict[str, Any]]) -> int:
    longest = current = 0
    for event in events:
        value = event.get("scoreR")
        if value is None:
            continue
        if float(value) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def summarize_events(events: List[Dict[str, Any]], baseline: Dict[str, Any] | None = None) -> Dict[str, Any]:
    r_values = _values(events, "scoreR")
    mae = _values(events, "maeR")
    mfe = _values(events, "mfeR")
    capture = _values(events, "profitCaptureRatio")
    sample_count = len(events)
    unresolved = sum(1 for event in events if event.get("scoreR") is None)
    false_entries = sum(1 for value in r_values if value < 0)
    payload = {
        "sampleCount": sample_count,
        "scoredSampleCount": len(r_values),
        "unresolvedSampleCount": unresolved,
        "netR": round(sum(r_values), 4) if r_values else 0.0,
        "avgR": round(mean(r_values), 4) if r_values else None,
        "medianR": round(median(r_values), 4) if r_values else None,
        "maxAdverseR": round(min(mae), 4) if mae else None,
        "maxFavorableR": round(max(mfe), 4) if mfe else None,
        "profitCaptureRatio": round(mean(capture), 4) if capture else None,
        "falseEntryCount": false_entries,
        "winRate": round(sum(1 for value in r_values if value > 0) / len(r_values) * 100, 2) if r_values else None,
        "lossStreak": loss_streak(events),
        "evidenceQuality": "NEEDS_BAR_REPLAY" if unresolved else "CAUSAL_REPLAY_READY",
    }
    if baseline:
        payload["entryCountDelta"] = sample_count - int(baseline.get("sampleCount") or 0)
        payload["netRDelta"] = round(payload["netR"] - float(baseline.get("netR") or 0.0), 4)
        payload["missedOpportunityReduction"] = max(0, payload["entryCountDelta"])
    else:
        payload["entryCountDelta"] = 0
        payload["netRDelta"] = 0.0
        payload["missedOpportunityReduction"] = 0
    payload["conclusion"] = grade_variant(payload, baseline)
    return payload


def grade_variant(metrics: Dict[str, Any], baseline: Dict[str, Any] | None = None) -> str:
    sample_count = int(metrics.get("scoredSampleCount") or 0)
    net_delta = float(metrics.get("netRDelta") or 0.0)
    max_adverse = metrics.get("maxAdverseR")
    baseline_adverse = baseline.get("maxAdverseR") if baseline else None
    adverse_worse = False
    try:
        if max_adverse is not None and baseline_adverse is not None:
            adverse_worse = float(max_adverse) < float(baseline_adverse) - 0.35
    except (TypeError, ValueError):
        adverse_worse = False
    if baseline and (net_delta <= 0 or adverse_worse):
        return CONCLUSION_REJECTED
    if sample_count < 5 or metrics.get("evidenceQuality") == "NEEDS_BAR_REPLAY":
        return CONCLUSION_SHADOW_ONLY
    if sample_count >= 20 and float(metrics.get("netR") or 0.0) > 0 and not adverse_worse and (metrics.get("winRate") or 0) >= 55:
        return CONCLUSION_LIVE_CONFIG_ELIGIBLE
    return CONCLUSION_TESTER_ONLY

