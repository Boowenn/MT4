from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .env_reader import as_float, as_int, load_env, truthy
from .evidence import load_runtime_evidence, symbol_fastlane_status, symbol_gate_passed
from .schema import DEFAULT_CONFIRMATION_PHRASE, DEFAULT_MAX_DAILY_LOSS_R, DEFAULT_MAX_DAILY_TRADES, DEFAULT_MAX_LOT, add_check, base_report, validate_no_secret_or_execution_flags

SAFE_TRIGGER_STATES = {"WAIT_TRIGGER_CONFIRMATION", "WAIT_CONFIRMATION", "WAITING_CONFIRMATION", "READY_FOR_REVIEW"}


def _env_list(env: Dict[str, str], key: str) -> List[str]:
    return [part.strip() for part in env.get(key, "").split(",") if part.strip()]


def _find_trigger_state(payload: Dict[str, Any] | None, symbol: str, direction: str) -> str:
    if not payload:
        return "MISSING"
    rows = payload.get("decisions") or payload.get("triggers") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return "UNKNOWN"
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        row_direction = str(row.get("direction") or row.get("side") or "").upper()
        if row_direction and row_direction != direction.upper():
            continue
        return str(row.get("state") or row.get("status") or row.get("decision") or "UNKNOWN").upper()
    return "MISSING"


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _runtime_snapshot_fresh(snapshot: Dict[str, Any], max_age_seconds: int = 300) -> bool:
    for key in ("runtimeFresh", "fresh", "isFresh"):
        if key in snapshot:
            return bool(snapshot.get(key))
    ts = _parse_iso(snapshot.get("generatedAt") or snapshot.get("generatedAtIso") or snapshot.get("timeIso"))
    current_price = snapshot.get("current_price")
    if ts is None and isinstance(current_price, dict):
        ts = _parse_iso(current_price.get("timeIso"))
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() <= max_age_seconds


def _find_sltp_status(payload: Dict[str, Any] | None, symbol: str, direction: str) -> str:
    if not payload:
        return "MISSING"
    rows = payload.get("plans") or payload.get("calibrations") or payload.get("items") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return str(payload.get("status") or payload.get("state") or "UNKNOWN").upper()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        row_direction = str(row.get("direction") or row.get("side") or "").upper()
        if row_direction and row_direction != direction.upper():
            continue
        return str(row.get("status") or row.get("state") or "UNKNOWN").upper()
    return "MISSING"


