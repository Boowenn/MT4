from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .config_patch import build_config_patch
from .schema import FOCUS_SYMBOL, HARD_SAFETY, SCHEMA_STATE, utc_now_iso

try:
    from tools.autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
except ModuleNotFoundError:  # pragma: no cover
    from autonomous_lifecycle.lifecycle import build_autonomous_lifecycle


def build_agent_state(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    patch = build_config_patch(runtime_dir, write=write)
    decision = patch.get("sourceDecision") if isinstance(patch.get("sourceDecision"), dict) else {}
    lifecycle = build_autonomous_lifecycle(runtime_dir, write=write)
    payload: Dict[str, Any] = {
        "ok": True,
        "schema": SCHEMA_STATE,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "stage": patch.get("stage"),
        "executionStage": patch.get("executionStage") or patch.get("stage"),
        "stageZh": patch.get("stageZh"),
        "patchWritable": patch.get("patchWritable"),
        "patchAllowed": patch.get("patchAllowed"),
        "liveMutationAllowed": False,
        "currentPatch": {
            "changes": patch.get("changes"),
            "limits": patch.get("limits"),
            "rollback": patch.get("rollback"),
            "executionStage": patch.get("executionStage") or patch.get("stage"),
            "patchWritable": patch.get("patchWritable"),
            "liveMutationAllowed": False,
        },
        "promotionDecision": decision,
        "autonomousLifecycle": lifecycle,
        "centAccount": lifecycle.get("centAccount"),
        "lanes": lifecycle.get("lanes"),
        "eaReproducibility": lifecycle.get("eaReproducibility"),
        "requiresManualReview": False,
        "requiresAutonomousGovernance": True,
        "autoApplyAllowed": "stage_gated",
        "safety": HARD_SAFETY,
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_AutonomousAgentState.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
