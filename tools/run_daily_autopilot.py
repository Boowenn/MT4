#!/usr/bin/env python3
"""Run QuantGod's daily safe automation loop.

This orchestrator turns Dashboard "today" items into file-based work:
refresh evidence, maintain ParamLab queues, evaluate the tester guard, run
tester-only tasks only when explicitly enabled and guarded, refresh Polymarket
research, and write the DailyReview artifact. It never applies live promotion
or sends financial orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTOPILOT_NAME = "QuantGod_DailyAutopilot.json"
DEFAULT_AUTOPILOT_LEDGER = "QuantGod_DailyAutopilotLedger.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QuantGod daily safe autopilot.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR") or "")
    parser.add_argument("--dashboard-dir", default=os.environ.get("QG_DASHBOARD_FILES_DIR") or "")
    parser.add_argument("--tester-root", default=os.environ.get("QG_PARAMLAB_TESTER_ROOT") or os.environ.get("QG_MT5_TESTER_ROOT") or "")
    parser.add_argument("--hfm-root", default=os.environ.get("QG_PARAMLAB_HFM_ROOT") or "")
    parser.add_argument("--python-bin", default=os.environ.get("QG_PYTHON_BIN", "python3"))
    parser.add_argument("--interval-minutes", type=float, default=float(os.environ.get("QG_DAILY_AUTOPILOT_INTERVAL_MINUTES", "60")))
    parser.add_argument("--max-tasks", type=int, default=int(os.environ.get("QG_DAILY_AUTOPILOT_MAX_TASKS", "5")))
    parser.add_argument("--allow-tester-run", action="store_true", default=os.environ.get("QG_DAILY_AUTOPILOT_ALLOW_TESTER_RUN", "0") == "1")
    parser.add_argument("--skip-polymarket", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    return parser.parse_args()


def mac_mt5_files_dir() -> Path:
    return Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"


def resolve_runtime_dir(repo_root: Path, configured: str) -> Path:
    candidate = Path(configured).expanduser() if configured else repo_root / "Dashboard"
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    source_mode = os.environ.get("QG_MAC_RUNTIME_SOURCE", "auto").strip().lower()
    mac_files = mac_mt5_files_dir()
    if os.uname().sysname == "Darwin" and mac_files.exists():
        normalized = str(candidate).replace("\\", "/")
        if source_mode == "mt5" or (source_mode == "auto" and "/runtime/mac_import/mt5_files_snapshot" in normalized):
            return mac_files
    return candidate


def resolve_dashboard_dir(repo_root: Path, configured: str) -> Path:
    candidate = Path(configured).expanduser() if configured else repo_root / "Dashboard"
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if "/runtime/mac_import/dashboard_runtime_snapshot" in str(candidate).replace("\\", "/"):
        return repo_root / "Dashboard"
    return candidate


def append_csv(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        existing_header = rows[0] if rows else []
        if existing_header != fieldnames:
            migrated_rows: list[dict[str, Any]] = []
            for values in rows[1:]:
                source_header = fieldnames if len(values) == len(fieldnames) else existing_header
                migrated_rows.append(dict(zip(source_header, values)))
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for existing_row in migrated_rows:
                    writer.writerow({key: existing_row.get(key, "") for key in fieldnames})
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_step(
    name: str,
    command: list[str],
    cwd: Path,
    timeout: int = 900,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if env_overrides:
        env.update(env_overrides)
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        status = "OK" if result.returncode == 0 else "ERROR"
        return {
            "name": name,
            "status": status,
            "exitCode": result.returncode,
            "startedAtIso": started.isoformat(),
            "finishedAtIso": datetime.now(timezone.utc).isoformat(),
            "stdoutTail": result.stdout.strip()[-1600:],
            "stderrTail": result.stderr.strip()[-1600:],
        }
    except subprocess.TimeoutExpired as error:
        return {
            "name": name,
            "status": "TIMEOUT",
            "exitCode": -1,
            "startedAtIso": started.isoformat(),
            "finishedAtIso": datetime.now(timezone.utc).isoformat(),
            "stdoutTail": (error.stdout or "")[-1600:] if isinstance(error.stdout, str) else "",
            "stderrTail": (error.stderr or "")[-1600:] if isinstance(error.stderr, str) else "",
        }


def tool(python_bin: str, script: str, *args: str) -> list[str]:
    return [python_bin, str(DEFAULT_REPO_ROOT / "tools" / script), *args]


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    runtime_dir = resolve_runtime_dir(repo_root, args.runtime_dir)
    dashboard_dir = resolve_dashboard_dir(repo_root, args.dashboard_dir)
    tester_root = Path(args.tester_root).expanduser() if args.tester_root else repo_root / "runtime/HFM_MT5_Tester_Isolated"
    hfm_root = Path(args.hfm_root).expanduser() if args.hfm_root else repo_root / "runtime/ParamLab_Tester_Sandbox/live_hfm_placeholder"
    if not tester_root.is_absolute():
        tester_root = repo_root / tester_root
    if not hfm_root.is_absolute():
        hfm_root = repo_root / hfm_root
    runtime_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc)
    steps: list[dict[str, Any]] = []
    common = ["--runtime-dir", str(runtime_dir)]
    repo_common = ["--repo-root", str(repo_root), "--runtime-dir", str(runtime_dir)]

    pipeline = [
        ("mt5_research_stats", tool(args.python_bin, "build_mt5_research_stats.py", *common)),
        ("collect_paramlab_results", tool(args.python_bin, "collect_param_lab_results.py", *repo_common)),
        ("watch_paramlab_reports", tool(args.python_bin, "watch_param_lab_reports.py", *repo_common)),
        ("paramlab_run_recovery", tool(args.python_bin, "build_param_lab_run_recovery.py", *repo_common)),
        ("governance_advisor_first_pass", tool(args.python_bin, "build_governance_advisor.py", *common)),
        ("optimizer_v2_plan", tool(args.python_bin, "build_optimizer_v2_plan.py", *repo_common)),
        ("param_optimization_plan", tool(args.python_bin, "build_param_optimization_plan.py", *repo_common, "--max-tasks", str(max(args.max_tasks, 8)))),
        ("strategy_version_registry", tool(args.python_bin, "build_strategy_version_registry.py", *repo_common)),
        ("version_promotion_gate", tool(args.python_bin, "build_version_promotion_gate.py", *common)),
        ("paramlab_auto_scheduler", tool(args.python_bin, "build_param_lab_auto_scheduler.py", *repo_common, "--max-tasks", str(max(args.max_tasks, 1)))),
    ]
    for name, command in pipeline:
        steps.append(run_step(name, command, repo_root))

    if not args.skip_polymarket:
        mac_files = mac_mt5_files_dir()
        polymarket_source = "mt5" if runtime_dir == mac_files else "local"
        steps.append(run_step(
            "polymarket_readonly_cycle",
            ["bash", "tools/run_mac_polymarket_readonly_cycle.sh"],
            repo_root,
            timeout=1200,
            env_overrides={
                "QG_RUNTIME_DIR": str(runtime_dir),
                "QG_MT5_FILES_DIR": str(runtime_dir),
                "QG_DASHBOARD_FILES_DIR": str(dashboard_dir),
                "QG_MAC_RUNTIME_SOURCE": polymarket_source,
            },
        ))

    if args.allow_tester_run:
        steps.append(run_step(
            "create_auto_tester_lock",
            tool(
                args.python_bin,
                "create_paramlab_auto_tester_lock.py",
                "--runtime-dir",
                str(runtime_dir),
                "--hfm-root",
                str(tester_root),
                "--ttl-minutes",
                "90",
                "--max-tasks",
                str(args.max_tasks),
                "--source",
                "daily_autopilot",
            ),
            repo_root,
        ))

    eval_command = tool(
        args.python_bin,
        "run_param_lab_auto_tester_window.py",
        "--repo-root",
        str(repo_root),
        "--runtime-dir",
        str(runtime_dir),
        "--hfm-root",
        str(hfm_root),
        "--tester-root",
        str(tester_root),
        "--max-tasks",
        str(args.max_tasks),
    )
    steps.append(run_step("auto_tester_evaluate", eval_command, repo_root))
    auto_tester = read_json(runtime_dir / "QuantGod_AutoTesterWindow.json")
    can_run = bool(auto_tester.get("summary", {}).get("canRunTerminal"))
    run_attempted = False
    if args.allow_tester_run and can_run:
        run_attempted = True
        run_command = [
            *eval_command,
            "--run-terminal",
            "--authorized-strategy-tester",
            "--continuous-watch",
        ]
        steps.append(run_step("auto_tester_guarded_run", run_command, repo_root, timeout=2400))
        steps.append(run_step("watch_paramlab_reports_after_run", tool(args.python_bin, "watch_param_lab_reports.py", *repo_common), repo_root))
        steps.append(run_step("version_promotion_gate_after_run", tool(args.python_bin, "build_version_promotion_gate.py", *common), repo_root))
        steps.append(run_step("governance_advisor_after_run", tool(args.python_bin, "build_governance_advisor.py", *common), repo_root))

    steps.append(run_step("daily_review", tool(args.python_bin, "build_daily_review.py", *common, "--max-actions", str(max(args.max_tasks, 1))), repo_root))
    daily_review = read_json(runtime_dir / "QuantGod_DailyReview.json")

    status = "OK" if all(step["status"] == "OK" for step in steps) else "PARTIAL"
    payload = {
        "schemaVersion": 1,
        "mode": "QUANTGOD_DAILY_AUTOPILOT_SAFE_LOOP",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "startedAtIso": started.isoformat(),
        "runtimeDir": str(runtime_dir),
        "dashboardDir": str(dashboard_dir),
        "allowTesterRun": bool(args.allow_tester_run),
        "testerRunAttempted": run_attempted,
        "status": status,
        "safety": {
            "mutatesMt5": False,
            "orderSendAllowed": False,
            "walletWriteAllowed": False,
            "livePresetMutationAllowed": False,
            "autoApplyLivePromotion": False,
        },
        "steps": steps,
        "dailyReviewSummary": daily_review.get("summary", {}),
        "codexReview": daily_review.get("codexReview", {}),
        "promotionRecommendations": daily_review.get("promotionRecommendations", []),
        "nextActions": daily_review.get("nextActions", []),
    }
    output = runtime_dir / DEFAULT_AUTOPILOT_NAME
    ledger = runtime_dir / DEFAULT_AUTOPILOT_LEDGER
    write_json(output, payload)
    append_csv(
        ledger,
        {
            "GeneratedAtIso": payload["generatedAtIso"],
            "Status": status,
            "StepCount": len(steps),
            "ErrorCount": sum(1 for step in steps if step["status"] != "OK"),
            "AllowTesterRun": str(bool(args.allow_tester_run)).lower(),
            "TesterRunAttempted": str(run_attempted).lower(),
            "DailyReviewDateJst": daily_review.get("summary", {}).get("dailyReviewDateJst", ""),
            "DailyParamActions": daily_review.get("summary", {}).get("paramActionCount", ""),
            "DailyParamWaitWindow": daily_review.get("summary", {}).get("paramWaitWindowCount", ""),
            "TodayTodoStatus": daily_review.get("summary", {}).get("todayTodoStatus", ""),
            "NextTesterWindowLabel": daily_review.get("summary", {}).get("nextTesterWindowLabel", ""),
            "PromotionReviewCount": daily_review.get("summary", {}).get("promotionReviewCount", ""),
            "CodexReviewRequired": str(bool(daily_review.get("codexReview", {}).get("required"))).lower(),
        },
        [
            "GeneratedAtIso",
            "Status",
            "StepCount",
            "ErrorCount",
            "AllowTesterRun",
            "TesterRunAttempted",
            "DailyReviewDateJst",
            "DailyParamActions",
            "DailyParamWaitWindow",
            "TodayTodoStatus",
            "NextTesterWindowLabel",
            "PromotionReviewCount",
            "CodexReviewRequired",
        ],
    )
    print(
        "DAILY_AUTOPILOT "
        f"status={status} steps={len(steps)} errors={sum(1 for step in steps if step['status'] != 'OK')} "
        f"testerRunAttempted={run_attempted} output={output}"
    )
    return payload


def main() -> int:
    args = parse_args()
    if not args.loop:
        args.once = True
    while True:
        run_cycle(args)
        if args.once:
            return 0
        time.sleep(max(60.0, float(args.interval_minutes) * 60.0))


if __name__ == "__main__":
    raise SystemExit(main())
