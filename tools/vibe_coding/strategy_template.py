"""BaseStrategy contract for AI-generated QuantGod strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class StrategySignal:
    """Normalized output returned by BaseStrategy.evaluate."""

    signal: str | None
    confidence: float
    sl_pips: float
    tp_pips: float
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal if self.signal in {"BUY", "SELL"} else None,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "sl_pips": max(0.0, float(self.sl_pips)),
            "tp_pips": max(0.0, float(self.tp_pips)),
            "reasoning": str(self.reasoning or "")[:2000],
        }


class BaseStrategy(ABC):
    """Abstract contract for Vibe Coding generated strategies."""

    name: ClassVar[str] = "UnnamedVibeStrategy"
    version: ClassVar[str] = "v0"
    description: ClassVar[str] = ""
    timeframe: ClassVar[str] = "H1"
    symbols: ClassVar[list[str]] = ["EURUSDc"]

    @abstractmethod
    def evaluate(self, bars) -> dict[str, Any]:
        """Return {'signal', 'confidence', 'sl_pips', 'tp_pips', 'reasoning'}."""

    def indicators(self, bars) -> dict[str, Any]:
        """Optional indicator payload for K-line overlays."""
        return {}


def normalize_signal(raw: dict[str, Any] | StrategySignal | None) -> dict[str, Any]:
    if isinstance(raw, StrategySignal):
        return raw.to_dict()
    if not isinstance(raw, dict):
        return StrategySignal(None, 0.0, 0.0, 0.0, "empty_or_invalid_strategy_output").to_dict()
    signal = raw.get("signal")
    if signal is not None:
        signal = str(signal).upper()
        if signal not in {"BUY", "SELL"}:
            signal = None
    return StrategySignal(
        signal=signal,
        confidence=float(raw.get("confidence") or 0.0),
        sl_pips=float(raw.get("sl_pips") or 0.0),
        tp_pips=float(raw.get("tp_pips") or 0.0),
        reasoning=str(raw.get("reasoning") or "")[:2000],
    ).to_dict()
