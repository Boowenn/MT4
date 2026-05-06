from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .rsi_replay import entry_decision
from .schema import POSTERIOR_WINDOWS, VARIANT_CURRENT, VARIANT_RELAXED_ENTRY


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def posterior_r(sample: Dict[str, Any]) -> float | None:
    posterior = sample.get("posteriorR") if isinstance(sample.get("posteriorR"), dict) else {}
    for window in ("60m", "120m", "30m", "15m"):
        value = _maybe_float(posterior.get(window))
        if value is not None:
            return value
    posterior_pips = sample.get("posteriorPips") if isinstance(sample.get("posteriorPips"), dict) else {}
    risk_pips = _maybe_float(sample.get("riskPips"))
    if not risk_pips or risk_pips <= 0:
        return None
    for window in ("60m", "120m", "30m", "15m"):
        pips = _maybe_float(posterior_pips.get(window))
        if pips is not None:
            return round(pips / risk_pips, 4)
    return None


def posterior_pips(sample: Dict[str, Any]) -> float | None:
    posterior = sample.get("posteriorPips") if isinstance(sample.get("posteriorPips"), dict) else {}
    for window in ("60m", "120m", "30m", "15m"):
        value = _maybe_float(posterior.get(window))
        if value is not None:
            return value
    value_r = posterior_r(sample)
    risk_pips = _maybe_float(sample.get("riskPips"))
    if value_r is not None and risk_pips:
        return round(value_r * risk_pips, 4)
    return None


def build_entry_events(samples: Iterable[Dict[str, Any]], variant: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for sample in samples:
        decision = entry_decision(sample, VARIANT_RELAXED_ENTRY if variant == VARIANT_RELAXED_ENTRY else VARIANT_CURRENT)
        if not decision["allowed"]:
            continue
        actual_r = _maybe_float(sample.get("profitR"))
        scored_r = actual_r if sample.get("didEnter") else posterior_r(sample)
        scored_pips = _maybe_float(sample.get("profitPips")) if sample.get("didEnter") else posterior_pips(sample)
        events.append({
            **decision,
            "variant": variant,
            "didEnter": bool(sample.get("didEnter")),
            "scoreR": scored_r,
            "scorePips": scored_pips,
            "maeR": _maybe_float(sample.get("maeR")),
            "mfeR": _maybe_float(sample.get("mfeR")),
            "evidenceQuality": "HAS_CAUSAL_ENTRY_AND_OUTCOME" if scored_r is not None else "NEEDS_BAR_REPLAY",
            "posteriorWindowsAvailable": [
                window for window in POSTERIOR_WINDOWS
                if _maybe_float((sample.get("posteriorR") or {}).get(window) if isinstance(sample.get("posteriorR"), dict) else None) is not None
                or _maybe_float((sample.get("posteriorPips") or {}).get(window) if isinstance(sample.get("posteriorPips"), dict) else None) is not None
            ],
        })
    return events

