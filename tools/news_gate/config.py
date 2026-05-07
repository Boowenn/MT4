from __future__ import annotations

import os
from dataclasses import dataclass

from .schema import NEWS_GATE_HARD, NEWS_GATE_HARD_ONLY, NEWS_GATE_OFF, NEWS_GATE_SOFT


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return default


def _normalize_mode(value: str) -> str:
    mode = str(value or NEWS_GATE_SOFT).strip().upper()
    if mode in {"HARDONLY", "HARD_ONLY", "HIGH_IMPACT_ONLY"}:
        return NEWS_GATE_HARD_ONLY
    if mode in {NEWS_GATE_OFF, NEWS_GATE_SOFT, NEWS_GATE_HARD}:
        return mode
    return NEWS_GATE_SOFT


@dataclass(frozen=True)
class NewsGateConfig:
    mode: str = NEWS_GATE_SOFT
    hardBlockOnlyHighImpact: bool = True
    softLotMultiplier: float = 0.5
    unknownLotMultiplier: float = 0.75
    softStageDowngrade: bool = True
    hardBlockMinutesBefore: int = 30
    hardBlockMinutesAfter: int = 30


def read_news_gate_config() -> NewsGateConfig:
    return NewsGateConfig(
        mode=_normalize_mode(os.environ.get("QG_NEWS_GATE_MODE", NEWS_GATE_SOFT)),
        hardBlockOnlyHighImpact=_env_bool("QG_NEWS_HARD_BLOCK_ONLY_HIGH_IMPACT", True),
        softLotMultiplier=max(0.01, min(1.0, _env_float("QG_NEWS_SOFT_LOT_MULTIPLIER", 0.5))),
        unknownLotMultiplier=max(0.01, min(1.0, _env_float("QG_NEWS_UNKNOWN_LOT_MULTIPLIER", 0.75))),
        softStageDowngrade=_env_bool("QG_NEWS_SOFT_STAGE_DOWNGRADE", True),
        hardBlockMinutesBefore=_env_int("QG_NEWS_HARD_BLOCK_MINUTES_BEFORE", 30),
        hardBlockMinutesAfter=_env_int("QG_NEWS_HARD_BLOCK_MINUTES_AFTER", 30),
    )

