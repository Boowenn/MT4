"""USDJPY-only strategy policy lab for QuantGod.

This package is local-only. It produces read-only policy/evidence files for
USDJPY strategy research and EA dry-run review. It never sends, closes, cancels,
or modifies orders.
"""

from .schema import FOCUS_SYMBOL, normalize_symbol, is_focus_symbol
from .policy_builder import build_usdjpy_policy
from .strategy_scoreboard import build_strategy_scoreboard

__all__ = [
    "FOCUS_SYMBOL",
    "normalize_symbol",
    "is_focus_symbol",
    "build_usdjpy_policy",
    "build_strategy_scoreboard",
]
