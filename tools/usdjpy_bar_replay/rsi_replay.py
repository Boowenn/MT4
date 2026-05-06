from __future__ import annotations

from typing import Any, Dict

from .market_clock import classify_gates


def current_entry_allowed(sample: Dict[str, Any]) -> bool:
    gates = classify_gates(sample)
    if not gates["hardGatePass"]:
        return False
    return bool(sample.get("didEnter") or (sample.get("wouldEnter") and gates["tacticalGatePass"]))


def relaxed_entry_allowed(sample: Dict[str, Any]) -> bool:
    gates = classify_gates(sample)
    if not gates["hardGatePass"]:
        return False
    if sample.get("didEnter") or sample.get("wouldEnter"):
        return True
    return bool(gates["tacticalBlockers"])


def entry_decision(sample: Dict[str, Any], variant: str) -> Dict[str, Any]:
    gates = classify_gates(sample)
    if variant == "relaxed_entry_v1":
        allowed = relaxed_entry_allowed(sample)
    else:
        allowed = current_entry_allowed(sample)
    return {
        "timestamp": sample.get("timestamp"),
        "symbol": sample.get("symbol"),
        "strategy": sample.get("strategy"),
        "direction": sample.get("direction"),
        "allowed": allowed,
        "hardGatePass": gates["hardGatePass"],
        "tacticalGatePass": gates["tacticalGatePass"],
        "hardBlockers": gates["hardBlockers"],
        "tacticalBlockers": gates["tacticalBlockers"],
        "causalInputsOnly": True,
        "posteriorUsedForTrigger": False,
    }

