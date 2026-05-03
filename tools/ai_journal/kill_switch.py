"""Signal-level kill switch for weak AI advisory families.

This kill switch only downgrades Telegram advisory language. It does not touch
MT5, broker execution, presets, credentials, or Telegram commands.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .reader import kill_switch_path, read_json, write_json, latest_outcomes
from .schema import safety_payload, utc_now_iso


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def settings_from_env() -> dict[str, Any]:
    return {
        "enabled": env_bool("QG_AI_JOURNAL_KILL_SWITCH_ENABLED", True),
        "minSamples": _int(os.environ.get("QG_AI_JOURNAL_MIN_SAMPLES"), 5),
        "avgScoreRThreshold": _num(os.environ.get("QG_AI_JOURNAL_AVG_R_THRESHOLD"), -0.25),
        "hitRateThreshold": _num(os.environ.get("QG_AI_JOURNAL_HIT_RATE_THRESHOLD"), 0.4),
        "consecutiveLosses": _int(os.environ.get("QG_AI_JOURNAL_CONSECUTIVE_LOSSES"), 5),
        "cooldownSeconds": _int(os.environ.get("QG_AI_JOURNAL_COOLDOWN_SECONDS"), 24 * 60 * 60),
    }


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _now(now_iso: str | None = None) -> datetime:
    parsed = _parse_time(now_iso)
    if parsed:
        return parsed
    return datetime.now(timezone.utc)


def signal_family(report: dict[str, Any]) -> dict[str, str]:
    symbol = str(report.get("symbol") or "UNKNOWN")
    fusion = _as_dict(report.get("advisory_fusion"))
    decision = _as_dict(report.get("decision"))
    action = str(fusion.get("finalAction") or decision.get("action") or "HOLD").upper()
    if action in {"BUY", "WATCH_LONG", "LONG"}:
        direction = "LONG"
    elif action in {"SELL", "WATCH_SHORT", "SHORT"}:
        direction = "SHORT"
    else:
        direction = "NONE"
    return {"symbol": symbol, "direction": direction, "key": f"{symbol}:{direction}"}


def _recent_family_outcomes(runtime_dir: str | Path, symbol: str, direction: str, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = latest_outcomes(runtime_dir, limit=limit)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "scored":
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if str(row.get("direction") or "").upper() != direction:
            continue
        filtered.append(row)
    return filtered


def evaluate_family(runtime_dir: str | Path, symbol: str, direction: str, *, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or settings_from_env()
    rows = _recent_family_outcomes(runtime_dir, symbol, direction, limit=100)
    scored = rows[-max(1, int(settings.get("minSamples") or 5)) :]
    values: list[float] = []
    wins = 0
    losses = 0
    for row in scored:
        if row.get("scoreR") is not None:
            values.append(_num(row.get("scoreR"), 0.0))
        if row.get("directionCorrect") is True:
            wins += 1
        if row.get("directionCorrect") is False:
            losses += 1
    hit_rate = wins / len(scored) if scored else None
    avg_score = mean(values) if values else None
    recent_losses = 0
    for row in reversed(rows):
        if row.get("directionCorrect") is False:
            recent_losses += 1
        else:
            break
    pause = False
    reasons: list[str] = []
    if direction not in {"LONG", "SHORT"}:
        reasons.append("非方向性建议")
    elif len(scored) < int(settings.get("minSamples") or 5):
        reasons.append("样本不足")
    else:
        if avg_score is not None and avg_score < float(settings.get("avgScoreRThreshold") or -0.25):
            pause = True
            reasons.append("平均影子R低于阈值")
        if hit_rate is not None and hit_rate < float(settings.get("hitRateThreshold") or 0.4):
            pause = True
            reasons.append("方向命中率低于阈值")
        if recent_losses >= int(settings.get("consecutiveLosses") or 5):
            pause = True
            reasons.append("连续负向样本过多")
    return {
        "ok": True,
        "symbol": symbol,
        "direction": direction,
        "samples": len(scored),
        "wins": wins,
        "losses": losses,
        "hitRate": round(hit_rate, 4) if hit_rate is not None else None,
        "averageScoreR": round(avg_score, 4) if avg_score is not None else None,
        "recentConsecutiveLosses": recent_losses,
        "pause": pause,
        "reasons": reasons,
        "settings": settings,
        "safety": safety_payload(),
    }


def current_pause_state(runtime_dir: str | Path, key: str, *, now_iso: str | None = None) -> dict[str, Any]:
    state = read_json(kill_switch_path(runtime_dir))
    pauses = state.get("pauses") if isinstance(state.get("pauses"), dict) else {}
    pause = pauses.get(key) if isinstance(pauses.get(key), dict) else {}
    until = _parse_time(pause.get("pausedUntil"))
    if until and until > _now(now_iso):
        return {"active": True, **pause}
    return {"active": False}


def _write_pause(runtime_dir: str | Path, key: str, payload: dict[str, Any]) -> None:
    path = kill_switch_path(runtime_dir)
    state = read_json(path)
    state.setdefault("schema", "quantgod.ai_signal_kill_switch.v1")
    state["updatedAt"] = utc_now_iso()
    state.setdefault("pauses", {})
    if isinstance(state["pauses"], dict):
        state["pauses"][key] = payload
    state["safety"] = safety_payload()
    write_json(path, state)


def build_pause(runtime_dir: str | Path, evaluation: dict[str, Any], *, now_iso: str | None = None) -> dict[str, Any]:
    now = _now(now_iso)
    settings = evaluation.get("settings") if isinstance(evaluation.get("settings"), dict) else settings_from_env()
    until = now + timedelta(seconds=int(settings.get("cooldownSeconds") or 24 * 60 * 60))
    key = f"{evaluation.get('symbol')}:{evaluation.get('direction')}"
    payload = {
        "active": True,
        "key": key,
        "symbol": evaluation.get("symbol"),
        "direction": evaluation.get("direction"),
        "pausedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pausedUntil": until.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "reasonZh": "近期影子样本表现为负，系统暂停该方向建议。",
        "evaluation": evaluation,
        "safety": safety_payload(),
    }
    _write_pause(runtime_dir, key, payload)
    return payload


def _apply_pause_to_report(report: dict[str, Any], pause: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(report)
    decision = dict(_as_dict(enriched.get("decision")))
    decision["action"] = "HOLD"
    decision["reasoning"] = "AI 建议熔断已触发：近期影子样本表现为负，本条仅允许观察复核。"
    enriched["decision"] = decision
    fusion = dict(_as_dict(enriched.get("advisory_fusion")))
    fusion.update(
        {
            "finalAction": "PAUSED",
            "notifySeverity": "SIGNAL_PAUSED",
            "riskOverride": True,
            "riskOverrideReason": "ai_journal_signal_pause",
            "agreement": "已由 AI 建议复盘熔断降级",
        }
    )
    enriched["advisory_fusion"] = fusion
    deepseek = dict(_as_dict(enriched.get("deepseek_advice")))
    advice = dict(_as_dict(deepseek.get("advice")))
    advice.update(
        {
            "headline": "该方向近期影子表现不佳，系统暂停主动建议。",
            "verdict": "暂停，不开新仓，仅观察复核",
            "signalGrade": "暂停级",
            "planStatus": "暂停：AI 建议复盘熔断已触发",
            "entryZone": "不生成，等待复盘评分恢复",
            "targets": ["不生成", "不生成", "不生成"],
            "defense": "不生成",
            "riskReward": "不评估",
            "positionAdvice": "不构成下单建议；仅允许人工观察复核",
            "invalidation": "复盘评分恢复、冷却期结束、运行快照新鲜且程序风控允许后再评估",
            "executionBoundary": "仅中文观察建议；不会下单、平仓、撤单或修改实盘参数。",
        }
    )
    deepseek["advice"] = advice
    enriched["deepseek_advice"] = deepseek
    enriched["ai_journal_gate"] = {
        "ok": True,
        "status": "paused",
        "reasonZh": pause.get("reasonZh") or "AI 建议复盘熔断已触发。",
        "pausedUntil": pause.get("pausedUntil"),
        "evaluation": pause.get("evaluation") or {},
        "safety": safety_payload(),
    }
    return enriched


def apply_signal_kill_switch(report: dict[str, Any], *, runtime_dir: str | Path, now_iso: str | None = None) -> dict[str, Any]:
    settings = settings_from_env()
    family = signal_family(report)
    if not settings.get("enabled") or family["direction"] not in {"LONG", "SHORT"}:
        out = dict(report)
        out.setdefault("ai_journal_gate", {"ok": True, "status": "not_applicable", "family": family, "safety": safety_payload()})
        return out
    active_pause = current_pause_state(runtime_dir, family["key"], now_iso=now_iso)
    if active_pause.get("active"):
        return _apply_pause_to_report(report, active_pause)
    evaluation = evaluate_family(runtime_dir, family["symbol"], family["direction"], settings=settings)
    if evaluation.get("pause"):
        pause = build_pause(runtime_dir, evaluation, now_iso=now_iso)
        return _apply_pause_to_report(report, pause)
    out = dict(report)
    out["ai_journal_gate"] = {
        "ok": True,
        "status": "pass",
        "family": family,
        "evaluation": evaluation,
        "safety": safety_payload(),
    }
    return out
