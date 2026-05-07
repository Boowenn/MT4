from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class BacktestCostModel:
    spread_pips: float = 0.8
    slippage_pips: float = 0.2
    commission_pips: float = 0.0

    @property
    def round_turn_pips(self) -> float:
        return max(0.0, self.spread_pips + self.slippage_pips + self.commission_pips)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema": "quantgod.backtest_cost_model.v1",
            "spreadPips": round(self.spread_pips, 4),
            "slippagePips": round(self.slippage_pips, 4),
            "commissionPips": round(self.commission_pips, 4),
            "roundTurnPips": round(self.round_turn_pips, 4),
            "reasonZh": "回测按固定点差、滑点和手续费扣减；这是 GA 评分成本口径，不代表实盘保证成交。",
        }


def cost_model_from_strategy(strategy: Dict[str, Any]) -> BacktestCostModel:
    risk = strategy.get("risk") if isinstance(strategy.get("risk"), dict) else {}
    costs = strategy.get("costs") if isinstance(strategy.get("costs"), dict) else {}
    spread = _num(costs.get("spreadPips", risk.get("spreadPips", 0.8)), 0.8)
    slippage = _num(costs.get("slippagePips", risk.get("slippagePips", 0.2)), 0.2)
    commission = _num(costs.get("commissionPips", risk.get("commissionPips", 0.0)), 0.0)
    return BacktestCostModel(
        spread_pips=max(0.0, min(8.0, spread)),
        slippage_pips=max(0.0, min(5.0, slippage)),
        commission_pips=max(0.0, min(5.0, commission)),
    )


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
