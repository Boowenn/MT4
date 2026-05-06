from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    from tools.usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso

from .cent_account_rules import cent_account_config
from .ea_reproducibility import build_ea_reproducibility
from .mt5_shadow_lane import build_mt5_shadow_lane
from .polymarket_shadow_lane import build_polymarket_shadow_lane


def build_autonomous_lifecycle(
    runtime_dir: Path,
    *,
    repo_root: Path | None = None,
    write: bool = False,
) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    cent = cent_account_config()
    mt5_shadow = build_mt5_shadow_lane(runtime_dir, write=write)
    polymarket_shadow = build_polymarket_shadow_lane(runtime_dir, write=write)
    ea_repro = build_ea_reproducibility(runtime_dir, repo_root=repo_root, write=write)
    payload: Dict[str, Any] = {
        "ok": True,
        "schema": "quantgod.autonomous_lifecycle.v2_3",
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "sloganZh": "实盘要窄，模拟要宽，升降级要快，回滚要硬。",
        "singleSourceOfTruth": "USDJPY_LIVE_LOOP_WITH_AUTONOMOUS_LIFECYCLE",
        "centAccount": cent,
        "lanes": {
            "live": {
                "lane": "LIVE",
                "laneZh": "实盘车道",
                "symbol": FOCUS_SYMBOL,
                "strategy": "RSI_Reversal",
                "direction": "LONG",
                "allowedLiveStages": ["MICRO_LIVE", "LIVE_LIMITED"],
                "forbiddenZh": ["USDJPY SELL 实盘", "非 RSI 实盘", "非 USDJPY 实盘", "Polymarket 真实钱包交易"],
                "maxLotIsCapNotFixed": True,
            },
            "mt5Shadow": mt5_shadow,
            "polymarketShadow": polymarket_shadow,
        },
        "eaReproducibility": ea_repro,
        "safety": {
            "requiresManualReview": False,
            "requiresAutonomousGovernance": True,
            "autoApplyAllowed": "stage_gated",
            "patchWritable": True,
            "liveMutationAllowed": False,
            "orderSendAllowed": False,
            "polymarketRealMoneyAllowed": False,
            "deepSeekCanApproveLive": False,
            "telegramCommandExecutionAllowed": False,
        },
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_AutonomousLifecycle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
