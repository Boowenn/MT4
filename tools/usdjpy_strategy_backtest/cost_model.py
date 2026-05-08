from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Dict


@dataclass(frozen=True)
class BacktestCostModel:
    spread_pips: float = 0.8
    slippage_pips: float = 0.2
    commission_pips: float = 0.0
    dynamic_spread_from_bars: bool = True
    max_spread_pips: float = 8.0

    @property
    def round_turn_pips(self) -> float:
        return max(0.0, self.spread_pips + self.slippage_pips + self.commission_pips)

    def spread_pips_for_bar(self, bar: Any) -> float:
        if not self.dynamic_spread_from_bars:
            return self.spread_pips
        raw_points = getattr(bar, "spread", None)
        try:
            points = float(raw_points)
        except Exception:
            points = 0.0
        if points <= 0:
            return self.spread_pips
        # HFM USDJPYc is normally 3 digits: 10 points = 1 pip.
        return max(0.0, min(self.max_spread_pips, points * 0.1))

    def round_turn_pips_for_bar(self, bar: Any) -> float:
        spread = self.spread_pips_for_bar(bar)
        return max(0.0, spread + self.slippage_pips + self.commission_pips)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema": "quantgod.backtest_cost_model.v1",
            "spreadPips": round(self.spread_pips, 4),
            "slippagePips": round(self.slippage_pips, 4),
            "commissionPips": round(self.commission_pips, 4),
            "dynamicSpreadFromBars": self.dynamic_spread_from_bars,
            "maxSpreadPips": round(self.max_spread_pips, 4),
            "roundTurnPips": round(self.round_turn_pips, 4),
            "reasonZh": "回测优先使用 MT5 导出的 bar spread，并叠加滑点和手续费；这是 GA 评分成本口径，不代表实盘保证成交。",
        }


def cost_model_from_strategy(strategy: Dict[str, Any]) -> BacktestCostModel:
    risk = strategy.get("risk") if isinstance(strategy.get("risk"), dict) else {}
    costs = strategy.get("costs") if isinstance(strategy.get("costs"), dict) else {}
    spread = _num(costs.get("spreadPips", risk.get("spreadPips", os.environ.get("QG_BACKTEST_SPREAD_PIPS", 0.8))), 0.8)
    slippage = _num(costs.get("slippagePips", risk.get("slippagePips", os.environ.get("QG_BACKTEST_SLIPPAGE_PIPS", 0.2))), 0.2)
    commission = _num(costs.get("commissionPips", risk.get("commissionPips", os.environ.get("QG_BACKTEST_COMMISSION_PIPS", 0.0))), 0.0)
    dynamic_spread = _bool(costs.get("dynamicSpreadFromBars", os.environ.get("QG_BACKTEST_DYNAMIC_SPREAD", "1")), True)
    max_spread = _num(costs.get("maxSpreadPips", os.environ.get("QG_BACKTEST_MAX_SPREAD_PIPS", 8.0)), 8.0)
    return BacktestCostModel(
        spread_pips=max(0.0, min(8.0, spread)),
        slippage_pips=max(0.0, min(5.0, slippage)),
        commission_pips=max(0.0, min(5.0, commission)),
        dynamic_spread_from_bars=dynamic_spread,
        max_spread_pips=max(0.1, min(30.0, max_spread)),
    )


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
