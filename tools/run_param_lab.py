#!/usr/bin/env python3
"""Prepare and optionally run QuantGod ParamLab Strategy Tester tasks.

ParamLab is the offline runner for QuantGod_ParamOptimizationPlan.json. It
materializes tester-only presets and MT5 tester configs for ranked RSI/BB/MACD/SR
parameter candidates, records the run status, and can parse tester reports. It
does not mutate the HFM live preset and does not send orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from auto_tester_window_guard import (
    LOCK_NAME,
    evaluate_execution_gate,
    read_json as read_guard_json,
    validate_materialized_task,
    validate_tester_profile_matches,
)


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HFM_ROOT = Path(r"C:\Program Files\HFM Metatrader 5")
DEFAULT_RUNTIME_DIR = DEFAULT_HFM_ROOT / "MQL5" / "Files"
PLAN_NAME = "QuantGod_ParamOptimizationPlan.json"
STATUS_NAME = "QuantGod_ParamLabStatus.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare QuantGod ParamLab tester tasks.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--hfm-root", default=str(DEFAULT_HFM_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--plan", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--max-tasks", type=int, default=4)
    parser.add_argument("--route", action="append", default=[], help="Route key to include. Can be repeated.")
    parser.add_argument("--candidate-id", action="append", default=[], help="Exact candidate id to include.")
    parser.add_argument(
        "--rank-mode",
        choices=("route-balanced", "score"),
        default="route-balanced",
        help="Default picks the top task per route before filling by score.",
    )
    parser.add_argument("--from-date", default=(datetime.now() - timedelta(days=90)).strftime("%Y.%m.%d"))
    parser.add_argument("--to-date", default=datetime.now().strftime("%Y.%m.%d"))
    parser.add_argument("--login", default="186054398")
    parser.add_argument("--server", default="HFMarketsGlobal-Live12")
    parser.add_argument("--run-terminal", action="store_true", help="Launch MT5 Strategy Tester for selected tasks.")
    parser.add_argument(
        "--authorized-strategy-tester",
        action="store_true",
        help="Required with --run-terminal to confirm this is a controlled Strategy Tester run.",
    )
    parser.add_argument(
        "--allow-outside-window",
        action="store_true",
        help="Allow --run-terminal outside the regular weekend tester window only when the authorization lock allows it.",
    )
    parser.add_argument(
        "--auto-tester-lock",
        default="",
        help="Authorization lock JSON required for --run-terminal. Defaults to <runtime-dir>/QuantGod_AutoTesterWindow.lock.json.",
    )
    parser.add_argument(
        "--max-live-snapshot-age-minutes",
        type=int,
        default=30,
        help="Maximum age for QuantGod_Dashboard.json before --run-terminal is blocked.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
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


def normalize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def load_preset_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return read_text(path).splitlines()


def merge_preset_lines(base_lines: list[str], overrides: dict[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for line in base_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, tail = line.split("=", 1)
        if key in overrides:
            value = normalize_value(overrides[key])
            if "||" in tail:
                _, suffix = tail.split("||", 1)
                output.append(f"{key}={value}||{suffix}")
            else:
                output.append(f"{key}={value}")
            seen.add(key)
        else:
            output.append(line)
    for key in sorted(overrides):
        if key not in seen:
            output.append(f"{key}={normalize_value(overrides[key])}")
    return output


def write_ascii_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="ignore")


def timeframe_to_period(timeframe: str) -> str:
    value = str(timeframe or "").upper()
    if value in {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}:
        return value
    return "M15"


def tester_config_text(
    *,
    login: str,
    server: str,
    symbol: str,
    period: str,
    preset_name: str,
    from_date: str,
    to_date: str,
    report_path: Path,
) -> str:
    return f"""[Common]
Login={login}
Server={server}
KeepPrivate=1

