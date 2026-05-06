from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .schema import VARIANT_CURRENT, VARIANT_LET_PROFIT_RUN


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_exit_events(samples: Iterable[Dict[str, Any]], variant: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for sample in samples:
        if not sample.get("didEnter"):
            continue
        profit_r = _maybe_float(sample.get("profitR"))
        mfe_r = _maybe_float(sample.get("mfeR"))
        mae_r = _maybe_float(sample.get("maeR"))
        if profit_r is None:
            continue
        if variant == VARIANT_LET_PROFIT_RUN and mfe_r is not None and mfe_r > 0:
            score_r = max(profit_r, min(mfe_r * 0.62, mfe_r - 0.10))
        else:
            score_r = profit_r
        capture = None
        if mfe_r and mfe_r > 0:
            capture = round(max(0.0, score_r) / mfe_r, 4)
        events.append({
            "timestamp": sample.get("timestamp"),
            "symbol": sample.get("symbol"),
            "strategy": sample.get("strategy"),
            "direction": sample.get("direction"),
            "variant": variant,
            "scoreR": round(score_r, 4),
            "actualProfitR": profit_r,
            "mfeR": mfe_r,
            "maeR": mae_r,
            "profitCaptureRatio": capture,
            "exitReason": sample.get("exitReason"),
            "causalInputsOnly": True,
        })
    return events

