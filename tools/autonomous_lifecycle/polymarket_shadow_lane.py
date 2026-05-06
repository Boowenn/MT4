from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    from tools.build_daily_review import polymarket_daily_review
    from tools.usdjpy_strategy_lab.schema import utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from build_daily_review import polymarket_daily_review
    from usdjpy_strategy_lab.schema import utc_now_iso

from .stage_machine import (
    STAGE_FAST_SHADOW,
    STAGE_PAPER_CONTEXT,
    STAGE_QUARANTINED,
    STAGE_SHADOW,
    stage_label,
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _stage(summary: Dict[str, Any], copy_review: Dict[str, Any]) -> str:
    shadow_pf = _number(summary.get("shadowProfitFactor"))
    shadow_net = _number(summary.get("shadowNetUSDC"))
    shadow_closed = int(_number(summary.get("shadowClosed"), 0))
    copy_metrics = copy_review.get("bestMetrics") if isinstance(copy_review.get("bestMetrics"), dict) else {}
    copy_pf = _number(copy_metrics.get("profitFactor"))
    copy_net = _number(copy_metrics.get("realizedPnl"))
    copy_closed = int(_number(copy_metrics.get("closed"), 0))
    if shadow_pf < 1.0 or shadow_net < 0 or copy_pf < 1.0 or copy_net < 0:
        return STAGE_QUARANTINED
    if copy_closed >= 100 and copy_pf > 1.05 and copy_net > 0:
        return STAGE_PAPER_CONTEXT
    if shadow_closed >= 100 and shadow_pf > 1.05 and shadow_net > 0:
        return STAGE_FAST_SHADOW
    return STAGE_SHADOW


def build_polymarket_shadow_lane(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    review = polymarket_daily_review(runtime_dir)
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    copy_review = review.get("copyTradingReview") if isinstance(review.get("copyTradingReview"), dict) else {}
    stage = _stage(summary, copy_review)
    copy_metrics = copy_review.get("bestMetrics") if isinstance(copy_review.get("bestMetrics"), dict) else {}
    payload = {
        "ok": True,
        "schema": "quantgod.polymarket_shadow_lane.v1",
        "generatedAtIso": utc_now_iso(),
        "lane": "POLYMARKET_SHADOW",
        "laneZh": "Polymarket 模拟与事件风险车道",
        "stage": stage,
        "stageZh": stage_label(stage),
        "summary": {
            "shadowClosed": summary.get("shadowClosed", 0),
            "shadowProfitFactor": summary.get("shadowProfitFactor", 0),
            "shadowNetUSDC": summary.get("shadowNetUSDC", 0),
            "copyTradingStatus": copy_review.get("status", ""),
            "copyTradingSummary": copy_review.get("summary", ""),
            "copyClosed": copy_metrics.get("closed", 0),
            "copyProfitFactor": copy_metrics.get("profitFactor", 0),
            "copyNetUSDC": copy_metrics.get("realizedPnl", 0),
            "retuneRed": summary.get("retuneRed", 0),
            "retuneYellow": summary.get("retuneYellow", 0),
            "todoCount": summary.get("todoCount", 0),
        },
        "actionQueue": review.get("actionQueue", []),
        "completedActionQueue": review.get("completedActionQueue", []),
        "copyTradingReview": copy_review,
        "safety": {
            "shadowOnly": True,
            "walletIntegrationAllowed": False,
            "polymarketRealMoneyAllowed": False,
            "polymarketOrderAllowed": False,
            "privateKeyAllowed": False,
            "orderSendAllowed": False,
            "noteZh": "Polymarket 继续模拟跟单和事件风险；不连接真实钱包，不下注，不赎回。",
        },
        "reasonZh": (
            "模拟账本仍为负期望，继续隔离和重调。"
            if stage == STAGE_QUARANTINED else
            "可作为事件风险上下文，但仍不触碰真钱钱包。"
            if stage == STAGE_PAPER_CONTEXT else
            "继续模拟观察。"
        ),
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_PolymarketShadowLane.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