[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=1
Account=0
Profile=0

[Tester]
Expert=QuantGod_MultiStrategy.ex5
ExpertParameters={preset_name}
Symbol={symbol}
Period={period}
Model=1
ExecutionMode=0
Optimization=0
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit=10000
Currency=USC
Leverage=1000
Report={report_path}
ReplaceReport=1
ShutdownTerminal=1
"""


def metric_from_report(text: str, labels: list[str]) -> float | None:
    for label in labels:
        escaped = re.escape(label)
        patterns = [
            rf"{escaped}\s*</[^>]+>\s*<[^>]+>\s*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?)",
            rf"{escaped}[^-+0-9]*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                raw = match.group(1).replace(" ", "").replace(",", "")
                try:
                    number = float(raw)
                    if math.isfinite(number):
                        return number
                except Exception:
                    pass
    return None


def parse_report(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        return {
            "reportExists": False,
            "parseStatus": "REPORT_MISSING",
            "closedTrades": None,
            "netProfit": None,
            "profitFactor": None,
            "winRate": None,
        }
    text = read_text(report_path)
    net_profit = metric_from_report(text, ["Total Net Profit", "Net Profit", "Total profit"])
    profit_factor = metric_from_report(text, ["Profit Factor"])
    total_trades = metric_from_report(text, ["Total Trades", "Trades"])
    win_rate = metric_from_report(text, ["Profit Trades (% of total)", "Win rate", "Winning trades"])
    return {
        "reportExists": True,
        "parseStatus": "PARSED_PARTIAL" if net_profit is not None or total_trades is not None else "REPORT_FOUND_UNPARSED",
        "closedTrades": total_trades,
        "netProfit": net_profit,
        "profitFactor": profit_factor,
        "winRate": win_rate,
    }


def sync_tester_profile(preset_path: Path, profile_path: Path) -> bool:
    if not preset_path.exists():
        return False
    values: dict[str, str] = {}
    for line in read_text(preset_path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith((";", "#")) and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key] = value.split("||", 1)[0]
    if not values:
        return False

    profile_lines = load_preset_lines(profile_path) or [
        "; generated by QuantGod ParamLab",
        "; this file contains input parameters for testing QuantGod_MultiStrategy expert advisor",
    ]
    output: list[str] = []
    seen: set[str] = set()
    for line in profile_lines:
        if "=" not in line or line.lstrip().startswith((";", "#")):
            output.append(line)
            continue
        key, tail = line.split("=", 1)
        if key in values:
            if "||" in tail:
                _, suffix = tail.split("||", 1)
                output.append(f"{key}={values[key]}||{suffix}")
            else:
                output.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key in sorted(values):
        if key not in seen:
            output.append(f"{key}={values[key]}")
    write_ascii_lines(profile_path, output)
    return True


def in_regular_tester_window(now_jst: datetime | None = None) -> bool:
    now = now_jst or datetime.now(timezone(timedelta(hours=9)))
    weekday = now.weekday()  # Monday=0
    minutes = now.hour * 60 + now.minute
    saturday_window = weekday == 5 and (7 * 60 + 10) <= minutes <= (9 * 60 + 30)
    sunday_window = weekday == 6 and (8 * 60) <= minutes <= (9 * 60 + 30)
    return saturday_window or sunday_window


def select_tasks(
    plan: dict[str, Any],
    max_tasks: int,
    routes: list[str],
    candidate_ids: list[str],
    rank_mode: str,
) -> list[dict[str, Any]]:
    tasks = plan.get("backtestTasks") if isinstance(plan.get("backtestTasks"), list) else []
    route_filter = {item.strip() for item in routes if item.strip()}
    id_filter = {item.strip() for item in candidate_ids if item.strip()}
    selected = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if route_filter and str(task.get("routeKey", "")) not in route_filter:
            continue
        if id_filter and str(task.get("candidateId", "")) not in id_filter:
            continue
        selected.append(task)
    selected.sort(key=lambda item: int(item.get("rank") or 9999))
    limit = max(1, max_tasks)
    if rank_mode == "score" or id_filter or route_filter:
        return selected[:limit]

    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in selected:
        by_route[str(task.get("routeKey") or "UNKNOWN")].append(task)

    route_balanced: list[dict[str, Any]] = []
    for route_key in sorted(by_route):
        by_route[route_key].sort(key=lambda item: int(item.get("rank") or 9999))
        route_balanced.append(by_route[route_key][0])
    used = {id(item) for item in route_balanced}
    for task in selected:
        if len(route_balanced) >= limit:
            break
        if id(task) not in used:
            route_balanced.append(task)
            used.add(id(task))
    route_balanced.sort(key=lambda item: int(item.get("rank") or 9999))
    return route_balanced[:limit]


def candidate_by_id(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for route_plan in plan.get("routePlans", []) if isinstance(plan.get("routePlans"), list) else []:
        if not isinstance(route_plan, dict):
            continue
        for candidate in route_plan.get("candidates", []) if isinstance(route_plan.get("candidates"), list) else []:
            if isinstance(candidate, dict) and candidate.get("candidateId"):
                result[str(candidate["candidateId"])] = candidate
    return result


def update_plan_with_run(plan: dict[str, Any], status: dict[str, Any], plan_path: Path) -> None:
    task_status = {str(task.get("candidateId")): task for task in status.get("tasks", []) if isinstance(task, dict)}
    for task in plan.get("backtestTasks", []) if isinstance(plan.get("backtestTasks"), list) else []:
        candidate_id = str(task.get("candidateId", ""))
        if candidate_id in task_status:
            result = task_status[candidate_id]
            task["status"] = result.get("status", task.get("status", ""))
            task["paramLabRunId"] = status.get("runId", "")
            task["configPath"] = result.get("configPath", "")
            task["reportPath"] = result.get("reportPath", "")
            task["presetPath"] = result.get("presetPath", "")
            task["hfmPresetPath"] = result.get("hfmPresetPath", "")
            task["metrics"] = result.get("metrics", {})
    plan["paramLabLatestRun"] = {
        "runId": status.get("runId", ""),
        "generatedAtIso": status.get("generatedAtIso", ""),
        "mode": status.get("mode", ""),
        "runTerminal": status.get("runTerminal", False),
        "selectedTaskCount": status.get("selectedTaskCount", 0),
        "summary": status.get("summary", {}),
    }
    write_json(plan_path, plan)


def build_runner_status(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root)
    hfm_root = Path(args.hfm_root)
    runtime_dir = Path(args.runtime_dir)
    plan_path = Path(args.plan) if args.plan else runtime_dir / PLAN_NAME
    output_path = Path(args.output) if args.output else runtime_dir / STATUS_NAME
    plan = read_json(plan_path)
    if not plan:
        raise FileNotFoundError(f"Param optimization plan not found or unreadable: {plan_path}")

    run_terminal_gate: dict[str, Any] = {}
    if args.run_terminal:
        if not args.authorized_strategy_tester:
            raise RuntimeError("--run-terminal requires --authorized-strategy-tester.")
        lock_path = Path(args.auto_tester_lock) if args.auto_tester_lock else runtime_dir / LOCK_NAME
        scheduler_doc = read_guard_json(plan_path)
        run_terminal_gate = evaluate_execution_gate(
            scheduler=scheduler_doc,
            runtime_dir=runtime_dir,
            hfm_root=hfm_root,
            repo_root=repo_root,
            lock_path=lock_path,
            max_tasks=args.max_tasks,
            allow_outside_window=args.allow_outside_window,
            expected_login=args.login,
            expected_server=args.server,
            max_live_snapshot_age_minutes=args.max_live_snapshot_age_minutes,
        )
        if not run_terminal_gate.get("canRunTerminal"):
            blockers = ", ".join(run_terminal_gate.get("blockers") or ["unknown_guard_blocker"])
            raise RuntimeError(f"--run-terminal blocked by AUTO_TESTER_WINDOW guard: {blockers}")

    terminal = hfm_root / "terminal64.exe"
    hfm_presets = hfm_root / "MQL5" / "Presets"
    hfm_tester_profiles = hfm_root / "MQL5" / "Profiles" / "Tester"
    hfm_experts = hfm_root / "MQL5" / "Experts"

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = repo_root / "archive" / "param-lab" / "runs" / run_id
    preset_dir = run_dir / "presets"
    config_dir = run_dir / "configs"
    report_dir = run_dir / "reports"
    for directory in (preset_dir, config_dir, report_dir, hfm_presets, hfm_tester_profiles):
        directory.mkdir(parents=True, exist_ok=True)

    source_synced = False
    binary_synced = False
    source_path = repo_root / "MQL5" / "Experts" / "QuantGod_MultiStrategy.mq5"
    binary_path = repo_root / "MQL5" / "Experts" / "QuantGod_MultiStrategy.ex5"
    if source_path.exists():
        hfm_experts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, hfm_experts / source_path.name)
        source_synced = True
    if binary_path.exists():
        hfm_experts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary_path, hfm_experts / binary_path.name)
        binary_synced = True

    candidates = candidate_by_id(plan)
    selected = select_tasks(plan, args.max_tasks, args.route, args.candidate_id, args.rank_mode)
    task_results: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []

    for task in selected:
        candidate_id = str(task.get("candidateId", ""))
        candidate = candidates.get(candidate_id, {})
        symbol = str(task.get("symbol") or candidate.get("symbol") or "")
        route_key = str(task.get("routeKey") or candidate.get("routeKey") or "")
        timeframe = str(task.get("timeframe") or candidate.get("timeframe") or "M15")
        preset_name = str(task.get("presetName") or candidate.get("presetName") or f"QuantGod_MT5_ParamLab_{candidate_id}.set")
        base_preset = Path(str(candidate.get("basePreset") or repo_root / "MQL5" / "Presets" / f"QuantGod_MT5_HFM_Backtest_{symbol}.set"))
        overrides = task.get("presetOverrides") if isinstance(task.get("presetOverrides"), dict) else candidate.get("presetOverrides", {})
        if not isinstance(overrides, dict):
            overrides = {}

        local_preset = preset_dir / preset_name
        hfm_preset = hfm_presets / preset_name
        config_path = config_dir / f"{candidate_id}.ini"
        symbol_report_dir = report_dir / symbol
        symbol_report_dir.mkdir(parents=True, exist_ok=True)
        report_path = symbol_report_dir / f"{candidate_id}.html"

        merged_lines = merge_preset_lines(load_preset_lines(base_preset), overrides)
        write_ascii_lines(local_preset, merged_lines)
        shutil.copy2(local_preset, hfm_preset)
        config_path.write_text(
            tester_config_text(
                login=args.login,
                server=args.server,
                symbol=symbol,
                period=timeframe_to_period(timeframe),
                preset_name=preset_name,
                from_date=args.from_date,
                to_date=args.to_date,
                report_path=report_path,
            ),
            encoding="ascii",
        )

        materialized_guard = validate_materialized_task(
            {
                "candidateId": candidate_id,
                "routeKey": route_key,
                "symbol": symbol,
                "timeframe": timeframe,
                "configPath": str(config_path),
                "presetPath": str(local_preset),
                "hfmPresetPath": str(hfm_preset),
            },
            repo_root=repo_root,
            hfm_root=hfm_root,
        )
        if not materialized_guard.get("ok"):
            blockers = ", ".join(materialized_guard.get("blockers") or ["unknown_materialized_guard_blocker"])
            raise RuntimeError(f"Materialized tester task failed AUTO_TESTER_WINDOW guard for {candidate_id}: {blockers}")

        profile_synced = False
        terminal_exit_code: int | None = None
        runner_status = "CONFIG_READY"
        if args.run_terminal:
            if not terminal.exists():
                raise FileNotFoundError(f"HFM terminal not found: {terminal}")
            tester_profile = hfm_tester_profiles / "QuantGod_MultiStrategy.set"
            profile_synced = sync_tester_profile(hfm_preset, tester_profile)
            profile_guard = validate_tester_profile_matches(tester_profile, hfm_preset)
            if not profile_guard.get("ok"):
                blockers = ", ".join(profile_guard.get("blockers") or ["unknown_profile_guard_blocker"])
                raise RuntimeError(f"Tester profile failed AUTO_TESTER_WINDOW guard for {candidate_id}: {blockers}")
            if profile_synced:
                shutil.copy2(tester_profile, hfm_tester_profiles / preset_name)
            process = subprocess.run([str(terminal), f"/config:{config_path}"], check=False)
            terminal_exit_code = process.returncode
            runner_status = "RUN_ATTEMPTED"

        metrics = parse_report(report_path)
        if metrics["reportExists"] and metrics["parseStatus"].startswith("PARSED"):
            runner_status = metrics["parseStatus"]
        elif args.run_terminal and not metrics["reportExists"]:
            runner_status = "REPORT_MISSING_AFTER_RUN"

        result = {
            "rank": task.get("rank"),
            "candidateId": candidate_id,
            "routeKey": route_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "variant": candidate.get("variant", ""),
            "score": candidate.get("score", task.get("score")),
            "status": runner_status,
            "configPath": str(config_path),
            "reportPath": str(report_path),
            "presetPath": str(local_preset),
            "hfmPresetPath": str(hfm_preset),
            "testerProfileSynced": profile_synced,
            "terminalExitCode": terminal_exit_code,
            "metrics": metrics,
            "materializedGuard": materialized_guard,
            "livePresetMutation": False,
        }
        task_results.append(result)
        ledger_rows.append({
            "RunId": run_id,
            "GeneratedAtIso": datetime.now(timezone.utc).isoformat(),
            "CandidateId": candidate_id,
            "RouteKey": route_key,
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Variant": candidate.get("variant", ""),
            "Status": runner_status,
            "ClosedTrades": metrics.get("closedTrades"),
            "NetProfit": metrics.get("netProfit"),
            "ProfitFactor": metrics.get("profitFactor"),
            "WinRate": metrics.get("winRate"),
            "ConfigPath": str(config_path),
            "ReportPath": str(report_path),
        })

    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in task_results:
        by_route[str(task.get("routeKey", ""))].append(task)
    top_by_route = {}
    for route_key, rows in by_route.items():
        rows.sort(key=lambda item: int(item.get("rank") or 9999))
        top_by_route[route_key] = rows[0]

    summary = {
        "configReadyCount": sum(1 for item in task_results if item["status"] == "CONFIG_READY"),
        "runAttemptedCount": sum(1 for item in task_results if item["terminalExitCode"] is not None),
        "reportParsedCount": sum(1 for item in task_results if item["metrics"].get("reportExists")),
        "selectedTaskCount": len(task_results),
        "sourceSynced": source_synced,
        "binarySynced": binary_synced,
    }
    status = {
        "schemaVersion": 1,
        "source": "QuantGod ParamLab controlled runner",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "mode": "STRATEGY_TESTER_RUN" if args.run_terminal else "CONFIG_ONLY",
        "runTerminal": bool(args.run_terminal),
        "runtimeDir": str(runtime_dir),
        "planPath": str(plan_path),
        "archiveDir": str(run_dir),
        "selectedTaskCount": len(task_results),
        "rankMode": args.rank_mode,
        "summary": summary,
        "autoTesterWindowGate": run_terminal_gate,
        "topByRoute": top_by_route,
        "tasks": task_results,
        "hardGuards": [
            "No HFM live preset was modified.",
            "No broker live order path is used by this runner.",
            "Generated presets are ParamLab tester-only files.",
            "Strategy Tester launch requires --run-terminal and --authorized-strategy-tester.",
            "Regular unattended tester runs are blocked outside the weekend tester window.",
            "Run-terminal is blocked unless the live dashboard confirms zero open live positions, no margin in use, and compatible live account/server/session state.",
        ],
        "nextOperatorSteps": [
            "Review CONFIG_READY tasks in Governance Advisor before any Strategy Tester launch.",
            "Run with --run-terminal only in the authorized tester window or explicitly authorized session.",
            "Use parsed ParamLab results as evidence only; do not write them into the live preset automatically.",
        ],
    }
    write_json(output_path, status)
    write_json(run_dir / STATUS_NAME, status)
    write_csv(
        run_dir / "QuantGod_ParamLabLedger.csv",
        ledger_rows,
        [
            "RunId",
            "GeneratedAtIso",
            "CandidateId",
            "RouteKey",
            "Symbol",
            "Timeframe",
            "Variant",
            "Status",
            "ClosedTrades",
            "NetProfit",
            "ProfitFactor",
            "WinRate",
            "ConfigPath",
            "ReportPath",
        ],
    )
    update_plan_with_run(plan, status, plan_path)
    return status


def main() -> int:
    args = parse_args()
    try:
        status = build_runner_status(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Wrote {status['runtimeDir']}\\{STATUS_NAME}")
    print(f"ParamLab {status['mode']}: {status['selectedTaskCount']} task(s), archive {status['archiveDir']}")
    print(
        "Summary: "
        f"configReady={status['summary']['configReadyCount']} "
        f"runAttempted={status['summary']['runAttemptedCount']} "
        f"reportParsed={status['summary']['reportParsedCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
