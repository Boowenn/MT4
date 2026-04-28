#!/usr/bin/env python3
"""Build a config-only ParamLab Auto Scheduler queue.

The scheduler is the file-based bridge between Version Promotion Gate decisions
and the existing ParamLab runner. It selects the next tester-only batch from
WAIT_REPORT / RETUNE / WAIT_FORWARD evidence, writes a safe queue, and exposes
ParamLab-compatible backtestTasks. It never launches MT5 and never mutates the
HFM live preset.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")

GATE_NAME = "QuantGod_VersionPromotionGate.json"
OPTIMIZER_NAME = "QuantGod_OptimizerV2Plan.json"
PARAM_PLAN_NAME = "QuantGod_ParamOptimizationPlan.json"
PARAM_LAB_STATUS_NAME = "QuantGod_ParamLabStatus.json"
PARAM_LAB_RESULTS_NAME = "QuantGod_ParamLabResults.json"
OUTPUT_NAME = "QuantGod_ParamLabAutoScheduler.json"
LEDGER_NAME = "QuantGod_ParamLabAutoSchedulerLedger.csv"

CORE_ROUTE_KEYS = ["MA_Cross", "RSI_Reversal", "BB_Triple", "MACD_Divergence", "SR_Breakout"]
ROUTE_LABELS = {
    "MA_Cross": "MA_Cross M15+H1",
    "RSI_Reversal": "USDJPY RSI_Reversal H1",
    "BB_Triple": "BB_Triple H1",
    "MACD_Divergence": "MACD_Divergence H1",
    "SR_Breakout": "SR_Breakout M15",
}
ROUTE_STRATEGIES = {
    "MA_Cross": "MA_Cross",
    "RSI_Reversal": "RSI_Reversal",
    "BB_Triple": "BB_Triple",
    "MACD_Divergence": "MACD_Divergence",
    "SR_Breakout": "SR_Breakout",
}
ROUTE_DEFAULT_TIMEFRAMES = {
    "MA_Cross": "M15",
    "RSI_Reversal": "H1",
    "BB_Triple": "H1",
    "MACD_Divergence": "H1",
    "SR_Breakout": "M15",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod ParamLab Auto Scheduler queue.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--max-tasks", type=int, default=8)
    parser.add_argument("--max-per-route", type=int, default=2)
    parser.add_argument("--route", action="append", default=[], help="Optional route key filter. Can be repeated.")
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


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def as_int(value: Any, default: int = 9999) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_symbol(value: Any, fallback: str = "EURUSDc") -> str:
    text = str(value or "").strip()
    if text:
        return text
    return fallback


def variant_from_id(candidate_id: str, route_key: str) -> str:
    prefix = f"{route_key}_"
    value = candidate_id
    if value.startswith(prefix):
        value = value[len(prefix):]
    for symbol in ("EURUSDc_", "USDJPYc_"):
        value = value.replace(symbol, "")
    return value or "auto_scheduler"


def index_param_candidates(param_plan: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_route_symbol: dict[tuple[str, str], dict[str, Any]] = {}
    by_route: dict[str, dict[str, Any]] = {}
    for route_plan in safe_list(param_plan.get("routePlans")):
        route_plan = safe_dict(route_plan)
        for candidate in safe_list(route_plan.get("candidates")):
            candidate = safe_dict(candidate)
            candidate_id = str(candidate.get("candidateId") or "")
            route_key = str(candidate.get("routeKey") or route_plan.get("routeKey") or "")
            symbol = str(candidate.get("symbol") or "")
            if candidate_id:
                by_id[candidate_id] = candidate
            if route_key and symbol and (route_key, symbol) not in by_route_symbol:
                by_route_symbol[(route_key, symbol)] = candidate
            if route_key and route_key not in by_route:
                by_route[route_key] = candidate
    return by_id, by_route_symbol, by_route


def index_status_and_results(status: dict[str, Any], results: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    status_by_id: dict[str, dict[str, Any]] = {}
    result_by_id: dict[str, dict[str, Any]] = {}
    for task in safe_list(status.get("tasks")):
        task = safe_dict(task)
        candidate_id = str(task.get("candidateId") or "")
        if candidate_id:
            status_by_id[candidate_id] = task
    for row in safe_list(results.get("results")):
        row = safe_dict(row)
        candidate_id = str(row.get("candidateId") or "")
        if not candidate_id:
            continue
        existing = result_by_id.get(candidate_id)
        if not existing:
            result_by_id[candidate_id] = row
            continue
        existing_grade = str(existing.get("grade") or "")
        row_grade = str(row.get("grade") or "")
        if existing_grade == "PENDING_REPORT" and row_grade != "PENDING_REPORT":
            result_by_id[candidate_id] = row
    return status_by_id, result_by_id


def proposal_index(optimizer: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for proposal in safe_list(optimizer.get("rankedProposals")):
        proposal = safe_dict(proposal)
        proposal_id = str(proposal.get("proposalId") or proposal.get("candidateVersionId") or "")
        route_key = str(proposal.get("routeKey") or "")
        if not proposal_id or not route_key:
            continue
        by_id[proposal_id] = proposal
        by_route[route_key].append(proposal)
    for rows in by_route.values():
        rows.sort(key=lambda item: (-as_float(item.get("rankScore")), as_int(item.get("routeRank"))))
    return by_id, by_route


def command_for_candidate(repo_root: Path, runtime_dir: Path, candidate_id: str) -> str:
    runner = repo_root / "tools" / "run_param_lab.py"
    scheduler_plan = runtime_dir / OUTPUT_NAME
    return f'python "{runner}" --plan "{scheduler_plan}" --candidate-id "{candidate_id}"'


def fallback_overrides(route_key: str, symbol: str, params: dict[str, Any]) -> dict[str, Any]:
    route_flags = {
        "EnablePilotMA": "true" if route_key == "MA_Cross" else "false",
        "EnablePilotRsiH1Candidate": "true" if route_key == "RSI_Reversal" else "false",
        "EnablePilotRsiH1Live": "true" if route_key == "RSI_Reversal" else "false",
        "EnablePilotBBH1Candidate": "true" if route_key == "BB_Triple" else "false",
        "EnablePilotBBH1Live": "true" if route_key == "BB_Triple" else "false",
        "EnablePilotMacdH1Candidate": "true" if route_key == "MACD_Divergence" else "false",
        "EnablePilotMacdH1Live": "true" if route_key == "MACD_Divergence" else "false",
        "EnablePilotSRM15Candidate": "true" if route_key == "SR_Breakout" else "false",
        "EnablePilotSRM15Live": "true" if route_key == "SR_Breakout" else "false",
    }
    base = {
        "DashboardBuild": "QuantGod-v3.12-auto-scheduler-v1",
        "Watchlist": symbol,
        "PreferredSymbolSuffix": "AUTO",
        "ShadowMode": "false",
        "ReadOnlyMode": "false",
        "EnablePilotAutoTrading": "true",
        "PilotLotSize": "0.01",
        "PilotMaxTotalPositions": "1",
        "PilotMaxPositionsPerSymbol": "1",
        "PilotBlockManualPerSymbol": "false",
        "EnableManualSafetyGuard": "false",
        "PilotCloseOnKillSwitch": "true",
    }
    base.update(route_flags)
    base.update(params)
    return base


def candidate_from_proposal(
    *,
    repo_root: Path,
    proposal: dict[str, Any],
    template_by_route_symbol: dict[tuple[str, str], dict[str, Any]],
    template_by_route: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposalId") or proposal.get("candidateVersionId") or "")
    route_key = str(proposal.get("routeKey") or "")
    symbol = normalize_symbol(proposal.get("symbol"), "USDJPYc" if route_key == "RSI_Reversal" else "EURUSDc")
    template = template_by_route_symbol.get((route_key, symbol)) or template_by_route.get(route_key) or {}
    params = safe_dict(proposal.get("parameterOverrides"))
    template_overrides = dict(safe_dict(template.get("presetOverrides")))
    if template_overrides:
        template_overrides.update(params)
        overrides = template_overrides
    else:
        overrides = fallback_overrides(route_key, symbol, params)
    base_preset = str(template.get("basePreset") or repo_root / "MQL5" / "Presets" / f"QuantGod_MT5_HFM_Backtest_{symbol}.set")
    return {
        "candidateId": proposal_id,
        "routeKey": route_key,
        "strategy": str(proposal.get("strategy") or ROUTE_STRATEGIES.get(route_key) or route_key),
        "label": ROUTE_LABELS.get(route_key, route_key),
        "symbol": symbol,
        "timeframe": str(proposal.get("timeframe") or ROUTE_DEFAULT_TIMEFRAMES.get(route_key) or "M15"),
        "candidateRoute": str(template.get("candidateRoute") or ""),
        "variant": str(proposal.get("template") or variant_from_id(proposal_id, route_key)),
        "intent": str(proposal.get("nextStep") or "Auto-scheduled by Version Promotion Gate evidence."),
        "score": as_float(proposal.get("rankScore")),
        "basePreset": base_preset,
        "basePresetFound": Path(base_preset).exists(),
        "presetName": f"QuantGod_MT5_ParamLab_{proposal_id}.set",
        "presetOverrides": overrides,
        "parameterSummary": str(proposal.get("parameterSummary") or ""),
        "testerOnly": True,
        "livePresetMutation": False,
        "candidateVersionId": str(proposal.get("candidateVersionId") or ""),
        "parentVersionId": str(proposal.get("parentVersionId") or ""),
        "optimizerObjective": str(proposal.get("objective") or ""),
    }


def candidate_from_param_task(param_candidates: dict[str, dict[str, Any]], task: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(task.get("candidateId") or "")
    candidate = dict(param_candidates.get(candidate_id) or {})
    if candidate:
        return candidate
    route_key = str(task.get("routeKey") or "")
    symbol = normalize_symbol(task.get("symbol"), "EURUSDc")
    overrides = safe_dict(task.get("presetOverrides"))
    return {
        "candidateId": candidate_id,
        "routeKey": route_key,
        "strategy": str(task.get("strategy") or ROUTE_STRATEGIES.get(route_key) or route_key),
        "label": ROUTE_LABELS.get(route_key, route_key),
        "symbol": symbol,
        "timeframe": str(task.get("timeframe") or ROUTE_DEFAULT_TIMEFRAMES.get(route_key) or "M15"),
        "variant": variant_from_id(candidate_id, route_key),
        "score": as_float(task.get("score")),
        "basePreset": str(DEFAULT_REPO_ROOT / "MQL5" / "Presets" / f"QuantGod_MT5_HFM_Backtest_{symbol}.set"),
        "presetName": str(task.get("presetName") or f"QuantGod_MT5_ParamLab_{candidate_id}.set"),
        "presetOverrides": overrides,
        "parameterSummary": str(task.get("parameterSummary") or ""),
        "testerOnly": True,
        "livePresetMutation": False,
    }


def build_source_records(
    *,
    gate: dict[str, Any],
    optimizer_by_id: dict[str, dict[str, Any]],
    optimizer_by_route: dict[str, list[dict[str, Any]]],
    param_plan: dict[str, Any],
    route_filter: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    route_decision_by_route = {
        str(item.get("routeKey") or ""): safe_dict(item)
        for item in safe_list(gate.get("routeDecisions"))
        if isinstance(item, dict)
    }
    source_records: list[dict[str, Any]] = []
    route_plans: list[dict[str, Any]] = []

    for route_key in CORE_ROUTE_KEYS:
        if route_filter and route_key not in route_filter:
            continue
        route_decision = route_decision_by_route.get(route_key, {})
        current_decision = str(route_decision.get("currentDecision") or "UNKNOWN")
        proposals = optimizer_by_route.get(route_key, [])
        route_plans.append({
            "routeKey": route_key,
            "label": ROUTE_LABELS.get(route_key, route_key),
            "currentDecision": current_decision,
            "currentVersionId": str(route_decision.get("currentVersionId") or ""),
            "queueMode": "CONFIG_ONLY_QUEUE" if current_decision in {"RETUNE", "WAIT_REPORT"} else "OBSERVE_FORWARD",
            "reason": str(route_decision.get("currentReason") or ""),
            "blockers": route_decision.get("blockers") or [],
            "availableOptimizerProposalCount": len(proposals),
        })

    for decision in safe_list(gate.get("versionDecisions")):
        decision = safe_dict(decision)
        route_key = str(decision.get("routeKey") or "")
        if route_filter and route_key not in route_filter:
            continue
        if str(decision.get("decision") or "") != "WAIT_REPORT":
            continue
        candidate_id = str(decision.get("proposalId") or decision.get("candidateId") or "")
        if not candidate_id:
            continue
        route_decision = route_decision_by_route.get(route_key, {})
        source_records.append({
            "source": "VERSION_GATE_WAIT_REPORT",
            "candidateId": candidate_id,
            "proposalId": str(decision.get("proposalId") or ""),
            "routeKey": route_key,
            "sourceDecision": "WAIT_REPORT",
            "routeCurrentDecision": str(route_decision.get("currentDecision") or ""),
            "versionId": str(decision.get("versionId") or ""),
            "candidateVersionId": str(decision.get("candidateId") or ""),
            "parentVersionId": str(decision.get("parentVersionId") or ""),
            "status": str(decision.get("status") or ""),
            "reason": str(decision.get("reason") or "Gate needs a Strategy Tester report before scoring this version."),
            "blockers": decision.get("blockers") or [],
            "requiredEvidence": decision.get("requiredEvidence") or [],
            "priorityBase": 100.0,
        })

    for route_key, route_decision in route_decision_by_route.items():
        if route_filter and route_key not in route_filter:
            continue
        current_decision = str(route_decision.get("currentDecision") or "")
        if current_decision != "RETUNE":
            continue
        for proposal in optimizer_by_route.get(route_key, [])[:3]:
            proposal_id = str(proposal.get("proposalId") or "")
            if not proposal_id:
                continue
            source_records.append({
                "source": "ROUTE_GATE_RETUNE",
                "candidateId": proposal_id,
                "proposalId": proposal_id,
                "routeKey": route_key,
                "sourceDecision": "RETUNE",
                "routeCurrentDecision": current_decision,
                "versionId": str(route_decision.get("currentVersionId") or ""),
                "candidateVersionId": str(proposal.get("candidateVersionId") or ""),
                "parentVersionId": str(proposal.get("parentVersionId") or ""),
                "status": "SIM_CANDIDATE",
                "reason": str(route_decision.get("currentReason") or "Route is weak and should retune before promotion."),
                "blockers": route_decision.get("blockers") or [],
                "requiredEvidence": ["Run the retuned parameter proposal through ParamLab before promotion review."],
                "priorityBase": 85.0,
            })

    param_tasks = safe_list(param_plan.get("backtestTasks"))
    for task in param_tasks:
        task = safe_dict(task)
        route_key = str(task.get("routeKey") or "")
        if route_filter and route_key not in route_filter:
            continue
        route_decision = route_decision_by_route.get(route_key, {})
        if str(route_decision.get("currentDecision") or "") not in {"RETUNE", "WAIT_REPORT"}:
            continue
        candidate_id = str(task.get("candidateId") or "")
        if not candidate_id:
            continue
        source_records.append({
            "source": "LEGACY_PARAM_PLAN_TASK",
            "candidateId": candidate_id,
            "proposalId": "",
            "routeKey": route_key,
            "sourceDecision": str(route_decision.get("currentDecision") or "WAIT_REPORT"),
            "routeCurrentDecision": str(route_decision.get("currentDecision") or ""),
            "versionId": str(route_decision.get("currentVersionId") or ""),
            "candidateVersionId": candidate_id,
            "parentVersionId": "",
            "status": "PARAM_PLAN_TASK",
            "reason": "Legacy ParamOptimizationPlan task remains a valid control arm for this route.",
            "blockers": route_decision.get("blockers") or [],
            "requiredEvidence": ["Use this as a control-arm report against Optimizer V2 proposals."],
            "priorityBase": 70.0,
            "paramTask": task,
        })
    return source_records, route_plans


def score_source(record: dict[str, Any], proposal: dict[str, Any], status: dict[str, Any], result: dict[str, Any]) -> float:
    score = as_float(record.get("priorityBase"))
    score += as_float(proposal.get("rankScore")) * 0.1
    grade = str(result.get("grade") or "")
    task_status = str(status.get("status") or "")
    if grade == "PENDING_REPORT" or task_status in {"CONFIG_READY", "PENDING_REPORT"}:
        score += 12.0
    if record.get("sourceDecision") == "RETUNE":
        score += 8.0
    return round(score, 3)


def build_scheduler(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    gate = read_json(runtime_dir / GATE_NAME)
    optimizer = read_json(runtime_dir / OPTIMIZER_NAME)
    param_plan = read_json(runtime_dir / PARAM_PLAN_NAME)
    param_status = read_json(runtime_dir / PARAM_LAB_STATUS_NAME)
    param_results = read_json(runtime_dir / PARAM_LAB_RESULTS_NAME)

    optimizer_by_id, optimizer_by_route = proposal_index(optimizer)
    param_candidates, template_by_route_symbol, template_by_route = index_param_candidates(param_plan)
    status_by_id, result_by_id = index_status_and_results(param_status, param_results)
    route_filter = {item.strip() for item in args.route if item.strip()}

    source_records, route_plans = build_source_records(
        gate=gate,
        optimizer_by_id=optimizer_by_id,
        optimizer_by_route=optimizer_by_route,
        param_plan=param_plan,
        route_filter=route_filter,
    )

    dedup: dict[str, dict[str, Any]] = {}
    for record in source_records:
        candidate_id = str(record.get("candidateId") or "")
        if not candidate_id:
            continue
        proposal = optimizer_by_id.get(candidate_id) or optimizer_by_id.get(str(record.get("proposalId") or "")) or {}
        status = status_by_id.get(candidate_id, {})
        result = result_by_id.get(candidate_id, {})
        priority = score_source(record, proposal, status, result)
        existing = dedup.get(candidate_id)
        if existing and as_float(existing.get("priorityScore")) >= priority:
            continue
        record = dict(record)
        record["priorityScore"] = priority
        record["optimizerProposal"] = proposal
        record["existingTaskStatus"] = status.get("status", "")
        record["existingConfigPath"] = status.get("configPath", "")
        record["existingReportPath"] = status.get("reportPath", "") or result.get("reportPath", "")
        record["existingGrade"] = result.get("grade", "")
        record["existingResultScore"] = result.get("resultScore", "")
        dedup[candidate_id] = record

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in dedup.values():
        grouped[str(record.get("routeKey") or "UNKNOWN")].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda item: (-as_float(item.get("priorityScore")), str(item.get("candidateId") or "")))

    max_tasks = max(1, int(args.max_tasks))
    max_per_route = max(1, int(args.max_per_route))
    selected_records: list[dict[str, Any]] = []
    used: set[str] = set()
    for slot in range(max_per_route):
        for route_key in CORE_ROUTE_KEYS:
            rows = grouped.get(route_key, [])
            if slot >= len(rows):
                continue
            row = rows[slot]
            if len(selected_records) >= max_tasks:
                break
            candidate_id = str(row.get("candidateId") or "")
            if candidate_id and candidate_id not in used:
                selected_records.append(row)
                used.add(candidate_id)
        if len(selected_records) >= max_tasks:
            break
    if len(selected_records) < max_tasks:
        leftovers = sorted(dedup.values(), key=lambda item: (-as_float(item.get("priorityScore")), str(item.get("candidateId") or "")))
        for row in leftovers:
            candidate_id = str(row.get("candidateId") or "")
            if candidate_id in used:
                continue
            selected_records.append(row)
            used.add(candidate_id)
            if len(selected_records) >= max_tasks:
                break

    candidates_by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    backtest_tasks: list[dict[str, Any]] = []
    selected_tasks: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for rank, record in enumerate(selected_records, start=1):
        candidate_id = str(record.get("candidateId") or "")
        proposal = safe_dict(record.get("optimizerProposal"))
        if proposal:
            candidate = candidate_from_proposal(
                repo_root=repo_root,
                proposal=proposal,
                template_by_route_symbol=template_by_route_symbol,
                template_by_route=template_by_route,
            )
        else:
            candidate = candidate_from_param_task(param_candidates, safe_dict(record.get("paramTask")))
        route_key = str(candidate.get("routeKey") or record.get("routeKey") or "")
        command = command_for_candidate(repo_root, runtime_dir, candidate_id)
        source_decision = str(record.get("sourceDecision") or "")
        route_current_decision = str(record.get("routeCurrentDecision") or "")
        if source_decision == "WAIT_REPORT" and route_current_decision == "RETUNE":
            schedule_action = "CONFIG_ONLY_WAIT_REPORT_RETUNE"
        elif source_decision == "WAIT_REPORT":
            schedule_action = "CONFIG_ONLY_WAIT_REPORT"
        else:
            schedule_action = "CONFIG_ONLY_RETUNE"
        task = {
            "rank": rank,
            "candidateId": candidate_id,
            "routeKey": route_key,
            "strategy": candidate.get("strategy", ""),
            "symbol": candidate.get("symbol", ""),
            "timeframe": candidate.get("timeframe", ""),
            "variant": candidate.get("variant", ""),
            "score": candidate.get("score", record.get("priorityScore")),
            "presetName": candidate.get("presetName", f"QuantGod_MT5_ParamLab_{candidate_id}.set"),
            "presetOverrides": candidate.get("presetOverrides", {}),
            "parameterSummary": candidate.get("parameterSummary", ""),
            "scheduleAction": schedule_action,
            "schedulerSource": record.get("source", ""),
            "sourceDecision": record.get("sourceDecision", ""),
            "routeCurrentDecision": route_current_decision,
            "sourceVersionId": record.get("versionId", ""),
            "candidateVersionId": record.get("candidateVersionId", ""),
            "parentVersionId": record.get("parentVersionId", ""),
            "priorityScore": record.get("priorityScore", 0),
            "reason": record.get("reason", ""),
            "blockers": record.get("blockers", []),
            "requiredEvidence": record.get("requiredEvidence", []),
            "existingTaskStatus": record.get("existingTaskStatus", ""),
            "existingConfigPath": record.get("existingConfigPath", ""),
            "existingReportPath": record.get("existingReportPath", ""),
            "existingGrade": record.get("existingGrade", ""),
            "existingResultScore": record.get("existingResultScore", ""),
            "reportPathHint": proposal.get("reportPathHint", "") if proposal else "",
            "testerOnlyCommand": command,
            "configOnlyCommand": command,
            "runTerminalDefault": False,
            "livePresetMutation": False,
            "testerOnly": True,
        }
        candidate.update({
            "routeRank": len(candidates_by_route[route_key]) + 1,
            "autoSchedulerRank": rank,
            "scheduleAction": schedule_action,
            "schedulerSource": record.get("source", ""),
            "sourceDecision": record.get("sourceDecision", ""),
            "routeCurrentDecision": route_current_decision,
            "priorityScore": record.get("priorityScore", 0),
            "testerOnlyCommand": command,
            "configOnlyCommand": command,
        })
        candidates_by_route[route_key].append(candidate)
        backtest_tasks.append(task)
        selected_tasks.append(task)

    route_plan_output = []
    for route_plan in route_plans:
        route_key = str(route_plan.get("routeKey") or "")
        route_plan = dict(route_plan)
        route_plan["scheduledTaskCount"] = len(candidates_by_route.get(route_key, []))
        route_plan["candidates"] = candidates_by_route.get(route_key, [])
        route_plan_output.append(route_plan)

    wait_forward_count = sum(1 for item in route_plans if item.get("currentDecision") == "WAIT_FORWARD")
    wait_report_count = sum(1 for item in selected_tasks if item.get("sourceDecision") == "WAIT_REPORT")
    retune_count = sum(1 for item in selected_tasks if item.get("routeCurrentDecision") == "RETUNE" or item.get("sourceDecision") == "RETUNE")
    summary = {
        "queueCount": len(selected_tasks),
        "maxTasks": max_tasks,
        "maxPerRoute": max_per_route,
        "waitReportQueueCount": wait_report_count,
        "retuneQueueCount": retune_count,
        "waitForwardObserveCount": wait_forward_count,
        "routeCount": len(route_plan_output),
        "configOnly": True,
        "runTerminal": False,
        "livePresetMutation": False,
        "dryRun": True,
        "topCandidateId": selected_tasks[0]["candidateId"] if selected_tasks else "",
    }
    plan = {
        "schemaVersion": 1,
        "source": "QuantGod ParamLab Auto Scheduler",
        "generatedAtIso": now_iso,
        "mode": "CONFIG_ONLY_AUTO_SCHEDULER",
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "summary": summary,
        "sourceFiles": {
            "versionPromotionGate": str(runtime_dir / GATE_NAME),
            "optimizerV2": str(runtime_dir / OPTIMIZER_NAME),
            "paramOptimizationPlan": str(runtime_dir / PARAM_PLAN_NAME),
            "paramLabStatus": str(runtime_dir / PARAM_LAB_STATUS_NAME),
            "paramLabResults": str(runtime_dir / PARAM_LAB_RESULTS_NAME),
        },
        "routePlans": route_plan_output,
        "selectedTasks": selected_tasks,
        "backtestTasks": backtest_tasks,
        "batchCommand": f'python "{repo_root / "tools" / "run_param_lab.py"}" --plan "{runtime_dir / OUTPUT_NAME}" --max-tasks {max_tasks}',
        "hardGuards": [
            "Auto Scheduler is config-only and never adds -RunTerminal.",
            "No HFM live preset is mutated.",
            "No broker account, server, credential, lot size, position cap, SL/TP, or live switch is changed.",
            "Generated tasks are tester-only and compatible with tools/run_param_lab.py --plan.",
            "Strategy Tester launch still requires explicit --run-terminal and --authorized-strategy-tester on the runner.",
        ],
        "nextOperatorSteps": [
            "Review this queue in Dashboard before any weekend tester run.",
            "Run the batch command without --run-terminal to materialize safe tester-only configs.",
            "Only add --run-terminal to the ParamLab runner during an authorized Strategy Tester window.",
            "After reports exist, run collect_param_lab_results.py and rebuild Governance Advisor.",
        ],
    }
    return plan


def ledger_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for task in safe_list(plan.get("selectedTasks")):
        task = safe_dict(task)
        rows.append({
            "GeneratedAtIso": plan.get("generatedAtIso", ""),
            "Rank": task.get("rank", ""),
            "RouteKey": task.get("routeKey", ""),
            "CandidateId": task.get("candidateId", ""),
            "ScheduleAction": task.get("scheduleAction", ""),
            "SchedulerSource": task.get("schedulerSource", ""),
            "SourceDecision": task.get("sourceDecision", ""),
            "RouteCurrentDecision": task.get("routeCurrentDecision", ""),
            "PriorityScore": task.get("priorityScore", ""),
            "Symbol": task.get("symbol", ""),
            "Timeframe": task.get("timeframe", ""),
            "ExistingTaskStatus": task.get("existingTaskStatus", ""),
            "ExistingGrade": task.get("existingGrade", ""),
            "ConfigOnlyCommand": task.get("configOnlyCommand", ""),
            "LivePresetMutation": task.get("livePresetMutation", False),
            "RunTerminalDefault": task.get("runTerminalDefault", False),
        })
    return rows


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = output.with_name(LEDGER_NAME)
    plan = build_scheduler(args)
    write_json(output, plan)
    write_csv(
        ledger,
        ledger_rows(plan),
        [
            "GeneratedAtIso",
            "Rank",
            "RouteKey",
            "CandidateId",
            "ScheduleAction",
            "SchedulerSource",
            "SourceDecision",
            "RouteCurrentDecision",
            "PriorityScore",
            "Symbol",
            "Timeframe",
            "ExistingTaskStatus",
            "ExistingGrade",
            "ConfigOnlyCommand",
            "LivePresetMutation",
            "RunTerminalDefault",
        ],
    )
    print(f"Wrote {output}")
    print(f"Wrote {ledger}")
    print(
        "Auto Scheduler: "
        f"queue={plan['summary']['queueCount']} "
        f"waitReport={plan['summary']['waitReportQueueCount']} "
        f"retune={plan['summary']['retuneQueueCount']} "
        f"runTerminal={plan['summary']['runTerminal']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
