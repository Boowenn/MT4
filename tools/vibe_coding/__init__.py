"""QuantGod Phase 3 Vibe Coding strategy workbench.

This package is local-first and research-only. Generated strategies are stored as
research/backtest artifacts and cannot send broker orders or mutate live presets.
"""

from .strategy_template import BaseStrategy
from .vibe_coding_service import VibeCodingService

__all__ = ["BaseStrategy", "VibeCodingService"]
