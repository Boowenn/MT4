"""Fuse local QuantGod AI Analysis V2 output with validated DeepSeek advice.

This layer is for Telegram advisory quality only.  It does not create execution
capabilities, broker adapters, live preset mutations, webhook receivers, or
Telegram command handlers.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .deepseek_validator import evidence_quality, local_action, local_confidence, validate_deepseek_advice

SCHEMA = "quantgod.ai_advisory_fusion.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _final_action(validation: dict[str, Any]) -> str:
    if validation.get("status") != "pass":
        return "HOLD"
    local = str(validation.get("localAction") or "HOLD").upper()
    confidence = float(validation.get("localConfidencePct") or 0.0)
    if local == "BUY" and confidence >= 50:
        return "WATCH_LONG"
    if local == "SELL" and confidence >= 50:
        return "WATCH_SHORT"
    return "HOLD"


def _severity(validation: dict[str, Any]) -> str:
    reason = str(validation.get("primaryReason") or "ok")
    if reason in {"execution_language_detected", "kill_switch_active"}:
        return "CRITICAL_RISK"
    if reason in {"fallback_snapshot", "runtime_not_fresh", "local_deepseek_conflict"}:
        return "REVIEW_REQUIRED"
    action = _final_action(validation)
    if action in {"WATCH_LONG", "WATCH_SHORT"}:
        return "SIGNAL_REVIEW"
    return "INFO"


def _evidence_quality_score(validation: dict[str, Any]) -> float:
    quality = _as_dict(validation.get("evidenceQuality"))
    score = 1.0
    if quality.get("fallback"):
        score -= 0.45
    if not quality.get("runtimeFresh"):
        score -= 0.35
    if quality.get("killSwitchActive"):
        score -= 0.40
    risk = str(quality.get("riskLevel") or "unknown").lower()
    if risk in {"high", "critical"}:
        score -= 0.20
    elif risk in {"medium_high", "medium-high"}:
        score -= 0.10
    return round(max(0.0, min(1.0, score)), 2)


def build_fusion(validation: dict[str, Any]) -> dict[str, Any]:
    final_action = _final_action(validation)
    reason = str(validation.get("primaryReason") or "ok")
    return {
        "ok": True,
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "finalAction": final_action,
        "agreement": validation.get("agreement") or "unknown",
        "notifySeverity": _severity(validation),
        "riskOverride": validation.get("status") != "pass",
        "riskOverrideReason": None if validation.get("status") == "pass" else reason,
        "evidenceQualityScore": _evidence_quality_score(validation),
        "localDecision": {
            "action": validation.get("localAction") or "HOLD",
            "confidencePct": validation.get("localConfidencePct"),
        },
        "deepseek": {
            "provider": validation.get("provider") or "deepseek",
            "model": validation.get("model") or "unknown",
            "bias": validation.get("deepseekBias") or "HOLD",
            "validationStatus": validation.get("status") or "unknown",
            "validationReasons": validation.get("reasons") or [],
        },
        "evidenceQuality": validation.get("evidenceQuality") or {},
        "shouldNotify": True,
        "notifyReason": reason,
        "safety": {
            "localOnly": True,
            "readOnlyDataPlane": True,
            "advisoryOnly": True,
            "telegramPushOnly": True,
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "credentialStorageAllowed": False,
            "livePresetMutationAllowed": False,
            "canOverrideKillSwitch": False,
            "telegramCommandExecutionAllowed": False,
            "telegramWebhookReceiverAllowed": False,
            "webhookReceiverAllowed": False,
            "emailDeliveryAllowed": False,
        },
    }


def _inject_validator_context(effective_advice: dict[str, Any], validation: dict[str, Any], fusion: dict[str, Any]) -> dict[str, Any]:
    advice = deepcopy(effective_advice)
    status = str(validation.get("status") or "unknown")
    reasons = validation.get("reasons") if isinstance(validation.get("reasons"), list) else []
    reason_text = ",".join(str(item) for item in reasons) if reasons else "ok"
    final_action = str(fusion.get("finalAction") or "HOLD")
    agreement = str(fusion.get("agreement") or "unknown")

    risk_notes = advice.get("riskNotes") if isinstance(advice.get("riskNotes"), list) else []
    risk_notes = [str(item) for item in risk_notes]
    risk_notes.append(f"Fusion：finalAction={final_action}；agreement={agreement}；validator={status}/{reason_text}")
    risk_notes.append("边界：advisory-only，Telegram push-only，不触发交易执行。")
    advice["riskNotes"] = risk_notes[:4]

    watch_points = advice.get("watchPoints") if isinstance(advice.get("watchPoints"), list) else []
    watch_points = [str(item) for item in watch_points]
    watch_points.append("复核本地多 Agent 与 DeepSeek 是否继续一致；冲突时保持 HOLD。")
    advice["watchPoints"] = watch_points[:4]

    boundary = str(advice.get("executionBoundary") or "仅建议，不执行交易。").strip()
    advice["executionBoundary"] = (
        f"{boundary} validator={status}; fusionFinalAction={final_action}; "
        "advisory-only; no order/close/cancel/live preset mutation."
    )
    return advice


def fuse_advisory_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a report with validated DeepSeek advice and fusion meta."""
    enriched = deepcopy(report)
    deepseek_payload = _as_dict(enriched.get("deepseek_advice"))
    validation = validate_deepseek_advice(enriched, deepseek_payload)
    fusion = build_fusion(validation)

    effective_advice = _inject_validator_context(
        _as_dict(validation.get("effectiveAdvice")),
        validation,
        fusion,
    )

    payload = dict(deepseek_payload)
    payload.setdefault("provider", validation.get("provider") or "deepseek")
    payload.setdefault("model", validation.get("model") or "unknown")
    payload["validation"] = {key: value for key, value in validation.items() if key != "effectiveAdvice"}
    payload["advice"] = effective_advice
    payload["effectiveAdviceApplied"] = True
    if not payload.get("ok") and validation.get("primaryReason") == "deepseek_not_available":
        payload["status"] = payload.get("status") or "not_available"

    enriched["deepseek_advice"] = payload
    enriched["advisory_fusion"] = fusion
    enriched.setdefault("safety", {})
    if isinstance(enriched["safety"], dict):
        enriched["safety"].update(
            {
                "advisoryFusionApplied": True,
                "orderSendAllowed": False,
                "closeAllowed": False,
                "cancelAllowed": False,
                "livePresetMutationAllowed": False,
                "canOverrideKillSwitch": False,
            }
        )
    return enriched


