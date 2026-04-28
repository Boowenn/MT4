#!/usr/bin/env python3
"""Build QuantGod Optimizer V2 proposals from registered strategy versions.

Optimizer V2 is a no-trade, tester-only evolution planner. It adapts the
QuantDinger ideas of structured parameter evolution and multi-factor scoring to
QuantGod's local ledger workflow. It writes proposals, not live configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
REGISTRY_NAME = "QuantGod_StrategyVersionRegistry.json"
PARAM_PLAN_NAME = "QuantGod_ParamOptimizationPlan.json"
PARAM_STATUS_NAME = "QuantGod_ParamLabStatus.json"
PARAM_RESULTS_NAME = "QuantGod_ParamLabResults.json"
GOVERNANCE_NAME = "QuantGod_GovernanceAdvisor.json"
OUTPUT_NAME = "QuantGod_OptimizerV2Plan.json"
LEDGER_NAME = "QuantGod_OptimizerV2Ledger.csv"


PARAMETER_SPACES: dict[str, list[dict[str, Any]]] = {
    "MA_Cross": [
        {
            "name": "ma_control_tight_exit",
            "objective": "Keep the live MA baseline but test a tighter continuation window.",
            "params": {"PilotCrossLookbackBars": 5, "PilotContinuationLookbackBars": 18, "PilotATRMulitplierSL": 1.8},
        },
        {
            "name": "ma_slower_confirmation",
            "objective": "Reduce whipsaws by demanding a longer continuation lookback.",
            "params": {"PilotCrossLookbackBars": 8, "PilotContinuationLookbackBars": 30, "PilotATRMulitplierSL": 2.0},
        },
    ],
    "RSI_Reversal": [
        {
            "name": "rsi_extreme_crossback_v2",
            "objective": "Keep RSI as live route but reduce early reversal entries.",
            "params": {
                "PilotRsiPeriod": 2,
                "PilotRsiOverbought": 85,
                "PilotRsiOversold": 15,
                "PilotRsiBandTolerancePct": 0.006,
                "PilotRsiATRMultiplierSL": 1.35,
            },
        },
        {
            "name": "rsi_ultra_extreme_guard",
            "objective": "Probe whether even stronger H1 extremes improve drawdown control.",
            "params": {
                "PilotRsiPeriod": 2,
                "PilotRsiOverbought": 88,
                "PilotRsiOversold": 12,
                "PilotRsiBandTolerancePct": 0.004,
                "PilotRsiATRMultiplierSL": 1.25,
            },
        },
        {
            "name": "rsi_smooth_retest",
            "objective": "Smooth RSI slightly while keeping strict zones.",
            "params": {
                "PilotRsiPeriod": 3,
                "PilotRsiOverbought": 82,
                "PilotRsiOversold": 18,
                "PilotRsiBandTolerancePct": 0.006,
                "PilotRsiATRMultiplierSL": 1.45,
            },
        },
    ],
    "BB_Triple": [
        {
            "name": "bb_outer_band_strict_v2",
            "objective": "Demand wider band touch and stronger RSI confirmation.",
            "params": {
                "PilotBBPeriod": 20,
                "PilotBBDeviation": 2.25,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 70,
                "PilotBBRsiOversold": 30,
            },
        },
        {
            "name": "bb_slow_regime_filter",
            "objective": "Slow the band and keep edge-only confirmation for choppy H1 regimes.",
            "params": {
                "PilotBBPeriod": 24,
                "PilotBBDeviation": 2.1,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 68,
                "PilotBBRsiOversold": 32,
            },
        },
        {
            "name": "bb_deep_touch_only",
            "objective": "Test fewer but cleaner band extremes.",
            "params": {
                "PilotBBPeriod": 24,
                "PilotBBDeviation": 2.4,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 72,
                "PilotBBRsiOversold": 28,
            },
        },
    ],
    "MACD_Divergence": [
        {
            "name": "macd_fast_momentum_turn_v2",
            "objective": "React faster to momentum turns while MACD remains simulation-only.",
            "params": {"PilotMacdFast": 8, "PilotMacdSlow": 21, "PilotMacdSignal": 5, "PilotMacdLookback": 18},
        },
        {
            "name": "macd_balanced_turn",
            "objective": "Use a moderate MACD speed to reduce false early turns.",
            "params": {"PilotMacdFast": 10, "PilotMacdSlow": 26, "PilotMacdSignal": 7, "PilotMacdLookback": 24},
        },
        {
            "name": "macd_slow_quality_filter",
            "objective": "Filter noise with slower confirmation and larger lookback.",
            "params": {"PilotMacdFast": 12, "PilotMacdSlow": 34, "PilotMacdSignal": 9, "PilotMacdLookback": 30},
        },
    ],
    "SR_Breakout": [
        {
            "name": "sr_strict_structure_v2",
            "objective": "Require a longer structure window and wider break.",
            "params": {"PilotSRLookback": 48, "PilotSRBreakPips": 3.5},
        },
        {
            "name": "sr_very_strict_break",
            "objective": "Test whether rare clean breaks outperform noisy M15 breakouts.",
            "params": {"PilotSRLookback": 64, "PilotSRBreakPips": 4.0},
        },
        {
            "name": "sr_mid_retest_filter",
            "objective": "Balance sample speed and false-break filtering.",
            "params": {"PilotSRLookback": 32, "PilotSRBreakPips": 3.0},
        },
    ],
}


ROUTE_SYMBOLS: dict[str, list[str]] = {
    "MA_Cross": ["EURUSDc", "USDJPYc"],
    "RSI_Reversal": ["USDJPYc"],
    "BB_Triple": ["EURUSDc", "USDJPYc"],
    "MACD_Divergence": ["EURUSDc", "USDJPYc"],
    "SR_Breakout": ["EURUSDc", "USDJPYc"],
}


ROUTE_TIMEFRAMES = {
    "MA_Cross": "M15",
    "RSI_Reversal": "H1",
    "BB_Triple": "H1",
    "MACD_Divergence": "H1",
    "SR_Breakout": "M15",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod Optimizer V2 tester-only proposals.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--max-proposals-per-route", type=int, default=3)
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
            writer.writerow({field: row.get(field, "") for field in fieldnames})


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


def stable_hash(payload: Any, length: int = 10) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def parameter_summary(params: dict[str, Any]) -> str:
    return ", ".join(
        f"{key.replace('Pilot', '').replace('Mulitplier', 'Mult').replace('Multiplier', 'Mult')}={normalize_param_value(value)}"
        for key, value in params.items()
    )


def registry_by_route(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("routes")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("routeKey", "")): row for row in rows if isinstance(row, dict)}


def advisor_by_route(advisor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = advisor.get("routeDecisions")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("strategy") or row.get("key") or ""): row for row in rows if isinstance(row, dict)}


def top_result_by_route(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    top = results.get("topByRoute")
    return top if isinstance(top, dict) else {}


def status_by_candidate(status_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for batch in status_doc.get("batches") or []:
        tasks = batch.get("tasks") if isinstance(batch, dict) else []
        for task in tasks or []:
            if isinstance(task, dict) and task.get("candidateId"):
                result[str(task["candidateId"])] = task
    return result


def route_result_state(route_result: dict[str, Any]) -> str:
    grade = str(route_result.get("grade") or "").upper()
    status = str(route_result.get("status") or route_result.get("resultStatus") or "").upper()
    if grade in {"A", "B", "C", "D"}:
        return "SCORED"
    if grade == "PENDING_REPORT" or status in {"PENDING_REPORT", "REPORT_MISSING", "REPORT_MISSING_AFTER_RUN"}:
        return "WAITING_REPORT"
    return "NOT_RUN"


def score_proposal(
    route_key: str,
    route_version: dict[str, Any],
    advisor_route: dict[str, Any],
    route_result: dict[str, Any],
    template: dict[str, Any],
) -> tuple[float, list[str], str]:
    evidence = route_version.get("evidence") or {}
    live_forward = evidence.get("liveForward") if isinstance(evidence.get("liveForward"), dict) else {}
    candidate_samples = evidence.get("candidateSamples") if isinstance(evidence.get("candidateSamples"), dict) else {}
    action = str(evidence.get("governanceAction") or advisor_route.get("recommendedAction") or "")
    result_metrics = route_result.get("metrics") if isinstance(route_result.get("metrics"), dict) else {}
    result_state = route_result_state(route_result)
    blockers: list[str] = []
    score = 50.0

    live_pf = as_float(live_forward.get("profitFactor"))
    if live_pf is not None:
        score += max(min(live_pf - 1.0, 1.5), -1.0) * 18.0
        if live_pf < 1.0:
            blockers.append("live_pf_lt_1")
    live_closed = as_int(live_forward.get("closedTrades"))
    score += min(live_closed, 50) * 0.2

    candidate_rows = as_int(candidate_samples.get("horizonRows") or candidate_samples.get("ledgerRows"))
    candidate_win = as_float(candidate_samples.get("winRatePct"))
    candidate_avg = as_float(candidate_samples.get("avgSignedPips"))
    score += min(candidate_rows, 80) * 0.18
    if candidate_win is not None:
        score += (candidate_win - 50.0) * 0.35
        if candidate_win < 45:
            blockers.append("candidate_win_lt_45")
    if candidate_avg is not None:
        score += max(min(candidate_avg, 10.0), -10.0) * 0.9
        if candidate_avg < 0:
            blockers.append("candidate_avg_negative")

    result_score = as_float(route_result.get("resultScore"))
    if result_score is not None:
        score += max(min(result_score - 50.0, 35.0), -35.0) * 0.25
    pf = as_float(result_metrics.get("profitFactor"))
    if pf is not None:
        score += max(min(pf - 1.0, 1.5), -1.0) * 12.0
        if pf < 1.0:
            blockers.append("param_pf_lt_1")
    net = as_float(result_metrics.get("netProfit"))
    if net is not None:
        score += max(min(net, 400.0), -400.0) * 0.025
        if net <= 0:
            blockers.append("param_net_not_positive")

    if result_state == "WAITING_REPORT":
        score -= 12.0
        blockers.append("waiting_existing_report")
    elif result_state == "NOT_RUN":
        score -= 3.0
    if action in {"RETUNE_SIM", "DEMOTE_REVIEW"}:
        score += 10.0
    elif action == "PROMOTION_REVIEW":
        score += 5.0
    elif action == "KEEP_LIVE_WATCH" and route_key in {"MA_Cross", "RSI_Reversal"}:
        score += 3.0

    if route_key in {"BB_Triple", "MACD_Divergence", "SR_Breakout"}:
        blockers.append("simulation_only_live_off")
    objective = "RETUNE_SIM" if action in {"RETUNE_SIM", "DEMOTE_REVIEW"} else "VERSION_IMPROVEMENT"
    if result_state == "WAITING_REPORT":
        objective = "RUN_PENDING_REPORT_FIRST"
    return round(score, 3), sorted(set(blockers)), objective


def tester_command(repo_root: Path, proposal_id: str) -> str:
    runner = repo_root / "tools" / "run_param_lab.py"
    scheduler_plan = DEFAULT_RUNTIME_DIR / "QuantGod_ParamLabAutoScheduler.json"
    return f'python "{runner}" --plan "{scheduler_plan}" --candidate-id "{proposal_id}"'


def build_proposal(
    repo_root: Path,
    route_key: str,
    route_version: dict[str, Any],
    advisor_route: dict[str, Any],
    route_result: dict[str, Any],
    template: dict[str, Any],
    symbol: str,
) -> dict[str, Any]:
    params = template.get("params") or {}
    parent_version_id = str(route_version.get("versionId") or "")
    proposal_hash = stable_hash({
        "routeKey": route_key,
        "parentVersionId": parent_version_id,
        "symbol": symbol,
        "params": params,
        "template": template.get("name", ""),
    })
    proposal_id = f"{route_key}_{symbol}_{template.get('name', 'candidate')}"
    candidate_version_id = f"{route_key}-optv2-{proposal_hash}"
    score, blockers, objective = score_proposal(route_key, route_version, advisor_route, route_result, template)
    return {
        "proposalId": proposal_id,
        "candidateVersionId": candidate_version_id,
        "parentVersionId": parent_version_id,
        "routeKey": route_key,
        "strategy": route_key,
        "symbol": symbol,
        "timeframe": ROUTE_TIMEFRAMES.get(route_key, ""),
        "template": template.get("name", ""),
        "objective": objective,
        "reason": template.get("objective", ""),
        "rankScore": score,
        "blockers": blockers,
        "parameterOverrides": params,
        "parameterSummary": parameter_summary(params),
        "testerOnlyCommand": tester_command(repo_root, proposal_id),
        "reportPathHint": f"archive/param_lab_runs/<run_id>/reports/{proposal_id}.htm",
        "livePresetMutation": False,
        "testerOnly": True,
        "nextStep": "Run existing pending report first." if objective == "RUN_PENDING_REPORT_FIRST" else "Queue for authorized Strategy Tester window, then parse reports into ParamLabResults.",
    }


def build_plan(repo_root: Path, runtime_dir: Path, max_per_route: int) -> dict[str, Any]:
    registry = read_json(runtime_dir / REGISTRY_NAME)
    advisor = read_json(runtime_dir / GOVERNANCE_NAME)
    results = read_json(runtime_dir / PARAM_RESULTS_NAME)
    status = read_json(runtime_dir / PARAM_STATUS_NAME)
    param_plan = read_json(runtime_dir / PARAM_PLAN_NAME)
    versions = registry_by_route(registry)
    advisor_routes = advisor_by_route(advisor)
    route_results = top_result_by_route(results)
    task_index = status_by_candidate(status)

    route_plans: list[dict[str, Any]] = []
    all_proposals: list[dict[str, Any]] = []
    for route_key, templates in PARAMETER_SPACES.items():
        route_version = versions.get(route_key, {})
        advisor_route = advisor_routes.get(route_key, {})
        route_result = route_results.get(route_key, {})
        symbols = ROUTE_SYMBOLS.get(route_key, ["EURUSDc"])
        proposals = []
        for template in templates:
            for symbol in symbols:
                proposals.append(build_proposal(repo_root, route_key, route_version, advisor_route, route_result, template, symbol))
        proposals.sort(key=lambda row: row["rankScore"], reverse=True)
        selected = proposals[:max(1, max_per_route)]
        for rank, proposal in enumerate(selected, start=1):
            proposal["routeRank"] = rank
            task = task_index.get(proposal["proposalId"], {})
            proposal["existingTaskStatus"] = task.get("status", "")
            proposal["existingReportPath"] = task.get("reportPath", "")
            all_proposals.append(proposal)

        result_state = route_result_state(route_result)
        action = str((route_version.get("evidence") or {}).get("governanceAction") or advisor_route.get("recommendedAction") or "")
        primary_action = "RUN_PENDING_REPORT_FIRST" if result_state == "WAITING_REPORT" else ("RETUNE_NEXT_GENERATION" if action in {"RETUNE_SIM", "DEMOTE_REVIEW"} else "PROPOSE_NEXT_CANDIDATES")
        route_plans.append({
            "routeKey": route_key,
            "strategy": route_key,
            "currentVersionId": route_version.get("versionId", ""),
            "currentStatus": route_version.get("status", "UNKNOWN"),
            "governanceAction": action,
            "primaryAction": primary_action,
            "resultState": result_state,
            "proposalCount": len(selected),
            "topProposalId": selected[0]["proposalId"] if selected else "",
            "topRankScore": selected[0]["rankScore"] if selected else 0,
            "proposals": selected,
        })

    all_proposals.sort(key=lambda row: row["rankScore"], reverse=True)
    waiting_report_count = sum(1 for row in all_proposals if row["objective"] == "RUN_PENDING_REPORT_FIRST")
    retune_count = sum(1 for plan in route_plans if plan["primaryAction"] == "RETUNE_NEXT_GENERATION")
    ready_count = sum(1 for row in all_proposals if row["objective"] != "RUN_PENDING_REPORT_FIRST")
    return {
        "schemaVersion": 1,
        "source": "QuantGod Optimizer V2",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "mode": "VERSION_AWARE_TESTER_ONLY_OPTIMIZER",
        "hardGuards": [
            "No live preset is mutated.",
            "No terminal is launched by this builder.",
            "No broker connection or OrderSend path is added.",
            "Optimizer V2 proposals are tester-only until Governance promotion review passes.",
        ],
        "summary": {
            "routeCount": len(route_plans),
            "proposalCount": len(all_proposals),
            "readyToQueueCount": ready_count,
            "waitingReportCount": waiting_report_count,
            "retuneRouteCount": retune_count,
            "topProposalId": all_proposals[0]["proposalId"] if all_proposals else "",
            "livePresetMutation": False,
        },
        "quantDingerMigration": {
            "borrowedIdeas": [
                "Structured parameter spaces drive candidate evolution.",
                "Scoring combines forward, candidate outcome, and backtest result signals.",
                "Every proposal points back to a parent strategy version.",
                "Runner output is queue-ready but remains tester-only.",
            ],
            "remainingWorthPorting": [
                "Streaming runner progress and DB experiment tables are deferred until QuantGod needs a backend service.",
                "LLM-generated parameter spaces are deferred; current spaces are deterministic and reviewable.",
            ],
        },
        "routePlans": route_plans,
        "rankedProposals": all_proposals,
        "sourceFiles": {
            "registry": REGISTRY_NAME,
            "governanceAdvisor": GOVERNANCE_NAME,
            "paramOptimizationPlan": PARAM_PLAN_NAME,
            "paramLabStatus": PARAM_STATUS_NAME,
            "paramLabResults": PARAM_RESULTS_NAME,
        },
        "nextOperatorSteps": [
            "Use rankedProposals as the next offline ParamLab queue, not as live preset changes.",
            "Run pending existing ParamLab reports before promoting any new generation.",
            "After reports parse into ParamLabResults, rebuild the registry and Optimizer V2 so promotion/demotion is version-aware.",
        ],
    }


def ledger_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for proposal in plan.get("rankedProposals") or []:
        rows.append({
            "GeneratedAtIso": plan.get("generatedAtIso", ""),
            "RouteKey": proposal.get("routeKey", ""),
            "ProposalId": proposal.get("proposalId", ""),
            "CandidateVersionId": proposal.get("candidateVersionId", ""),
            "ParentVersionId": proposal.get("parentVersionId", ""),
            "Objective": proposal.get("objective", ""),
            "RankScore": proposal.get("rankScore", ""),
            "Symbol": proposal.get("symbol", ""),
            "Timeframe": proposal.get("timeframe", ""),
            "ExistingTaskStatus": proposal.get("existingTaskStatus", ""),
            "Blockers": ";".join(proposal.get("blockers") or []),
            "ParameterSummary": proposal.get("parameterSummary", ""),
            "TesterOnlyCommand": proposal.get("testerOnlyCommand", ""),
        })
    return rows


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    plan = build_plan(repo_root, runtime_dir, max(1, args.max_proposals_per_route))
    write_json(output, plan)
    write_csv(ledger, ledger_rows(plan), [
        "GeneratedAtIso",
        "RouteKey",
        "ProposalId",
        "CandidateVersionId",
        "ParentVersionId",
        "Objective",
        "RankScore",
        "Symbol",
        "Timeframe",
        "ExistingTaskStatus",
        "Blockers",
        "ParameterSummary",
        "TesterOnlyCommand",
    ])
    print(f"Wrote {output}")
    print(f"Wrote {ledger}")
    print(
        f"Routes: {plan['summary']['routeCount']} | proposals: "
        f"{plan['summary']['proposalCount']} | top: {plan['summary']['topProposalId']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
