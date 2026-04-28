#!/usr/bin/env python3
"""Guarded AUTO_TESTER_WINDOW entrypoint for ParamLab Strategy Tester runs.

Default mode is evaluation-only: it writes guard status for Dashboard/Governance
without launching MT5. With --run-terminal, this script refuses to run unless
the shared guard proves the window, lock, queue, profile root, and tester-only
constraints are all satisfied. The underlying runner performs the same lock and
config checks again before terminal launch.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auto_tester_window_guard import (
    AUTO_TESTER_WINDOW_LEDGER_NAME,
    AUTO_TESTER_WINDOW_NAME,
    LOCK_NAME,
    evaluate_execution_gate,
    parse_now,
    read_json,
)


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HFM_ROOT = Path(r"C:\Program Files\HFM Metatrader 5")
DEFAULT_RUNTIME_DIR = DEFAULT_HFM_ROOT / "MQL5" / "Files"
SCHEDULER_NAME = "QuantGod_ParamLabAutoScheduler.json"
STATUS_NAME = "QuantGod_ParamLabStatus.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate or run the QuantGod AUTO_TESTER_WINDOW guard.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--hfm-root", default=str(DEFAULT_HFM_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--scheduler", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--lock", default="")
    parser.add_argument("--max-tasks", type=int, default=4)
    parser.add_argument("--route", action="append", default=[])
    parser.add_argument("--candidate-id", action="append", default=[])
    parser.add_argument("--rank-mode", choices=("route-balanced", "score"), default="route-balanced")
    parser.add_argument("--from-date", default="")
    parser.add_argument("--to-date", default="")
    parser.add_argument("--login", default="186054398")
    parser.add_argument("--server", default="HFMarketsGlobal-Live12")
    parser.add_argument("--now-iso", default="", help="Testing hook for guard evaluation.")
    parser.add_argument("--run-terminal", action="store_true", help="Attempt a guarded Strategy Tester run.")
    parser.add_argument(
        "--authorized-strategy-tester",
        action="store_true",
        help="Required with --run-terminal; the lock and time window are still required.",
    )
    parser.add_argument(
        "--allow-outside-window",
        action="store_true",
        help="Only honored when the authorization lock also has allowOutsideWindow=true.",
    )
    return parser.parse_args()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def command_for_runner(args: argparse.Namespace, *, run_terminal: bool, lock_path: Path) -> list[str]:
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    scheduler_path = Path(args.scheduler) if args.scheduler else runtime_dir / SCHEDULER_NAME
    command = [
        "python",
        str(repo_root / "tools" / "run_param_lab.py"),
        "--repo-root",
        str(repo_root),
        "--hfm-root",
        str(Path(args.hfm_root)),
        "--runtime-dir",
        str(runtime_dir),
        "--plan",
        str(scheduler_path),
        "--max-tasks",
        str(args.max_tasks),
        "--rank-mode",
        args.rank_mode,
        "--login",
        args.login,
        "--server",
        args.server,
        "--auto-tester-lock",
        str(lock_path),
    ]
    if args.from_date:
        command.extend(["--from-date", args.from_date])
    if args.to_date:
        command.extend(["--to-date", args.to_date])
    for route in args.route:
        command.extend(["--route", route])
    for candidate_id in args.candidate_id:
        command.extend(["--candidate-id", candidate_id])
    if run_terminal:
        command.extend(["--run-terminal", "--authorized-strategy-tester"])
        if args.allow_outside_window:
            command.append("--allow-outside-window")
    return command


def command_to_text(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def summarize_selected_tasks(scheduler: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = scheduler.get("selectedTasks") if isinstance(scheduler.get("selectedTasks"), list) else []
    rows = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        rows.append({
            "rank": task.get("rank", ""),
            "candidateId": task.get("candidateId", ""),
            "routeKey": task.get("routeKey", ""),
            "symbol": task.get("symbol", ""),
            "timeframe": task.get("timeframe", ""),
            "scheduleAction": task.get("scheduleAction", ""),
            "sourceDecision": task.get("sourceDecision", ""),
            "testerOnly": task.get("testerOnly") is True,
            "livePresetMutation": bool(task.get("livePresetMutation")),
            "runTerminalDefault": bool(task.get("runTerminalDefault")),
        })
    return rows


def build_status(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo_root = Path(args.repo_root)
    hfm_root = Path(args.hfm_root)
    runtime_dir = Path(args.runtime_dir)
    scheduler_path = Path(args.scheduler) if args.scheduler else runtime_dir / SCHEDULER_NAME
    output_path = Path(args.output) if args.output else runtime_dir / AUTO_TESTER_WINDOW_NAME
    ledger_path = Path(args.ledger) if args.ledger else runtime_dir / AUTO_TESTER_WINDOW_LEDGER_NAME
    lock_path = Path(args.lock) if args.lock else runtime_dir / LOCK_NAME
    now = parse_now(args.now_iso)
    scheduler = read_json(scheduler_path)
    selected_tasks = summarize_selected_tasks(scheduler)

    gate = evaluate_execution_gate(
        scheduler=scheduler,
        runtime_dir=runtime_dir,
        hfm_root=hfm_root,
        repo_root=repo_root,
        lock_path=lock_path,
        now_utc=now,
        max_tasks=args.max_tasks,
        allow_outside_window=args.allow_outside_window,
    )
    config_only_command = command_for_runner(args, run_terminal=False, lock_path=lock_path)
    run_command = command_for_runner(args, run_terminal=True, lock_path=lock_path)
    child_status: dict[str, Any] = {
        "attempted": False,
        "exitCode": None,
        "stdoutTail": "",
        "stderrTail": "",
    }
    mode = "EVALUATE_ONLY"
    exit_code = 0

    if args.run_terminal:
        mode = "EXECUTE_STRATEGY_TESTER"
        if not args.authorized_strategy_tester:
            gate["blockers"].append("missing_authorized_strategy_tester_flag")
            gate["canRunTerminal"] = False
            gate["status"] = "blocked"
        if not gate["canRunTerminal"]:
            exit_code = 2
        else:
            process = subprocess.run(run_command, text=True, capture_output=True, check=False)
            child_status = {
                "attempted": True,
                "exitCode": process.returncode,
                "stdoutTail": "\n".join(process.stdout.splitlines()[-20:]),
                "stderrTail": "\n".join(process.stderr.splitlines()[-20:]),
            }
            exit_code = process.returncode

    latest_runner_status = read_json(runtime_dir / STATUS_NAME)
    summary = {
        "mode": mode,
        "canRunTerminal": bool(gate.get("canRunTerminal")),
        "runTerminalRequested": bool(args.run_terminal),
        "runAttempted": bool(child_status["attempted"]),
        "selectedTaskCount": len(selected_tasks),
        "queueCount": gate.get("queue", {}).get("queueCount", 0),
        "windowOk": bool(gate.get("window", {}).get("ok")),
        "lockOk": bool(gate.get("authorizationLock", {}).get("ok")),
        "queueOk": bool(gate.get("queue", {}).get("ok")),
        "environmentOk": gate.get("environment", {}).get("status") == "ready",
        "blockerCount": len(gate.get("blockers") or []),
        "childExitCode": child_status["exitCode"],
        "runTerminal": bool(child_status["attempted"]),
        "livePresetMutation": False,
    }
    status = {
        "schemaVersion": 1,
        "source": "QuantGod AUTO_TESTER_WINDOW Guard",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "evaluatedAtIso": now.isoformat(),
        "mode": mode,
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "hfmRoot": str(hfm_root),
        "schedulerPath": str(scheduler_path),
        "lockPath": str(lock_path),
        "summary": summary,
        "gate": gate,
        "selectedTasks": selected_tasks,
        "configOnlyCommand": command_to_text(config_only_command),
        "guardedRunCommand": command_to_text(run_command),
        "childProcess": child_status,
        "latestParamLabStatus": {
            "runId": latest_runner_status.get("runId", ""),
            "mode": latest_runner_status.get("mode", ""),
            "generatedAtIso": latest_runner_status.get("generatedAtIso", ""),
            "summary": latest_runner_status.get("summary", {}),
        },
        "hardGuards": gate.get("hardGuards", []),
        "nextOperatorSteps": [
            "Keep this in EVALUATE_ONLY mode on weekdays.",
            "Create the authorization lock only for a controlled Strategy Tester session.",
            "Use guardedRunCommand only when canRunTerminal=true.",
            "After reports land, run watch_param_lab_reports.py and rebuild Governance Advisor.",
        ],
    }
    write_json(output_path, status)
    rows = []
    for task in selected_tasks:
        rows.append({
            "GeneratedAtIso": status["generatedAtIso"],
            "Mode": mode,
            "CanRunTerminal": str(summary["canRunTerminal"]).lower(),
            "WindowOk": str(summary["windowOk"]).lower(),
            "LockOk": str(summary["lockOk"]).lower(),
            "QueueOk": str(summary["queueOk"]).lower(),
            "CandidateId": task.get("candidateId", ""),
            "RouteKey": task.get("routeKey", ""),
            "ScheduleAction": task.get("scheduleAction", ""),
            "Blockers": "/".join(gate.get("blockers") or []),
        })
    write_csv(
        ledger_path,
        rows,
        [
            "GeneratedAtIso",
            "Mode",
            "CanRunTerminal",
            "WindowOk",
            "LockOk",
            "QueueOk",
            "CandidateId",
            "RouteKey",
            "ScheduleAction",
            "Blockers",
        ],
    )
    print(f"Wrote {output_path}")
    print(f"Wrote {ledger_path}")
    print(
        "AUTO_TESTER_WINDOW: "
        f"mode={mode} canRunTerminal={summary['canRunTerminal']} "
        f"windowOk={summary['windowOk']} lockOk={summary['lockOk']} "
        f"queue={summary['queueCount']} blockers={summary['blockerCount']}"
    )
    return status, exit_code


def main() -> int:
    args = parse_args()
    try:
        _, exit_code = build_status(args)
        return exit_code
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