def fusion_summary_for_message(report: dict[str, Any]) -> str:
    fusion = _as_dict(report.get("advisory_fusion"))
    validation = _as_dict(_as_dict(report.get("deepseek_advice")).get("validation"))
    quality = evidence_quality(report)
    return (
        f"fusionFinalAction={fusion.get('finalAction', 'HOLD')} | "
        f"validator={validation.get('status', 'unknown')} | "
        f"agreement={fusion.get('agreement', 'unknown')} | "
        f"source={quality.source} | fallback={quality.fallback} | runtimeFresh={quality.runtime_fresh}"
    )


def compact_fusion_payload(report: dict[str, Any]) -> dict[str, Any]:
    fusion = _as_dict(report.get("advisory_fusion"))
    payload = _as_dict(report.get("deepseek_advice"))
    validation = _as_dict(payload.get("validation"))
    advice = _as_dict(payload.get("advice"))
    return {
        "schema": SCHEMA,
        "symbol": report.get("symbol"),
        "generatedAt": report.get("generatedAt"),
        "finalAction": fusion.get("finalAction"),
        "notifySeverity": fusion.get("notifySeverity"),
        "agreement": fusion.get("agreement"),
        "validatorStatus": validation.get("status"),
        "validatorReasons": validation.get("reasons"),
        "localAction": validation.get("localAction"),
        "deepseekBias": validation.get("deepseekBias"),
        "evidenceQuality": validation.get("evidenceQuality"),
        "headline": advice.get("headline"),
        "verdict": advice.get("verdict"),
        "planStatus": advice.get("planStatus"),
        "entryZone": advice.get("entryZone"),
        "targets": advice.get("targets"),
        "executionBoundary": advice.get("executionBoundary"),
        "safety": fusion.get("safety"),
    }
