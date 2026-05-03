"""Write AI advisory journal records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .price_probe import current_price_from_report
from .reader import append_jsonl, journal_path
from .schema import JOURNAL_SCHEMA, safety_payload, utc_now_iso, validate_record


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_decision(report: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(report.get("decision"))


def _extract_fusion(report: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(report.get("advisory_fusion"))


def _extract_deepseek(report: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(report.get("deepseek_advice"))
    advice = _as_dict(payload.get("advice"))
    validation = _as_dict(payload.get("validation"))
    return {
        "provider": payload.get("provider") or "deepseek",
        "model": payload.get("model") or "unknown",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status") or validation.get("status") or "unknown",
        "verdict": advice.get("verdict") or advice.get("headline") or "",
        "planStatus": advice.get("planStatus") or "",
        "validationStatus": validation.get("status") or "unknown",
        "validationReasons": validation.get("reasons") if isinstance(validation.get("reasons"), list) else [],
    }


def signal_direction(final_action: str, local_action: str) -> str:
    text = str(final_action or local_action or "HOLD").upper()
    if text in {"WATCH_LONG", "BUY", "LONG"}:
        return "LONG"
    if text in {"WATCH_SHORT", "SELL", "SHORT"}:
        return "SHORT"
    return "NONE"


def _reference_price(report: dict[str, Any]) -> float | None:
    decision = _extract_decision(report)
    price = current_price_from_report(report)
    return _num(decision.get("entry_price") or decision.get("entryPrice")) or _num(price.get("mid"))


def build_journal_record(
    report: dict[str, Any],
    *,
    runtime_dir: str | Path,
    delivery: dict[str, Any] | None = None,
    message: str = "",
    reason: str = "",
    dry_run: bool = True,
    now_iso: str | None = None,
) -> dict[str, Any]:
    now = now_iso or utc_now_iso()
    decision = _extract_decision(report)
    fusion = _extract_fusion(report)
    deepseek = _extract_deepseek(report)
    snapshot = _as_dict(report.get("snapshot"))
    risk = _as_dict(report.get("risk"))
    price = current_price_from_report(report)
    final_action = str(fusion.get("finalAction") or decision.get("action") or "HOLD").upper()
    local_action = str(decision.get("action") or "HOLD").upper()
    direction = signal_direction(final_action, local_action)
    reference_price = _reference_price(report)
    seed = {
        "symbol": report.get("symbol"),
        "generatedAt": report.get("generatedAt") or now,
        "finalAction": final_action,
        "referencePrice": reference_price,
        "reason": reason,
    }
    record_id = hashlib.sha256(json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    delivery = delivery or {}
    return {
        "schema": JOURNAL_SCHEMA,
        "recordId": record_id,
        "generatedAt": report.get("generatedAt") or now,
        "recordedAt": now,
        "runtimeDir": str(Path(runtime_dir).expanduser().resolve()),
        "symbol": report.get("symbol") or "UNKNOWN",
        "timeframes": report.get("timeframes") if isinstance(report.get("timeframes"), list) else [],
        "triggerReason": reason or "未知",
        "delivery": {
            "status": delivery.get("status") or "unknown",
            "telegramMessageId": delivery.get("telegramMessageId"),
            "dryRun": bool(dry_run),
        },
        "snapshot": {
            "source": snapshot.get("source") or "unknown",
            "fallback": bool(snapshot.get("fallback", False)),
            "runtimeFresh": bool(snapshot.get("runtimeFresh", False)),
            "runtimeAgeSeconds": snapshot.get("runtimeAgeSeconds"),
            "spread": price.get("spread"),
            "referencePrice": reference_price,
            "bid": price.get("bid"),
            "ask": price.get("ask"),
            "last": price.get("last"),
            "mid": price.get("mid"),
        },
        "localDecision": {
            "action": local_action,
            "confidence": decision.get("confidence"),
            "reasoning": str(decision.get("reasoning") or "")[:360],
        },
        "deepseekAdvice": deepseek,
        "fusion": {
            "finalAction": final_action,
            "agreement": fusion.get("agreement") or "unknown",
            "notifySeverity": fusion.get("notifySeverity") or "unknown",
            "evidenceQualityScore": fusion.get("evidenceQualityScore"),
        },
        "shadowSignal": {
            "direction": direction,
            "active": direction in {"LONG", "SHORT"},
            "referencePrice": reference_price,
            "scoreStatus": "pending" if direction in {"LONG", "SHORT"} and reference_price is not None else "not_actionable",
        },
        "risk": {
            "riskLevel": risk.get("risk_level") or risk.get("riskLevel") or "unknown",
            "killSwitchActive": bool(risk.get("kill_switch_active") or risk.get("killSwitchActive")),
        },
        "messagePreview": str(message or "")[:240],
        "safety": safety_payload(),
    }


def record_telegram_advisory(
    *,
    runtime_dir: str | Path,
    report: dict[str, Any],
    delivery: dict[str, Any] | None = None,
    message: str = "",
    reason: str = "",
    dry_run: bool = True,
    now_iso: str | None = None,
) -> dict[str, Any]:
    record = build_journal_record(
        report,
        runtime_dir=runtime_dir,
        delivery=delivery,
        message=message,
        reason=reason,
        dry_run=dry_run,
        now_iso=now_iso,
    )
    validate_record(record)
    append_jsonl(journal_path(runtime_dir), record)
    return {
        "ok": True,
        "status": "journal_recorded",
        "recordId": record["recordId"],
        "journalPath": str(journal_path(runtime_dir)),
        "shadowSignal": record["shadowSignal"],
        "safety": safety_payload(),
    }
