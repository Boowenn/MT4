from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .schema import (
    DEFAULT_ENTRY_CONDITIONS,
    DEFAULT_EXIT,
    DEFAULT_RSI,
    FOCUS_SYMBOL,
    SAFETY_BOUNDARY,
    SCHEMA_VERSION,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_strategy_json(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing safe defaults without granting extra permissions."""
    data = deepcopy(seed) if isinstance(seed, dict) else {}
    data["schema"] = data.get("schema") or SCHEMA_VERSION
    data["symbol"] = FOCUS_SYMBOL
    data["lane"] = data.get("lane") or "MT5_SHADOW"
    data["strategyFamily"] = data.get("strategyFamily") or "RSI_Reversal"
    data["direction"] = str(data.get("direction") or "LONG").upper()
    data["timeframes"] = data.get("timeframes") if isinstance(data.get("timeframes"), list) else ["M1", "M15", "H1"]

    indicators = _safe_dict(data.get("indicators"))
    rsi = {**DEFAULT_RSI, **_safe_dict(indicators.get("rsi"))}
    indicators["rsi"] = rsi
    data["indicators"] = indicators

    entry = _safe_dict(data.get("entry"))
    entry["mode"] = entry.get("mode") or "OPPORTUNITY_ENTRY"
    entry["conditions"] = entry.get("conditions") if isinstance(entry.get("conditions"), list) else list(DEFAULT_ENTRY_CONDITIONS)
    data["entry"] = entry

    data["exit"] = {**deepcopy(DEFAULT_EXIT), **_safe_dict(data.get("exit"))}
    risk = _safe_dict(data.get("risk"))
    risk["stage"] = risk.get("stage") or "SHADOW"
    risk["maxLot"] = risk.get("maxLot", 2.0)
    risk["opportunityLotMultiplier"] = risk.get("opportunityLotMultiplier", 0.35)
    data["risk"] = risk

    safety = {**SAFETY_BOUNDARY, **_safe_dict(data.get("safety"))}
    for key in SAFETY_BOUNDARY:
        if SAFETY_BOUNDARY[key] is False:
            safety[key] = False
    data["safety"] = safety
    return data

