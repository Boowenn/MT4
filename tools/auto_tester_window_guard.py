#!/usr/bin/env python3
"""Shared guards for controlled ParamLab Strategy Tester execution.

The guard is intentionally conservative. It only validates a tester-only queue
and authorization lock; it never launches MT5 and never edits live presets.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LOCK_NAME = "QuantGod_AutoTesterWindow.lock.json"
AUTO_TESTER_WINDOW_NAME = "QuantGod_AutoTesterWindow.json"
AUTO_TESTER_WINDOW_LEDGER_NAME = "QuantGod_AutoTesterWindowLedger.csv"
LIVE_DASHBOARD_NAME = "QuantGod_Dashboard.json"
LOCK_PURPOSE = "PARAM_LAB_STRATEGY_TESTER_ONLY"
JST = timezone(timedelta(hours=9))
ALLOWED_PERIODS = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def parse_now(value: str = "") -> datetime:
    parsed = parse_iso_datetime(value)
    if parsed:
        return parsed
    return datetime.now(timezone.utc)


def parse_dashboard_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = parse_iso_datetime(text)
    if parsed:
        return parsed
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=JST)
        except Exception:
            continue
    return None


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def path_same(left: Path, right: Path) -> bool:
    try:
        return str(left.resolve()).lower() == str(right.resolve()).lower()
    except Exception:
        return str(left).lower() == str(right).lower()


def path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def path_from_tester_text(value: str) -> Path:
    text = str(value or "").strip()
    if len(text) >= 3 and text[1:3] == ":\\" and text[0].upper() == "Z":
        return Path("/" + text[3:].replace("\\", "/").lstrip("/"))
    return Path(text)


def normalize_account_number(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def sum_numeric(rows: Any, key: str) -> float:
    total = 0.0
    if not isinstance(rows, list):
        return total
    for row in rows:
        if isinstance(row, dict):
            total += as_float(row.get(key), 0.0) or 0.0
    return total


def validate_live_session_compatibility(
    *,
    runtime_dir: Path,
    expected_login: str = "",
    expected_server: str = "",
    now_utc: datetime | None = None,
    max_snapshot_age_minutes: int = 30,
) -> dict[str, Any]:
    """Verify live pilot state before unattended tester execution.

    This guard reads only the live dashboard artifact. It never talks to the
    broker and never edits live state. Unknown or stale live state is treated as
    blocked because unattended Strategy Tester launches must not race a live
    pilot position or an unverified terminal session.
    """
    now = now_utc or datetime.now(timezone.utc)
    path = runtime_dir / LIVE_DASHBOARD_NAME
    snapshot = read_json(path)
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
    symbols = snapshot.get("symbols") if isinstance(snapshot.get("symbols"), list) else []
    open_trades = snapshot.get("openTrades") if isinstance(snapshot.get("openTrades"), list) else []
    strategies = snapshot.get("strategies") if isinstance(snapshot.get("strategies"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        blockers.append("live_dashboard_snapshot_missing")
    if not snapshot:
        blockers.append("live_dashboard_snapshot_unreadable")

    timestamp = parse_dashboard_time(snapshot.get("timestamp") or runtime.get("localTime") or runtime.get("serverTime"))
    age_minutes: float | None = None
    if not timestamp:
        blockers.append("live_dashboard_timestamp_missing")
    else:
        age_minutes = max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds() / 60.0)
        if max_snapshot_age_minutes > 0 and age_minutes > max_snapshot_age_minutes:
            blockers.append("live_dashboard_snapshot_stale")

    open_trade_count = len(open_trades)
    symbol_open_positions = int(sum_numeric(symbols, "openPositions"))
    strategy_open_positions = int(sum_numeric(list(strategies.values()), "positions"))
    margin_in_use = as_float(account.get("margin"), 0.0) or 0.0

    if open_trade_count > 0:
        blockers.append("open_live_positions_present")
    if symbol_open_positions > 0:
        blockers.append("symbol_open_positions_present")
    if strategy_open_positions > 0:
        blockers.append("strategy_open_positions_present")
    if margin_in_use > 0.01:
        blockers.append("live_account_margin_in_use")

    expected_login_text = normalize_account_number(expected_login)
    actual_login_text = normalize_account_number(account.get("number"))
    if expected_login_text and actual_login_text and expected_login_text != actual_login_text:
        blockers.append("live_account_number_mismatch")
    elif expected_login_text and not actual_login_text:
        blockers.append("live_account_number_missing")

    actual_server = str(account.get("server") or runtime.get("server") or "").strip()
    if expected_server and actual_server and actual_server != expected_server:
        blockers.append("live_account_server_mismatch")
    elif expected_server and not actual_server:
        blockers.append("live_account_server_missing")

    if runtime.get("connected") is not True:
        blockers.append("live_runtime_not_connected")
    if runtime.get("terminalConnected") is not True:
        blockers.append("live_terminal_not_connected")
    if runtime.get("accountAuthorized") is not True:
        blockers.append("live_account_not_authorized")
    if runtime.get("pilotKillSwitch") is True:
        blockers.append("live_pilot_kill_switch_active")

    trade_status = str(runtime.get("tradeStatus") or "").upper()
    risky_markers = ("ERROR", "FAIL", "PANIC", "KILL", "UNAUTHORIZED", "DISCONNECTED")
    if trade_status and any(marker in trade_status for marker in risky_markers):
        blockers.append("live_trade_status_incompatible")
    if runtime.get("livePilotMode") is not True:
        warnings.append("live_pilot_mode_not_confirmed")

    return {
        "path": str(path),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "snapshotTimestamp": timestamp.isoformat() if timestamp else "",
        "snapshotAgeMinutes": round(age_minutes, 2) if age_minutes is not None else None,
        "maxSnapshotAgeMinutes": max_snapshot_age_minutes,
        "openTradeCount": open_trade_count,
        "symbolOpenPositions": symbol_open_positions,
        "strategyOpenPositions": strategy_open_positions,
        "marginInUse": margin_in_use,
        "tradeStatus": runtime.get("tradeStatus", ""),
        "connected": runtime.get("connected"),
        "terminalConnected": runtime.get("terminalConnected"),
        "accountAuthorized": runtime.get("accountAuthorized"),
        "livePilotMode": runtime.get("livePilotMode"),
        "accountNumber": actual_login_text,
        "server": actual_server,
    }


def parse_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")) or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        values[key.strip()] = raw.split("||", 1)[0].strip()
    return values


def parse_ini(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = ""
    if not path.exists():
        return sections
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            sections.setdefault(current, {})
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            sections.setdefault(current, {})[key.strip()] = value.strip()
    return sections


def regular_tester_window(now_utc: datetime | None = None) -> dict[str, Any]:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(JST)
    weekday = now.weekday()  # Monday=0
    minutes = now.hour * 60 + now.minute
    daily_closeout_window = 0 <= minutes <= (2 * 60 + 30)
    daily_night_window = (20 * 60 + 10) <= minutes <= (23 * 60 + 30)
    weekend_morning_window = (
        (weekday == 5 and (7 * 60 + 10) <= minutes <= (9 * 60 + 30))
        or (weekday == 6 and (8 * 60) <= minutes <= (9 * 60 + 30))
    )
    open_now = daily_closeout_window or daily_night_window or weekend_morning_window
    return {
        "status": "ready" if open_now else "blocked",
        "ok": open_now,
        "nowJstIso": now.isoformat(),
        "windowLabel": "Daily closeout 00:00-02:30 JST, daily 20:10-23:30 JST, Sat 07:10-09:30 JST, or Sun 08:00-09:30 JST",
        "blockers": [] if open_now else ["outside_strategy_tester_window"],
    }


def validate_authorization_lock(
    lock_path: Path,
    *,
    runtime_dir: Path,
    hfm_root: Path,
    now_utc: datetime | None = None,
    max_tasks: int | None = None,
    allow_outside_window: bool = False,
) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    lock = read_json(lock_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not lock_path.exists():
        blockers.append("authorization_lock_missing")
    if not lock:
        blockers.append("authorization_lock_unreadable")
    if str(lock.get("purpose") or "") != LOCK_PURPOSE:
        blockers.append("authorization_lock_wrong_purpose")
    if lock.get("authorized") is not True:
        blockers.append("authorization_lock_not_authorized")
    if lock.get("testerOnly") is not True:
        blockers.append("authorization_lock_not_tester_only")
    if lock.get("allowRunTerminal") is not True:
        blockers.append("authorization_lock_run_terminal_not_allowed")
    if lock.get("livePresetMutation") not in (False, None):
        blockers.append("authorization_lock_allows_live_preset_mutation")
    if allow_outside_window and lock.get("allowOutsideWindow") is not True:
        blockers.append("outside_window_override_not_locked")

    expires_at = parse_iso_datetime(lock.get("expiresAtIso"))
    created_at = parse_iso_datetime(lock.get("createdAtIso"))
    if created_at and created_at > now + timedelta(minutes=2):
        blockers.append("authorization_lock_created_in_future")
    if not expires_at:
        blockers.append("authorization_lock_missing_expiry")
    elif expires_at <= now:
        blockers.append("authorization_lock_expired")

    lock_runtime = str(lock.get("runtimeDir") or "").strip()
    if lock_runtime and not path_same(Path(lock_runtime), runtime_dir):
        blockers.append("authorization_lock_runtime_dir_mismatch")
    elif not lock_runtime:
        warnings.append("authorization_lock_runtime_dir_not_pinned")

    lock_hfm = str(lock.get("hfmRoot") or "").strip()
    if lock_hfm and not path_same(Path(lock_hfm), hfm_root):
        blockers.append("authorization_lock_hfm_root_mismatch")
    elif not lock_hfm:
        warnings.append("authorization_lock_hfm_root_not_pinned")

    lock_max_tasks = lock.get("maxTasks")
    if max_tasks is not None and lock_max_tasks not in (None, ""):
        try:
            if int(lock_max_tasks) < int(max_tasks):
                blockers.append("authorization_lock_max_tasks_too_low")
        except Exception:
            blockers.append("authorization_lock_max_tasks_invalid")

    return {
        "path": str(lock_path),
        "exists": lock_path.exists(),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "expiresAtIso": expires_at.isoformat() if expires_at else "",
        "createdAtIso": created_at.isoformat() if created_at else "",
        "purpose": lock.get("purpose", ""),
        "allowOutsideWindow": bool(lock.get("allowOutsideWindow")),
    }


def validate_scheduler_queue(scheduler: dict[str, Any], *, max_tasks: int | None = None) -> dict[str, Any]:
    tasks = scheduler.get("selectedTasks") if isinstance(scheduler.get("selectedTasks"), list) else []
    blockers: list[str] = []
    task_rows: list[dict[str, Any]] = []
    if not scheduler:
        blockers.append("auto_scheduler_missing")
    if not tasks:
        blockers.append("auto_scheduler_queue_empty")
    summary = scheduler.get("summary") if isinstance(scheduler.get("summary"), dict) else {}
    if summary.get("runTerminal") not in (False, None):
        blockers.append("auto_scheduler_run_terminal_enabled")
    if summary.get("livePresetMutation") not in (False, None):
        blockers.append("auto_scheduler_live_preset_mutation_enabled")

    for task in tasks:
        if not isinstance(task, dict):
            blockers.append("auto_scheduler_task_not_object")
            continue
        task_blockers: list[str] = []
        candidate_id = str(task.get("candidateId") or "")
        command = str(task.get("testerOnlyCommand") or task.get("configOnlyCommand") or "")
        if not candidate_id:
            task_blockers.append("missing_candidate_id")
        if task.get("testerOnly") is not True:
            task_blockers.append("task_not_marked_tester_only")
        if task.get("livePresetMutation") not in (False, None):
            task_blockers.append("task_live_preset_mutation_enabled")
        if task.get("runTerminalDefault") not in (False, None):
            task_blockers.append("task_run_terminal_default_enabled")
        if "--run-terminal" in command.lower() or "-runterminal" in command.lower():
            task_blockers.append("task_command_contains_run_terminal")
        if task_blockers:
            blockers.extend(f"{candidate_id or 'unknown'}:{item}" for item in task_blockers)
        task_rows.append({
            "candidateId": candidate_id,
            "routeKey": task.get("routeKey", ""),
            "status": "ready" if not task_blockers else "blocked",
            "blockers": task_blockers,
        })

    return {
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "queueCount": len(tasks),
        "blockers": blockers,
        "tasks": task_rows,
    }


def validate_tester_config(config_path: Path, *, repo_root: Path) -> dict[str, Any]:
    sections = parse_ini(config_path)
    blockers: list[str] = []
    if not config_path.exists():
        blockers.append("tester_config_missing")
    common = sections.get("Common", {})
    experts = sections.get("Experts", {})
    tester = sections.get("Tester", {})
    if experts.get("AllowLiveTrading") != "0":
        blockers.append("tester_config_allow_live_trading_not_zero")
    if experts.get("AllowDllImport") != "0":
        blockers.append("tester_config_allow_dll_import_not_zero")
    if tester.get("Expert") != "QuantGod_MultiStrategy.ex5":
        blockers.append("tester_config_wrong_expert")
    preset_name = tester.get("ExpertParameters", "")
    if not preset_name.startswith("QuantGod_MT5_ParamLab_"):
        blockers.append("tester_config_not_paramlab_preset")
    if tester.get("Optimization") != "0":
        blockers.append("tester_config_optimization_not_zero")
    if tester.get("ReplaceReport") != "1":
        blockers.append("tester_config_replace_report_not_one")
    if tester.get("ShutdownTerminal") != "1":
        blockers.append("tester_config_shutdown_terminal_not_one")
    if tester.get("Period") not in ALLOWED_PERIODS:
        blockers.append("tester_config_period_invalid")
    if not tester.get("Symbol"):
        blockers.append("tester_config_symbol_missing")
    if not common.get("Login") or not common.get("Server"):
        blockers.append("tester_config_account_or_server_missing")
    if not tester.get("Login"):
        blockers.append("tester_config_tester_login_missing")

    report_text = tester.get("Report", "")
    report_path = path_from_tester_text(report_text) if report_text else Path()
    if not report_text:
        blockers.append("tester_config_report_missing")
    elif not path_under(report_path, repo_root / "archive" / "param-lab" / "runs"):
        blockers.append("tester_config_report_not_in_paramlab_archive")

    return {
        "path": str(config_path),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
        "presetName": preset_name,
        "reportPath": report_text,
    }


def validate_preset(path: Path) -> dict[str, Any]:
    values = parse_key_value_file(path)
    blockers: list[str] = []
    if not path.exists():
        blockers.append("preset_missing")
    lot = as_float(values.get("PilotLotSize"))
    if lot is not None and lot > 0.01:
        blockers.append("preset_lot_size_gt_0_01")
    max_total = as_float(values.get("PilotMaxTotalPositions"))
    if max_total is not None and max_total > 1:
        blockers.append("preset_max_total_positions_gt_1")
    max_symbol = as_float(values.get("PilotMaxPositionsPerSymbol"))
    if max_symbol is not None and max_symbol > 1:
        blockers.append("preset_max_positions_per_symbol_gt_1")
    return {
        "path": str(path),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
        "valuesChecked": {
            "PilotLotSize": values.get("PilotLotSize", ""),
            "PilotMaxTotalPositions": values.get("PilotMaxTotalPositions", ""),
            "PilotMaxPositionsPerSymbol": values.get("PilotMaxPositionsPerSymbol", ""),
        },
    }


def validate_tester_profile_matches(profile_path: Path, preset_path: Path) -> dict[str, Any]:
    profile = parse_key_value_file(profile_path)
    preset = parse_key_value_file(preset_path)
    blockers: list[str] = []
    if not profile_path.exists():
        blockers.append("tester_profile_missing")
    if not preset_path.exists():
        blockers.append("tester_profile_reference_preset_missing")
    for key in ("PilotLotSize", "PilotMaxTotalPositions", "PilotMaxPositionsPerSymbol"):
        if key in preset and profile.get(key) != preset.get(key):
            blockers.append(f"tester_profile_{key}_mismatch")
    if preset and not profile:
        blockers.append("tester_profile_unreadable")
    return {
        "path": str(profile_path),
        "referencePresetPath": str(preset_path),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
    }


def validate_materialized_task(task: dict[str, Any], *, repo_root: Path, hfm_root: Path) -> dict[str, Any]:
    candidate_id = str(task.get("candidateId") or "")
    config_path = Path(str(task.get("configPath") or ""))
    preset_path = Path(str(task.get("presetPath") or ""))
    hfm_preset_path = Path(str(task.get("hfmPresetPath") or ""))
    config_check = validate_tester_config(config_path, repo_root=repo_root)
    local_preset_check = validate_preset(preset_path)
    hfm_preset_check = validate_preset(hfm_preset_path)
    profile_root = hfm_root / "MQL5" / "Profiles" / "Tester"
    blockers = []
    if not profile_root.exists():
        blockers.append("tester_profile_root_missing")
    for check in (config_check, local_preset_check, hfm_preset_check):
        blockers.extend(check.get("blockers", []))
    return {
        "candidateId": candidate_id,
        "routeKey": task.get("routeKey", ""),
        "symbol": task.get("symbol", ""),
        "timeframe": task.get("timeframe", ""),
        "status": "ready" if not blockers else "blocked",
        "ok": not blockers,
        "blockers": blockers,
        "config": config_check,
        "localPreset": local_preset_check,
        "hfmPreset": hfm_preset_check,
        "testerProfileRoot": str(profile_root),
    }


def evaluate_execution_gate(
    *,
    scheduler: dict[str, Any],
    runtime_dir: Path,
    hfm_root: Path,
    repo_root: Path,
    lock_path: Path | None = None,
    now_utc: datetime | None = None,
    max_tasks: int | None = None,
    allow_outside_window: bool = False,
    expected_login: str = "",
    expected_server: str = "",
    max_live_snapshot_age_minutes: int = 30,
) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    effective_lock = lock_path or runtime_dir / LOCK_NAME
    window = regular_tester_window(now)
    lock = validate_authorization_lock(
        effective_lock,
        runtime_dir=runtime_dir,
        hfm_root=hfm_root,
        now_utc=now,
        max_tasks=max_tasks,
        allow_outside_window=allow_outside_window,
    )
    queue = validate_scheduler_queue(scheduler, max_tasks=max_tasks)
    live_session = validate_live_session_compatibility(
        runtime_dir=runtime_dir,
        expected_login=expected_login,
        expected_server=expected_server,
        now_utc=now,
        max_snapshot_age_minutes=max_live_snapshot_age_minutes,
    )
    terminal_path = hfm_root / "terminal64.exe"
    profile_root = hfm_root / "MQL5" / "Profiles" / "Tester"
    env_blockers: list[str] = []
    if not terminal_path.exists():
        env_blockers.append("terminal64_missing")
    if not profile_root.exists():
        env_blockers.append("tester_profile_root_missing")
    if not (runtime_dir.exists() and runtime_dir.is_dir()):
        env_blockers.append("runtime_dir_missing")
    if not (repo_root.exists() and repo_root.is_dir()):
        env_blockers.append("repo_root_missing")
    window_blockers = [] if (allow_outside_window or window["ok"]) else list(window["blockers"])
    if allow_outside_window and lock.get("allowOutsideWindow") is not True:
        window_blockers.append("outside_window_override_not_locked")

    blockers = []
    blockers.extend(lock["blockers"])
    blockers.extend(queue["blockers"])
    blockers.extend(live_session["blockers"])
    blockers.extend(env_blockers)
    blockers.extend(window_blockers)
    return {
        "status": "ready" if not blockers else "blocked",
        "canRunTerminal": not blockers,
        "generatedAtIso": now.isoformat(),
        "window": window,
        "authorizationLock": lock,
        "queue": queue,
        "liveSession": live_session,
        "environment": {
            "status": "ready" if not env_blockers else "blocked",
            "blockers": env_blockers,
            "terminalPath": str(terminal_path),
            "testerProfileRoot": str(profile_root),
            "runtimeDir": str(runtime_dir),
            "repoRoot": str(repo_root),
        },
        "blockers": blockers,
        "hardGuards": [
            "Run-terminal execution requires a valid authorization lock.",
            "Run-terminal execution requires the regular Strategy Tester window unless the lock explicitly allows the override.",
            "The scheduler queue must be tester-only and must not contain run-terminal by default.",
            "Generated tester configs must set AllowLiveTrading=0 and write reports under archive/param-lab/runs.",
            "Preset lot and position caps must stay at the 0.01 single-position pilot boundary.",
            "Unattended run-terminal execution requires a fresh live dashboard snapshot with zero open live positions and no margin in use.",
            "Live account/server/session compatibility must be confirmed before the isolated tester terminal can launch.",
        ],
    }
