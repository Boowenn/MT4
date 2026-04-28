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
    saturday_window = weekday == 5 and (7 * 60 + 10) <= minutes <= (9 * 60 + 30)
    sunday_window = weekday == 6 and (8 * 60) <= minutes <= (9 * 60 + 30)
    open_now = saturday_window or sunday_window
    return {
        "status": "ready" if open_now else "blocked",
        "ok": open_now,
        "nowJstIso": now.isoformat(),
        "windowLabel": "Sat 07:10-09:30 JST or Sun 08:00-09:30 JST",
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

    report_text = tester.get("Report", "")
    report_path = Path(report_text) if report_text else Path()
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
    blockers.extend(env_blockers)
    blockers.extend(window_blockers)
    return {
        "status": "ready" if not blockers else "blocked",
        "canRunTerminal": not blockers,
        "generatedAtIso": now.isoformat(),
        "window": window,
        "authorizationLock": lock,
        "queue": queue,
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
        ],
    }
