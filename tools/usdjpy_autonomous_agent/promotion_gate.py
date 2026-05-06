from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .rollback import append_rollback, evaluate_hard_rollback
from .schema import (
    FOCUS_SYMBOL,
    HARD_SAFETY,
    ROLLBACK_PAUSED,
    SCHEMA_DECISION,
    STAGE_LIVE_LIMITED,
    STAGE_MICRO_LIVE,
    STAGE_PAPER_LIVE_SIM,
    STAGE_REJECTED,
    STAGE_SHADOW_ONLY,
    STAGE_TESTER_ONLY,
    STAGE_ZH,
    utc_now_iso,
)
from .walk_forward import build_autonomous_walk_forward

try:
    from tools.autonomous_lifecycle.cent_account_rules import cent_account_config
    from tools.autonomous_lifecycle.demotion_speed import demotion_from_rollback
    from tools.autonomous_lifecycle.promotion_speed import cent_accelerated_stage
except ModuleNotFoundError:  # pragma: no cover
    from autonomous_lifecycle.cent_account_rules import cent_account_config
    from autonomous_lifecycle.demotion_speed import demotion_from_rollback
    from autonomous_lifecycle.promotion_speed import cent_accelerated_stage


def _stage_for_candidate(item: Dict[str, Any]) -> str:
    conclusion = str(item.get("conclusion") or "").upper()
    summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
    delta = float(summary.get("netRDelta") or 0.0)
    samples = int(summary.get("sampleCount") or 0)
    cfg = cent_account_config()
    if conclusion == "LIVE_CONFIG_PROPOSAL_ELIGIBLE":
        validation_delta = float(summary.get("validationNetRDelta") or 0.0)
        forward_delta = float(summary.get("forwardNetRDelta") or 0.0)
        min_samples = int(cfg.get("microLiveMinSamples") or 10)
        can_micro_live = (
            cfg.get("centFastPromotion")
            and samples >= min_samples
            and delta > 0
            and validation_delta > 0
            and forward_delta > 0
        )
        base_stage = STAGE_MICRO_LIVE if can_micro_live else STAGE_PAPER_LIVE_SIM
        accelerated = cent_accelerated_stage(base_stage, sample_count=samples, net_r_delta=delta)
        return str(accelerated.get("stage") or base_stage)
    if conclusion == "TESTER_ONLY":
        return STAGE_TESTER_ONLY
    if conclusion == "SHADOW_ONLY":
        return STAGE_SHADOW_ONLY
    return STAGE_REJECTED


def _stage_rank(stage: str) -> int:
    order = [STAGE_REJECTED, STAGE_SHADOW_ONLY, STAGE_TESTER_ONLY, STAGE_PAPER_LIVE_SIM, STAGE_MICRO_LIVE, STAGE_LIVE_LIMITED]
    try:
        return order.index(stage)
    except ValueError:
        return 0


def build_promotion_decision(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    walk_forward = build_autonomous_walk_forward(runtime_dir, write=write)
    report = walk_forward.get("report") if isinstance(walk_forward.get("report"), dict) else {}
    selection = walk_forward.get("selection") if isinstance(walk_forward.get("selection"), dict) else {}
    rollback = evaluate_hard_rollback(runtime_dir)
    selected = selection.get("selected") if isinstance(selection.get("selected"), list) else []
    rejected = selection.get("rejected") if isinstance(selection.get("rejected"), list) else []
    cent = cent_account_config()
    candidates: List[Dict[str, Any]] = []
    for item in [*selected, *rejected]:
        if not isinstance(item, dict):
            continue
        stage = _stage_for_candidate(item)
        candidates.append({
            **item,
            "autonomousStage": stage,
            "autonomousStageZh": STAGE_ZH.get(stage, stage),
        })
    best_stage = max((item.get("autonomousStage", STAGE_REJECTED) for item in candidates), key=_stage_rank, default=STAGE_REJECTED)
    if not rollback["ok"] and _stage_rank(best_stage) >= _stage_rank(STAGE_PAPER_LIVE_SIM):
        best_stage = ROLLBACK_PAUSED
    demotion = demotion_from_rollback(rollback)
    payload = {
        "ok": True,
        "schema": SCHEMA_DECISION,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "stage": best_stage,
        "executionStage": best_stage,
        "stageZh": STAGE_ZH.get(best_stage, best_stage),
        "status": "AUTONOMOUS_PROMOTION_READY" if best_stage not in {STAGE_REJECTED, ROLLBACK_PAUSED} else best_stage,
        "requiresAutonomousGovernance": True,
        "completedByAgent": True,
        "autoAppliedByAgent": best_stage not in {STAGE_REJECTED, ROLLBACK_PAUSED},
        "autoApplyAllowed": "stage_gated",
        "centAccount": cent,
        "demotionDecision": demotion,
        "hardRollback": rollback,
        "candidates": candidates,
        "walkForward": walk_forward,
        "walkForwardReport": report,
        "parameterSelection": selection,
        "safety": HARD_SAFETY,
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_AutonomousPromotionDecision.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if best_stage == ROLLBACK_PAUSED:
            append_rollback(runtime_dir, {"generatedAtIso": payload["generatedAtIso"], "stage": best_stage, "hardBlockers": rollback["hardBlockers"]})
    return payload
