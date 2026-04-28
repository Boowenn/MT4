#!/usr/bin/env python3
"""Build a dry-run version promotion gate for QuantGod MT5.

This gate is the final advisory layer between Strategy Version Registry,
Optimizer V2, ParamLab reports, and Governance Advisor. It only writes local
JSON/CSV evidence. It never mutates the HFM live preset, never launches MT5,
and never sends orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
REGISTRY_NAME = "QuantGod_StrategyVersionRegistry.json"
OPTIMIZER_V2_NAME = "QuantGod_OptimizerV2Plan.json"
PARAM_RESULTS_NAME = "QuantGod_ParamLabResults.json"
GOVERNANCE_NAME = "QuantGod_GovernanceAdvisor.json"
OUTPUT_NAME = "QuantGod_VersionPromotionGate.json"
LEDGER_NAME = "QuantGod_VersionPromotionGateLedger.csv"

LIVE_MIN_CLOSED_TRADES = 3
PROMOTION_MIN_CLOSED_TRADES = 10
PROMOTION_MIN_PF = 1.15
PROMOTION_MIN_WIN_RATE = 55.0
PROMOTION_MAX_REL_DD_PCT = 20.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod dry-run version promotion gate.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
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


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_grade(value: Any) -> str:
    return str(value or "").strip().upper()


def result_state(result: dict[str, Any]) -> str:
    grade = normalize_grade(result.get("grade"))
    status = normalize_grade(result.get("status") or result.get("resultStatus"))
    if grade in {"A", "B", "C", "D"}:
        return "SCORED"
    if grade == "PENDING_REPORT" or status in {"PENDING_REPORT", "REPORT_MISSING", "REPORT_MISSING_AFTER_RUN"}:
        return "WAITING_REPORT"
    if result:
        return "UNSCORED"
    return "MISSING"


def result_index(results: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_candidate: dict[str, dict[str, Any]] = {}
    by_route: dict[str, dict[str, Any]] = {}
    top = results.get("topByRoute")
    if isinstance(top, dict):
        by_route = {str(k): v for k, v in top.items() if isinstance(v, dict)}
    for row in as_list(results.get("results")):
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidateId") or "")
        if candidate_id:
            by_candidate[candidate_id] = row
        route_key = str(row.get("routeKey") or row.get("strategy") or "")
        if route_key and route_key not in by_route:
            by_route[route_key] = row
    return by_candidate, by_route


def advisor_by_route(advisor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = advisor.get("routeDecisions")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy") or row.get("key") or ""): row
        for row in rows
        if isinstance(row, dict)
    }


def score_result_for_promotion(result: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    metrics = as_dict(result.get("metrics"))
    grade = normalize_grade(result.get("grade"))
    closed = as_int(metrics.get("closedTrades"), 0)
    pf = as_float(metrics.get("profitFactor"))
    win_rate = as_float(metrics.get("winRate"))
    net = as_float(metrics.get("netProfit"))
    rel_dd = as_float(metrics.get("relativeDrawdownPct"))
    blockers: list[str] = []
    required: list[str] = []

    if result_state(result) != "SCORED":
        blockers.append("tester_report_missing_or_unscored")
        required.append("Parse Strategy Tester report into ParamLabResults.")
        return False, blockers, required
    if grade not in {"A", "B"}:
        blockers.append("grade_not_a_or_b")
    if closed < PROMOTION_MIN_CLOSED_TRADES:
        blockers.append("tester_closed_trades_lt_10")
    if pf is None or pf < PROMOTION_MIN_PF:
        blockers.append("tester_pf_lt_1_15")
    if win_rate is None or win_rate < PROMOTION_MIN_WIN_RATE:
        blockers.append("tester_win_rate_lt_55")
    if net is None or net <= 0:
        blockers.append("tester_net_not_positive")
    if rel_dd is not None and rel_dd > PROMOTION_MAX_REL_DD_PCT:
        blockers.append("tester_drawdown_too_high")

    if blockers:
        required.extend([
            "Need grade A/B, PF >= 1.15, win rate >= 55%, net profit > 0.",
            "Need at least 10 closed tester trades and controlled drawdown.",
        ])
    return not blockers, blockers, required


def candidate_support(candidate_samples: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    rows = as_int(candidate_samples.get("horizonRows") or candidate_samples.get("rows"), 0)
    win_rate = as_float(candidate_samples.get("winRatePct"))
    avg_pips = as_float(candidate_samples.get("avgSignedPips"))
    blockers: list[str] = []
    required: list[str] = []
    if rows < 20:
        blockers.append("candidate_outcome_sample_lt_20")
        required.append("Need at least 20 fresh candidate outcome samples.")
    if win_rate is None or win_rate < 55.0:
        blockers.append("candidate_win_rate_lt_55")
    if avg_pips is None or avg_pips <= 0:
        blockers.append("candidate_avg_signed_pips_not_positive")
    if blockers and len(required) == 0:
        required.append("Need candidate outcome posterior to stop disagreeing with promotion.")
    return not blockers, blockers, required


def current_route_decision(route: dict[str, Any], advisor_route: dict[str, Any], route_result: dict[str, Any]) -> dict[str, Any]:
    route_key = str(route.get("routeKey") or route.get("strategy") or "")
    evidence = as_dict(route.get("evidence"))
    promotion = as_dict(route.get("promotionState"))
    live_forward = as_dict(evidence.get("liveForward"))
    candidate = as_dict(evidence.get("candidateSamples"))
    live_enabled = bool(route.get("liveEnabled"))
    current_action = str(promotion.get("recommendedAction") or evidence.get("governanceAction") or advisor_route.get("recommendedAction") or "")
    blockers = list(dict.fromkeys(as_list(evidence.get("blockers")) + as_list(advisor_route.get("blockers"))))
    required: list[str] = []
    reason = "Current version remains in observation."
    decision = "KEEP_SIM"
    metrics = as_dict(route_result.get("metrics")) or as_dict(as_dict(evidence.get("paramLabResult")).get("metrics"))
    grade = normalize_grade(route_result.get("grade") or as_dict(evidence.get("paramLabResult")).get("grade"))

    if live_enabled:
        closed = as_int(live_forward.get("closedTrades"), 0)
        pf = as_float(live_forward.get("profitFactor"))
        net = as_float(live_forward.get("netProfitUSC"))
        consecutive = as_int(live_forward.get("consecutiveLosses"), 0)
        if closed >= LIVE_MIN_CLOSED_TRADES and consecutive >= 2:
            decision = "DEMOTE_LIVE"
            reason = "Live forward has enough samples and consecutive losses; dry-run recommends closing live switch review."
            blockers.append("live_consecutive_losses_ge_2")
        elif closed >= LIVE_MIN_CLOSED_TRADES and pf is not None and pf < 1.0 and net is not None and net < 0:
            decision = "DEMOTE_LIVE"
            reason = "Live forward PF is below 1 with negative net after the minimum sample gate."
            blockers.append("live_pf_lt_1_after_min_sample")
        elif closed < LIVE_MIN_CLOSED_TRADES:
            decision = "WAIT_FORWARD"
            reason = "Live route is allowed, but forward sample is still too thin for version promotion or demotion."
            blockers.append("live_forward_sample_lt_3")
            required.append("Collect at least 3 closed 0.01 live trades before promotion/demotion.")
        else:
            decision = "KEEP_LIVE"
            reason = "Live route has no hard demotion trigger; keep 0.01 guardrails unchanged."
        if pf is not None and pf < 1.0:
            blockers.append("live_pf_lt_1")
        if net is not None and net < 0:
            blockers.append("live_net_negative")
    else:
        candidate_ok, candidate_blockers, candidate_required = candidate_support(candidate)
        state = result_state(route_result)
        if current_action in {"RETUNE_SIM", "DEMOTE_REVIEW"}:
            decision = "RETUNE"
            reason = "Governance already marks this simulation route for retuning."
            blockers.append("governance_retune_signal")
            required.extend(candidate_required)
        elif not candidate_ok and as_int(candidate.get("horizonRows"), 0) >= 5:
            decision = "RETUNE"
            reason = "Candidate posterior is materially weak; do not wait passively for live promotion."
            blockers.extend(candidate_blockers)
            required.extend(candidate_required)
        elif state == "WAITING_REPORT":
            decision = "WAIT_REPORT"
            reason = "Route has tester-only work queued, but no parsed report yet."
            blockers.append("paramlab_report_missing")
            required.append("Run authorized Strategy Tester report and parse it into ParamLabResults.")
        elif state == "SCORED":
            result_ok, result_blockers, result_required = score_result_for_promotion(route_result)
            if result_ok and candidate_ok:
                decision = "PROMOTE_CANDIDATE"
                reason = "Tester result and candidate posterior pass dry-run promotion thresholds."
            elif grade in {"C", "D"} or as_float(metrics.get("profitFactor"), 0.0) < 1.0:
                decision = "RETUNE"
                reason = "Scored tester result does not support promotion; retune route."
                blockers.extend(result_blockers or ["tester_score_weak"])
            else:
                decision = "KEEP_SIM"
                reason = "Evidence is not strong enough to promote, but not weak enough to retune."
            required.extend(result_required + candidate_required)
        else:
            decision = "KEEP_SIM"
            reason = "Simulation route is still collecting candidate evidence."
            blockers.extend(candidate_blockers)
            required.extend(candidate_required)

    blockers = sorted({str(item) for item in blockers if item})
    required = sorted({str(item) for item in required if item})
    return {
        "routeKey": route_key,
        "strategy": route_key,
        "label": route.get("label", route_key),
        "versionType": "CURRENT_ROUTE",
        "versionId": route.get("versionId", ""),
        "parentVersionId": route.get("parentVersionId", ""),
        "candidateId": as_dict(evidence.get("paramLabResult")).get("candidateId", ""),
        "proposalId": "",
        "status": route.get("status", ""),
        "decision": decision,
        "reason": reason,
        "blockers": blockers,
        "requiredEvidence": required,
        "liveEnabled": live_enabled,
        "candidateEnabled": bool(route.get("candidateEnabled")),
        "rankScore": "",
        "resultScore": route_result.get("resultScore", as_dict(evidence.get("paramLabResult")).get("resultScore", "")),
        "grade": grade,
        "livePresetMutation": False,
        "dryRun": True,
        "evidence": {
            "liveForward": live_forward,
            "candidateSamples": candidate,
            "paramLabResult": route_result or as_dict(evidence.get("paramLabResult")),
            "governanceAction": current_action,
        },
    }


def proposal_decision(proposal: dict[str, Any], route: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    route_key = str(proposal.get("routeKey") or proposal.get("strategy") or "")
    blockers = [str(item) for item in as_list(proposal.get("blockers")) if item]
    required: list[str] = []
    state = result_state(result)
    decision = "WAIT_REPORT"
    reason = "Optimizer proposal is tester-only until a parsed Strategy Tester report exists."

    if state == "SCORED":
        result_ok, result_blockers, result_required = score_result_for_promotion(result)
        candidate_ok, candidate_blockers, candidate_required = candidate_support(as_dict(as_dict(route.get("evidence")).get("candidateSamples")))
        if result_ok and candidate_ok:
            decision = "PROMOTE_CANDIDATE"
            reason = "Proposal has a parsed strong report and candidate posterior support."
        else:
            decision = "RETUNE" if result_blockers else "KEEP_SIM"
            reason = "Proposal report is parsed but not strong enough for promotion."
        blockers.extend(result_blockers + candidate_blockers)
        required.extend(result_required + candidate_required)
    elif state == "WAITING_REPORT":
        decision = "WAIT_REPORT"
        reason = "Existing ParamLab task/report is still missing or unparsed."
        blockers.append("paramlab_report_missing")
        required.append("Run tester-only task in an authorized window and parse report.")
    elif proposal.get("existingTaskStatus"):
        decision = "WAIT_REPORT"
        reason = "Proposal has task status but no scored report yet."
        blockers.append("paramlab_task_without_score")
        required.append("Wait for report parsing before promotion review.")
    else:
        decision = "WAIT_REPORT"
        blockers.append("proposal_not_backtested")
        required.append("Queue tester-only config; do not promote before parsed report.")

    blockers = sorted({str(item) for item in blockers if item})
    required = sorted({str(item) for item in required if item})
    return {
        "routeKey": route_key,
        "strategy": route_key,
        "label": route.get("label", route_key),
        "versionType": "OPTIMIZER_PROPOSAL",
        "versionId": proposal.get("candidateVersionId", ""),
        "parentVersionId": proposal.get("parentVersionId", ""),
        "candidateId": proposal.get("proposalId", ""),
        "proposalId": proposal.get("proposalId", ""),
        "status": "TESTER_ONLY_PROPOSAL",
        "decision": decision,
        "reason": reason,
        "blockers": blockers,
        "requiredEvidence": required,
        "liveEnabled": False,
        "candidateEnabled": True,
        "rankScore": proposal.get("rankScore", ""),
        "resultScore": result.get("resultScore", ""),
        "grade": result.get("grade", ""),
        "livePresetMutation": False,
        "dryRun": True,
        "testerOnlyCommand": proposal.get("testerOnlyCommand", ""),
        "reportPathHint": proposal.get("existingReportPath") or proposal.get("reportPathHint", ""),
        "parameterSummary": proposal.get("parameterSummary", ""),
        "evidence": {
            "paramLabResult": result,
            "optimizerObjective": proposal.get("objective", ""),
            "optimizerBlockers": blockers,
        },
    }


def build_gate(runtime_dir: Path) -> dict[str, Any]:
    registry = read_json(runtime_dir / REGISTRY_NAME)
    optimizer = read_json(runtime_dir / OPTIMIZER_V2_NAME)
    results = read_json(runtime_dir / PARAM_RESULTS_NAME)
    advisor = read_json(runtime_dir / GOVERNANCE_NAME)
    by_candidate, by_route = result_index(results)
    advisor_routes = advisor_by_route(advisor)
    routes = [row for row in as_list(registry.get("routes")) if isinstance(row, dict)]
    route_by_key = {str(route.get("routeKey") or route.get("strategy") or ""): route for route in routes}

    decisions: list[dict[str, Any]] = []
    for route in routes:
        route_key = str(route.get("routeKey") or route.get("strategy") or "")
        decisions.append(current_route_decision(
            route,
            advisor_routes.get(route_key, {}),
            by_route.get(route_key, {}),
        ))

    for proposal in as_list(optimizer.get("rankedProposals")):
        if not isinstance(proposal, dict):
            continue
        route_key = str(proposal.get("routeKey") or proposal.get("strategy") or "")
        proposal_id = str(proposal.get("proposalId") or "")
        result = by_candidate.get(proposal_id, {})
        decisions.append(proposal_decision(proposal, route_by_key.get(route_key, {}), result))

    counts = Counter(row["decision"] for row in decisions)
    route_decisions: dict[str, list[dict[str, Any]]] = {}
    for row in decisions:
        route_decisions.setdefault(row["routeKey"], []).append(row)
    route_summary = []
    for route_key, rows in route_decisions.items():
        current = next((row for row in rows if row["versionType"] == "CURRENT_ROUTE"), rows[0])
        promote = sum(1 for row in rows if row["decision"] == "PROMOTE_CANDIDATE")
        wait_report = sum(1 for row in rows if row["decision"] == "WAIT_REPORT")
        retune = sum(1 for row in rows if row["decision"] == "RETUNE")
        demote = sum(1 for row in rows if row["decision"] == "DEMOTE_LIVE")
        route_summary.append({
            "routeKey": route_key,
            "currentVersionId": current.get("versionId", ""),
            "currentDecision": current.get("decision", ""),
            "currentReason": current.get("reason", ""),
            "promotionCandidateCount": promote,
            "waitingReportCount": wait_report,
            "retuneCount": retune,
            "demoteLiveCount": demote,
            "blockers": current.get("blockers", []),
            "dryRun": True,
            "livePresetMutation": False,
        })
    route_summary.sort(key=lambda row: str(row.get("routeKey", "")))

    return {
        "schemaVersion": 1,
        "source": "QuantGod Version Promotion Gate dry-run",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "mode": "VERSION_PROMOTION_GATE_DRY_RUN",
        "hardGuards": [
            "This gate is advisory only.",
            "No HFM live preset is mutated.",
            "No terminal is launched.",
            "No broker order path is added or called.",
            "PROMOTE_CANDIDATE and DEMOTE_LIVE are recommendations until a separate verified config change is authorized.",
        ],
        "thresholds": {
            "liveMinClosedTrades": LIVE_MIN_CLOSED_TRADES,
            "promotionMinClosedTrades": PROMOTION_MIN_CLOSED_TRADES,
            "promotionMinProfitFactor": PROMOTION_MIN_PF,
            "promotionMinWinRatePct": PROMOTION_MIN_WIN_RATE,
            "promotionMaxRelativeDrawdownPct": PROMOTION_MAX_REL_DD_PCT,
        },
        "summary": {
            "versionDecisionCount": len(decisions),
            "routeCount": len(route_summary),
            "promoteCandidateCount": counts.get("PROMOTE_CANDIDATE", 0),
            "demoteLiveCount": counts.get("DEMOTE_LIVE", 0),
            "retuneCount": counts.get("RETUNE", 0),
            "waitReportCount": counts.get("WAIT_REPORT", 0),
            "waitForwardCount": counts.get("WAIT_FORWARD", 0),
            "keepLiveCount": counts.get("KEEP_LIVE", 0),
            "keepSimCount": counts.get("KEEP_SIM", 0),
            "livePresetMutation": False,
            "dryRun": True,
        },
        "routeDecisions": route_summary,
        "versionDecisions": decisions,
        "sourceFiles": {
            "strategyVersionRegistry": REGISTRY_NAME,
            "optimizerV2": OPTIMIZER_V2_NAME,
            "paramLabResults": PARAM_RESULTS_NAME,
            "governanceAdvisor": GOVERNANCE_NAME,
        },
        "nextOperatorSteps": [
            "Use PROMOTE_CANDIDATE only as a dry-run review flag, not as live config mutation.",
            "Run WAIT_REPORT proposals in an authorized Strategy Tester window and parse reports first.",
            "Retune routes with persistent weak candidate posterior before considering live promotion.",
            "Keep live MA/RSI under 0.01 single-position EA guardrails until forward samples are sufficient.",
        ],
    }


def ledger_rows(gate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for decision in gate.get("versionDecisions") or []:
        rows.append({
            "GeneratedAtIso": gate.get("generatedAtIso", ""),
            "RouteKey": decision.get("routeKey", ""),
            "VersionId": decision.get("versionId", ""),
            "ParentVersionId": decision.get("parentVersionId", ""),
            "CandidateId": decision.get("candidateId", ""),
            "ProposalId": decision.get("proposalId", ""),
            "VersionType": decision.get("versionType", ""),
            "Decision": decision.get("decision", ""),
            "Reason": decision.get("reason", ""),
            "Blockers": ";".join(decision.get("blockers") or []),
            "RequiredEvidence": ";".join(decision.get("requiredEvidence") or []),
            "RankScore": decision.get("rankScore", ""),
            "ResultScore": decision.get("resultScore", ""),
            "Grade": decision.get("grade", ""),
            "DryRun": str(bool(decision.get("dryRun", True))).lower(),
            "LivePresetMutation": str(bool(decision.get("livePresetMutation", False))).lower(),
        })
    return rows


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    gate = build_gate(runtime_dir)
    write_json(output, gate)
    write_csv(ledger, ledger_rows(gate), [
        "GeneratedAtIso",
        "RouteKey",
        "VersionId",
        "ParentVersionId",
        "CandidateId",
        "ProposalId",
        "VersionType",
        "Decision",
        "Reason",
        "Blockers",
        "RequiredEvidence",
        "RankScore",
        "ResultScore",
        "Grade",
        "DryRun",
        "LivePresetMutation",
    ])
    summary = gate["summary"]
    print(f"Wrote {output}")
    print(f"Wrote {ledger}")
    print(
        "Gate decisions: "
        f"{summary['versionDecisionCount']} | promote {summary['promoteCandidateCount']} | "
        f"wait report {summary['waitReportCount']} | retune {summary['retuneCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
