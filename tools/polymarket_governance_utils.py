"""Shared helpers for guarded Polymarket execution governance.

These helpers are deliberately file/json/statistics only. They do not import
wallet clients, read private-key values, call Polymarket order APIs, or touch
MT5 state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REAL_MONEY_POLICY: dict[str, Any] = {
    "minDryRunOutcomeSamples": 60,
    "minDryRunWinRatePct": 58.0,
    "minDryRunProfitFactor": 1.35,
    "maxDryRunStopLossRatePct": 28.0,
    "maxDryRunConsecutiveLosses": 3,
    "minDryRunAverageReturnPct": 0.5,
    "minAiScore": 82.0,
    "minCompositeScore": 85.0,
    "maxSingleBetUSDC": 1.0,
    "maxDailyLossUSDC": 2.0,
    "maxOpenCanaryPositions": 1,
    "takeProfitPct": 18.0,
    "stopLossPct": 10.0,
    "trailingProfitPct": 8.0,
    "cancelUnfilledAfterMinutes": 15,
    "maxHoldHours": 36.0,
    "exitBeforeResolutionHours": 12.0,
    "allowedRiskLabels": ["low", "green"],
    "blockedAiColors": ["red", "yellow"],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def safe_number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_json_candidate(
    name: str,
    runtime_dir: Path,
    dashboard_dir: Path,
    explicit: str = "",
) -> tuple[dict[str, Any], str]:
    candidates = [Path(explicit)] if explicit else []
    candidates.extend([dashboard_dir / name, runtime_dir / name])
    for path in candidates:
        if not path or not path.exists():
            continue
        data = load_json(path)
        if data:
            return data, str(path)
    return {}, ""


def unique(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def get_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def market_key(row: dict[str, Any]) -> str:
    return str(row.get("marketId") or row.get("market_id") or "").strip()


def track_key(row: dict[str, Any]) -> str:
    return first_text(row.get("track"), row.get("suggestedShadowTrack"), row.get("shadowTrack"))


def index_by_market(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = market_key(row)
        if key and key not in out:
            out[key] = row
    return out


def index_outcomes(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in (str(row.get("trackingKey") or "").strip(), market_key(row)):
            if key and key not in out:
                out.setdefault(key, row)
    return out


def merge_policy(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = dict(DEFAULT_REAL_MONEY_POLICY)
    for key, value in (overrides or {}).items():
        if value is not None:
            policy[key] = value
    return policy


def _outcome_result(row: dict[str, Any]) -> tuple[str | None, float]:
    state = str(row.get("state") or "").upper()
    reason = str(row.get("wouldExitReason") or row.get("exitReason") or "").upper()
    pnl = safe_number(row.get("unrealizedPct"), None)
    if pnl is None:
        pnl = safe_number(row.get("realizedPct"), None)
    if pnl is None:
        current_price = safe_number(row.get("currentPrice"), None)
        entry_price = safe_number(row.get("entryPrice"), None)
        if current_price is not None and entry_price not in (None, 0):
            pnl = ((float(current_price) - float(entry_price)) / float(entry_price)) * 100.0
    pnl = float(pnl or 0.0)
    if "STOP_LOSS" in state or "STOP_LOSS" in reason:
        return "loss", pnl
    if "TAKE_PROFIT" in state or "TAKE_PROFIT" in reason or "TRAILING" in state or "TRAILING" in reason:
        return "win", pnl if pnl > 0 else abs(pnl)
    if state.startswith("WOULD_EXIT") or "TIME" in reason or "RESOLUTION" in reason:
        if pnl > 0:
            return "win", pnl
        if pnl < 0:
            return "loss", pnl
        return "flat", pnl
    return None, pnl


def _empty_profile(scope: str, key: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "key": key,
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "flats": 0,
        "stopLosses": 0,
        "grossWinPct": 0.0,
        "grossLossPct": 0.0,
        "winRatePct": 0.0,
        "profitFactor": 0.0,
        "stopLossRatePct": 0.0,
        "averageReturnPct": 0.0,
        "maxConsecutiveLosses": 0,
        "lastResult": "",
        "lastState": "",
        "lastGeneratedAt": "",
    }


def _profile_add(profile: dict[str, Any], row: dict[str, Any]) -> None:
    result, pnl = _outcome_result(row)
    if result is None:
        return
    profile["samples"] += 1
    profile["lastResult"] = result
    profile["lastState"] = str(row.get("state") or "")
    profile["lastGeneratedAt"] = str(row.get("generatedAt") or profile.get("lastGeneratedAt") or "")
    if result == "win":
        profile["wins"] += 1
        profile["grossWinPct"] += max(float(pnl), 0.01)
        profile["_currentLossRun"] = 0
    elif result == "loss":
        profile["losses"] += 1
        profile["grossLossPct"] += abs(min(float(pnl), -0.01))
        if "STOP_LOSS" in str(row.get("state") or row.get("wouldExitReason") or "").upper():
            profile["stopLosses"] += 1
        profile["_currentLossRun"] = int(profile.get("_currentLossRun") or 0) + 1
        profile["maxConsecutiveLosses"] = max(
            int(profile.get("maxConsecutiveLosses") or 0),
            int(profile.get("_currentLossRun") or 0),
        )
    else:
        profile["flats"] += 1


def _profile_finish(profile: dict[str, Any]) -> dict[str, Any]:
    samples = max(0, int(profile.get("samples") or 0))
    wins = int(profile.get("wins") or 0)
    gross_win = float(profile.get("grossWinPct") or 0.0)
    gross_loss = float(profile.get("grossLossPct") or 0.0)
    profile.pop("_currentLossRun", None)
    if samples:
        profile["winRatePct"] = round((wins / samples) * 100.0, 2)
        profile["stopLossRatePct"] = round((int(profile.get("stopLosses") or 0) / samples) * 100.0, 2)
        profile["averageReturnPct"] = round((gross_win - gross_loss) / samples, 3)
    profile["profitFactor"] = round((gross_win / gross_loss), 3) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    profile["grossWinPct"] = round(gross_win, 3)
    profile["grossLossPct"] = round(gross_loss, 3)
    return profile


def build_outcome_profiles(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {"global": _empty_profile("global", "global")}
    sorted_rows = sorted(rows, key=lambda row: str(row.get("generatedAt") or ""))
    for row in sorted_rows:
        keys = ["global"]
        mkey = market_key(row)
        tkey = track_key(row)
        if mkey:
            keys.append(f"market:{mkey}")
        if tkey:
            keys.append(f"track:{tkey}")
        for key in keys:
            if key not in profiles:
                scope, _, value = key.partition(":")
                profiles[key] = _empty_profile(scope or "global", value or "global")
            _profile_add(profiles[key], row)
    return {key: _profile_finish(value) for key, value in profiles.items()}


def choose_evidence_profile(
    candidate: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    min_samples: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    mkey = market_key(candidate)
    tkey = track_key(candidate)
    for key in [f"market:{mkey}" if mkey else "", f"track:{tkey}" if tkey else "", "global"]:
        if key and key in profiles:
            candidates.append(profiles[key])
    for profile in candidates:
        if int(profile.get("samples") or 0) >= min_samples:
            return profile
    return candidates[0] if candidates else _empty_profile("none", "")


def evaluate_real_money_readiness(
    *,
    candidate: dict[str, Any],
    ai: dict[str, Any],
    cross: dict[str, Any],
    evidence_profile: dict[str, Any],
    composite_score: float,
    policy: dict[str, Any],
    global_blockers: list[str] | None = None,
) -> tuple[bool, list[str]]:
    blockers = list(global_blockers or [])
    samples = int(evidence_profile.get("samples") or 0)
    win_rate = float(evidence_profile.get("winRatePct") or 0.0)
    profit_factor = float(evidence_profile.get("profitFactor") or 0.0)
    stop_loss_rate = float(evidence_profile.get("stopLossRatePct") or 0.0)
    avg_return = float(evidence_profile.get("averageReturnPct") or 0.0)
    max_consec_losses = int(evidence_profile.get("maxConsecutiveLosses") or 0)
    ai_score = safe_number(ai.get("score"), safe_number(candidate.get("aiScore"), None))
    ai_color = str(first_text(ai.get("color"), candidate.get("aiColor"))).lower()
    risk = str(first_text(candidate.get("risk"), ai.get("risk"), cross.get("sourceRisk"))).lower()
    macro_state = str(first_text(cross.get("macroRiskState"), candidate.get("macroRiskState"))).upper()

    if samples < int(policy["minDryRunOutcomeSamples"]):
        blockers.append("SIM_SAMPLE_LT_MIN")
    if win_rate < float(policy["minDryRunWinRatePct"]):
        blockers.append("SIM_WIN_RATE_LT_MIN")
    if profit_factor < float(policy["minDryRunProfitFactor"]):
        blockers.append("SIM_PROFIT_FACTOR_LT_MIN")
    if stop_loss_rate > float(policy["maxDryRunStopLossRatePct"]):
        blockers.append("SIM_STOP_LOSS_RATE_GT_MAX")
    if max_consec_losses > int(policy["maxDryRunConsecutiveLosses"]):
        blockers.append("SIM_CONSECUTIVE_LOSSES_GT_MAX")
    if avg_return < float(policy["minDryRunAverageReturnPct"]):
        blockers.append("SIM_AVG_RETURN_LT_MIN")
    if ai_score is None or float(ai_score) < float(policy["minAiScore"]):
        blockers.append("AI_SCORE_LT_REAL_MONEY_MIN")
    if ai_color in set(policy.get("blockedAiColors") or []):
        blockers.append(f"AI_COLOR_{ai_color.upper()}_BLOCKED")
    if composite_score < float(policy["minCompositeScore"]):
        blockers.append("COMPOSITE_SCORE_LT_REAL_MONEY_MIN")
    allowed_risk = set(policy.get("allowedRiskLabels") or [])
    if risk and risk not in allowed_risk:
        blockers.append("MARKET_RISK_NOT_LOW")
    if macro_state in {"HIGH", "RISK_ON", "REVIEW"}:
        blockers.append("CROSS_MARKET_RISK_REVIEW")
    if cross and cross.get("mt5ExecutionAllowed") is not False:
        blockers.append("CROSS_LINKAGE_BOUNDARY_UNCLEAR")
    if str(evidence_profile.get("lastResult") or "").lower() == "loss":
        blockers.append("LAST_DRY_RUN_OUTCOME_LOSS_REVIEW")
    blockers = unique(blockers)
    return not blockers, blockers
