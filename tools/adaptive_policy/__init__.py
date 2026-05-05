"""QuantGod P3-6 adaptive policy engine.

This package is read-only and advisory-only. It turns MT5 runtime evidence,
shadow outcomes, and journal samples into adaptive route status, entry gate,
and dynamic SL/TP advisory plans.
"""

from .policy_engine import build_adaptive_policy

__all__ = ["build_adaptive_policy"]
