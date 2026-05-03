"""QuantGod AI advisory outcome journal.

This package records Telegram advisory outputs as local read-only shadow signals,
scores them against later runtime prices, and can pause weak signal families.
It never creates order, close, cancel, credential, webhook, or Telegram command
capabilities.
"""

from .schema import JOURNAL_SCHEMA, safety_payload
from .writer import record_telegram_advisory
from .kill_switch import apply_signal_kill_switch

__all__ = [
    "JOURNAL_SCHEMA",
    "safety_payload",
    "record_telegram_advisory",
    "apply_signal_kill_switch",
]
