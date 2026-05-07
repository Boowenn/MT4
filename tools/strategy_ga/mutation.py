from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def mutate_seed(parent: Dict[str, Any], seed_id: str, generation: int, offset: int) -> Dict[str, Any]:
    """Mutate only strategy parameters, never safety or live permissions."""
    seed = deepcopy(parent)
    seed["seedId"] = seed_id
    seed["source"] = "MUTATION"
    seed["parentSeedId"] = parent.get("seedId")
    seed["strategyId"] = f"{parent.get('strategyId', 'USDJPY_STRATEGY')}_MUT_{generation:03d}_{offset:03d}"
    rsi = seed.setdefault("indicators", {}).setdefault("rsi", {})
    exit_cfg = seed.setdefault("exit", {})
    risk = seed.setdefault("risk", {})

    rsi["period"] = max(2, min(50, int(rsi.get("period", 14)) + ((offset % 3) - 1)))
    rsi["buyBand"] = max(20, min(45, float(rsi.get("buyBand", 34)) + ((offset % 5) - 2)))
    rsi["crossbackThreshold"] = round(max(0, min(3, float(rsi.get("crossbackThreshold", 0.8)) + (offset % 4 - 1) * 0.1)), 2)
    exit_cfg["breakevenDelayR"] = round(max(0, min(3, float(exit_cfg.get("breakevenDelayR", 1.0)) + (offset % 3) * 0.05)), 2)
    exit_cfg["trailStartR"] = round(max(0, min(5, float(exit_cfg.get("trailStartR", 1.5)) + (offset % 4 - 1) * 0.1)), 2)
    exit_cfg["mfeGivebackPct"] = round(max(0.1, min(0.9, float(exit_cfg.get("mfeGivebackPct", 0.6)) + (offset % 5 - 2) * 0.02)), 2)
    risk["opportunityLotMultiplier"] = round(max(0.1, min(1.0, float(risk.get("opportunityLotMultiplier", 0.35)) + (offset % 3) * 0.03)), 2)
    risk["stage"] = "SHADOW"
    risk["maxLot"] = min(2.0, float(risk.get("maxLot", 2.0)))
    return seed

