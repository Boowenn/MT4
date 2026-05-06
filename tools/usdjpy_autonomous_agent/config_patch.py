from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .promotion_gate import build_promotion_decision
from .schema import (
    FOCUS_SYMBOL,
    HARD_SAFETY,
    ROLLBACK_PAUSED,
    SCHEMA_PATCH,
    STAGE_LIVE_LIMITED,
    STAGE_MICRO_LIVE,
    STAGE_PAPER_LIVE_SIM,
    STAGE_REJECTED,
    STAGE_SHADOW_ONLY,
    STAGE_TESTER_ONLY,
    utc_now_iso,
)


def _stage_max_lot(stage: str) -> float:
    if stage == STAGE_MICRO_LIVE:
        return 0.03
    if stage == STAGE_LIVE_LIMITED:
        return 2.0
    return 0.0


def _changes_for_variant(variant: str) -> Dict[str, Any]:
    if variant == "relaxed_entry_v1":
        return {"rsiBuyCrossbackThreshold": 34}
    if variant == "let_profit_run_v1":
        return {"breakevenDelayR": 1.0, "mfeGivebackPct": 0.6}
    return {}


def build_config_patch(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    decision = build_promotion_decision(runtime_dir, write=write)
    stage = decision.get("stage", STAGE_REJECTED)
    allowed = stage in {STAGE_SHADOW_ONLY, STAGE_TESTER_ONLY, STAGE_PAPER_LIVE_SIM, STAGE_MICRO_LIVE, STAGE_LIVE_LIMITED}
    changes: Dict[str, Any] = {}
    for item in decision.get("candidates") or []:
        if item.get("autonomousStage") in {STAGE_TESTER_ONLY, STAGE_PAPER_LIVE_SIM, STAGE_MICRO_LIVE, STAGE_LIVE_LIMITED}:
            changes.update(_changes_for_variant(str(item.get("variant") or "")))
    payload = {
        "ok": True,
        "schema": SCHEMA_PATCH,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "strategy": "RSI_Reversal",
        "direction": "LONG",
        "stage": stage,
        "stageZh": decision.get("stageZh"),
        "patchAllowed": bool(allowed and changes and stage != ROLLBACK_PAUSED),
        "changes": changes if allowed else {},
        "limits": {
            "maxLot": 2.0,
            "stageMaxLot": _stage_max_lot(str(stage)),
            "maxDailyTrades": 2,
            "maxDailyLossR": 1.0,
            "maxConsecutiveLosses": 2,
        },
        "rollback": {
            "enabled": True,
            "trigger": "lossStreak>=2 OR dailyLossR<=-1.0 OR fastlane not in FAST/EA_DASHBOARD_OK OR runtime stale OR spread abnormal OR news block",
            "hardBlockers": (decision.get("hardRollback") or {}).get("hardBlockers", []),
        },
        "sourceDecision": decision,
        "safety": HARD_SAFETY,
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_AutonomousConfigPatch.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