def evaluate_pilot_safety_lock(runtime_dir: Path, symbol: str, direction: str, repo_root: Path | None = None) -> Dict[str, Any]:
    env = load_env(repo_root or Path.cwd())
    report = base_report()
    symbol = symbol.strip()
    direction = direction.strip().upper()
    report["symbol"] = symbol
    report["direction"] = direction

    lock_enabled = not truthy(env.get("QG_PILOT_SAFETY_LOCK_DISABLED", "0"))
    add_check(report, "安全锁启用", lock_enabled, "试点安全锁被关闭，禁止进入试点", "BLOCKER")

    env_allowed = truthy(env.get("QG_PILOT_EXECUTION_ALLOWED", "0"))
    add_check(report, "人工打开试点开关", env_allowed, "QG_PILOT_EXECUTION_ALLOWED 未显式设置为 1", "BLOCKER")

    phrase = env.get("QG_PILOT_CONFIRMATION_PHRASE", "")
    add_check(report, "人工确认短语", phrase == DEFAULT_CONFIRMATION_PHRASE, "缺少精确人工确认短语", "BLOCKER")

    max_lot = as_float(env.get("QG_PILOT_MAX_LOT", DEFAULT_MAX_LOT), DEFAULT_MAX_LOT)
    max_daily_trades = as_int(env.get("QG_PILOT_MAX_DAILY_TRADES", DEFAULT_MAX_DAILY_TRADES), DEFAULT_MAX_DAILY_TRADES)
    max_daily_loss_r = as_float(env.get("QG_PILOT_MAX_DAILY_LOSS_R", DEFAULT_MAX_DAILY_LOSS_R), DEFAULT_MAX_DAILY_LOSS_R)
    report["pilotEnvelope"] = {
        "maxLot": max_lot,
        "maxDailyTrades": max_daily_trades,
        "maxDailyLossR": max_daily_loss_r,
        "confirmationPhraseRequired": DEFAULT_CONFIRMATION_PHRASE,
    }
    add_check(report, "最小仓位限制", 0 < max_lot <= DEFAULT_MAX_LOT, f"QG_PILOT_MAX_LOT 必须 >0 且 <= {DEFAULT_MAX_LOT}", "BLOCKER")
    add_check(report, "日内次数限制", 1 <= max_daily_trades <= DEFAULT_MAX_DAILY_TRADES, f"QG_PILOT_MAX_DAILY_TRADES 必须在 1~{DEFAULT_MAX_DAILY_TRADES}", "BLOCKER")
    add_check(report, "日内亏损限制", 0 < max_daily_loss_r <= DEFAULT_MAX_DAILY_LOSS_R, f"QG_PILOT_MAX_DAILY_LOSS_R 必须 >0 且 <= {DEFAULT_MAX_DAILY_LOSS_R}", "BLOCKER")

    allowed_symbols = _env_list(env, "QG_PILOT_ALLOWED_SYMBOLS")
    allowed_strategies = _env_list(env, "QG_PILOT_ALLOWED_STRATEGIES")
    report["pilotEnvelope"]["allowedSymbols"] = allowed_symbols
    report["pilotEnvelope"]["allowedStrategies"] = allowed_strategies
    add_check(report, "品种白名单", bool(allowed_symbols) and symbol in allowed_symbols, "当前品种不在 QG_PILOT_ALLOWED_SYMBOLS 白名单", "BLOCKER")
    add_check(report, "策略白名单", bool(allowed_strategies), "QG_PILOT_ALLOWED_STRATEGIES 为空，禁止试点", "BLOCKER")

    evidence = load_runtime_evidence(runtime_dir, symbol)
    report["runtimeEvidence"] = {key: bool(value) if key != "symbol" else value for key, value in evidence.items()}

    snapshot = evidence.get("snapshot")
    add_check(report, "运行快照存在", snapshot is not None, "缺少 MT5 runtime snapshot，禁止试点", "BLOCKER")
    if snapshot:
        fallback = bool(snapshot.get("fallback", False))
        fresh = _runtime_snapshot_fresh(snapshot)
        add_check(report, "运行快照非回退", not fallback, "runtime snapshot 处于 fallback，禁止试点", "BLOCKER")
        add_check(report, "运行快照新鲜", bool(fresh), "runtime snapshot 不新鲜，禁止试点", "BLOCKER")
        secret_errors = validate_no_secret_or_execution_flags(snapshot)
        add_check(report, "运行快照无凭据/执行字段", not secret_errors, "；".join(secret_errors[:5]) if secret_errors else "通过", "BLOCKER")

    fastlane_status = symbol_fastlane_status(evidence.get("fastlaneQuality"), symbol)
    add_check(report, "快通道质量存在", fastlane_status != "MISSING", "缺少快通道质量证据，禁止试点", "BLOCKER")
    add_check(report, "快通道质量通过", fastlane_status in {"OK", "PASS", "HEALTHY"}, f"快通道质量为 {fastlane_status}，禁止试点", "BLOCKER")

    gate_passed = symbol_gate_passed(evidence.get("entryGate"), symbol, direction)
    add_check(report, "自适应入场闸门存在", gate_passed is not None, "缺少自适应入场闸门证据，禁止试点", "BLOCKER")
    add_check(report, "自适应入场闸门通过", gate_passed is True, "自适应入场闸门未通过，禁止试点", "BLOCKER")

    trigger_state = _find_trigger_state(evidence.get("entryTriggerPlan"), symbol, direction)
    add_check(report, "入场触发计划存在", trigger_state != "MISSING", "缺少 P3-9 入场触发计划，禁止试点", "BLOCKER")
    add_check(report, "入场触发处于复核态", trigger_state in SAFE_TRIGGER_STATES, f"入场触发状态为 {trigger_state}，不允许试点", "BLOCKER")

    sltp_status = _find_sltp_status(evidence.get("dynamicSltp"), symbol, direction)
    add_check(report, "动态止盈止损计划存在", sltp_status != "MISSING", "缺少动态止盈止损计划，禁止试点", "BLOCKER")
    add_check(report, "动态止盈止损可复核", sltp_status in {"CALIBRATED", "WATCH_ONLY", "READY", "OK"}, f"动态止盈止损状态为 {sltp_status}，禁止试点", "BLOCKER")

    if all(check["passed"] for check in report["checks"]):
        report["decision"] = "ARMABLE_FOR_MANUAL_PILOT"
        report["decisionZh"] = "可进入人工最小仓位试点复核"
        report["reasons"] = ["所有前置证据通过；本工具仍不会下单，只允许人工继续复核"]
    else:
        report["decision"] = "BLOCKED"
        report["decisionZh"] = "阻断"

    return report
