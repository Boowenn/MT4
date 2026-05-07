from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

try:
    from tools.strategy_json.schema import base_strategy_seed
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.schema import base_strategy_seed


def initial_seed_pool(population_size: int = 16) -> List[Dict[str, Any]]:
    """Create deterministic Strategy JSON seeds for the first GA generation."""
    families = [
        "RSI_Reversal",
        "MA_Cross",
        "BB_Triple",
        "MACD_Divergence",
        "SR_Breakout",
        "USDJPY_TOKYO_RANGE_BREAKOUT",
        "USDJPY_NIGHT_REVERSION_SAFE",
        "USDJPY_H4_TREND_PULLBACK",
    ]
    seeds: List[Dict[str, Any]] = []
    for index in range(population_size):
        family = families[index % len(families)]
        direction = "LONG" if index % 3 != 1 else "SHORT"
        seed = base_strategy_seed(f"GA-USDJPY-{index + 1:04d}", family=family, direction=direction)
        seed["source"] = "LLM_SEED" if index < 4 else "MANUAL_ARCHIVE_IMPORT"
        seed["strategyId"] = f"USDJPY_{family.upper()}_{direction}_SEED_{index + 1:03d}"
        rsi = seed["indicators"]["rsi"]
        rsi["buyBand"] = 30 + (index % 7)
        rsi["crossbackThreshold"] = round(0.4 + (index % 5) * 0.2, 2)
        seed["exit"]["breakevenDelayR"] = round(0.8 + (index % 4) * 0.1, 2)
        seed["exit"]["mfeGivebackPct"] = round(0.52 + (index % 5) * 0.03, 2)
        seeds.append(seed)
    return seeds


def clone_seed(seed: Dict[str, Any], seed_id: str, source: str) -> Dict[str, Any]:
    cloned = deepcopy(seed)
    cloned["seedId"] = seed_id
    cloned["source"] = source
    return cloned
