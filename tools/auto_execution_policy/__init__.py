"""QuantGod auto execution policy tuner.

Generates read-only EA policy artifacts for staged automatic trading logic.
It does not place orders or modify MT5 presets.
"""

from .schema import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]
