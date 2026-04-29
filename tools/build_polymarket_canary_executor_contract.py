#!/usr/bin/env python3
"""Build the guarded Polymarket canary executor contract.

V2 is still side-effect free: it does not read private-key values, place
orders, cancel orders, start executor loops, or mutate MT5. It upgrades the
old contract-only shell into a machine-verifiable contract that can mark a
candidate as evidence-ready for a future isolated canary executor.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

from polymarket_governance_utils import (
    DEFAULT_REAL_MONEY_POLICY,
    atomic_write_text,
    build_outcome_profiles,
    choose_evidence_profile,
    evaluate_real_money_readiness,
    first_text,
    get_rows,
    index_by_market,
    index_outcomes,
    market_key,
    merge_policy,
    read_json_candidate,
    safe_number,
    stable_id,
    track_key,
    unique,
    utc_now_iso,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"

GATE_NAME = "QuantGod_PolymarketExecutionGate.json"
DRY_RUN_NAME = "QuantGod_PolymarketDryRunOrders.json"
OUTCOME_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"
AI_SCORE_NAME = "QuantGod_PolymarketAiScoreV1.json"
CROSS_LINKAGE_NAME = "QuantGod_PolymarketCrossMarketLinkage.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"

OUTPUT_NAME = "QuantGod_PolymarketCanaryExecutorContract.json"
LEDGER_NAME = "QuantGod_PolymarketCanaryExecutorLedger.csv"
SCHEMA_VERSION = "POLYMARKET_CANARY_EXECUTOR_CONTRACT_V2"

LEDGER_FIELDS = [
    "generated_at",
    "schema_version",
    "canary_contract_id",
    "market_id",
    "question",
    "track",
    "side",
    "canary_state",
    "decision",
    "evidence_can_auto_authorize",
    "canary_eligible_now",
    "canary_stake_usdc",
    "max_single_bet_usdc",
    "max_daily_loss_usdc",
    "samples",
    "win_rate_pct",
    "profit_factor",
    "stop_loss_rate_pct",
    "max_consecutive_losses",
    "avg_return_pct",
    "ai_score",
    "source_score",
    "blockers",
    "wallet_write_allowed",
    "order_send_allowed",
    "starts_executor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--gate-path", default="")
    parser.add_argument("--dry-run-path", default="")
    parser.add_argument("--outcome-path", default="")
    parser.add_argument("--ai-score-path", default="")
    parser.add_argument("--cross-linkage-path", default="")
    parser.add_argument("--radar-path", default="")
    parser.add_argument("--max-candidates", type=int, default=24)
    parser.add_argument("--min-dry-run-outcomes", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["minDryRunOutcomeSamples"]))
    parser.add_argument("--min-dry-run-win-rate-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunWinRatePct"]))
    parser.add_argument("--min-dry-run-profit-factor", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunProfitFactor"]))
    parser.add_argument("--max-dry-run-stop-loss-rate-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["maxDryRunStopLossRatePct"]))
    parser.add_argument("--max-dry-run-consecutive-losses", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["maxDryRunConsecutiveLosses"]))
    parser.add_argument("--min-dry-run-average-return-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunAverageReturnPct"]))
    parser.add_argument("--min-ai-score", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minAiScore"]))
    parser.add_argument("--min-composite-score", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minCompositeScore"]))
    parser.add_argument("--max-single-bet-usdc", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["maxSingleBetUSDC"]))
    parser.add_argument("--max-daily-loss-usdc", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["maxDailyLossUSDC"]))
    parser.add_argument("--max-open-canary-positions", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["maxOpenCanaryPositions"]))
    parser.add_argument("--take-profit-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["takeProfitPct"]))
    parser.add_argument("--stop-loss-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["stopLossPct"]))
    parser.add_argument("--trailing-profit-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["trailingProfitPct"]))
    parser.add_argument("--cancel-unfilled-minutes", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["cancelUnfilledAfterMinutes"]))
    parser.add_argument("--max-hold-hours", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["maxHoldHours"]))
    parser.add_argument("--exit-before-resolution-hours", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["exitBeforeResolutionHours"]))
    return parser.parse_args()


def policy_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return merge_policy(
        {
            "minDryRunOutcomeSamples": args.min_dry_run_outcomes,
            "minDryRunWinRatePct": args.min_dry_run_win_rate_pct,
            "minDryRunProfitFactor": args.min_dry_run_profit_factor,
            "maxDryRunStopLossRatePct": args.max_dry_run_stop_loss_rate_pct,
            "maxDryRunConsecutiveLosses": args.max_dry_run_consecutive_losses,
            "minDryRunAverageReturnPct": args.min_dry_run_average_return_pct,
            "minAiScore": args.min_ai_score,
            "minCompositeScore": args.min_composite_score,
            "maxSingleBetUSDC": args.max_single_bet_usdc,
            "maxDailyLossUSDC": args.max_daily_loss_usdc,
            "maxOpenCanaryPositions": args.max_open_canary_positions,
            "takeProfitPct": args.take_profit_pct,
            "stopLossPct": args.stop_loss_pct,
            "trailingProfitPct": args.trailing_profit_pct,
            "cancelUnfilledAfterMinutes": args.cancel_unfilled_minutes,
            "maxHoldHours": args.max_hold_hours,
            "exitBeforeResolutionHours": args.exit_before_resolution_hours,
        }
    )


def make_candidate_seed(gate: dict[str, Any], dry_run: dict[str, Any], radar: dict[str, Any]) -> list[dict[str, Any]]:
    dry_orders = get_rows(dry_run, "dryRunOrders", "orders")
    if dry_orders:
        return dry_orders
    gate_rows = get_rows(gate, "marketDecisions")
    if gate_rows:
        return gate_rows
    return get_rows(radar, "radar")


def composite_score(seed: dict[str, Any], ai: dict[str, Any]) -> float:
    source_score = safe_number(seed.get("radarScore"), None)
    if source_score is None:
        source_score = safe_number(seed.get("aiRuleScore"), None)
    if source_score is None:
        source_score = safe_number(seed.get("sourceScore"), 0.0) or 0.0
    ai_score = safe_number(ai.get("score"), safe_number(seed.get("aiScore"), None))
    if ai_score is None:
        return round(float(source_score or 0.0), 3)
    return round((float(source_score or 0.0) * 0.45) + (float(ai_score) * 0.55), 3)


def build_global_blockers(gate: dict[str, Any], dry_run: dict[str, Any], outcome: dict[str, Any], ai_score: dict[str, Any]) -> list[str]:
    blockers = [
        "REAL_EXECUTION_SWITCH_FALSE",
        "CANARY_ACK_MISSING",
        "CANARY_KILL_SWITCH_REQUIRED",
        "WALLET_ADAPTER_NOT_VERIFIED",
        "ORDER_AUDIT_REQUIRED",
    ]
    if not gate:
        blockers.append("EXECUTION_GATE_MISSING")
    if not dry_run:
        blockers.append("DRY_RUN_ORDER_LAYER_MISSING")
    if not outcome:
        blockers.append("DRY_RUN_OUTCOME_LAYER_MISSING")
    if not ai_score:
        blockers.append("AI_SCORE_LAYER_MISSING")
    blockers.extend(str(item) for item in (gate.get("globalBlockers") or []))
    return unique(blockers)


def build_isolation_contract(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "GUARDED_CANARY_EXECUTOR_CONTRACT_V2",
        "schemaVersion": SCHEMA_VERSION,
        "canStartExecutorFromThisBuilder": False,
        "canaryLoopAllowedFromThisBuilder": False,
        "walletWriteAllowedFromThisBuilder": False,
        "orderSendAllowedFromThisBuilder": False,
        "readsPrivateKey": False,
        "readsEnvSecretValues": False,
        "callsClobApi": False,
        "mutatesMt5": False,
        "isolatedRuntime": {
            "requiredRoot": "runtime/Polymarket_Canary_Isolated",
            "separateProcessRequired": True,
            "sharedMt5RuntimeAllowed": False,
            "sharedPolymarketExecutorAllowed": False,
        },
        "runtimeSwitchContract": {
            "allRequiredForRealOrders": {
                "QG_POLYMARKET_REAL_EXECUTION": "true",
                "QG_POLYMARKET_CANARY_ACK": "REAL_MONEY_CANARY_OK",
                "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
                "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
            },
            "neverLogSecretEnvValues": True,
        },
        "realMoneyAutoOpenPolicy": policy,
        "stakeContract": {
            "maxSingleBetUSDC": round(float(policy["maxSingleBetUSDC"]), 2),
            "maxDailyLossUSDC": round(float(policy["maxDailyLossUSDC"]), 2),
            "maxOpenCanaryPositions": max(0, int(policy["maxOpenCanaryPositions"])),
            "perMarketExposureUSDC": round(float(policy["maxSingleBetUSDC"]), 2),
        },
        "exitContract": {
            "takeProfitPct": round(float(policy["takeProfitPct"]), 2),
            "stopLossPct": round(float(policy["stopLossPct"]), 2),
            "trailingProfitPct": round(float(policy["trailingProfitPct"]), 2),
            "cancelUnfilledAfterMinutes": max(1, int(policy["cancelUnfilledAfterMinutes"])),
            "maxHoldHours": round(float(policy["maxHoldHours"]), 2),
            "exitBeforeResolutionHours": round(float(policy["exitBeforeResolutionHours"]), 2),
            "mustHaveManagedExitBeforeOrder": True,
        },
        "killSwitchContract": {
            "globalKillSwitchRequired": True,
            "marketKillSwitchRequired": True,
            "dailyLossHardStopRequired": True,
            "cancelOpenOrdersOnKillSwitch": True,
            "closeOrReduceCanaryPositionOnDemotion": True,
        },
        "auditContract": {
            "contractFile": OUTPUT_NAME,
            "contractLedger": LEDGER_NAME,
            "requiredLedgers": [
                "QuantGod_PolymarketCanaryOrderAuditLedger.csv",
                "QuantGod_PolymarketCanaryPositionLedger.csv",
                "QuantGod_PolymarketCanaryExitLedger.csv",
            ],
        },
    }


def build_candidate_contracts(
    *,
    policy: dict[str, Any],
    seeds: list[dict[str, Any]],
    global_blockers: list[str],
    ai_index: dict[str, dict[str, Any]],
    cross_index: dict[str, dict[str, Any]],
    outcome_index: dict[str, dict[str, Any]],
    outcome_profiles: dict[str, dict[str, Any]],
    isolation: dict[str, Any],
    max_candidates: int,
) -> list[dict[str, Any]]:
    stake = isolation["stakeContract"]
    exit_contract = isolation["exitContract"]
    rows: list[dict[str, Any]] = []
    for seed in seeds[: max(0, max_candidates)]:
        market_id = market_key(seed)
        tracking_key = str(seed.get("trackingKey") or "").strip()
        ai = ai_index.get(market_id) or {}
        cross = cross_index.get(market_id) or {}
        latest_outcome = outcome_index.get(tracking_key) or outcome_index.get(market_id) or {}
        profile = choose_evidence_profile(seed, outcome_profiles, int(policy["minDryRunOutcomeSamples"]))
        score = composite_score(seed, ai)
        evidence_ready, evidence_blockers = evaluate_real_money_readiness(
            candidate=seed,
            ai=ai,
            cross=cross,
            evidence_profile=profile,
            composite_score=score,
            policy=policy,
            global_blockers=[],
        )
        blockers = unique([*global_blockers, *evidence_blockers])
        row_id = "CANARY-" + stable_id(market_id, seed.get("question"), track_key(seed), seed.get("suggestedShadowTrack"))
        reference_stake = safe_number(seed.get("hypotheticalStakeUSDC"), None)
        if reference_stake is None:
            reference_stake = safe_number(seed.get("referenceStakeUSDC"), stake["maxSingleBetUSDC"]) or 0.0
        reference_stake = min(float(reference_stake), float(stake["maxSingleBetUSDC"]))
        canary_state = "EVIDENCE_ELIGIBLE_SWITCH_REQUIRED" if evidence_ready else "EVIDENCE_BLOCKED"
        decision = "ELIGIBLE_FOR_CANARY_EXECUTOR_WHEN_RUNTIME_SWITCHES_ON" if evidence_ready else "KEEP_DRY_RUN_UNTIL_POLICY_PASS"
        row = {
            "canaryContractId": row_id,
            "schemaVersion": SCHEMA_VERSION,
            "marketId": market_id,
            "question": first_text(seed.get("question"), ai.get("question"), cross.get("question")),
            "polymarketUrl": first_text(seed.get("polymarketUrl"), seed.get("url"), ai.get("polymarketUrl"), cross.get("polymarketUrl")),
            "track": first_text(track_key(seed), ai.get("track"), "poly_shadow"),
            "side": first_text(seed.get("side"), "YES"),
            "canaryState": canary_state,
            "decision": decision,
            "evidenceCanAutoAuthorize": evidence_ready,
            "canaryEligibleNow": False,
            "referenceStakeUSDC": round(reference_stake, 2),
            "canaryStakeUSDC": 0.0,
            "maxSingleBetUSDC": stake["maxSingleBetUSDC"],
            "maxDailyLossUSDC": stake["maxDailyLossUSDC"],
            "takeProfitPct": exit_contract["takeProfitPct"],
            "stopLossPct": exit_contract["stopLossPct"],
            "trailingProfitPct": exit_contract["trailingProfitPct"],
            "cancelUnfilledAfterMinutes": exit_contract["cancelUnfilledAfterMinutes"],
            "maxHoldHours": exit_contract["maxHoldHours"],
            "exitBeforeResolutionHours": exit_contract["exitBeforeResolutionHours"],
            "sourceScore": safe_number(seed.get("sourceScore"), safe_number(seed.get("aiRuleScore"), safe_number(seed.get("radarScore"), None))),
            "aiScore": safe_number(ai.get("score"), safe_number(seed.get("aiScore"), None)),
            "aiColor": first_text(ai.get("color"), seed.get("aiColor")),
            "compositeScore": score,
            "crossRiskTag": first_text(cross.get("primaryRiskTag"), seed.get("crossRiskTag")),
            "macroRiskState": first_text(cross.get("macroRiskState"), seed.get("macroRiskState")),
            "dryRunState": first_text(seed.get("decision"), seed.get("gateDecision")),
            "outcomeState": first_text(latest_outcome.get("state")),
            "wouldExitReason": first_text(latest_outcome.get("wouldExitReason")),
            "evidenceProfile": profile,
            "blockers": blockers,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "auditLedger": LEDGER_NAME,
        }
        rows.append(row)
    return rows


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    gate, gate_path = read_json_candidate(GATE_NAME, runtime_dir, dashboard_dir, args.gate_path)
    dry_run, dry_run_path = read_json_candidate(DRY_RUN_NAME, runtime_dir, dashboard_dir, args.dry_run_path)
    outcome, outcome_path = read_json_candidate(OUTCOME_NAME, runtime_dir, dashboard_dir, args.outcome_path)
    ai_score, ai_path = read_json_candidate(AI_SCORE_NAME, runtime_dir, dashboard_dir, args.ai_score_path)
    cross, cross_path = read_json_candidate(CROSS_LINKAGE_NAME, runtime_dir, dashboard_dir, args.cross_linkage_path)
    radar, radar_path = read_json_candidate(RADAR_NAME, runtime_dir, dashboard_dir, args.radar_path)

    policy = policy_from_args(args)
    seeds = make_candidate_seed(gate, dry_run, radar)
    ai_index = index_by_market(get_rows(ai_score, "scores"))
    cross_index = index_by_market(get_rows(cross, "linkages"))
    outcome_rows = get_rows(outcome, "outcomes")
    outcome_index = index_outcomes(outcome_rows)
    outcome_profiles = build_outcome_profiles(outcome_rows)
    global_blockers = build_global_blockers(gate, dry_run, outcome, ai_score)
    isolation = build_isolation_contract(policy)
    contracts = build_candidate_contracts(
        policy=policy,
        seeds=seeds,
        global_blockers=global_blockers,
        ai_index=ai_index,
        cross_index=cross_index,
        outcome_index=outcome_index,
        outcome_profiles=outcome_profiles,
        isolation=isolation,
        max_candidates=args.max_candidates,
    )
    evidence_eligible = sum(1 for row in contracts if row.get("evidenceCanAutoAuthorize"))
    generated = utc_now_iso()
    return {
        "mode": "POLYMARKET_CANARY_EXECUTOR_CONTRACT_V2",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated,
        "status": "OK",
        "decision": "GUARDED_CANARY_CONTRACT_READY_NO_WALLET_WRITE_FROM_BUILDER",
        "summary": {
            "candidateContracts": len(contracts),
            "evidenceEligible": evidence_eligible,
            "eligibleNow": 0,
            "blocked": len(contracts) - evidence_eligible,
            "globalBlockers": len(global_blockers),
            "maxSingleBetUSDC": isolation["stakeContract"]["maxSingleBetUSDC"],
            "maxDailyLossUSDC": isolation["stakeContract"]["maxDailyLossUSDC"],
            "dryRunEvidenceRows": len(get_rows(dry_run, "dryRunOrders", "orders")),
            "outcomeEvidenceRows": len(outcome_rows),
            "aiScoreRows": len(get_rows(ai_score, "scores")),
            "crossLinkageRows": len(get_rows(cross, "linkages")),
        },
        "sourceFiles": {
            GATE_NAME: gate_path,
            DRY_RUN_NAME: dry_run_path,
            OUTCOME_NAME: outcome_path,
            AI_SCORE_NAME: ai_path,
            CROSS_LINKAGE_NAME: cross_path,
            RADAR_NAME: radar_path,
        },
        "safety": {
            "readsPrivateKey": False,
            "readsEnvSecretValues": False,
            "loadsEnv": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "startsCanaryLoop": False,
            "callsClobApi": False,
            "mutatesMt5": False,
            "mt5ExecutionAllowed": False,
            "boundary": "Builder only writes canary contract and evidence readiness. Real executor is separate and guarded.",
        },
        "globalBlockers": global_blockers,
        "isolationContract": isolation,
        "outcomeProfiles": {
            key: value for key, value in outcome_profiles.items() if key == "global" or int(value.get("samples") or 0) > 0
        },
        "candidateContracts": contracts,
        "nextActions": [
            "evidenceCanAutoAuthorize=true only means the candidate passed dry-run/AI/risk policy.",
            "Real orders still require isolated executor switches, wallet adapter verification, daily loss budget, and kill switch checks.",
            "If evidence is thin, keep collecting dry-run outcomes before allowing canary execution.",
        ],
    }


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    for row in snapshot.get("candidateContracts") or []:
        profile = row.get("evidenceProfile") if isinstance(row.get("evidenceProfile"), dict) else {}
        writer.writerow(
            {
                "generated_at": generated,
                "schema_version": row.get("schemaVersion", SCHEMA_VERSION),
                "canary_contract_id": row.get("canaryContractId", ""),
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("track", ""),
                "side": row.get("side", ""),
                "canary_state": row.get("canaryState", ""),
                "decision": row.get("decision", ""),
                "evidence_can_auto_authorize": row.get("evidenceCanAutoAuthorize", False),
                "canary_eligible_now": row.get("canaryEligibleNow", False),
                "canary_stake_usdc": row.get("canaryStakeUSDC", ""),
                "max_single_bet_usdc": row.get("maxSingleBetUSDC", ""),
                "max_daily_loss_usdc": row.get("maxDailyLossUSDC", ""),
                "samples": profile.get("samples", 0),
                "win_rate_pct": profile.get("winRatePct", 0),
                "profit_factor": profile.get("profitFactor", 0),
                "stop_loss_rate_pct": profile.get("stopLossRatePct", 0),
                "max_consecutive_losses": profile.get("maxConsecutiveLosses", 0),
                "avg_return_pct": profile.get("averageReturnPct", 0),
                "ai_score": row.get("aiScore", ""),
                "source_score": row.get("sourceScore", ""),
                "blockers": " / ".join(row.get("blockers") or []),
                "wallet_write_allowed": row.get("walletWriteAllowed", False),
                "order_send_allowed": row.get("orderSendAllowed", False),
                "starts_executor": row.get("startsExecutor", False),
            }
        )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = to_csv(snapshot)
    written: list[str] = []
    for base_dir in [runtime_dir, dashboard_dir]:
        if base_dir is None:
            continue
        atomic_write_text(base_dir / OUTPUT_NAME, json_text)
        atomic_write_text(base_dir / LEDGER_NAME, csv_text)
        written.extend([str(base_dir / OUTPUT_NAME), str(base_dir / LEDGER_NAME)])
    return written


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    written = write_outputs(
        snapshot,
        Path(args.runtime_dir),
        Path(args.dashboard_dir) if args.dashboard_dir else None,
    )
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | contracts={summary['candidateContracts']} "
        f"| evidence_eligible={summary['evidenceEligible']} | eligible_now=0 | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
