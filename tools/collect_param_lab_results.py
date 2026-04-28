#!/usr/bin/env python3
"""Collect ParamLab Strategy Tester results and feed scores back into plans.

This parser scans ParamLab run archives, parses any completed MT5 Strategy
Tester reports, writes a unified result ledger, and annotates
QuantGod_ParamOptimizationPlan.json. It is file-only: no terminal launch, no
live preset mutation, no broker connection, and no order path changes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
PLAN_NAME = "QuantGod_ParamOptimizationPlan.json"
RESULTS_NAME = "QuantGod_ParamLabResults.json"
LEDGER_NAME = "QuantGod_ParamLabResultsLedger.csv"
STATUS_NAME = "QuantGod_ParamLabStatus.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect QuantGod ParamLab tester results.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--archive-root", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--min-trades", type=int, default=10)
    return parser.parse_args()


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


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value)
    return int(number) if number is not None else default


def clean_number(raw: str) -> float | None:
    value = raw.replace(" ", "").replace(",", "").replace("%", "")
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return None


def metric_from_report(text: str, labels: list[str]) -> float | None:
    for label in labels:
        escaped = re.escape(label)
        patterns = [
            rf"{escaped}\s*</[^>]+>\s*<[^>]+>\s*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?\s*%?)",
            rf"{escaped}[^-+0-9]*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?\s*%?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                number = clean_number(match.group(1))
                if number is not None:
                    return number
    return None


def parse_report(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        return {
            "reportExists": False,
            "parseStatus": "PENDING_REPORT",
            "closedTrades": None,
            "netProfit": None,
            "profitFactor": None,
            "winRate": None,
            "maxDrawdown": None,
            "relativeDrawdownPct": None,
        }
    text = read_text(report_path)
    net_profit = metric_from_report(text, ["Total Net Profit", "Net Profit", "Total profit"])
    profit_factor = metric_from_report(text, ["Profit Factor"])
    total_trades = metric_from_report(text, ["Total Trades", "Trades"])
    win_rate = metric_from_report(text, ["Profit Trades (% of total)", "Win rate", "Winning trades"])
    max_drawdown = metric_from_report(text, ["Maximal drawdown", "Maximal Drawdown", "Balance Drawdown Maximal"])
    relative_drawdown = metric_from_report(text, ["Relative Drawdown", "Balance Drawdown Relative"])
    parsed = any(value is not None for value in (net_profit, profit_factor, total_trades, win_rate, max_drawdown, relative_drawdown))
    return {
        "reportExists": True,
        "parseStatus": "PARSED_PARTIAL" if parsed else "REPORT_FOUND_UNPARSED",
        "closedTrades": total_trades,
        "netProfit": net_profit,
        "profitFactor": profit_factor,
        "winRate": win_rate,
        "maxDrawdown": max_drawdown,
        "relativeDrawdownPct": relative_drawdown,
    }


def score_result(metrics: dict[str, Any], min_trades: int) -> tuple[float, str, str, list[str]]:
    if not metrics.get("reportExists"):
        return 0.0, "PENDING_REPORT", "WAIT_TESTER_REPORT", ["report_missing"]
    trades = as_int(metrics.get("closedTrades"))
    net = as_float(metrics.get("netProfit"), 0.0) or 0.0
    pf = as_float(metrics.get("profitFactor"))
    win_rate = as_float(metrics.get("winRate"))
    drawdown = as_float(metrics.get("maxDrawdown"))
    rel_dd = as_float(metrics.get("relativeDrawdownPct"))
    blockers: list[str] = []
    score = 50.0

    if trades < min_trades:
        blockers.append("trades_lt_min")
    score += min(trades, 100) * 0.18

    if pf is None:
        blockers.append("pf_missing")
    else:
        score += max(min(pf - 1.0, 2.0), -1.0) * 24.0
        if pf < 1.0:
            blockers.append("pf_lt_1")

    if win_rate is None:
        blockers.append("win_rate_missing")
    else:
        score += max(min(win_rate - 50.0, 25.0), -25.0) * 0.55
        if win_rate < 50.0:
            blockers.append("win_rate_lt_50")

    score += max(min(net, 500.0), -500.0) * 0.04
    if net <= 0:
        blockers.append("net_profit_not_positive")

    dd_penalty = 0.0
    if rel_dd is not None:
        dd_penalty += min(max(rel_dd, 0.0), 50.0) * 0.45
        if rel_dd > 20:
            blockers.append("relative_drawdown_gt_20")
    elif drawdown is not None:
        dd_penalty += min(max(drawdown, 0.0), 500.0) * 0.025
    else:
        blockers.append("drawdown_missing")
    score -= dd_penalty

    score = round(score, 3)
    if not blockers and score >= 75:
        return score, "A", "PROMOTION_REVIEW_READY", []
    if trades >= min_trades and pf is not None and pf >= 1.15 and net > 0 and score >= 62:
        return score, "B", "KEEP_TESTING", blockers
    if trades >= min_trades and (pf is not None and pf < 1.0 or net <= 0):
        return score, "D", "REJECT_OR_RETUNE", blockers
    return score, "C", "NEEDS_MORE_EVIDENCE", blockers


def load_param_lab_runs(archive_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not archive_root.exists():
        return runs
    for status_path in sorted(archive_root.glob(f"*/{STATUS_NAME}")):
        status = read_json(status_path)
        if status:
            status["_statusPath"] = str(status_path)
            runs.append(status)
    return runs


def result_from_task(run: dict[str, Any], task: dict[str, Any], min_trades: int) -> dict[str, Any]:
    report_path = Path(str(task.get("reportPath") or ""))
    metrics = parse_report(report_path)
    score, grade, readiness, blockers = score_result(metrics, min_trades)
    return {
        "runId": run.get("runId", ""),
        "runMode": run.get("mode", ""),
        "runGeneratedAtIso": run.get("generatedAtIso", ""),
        "candidateId": task.get("candidateId", ""),
        "routeKey": task.get("routeKey", ""),
        "symbol": task.get("symbol", ""),
        "timeframe": task.get("timeframe", ""),
        "variant": task.get("variant", ""),
        "configPath": task.get("configPath", ""),
        "reportPath": str(report_path),
        "presetPath": task.get("presetPath", ""),
        "status": metrics["parseStatus"],
        "resultScore": score,
        "grade": grade,
        "promotionReadiness": readiness,
        "blockers": blockers,
        "metrics": metrics,
    }


def best_results_by_candidate(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for result in results:
        candidate_id = str(result.get("candidateId") or "")
        if not candidate_id:
            continue
        previous = best.get(candidate_id)
        if previous is None or float(result.get("resultScore") or 0) > float(previous.get("resultScore") or 0):
            best[candidate_id] = result
    return best


def top_results_by_route(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    top: dict[str, dict[str, Any]] = {}
    for result in results:
        route_key = str(result.get("routeKey") or "")
        if not route_key:
            continue
        previous = top.get(route_key)
        if previous is None or float(result.get("resultScore") or 0) > float(previous.get("resultScore") or 0):
            top[route_key] = result
    return top


def annotate_plan(plan: dict[str, Any], results: list[dict[str, Any]], plan_path: Path) -> None:
    best_by_candidate = best_results_by_candidate(results)
    top_by_route = top_results_by_route(results)
    for route_plan in plan.get("routePlans", []) if isinstance(plan.get("routePlans"), list) else []:
        route_key = str(route_plan.get("routeKey") or "")
        route_plan["topResultCandidate"] = top_by_route.get(route_key, {})
        for candidate in route_plan.get("candidates", []) if isinstance(route_plan.get("candidates"), list) else []:
            candidate_id = str(candidate.get("candidateId") or "")
            if candidate_id in best_by_candidate:
                candidate["resultEvidence"] = best_by_candidate[candidate_id]
                candidate["resultScore"] = best_by_candidate[candidate_id].get("resultScore")
                candidate["resultGrade"] = best_by_candidate[candidate_id].get("grade")
                candidate["promotionReadiness"] = best_by_candidate[candidate_id].get("promotionReadiness")
        scored = [
            item for item in route_plan.get("candidates", [])
            if isinstance(item, dict) and item.get("resultEvidence")
        ]
        if scored:
            scored.sort(key=lambda item: float(item.get("resultScore") or 0), reverse=True)
            route_plan["topResultCandidate"] = scored[0].get("resultEvidence", {})

    for task in plan.get("backtestTasks", []) if isinstance(plan.get("backtestTasks"), list) else []:
        candidate_id = str(task.get("candidateId") or "")
        if candidate_id in best_by_candidate:
            evidence = best_by_candidate[candidate_id]
            task["resultStatus"] = evidence.get("status")
            task["resultScore"] = evidence.get("resultScore")
            task["resultGrade"] = evidence.get("grade")
            task["promotionReadiness"] = evidence.get("promotionReadiness")
            task["metrics"] = evidence.get("metrics", {})
    plan["paramLabResultsLatest"] = {
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "resultCount": len(results),
        "parsedReportCount": sum(1 for item in results if item.get("metrics", {}).get("reportExists")),
        "topByRoute": top_by_route,
    }
    write_json(plan_path, plan)


def build_results(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    archive_root = Path(args.archive_root) if args.archive_root else repo_root / "archive" / "param-lab" / "runs"
    plan_path = Path(args.plan) if args.plan else runtime_dir / PLAN_NAME
    output_path = Path(args.output) if args.output else runtime_dir / RESULTS_NAME
    ledger_path = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME

    runs = load_param_lab_runs(archive_root)
    results: list[dict[str, Any]] = []
    for run in runs:
        for task in run.get("tasks", []) if isinstance(run.get("tasks"), list) else []:
            if isinstance(task, dict):
                results.append(result_from_task(run, task, args.min_trades))
    results.sort(key=lambda item: (str(item.get("routeKey")), -float(item.get("resultScore") or 0), str(item.get("candidateId"))))
    top_by_route = top_results_by_route(results)
    parsed = sum(1 for item in results if item.get("metrics", {}).get("reportExists"))
    ready = sum(1 for item in results if item.get("promotionReadiness") == "PROMOTION_REVIEW_READY")
    output = {
        "schemaVersion": 1,
        "source": "QuantGod ParamLab results parser",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "archiveRoot": str(archive_root),
        "mode": "OFFLINE_RESULT_LEDGER_ONLY",
        "summary": {
            "runCount": len(runs),
            "resultCount": len(results),
            "parsedReportCount": parsed,
            "pendingReportCount": len(results) - parsed,
            "promotionReadyCount": ready,
            "topRouteCount": len(top_by_route),
        },
        "topByRoute": top_by_route,
        "results": results,
        "hardGuards": [
            "No terminal is launched by this parser.",
            "No live preset is mutated.",
            "No broker connection or OrderSend path is touched.",
            "Result scores are advisory evidence for Governance Advisor only.",
        ],
    }
    write_json(output_path, output)
    write_csv(
        ledger_path,
        [
            {
                "GeneratedAtIso": output["generatedAtIso"],
                "RunId": item.get("runId", ""),
                "CandidateId": item.get("candidateId", ""),
                "RouteKey": item.get("routeKey", ""),
                "Symbol": item.get("symbol", ""),
                "Timeframe": item.get("timeframe", ""),
                "Variant": item.get("variant", ""),
                "Status": item.get("status", ""),
                "ResultScore": item.get("resultScore", ""),
                "Grade": item.get("grade", ""),
                "PromotionReadiness": item.get("promotionReadiness", ""),
                "ClosedTrades": item.get("metrics", {}).get("closedTrades"),
                "ProfitFactor": item.get("metrics", {}).get("profitFactor"),
                "WinRate": item.get("metrics", {}).get("winRate"),
                "NetProfit": item.get("metrics", {}).get("netProfit"),
                "MaxDrawdown": item.get("metrics", {}).get("maxDrawdown"),
                "RelativeDrawdownPct": item.get("metrics", {}).get("relativeDrawdownPct"),
                "Blockers": "/".join(item.get("blockers") or []),
                "ReportPath": item.get("reportPath", ""),
            }
            for item in results
        ],
        [
            "GeneratedAtIso",
            "RunId",
            "CandidateId",
            "RouteKey",
            "Symbol",
            "Timeframe",
            "Variant",
            "Status",
            "ResultScore",
            "Grade",
            "PromotionReadiness",
            "ClosedTrades",
            "ProfitFactor",
            "WinRate",
            "NetProfit",
            "MaxDrawdown",
            "RelativeDrawdownPct",
            "Blockers",
            "ReportPath",
        ],
    )
    plan = read_json(plan_path)
    if plan:
        annotate_plan(plan, results, plan_path)
    return output


def main() -> int:
    args = parse_args()
    try:
        output = build_results(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    summary = output["summary"]
    print(f"Wrote {Path(args.output) if args.output else Path(args.runtime_dir) / RESULTS_NAME}")
    print(
        "ParamLab results: "
        f"runs={summary['runCount']} results={summary['resultCount']} "
        f"parsed={summary['parsedReportCount']} pending={summary['pendingReportCount']} "
        f"promotionReady={summary['promotionReadyCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
