from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .config_patch import build_config_patch
from .schema import FOCUS_SYMBOL, HARD_SAFETY, SCHEMA_STATE, utc_now_iso


def build_agent_state(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    patch = build_config_patch(runtime_dir, write=write)
    decision = patch.get("sourceDecision") if isinstance(patch.get("sourceDecision"), dict) else {}
    payload: Dict[str, Any] = {
        "ok": True,
        "schema": SCHEMA_STATE,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "stage": patch.get("stage"),
        "stageZh": patch.get("stageZh"),
        "patchAllowed": patch.get("patchAllowed"),
        "currentPatch": {
            "changes": patch.get("changes"),
            "limits": patch.get("limits"),
            "rollback": patch.get("rollback"),
        },
        "promotionDecision": decision,
        "requiresManualReview": False,
        "requiresAutonomousGovernance": True,
        "safety": HARD_SAFETY,
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_AutonomousAgentState.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

