from __future__ import annotations

from dataclasses import dataclass

from .schema import DEFAULT_MAX_LOT, DEFAULT_OPPORTUNITY_MULTIPLIER, DEFAULT_RISK_PCT, DEFAULT_STANDARD_MULTIPLIER, ENTRY_BLOCKED, ENTRY_OPPORTUNITY, ENTRY_STANDARD


@dataclass
class LotSizingConfig:
    max_lot: float = DEFAULT_MAX_LOT
    risk_per_trade_pct: float = DEFAULT_RISK_PCT
    opportunity_multiplier: float = DEFAULT_OPPORTUNITY_MULTIPLIER
    standard_multiplier: float = DEFAULT_STANDARD_MULTIPLIER
    minimum_lot: float = 0.01
    lot_step: float = 0.01
    account_equity: float = 1000.0


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def align_lot(value: float, step: float) -> float:
    if value <= 0:
        return 0.0
    if step <= 0:
        step = 0.01
    return round(int(value / step) * step, 2)


def size_lot(entry_mode: str, score: float, config: LotSizingConfig | None = None) -> float:
    config = config or LotSizingConfig()
    if entry_mode == ENTRY_BLOCKED:
        return 0.0
    # Conservative proxy when exact tick value / SL distance is unavailable.
    # This policy artifact recommends a lot cap; EA must still check broker specs and margin.
    risk_budget = max(0.0, config.account_equity * (config.risk_per_trade_pct / 100.0))
    normalized_risk_lot = risk_budget / 100.0
    score_multiplier = clamp_float(score / 100.0, 0.25, 1.0)
    mode_multiplier = config.standard_multiplier if entry_mode == ENTRY_STANDARD else config.opportunity_multiplier
    raw_lot = normalized_risk_lot * score_multiplier * mode_multiplier
    raw_lot = clamp_float(raw_lot, 0.0, config.max_lot)
    if raw_lot > 0 and raw_lot < config.minimum_lot:
        raw_lot = config.minimum_lot
    return align_lot(raw_lot, config.lot_step)
