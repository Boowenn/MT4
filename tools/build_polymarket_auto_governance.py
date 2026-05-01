#!/usr/bin/env python3
"""Build Polymarket automatic promotion/demotion governance.

V2 can mark a track as eligible for a future isolated real-money canary
executor when dry-run outcome statistics, AI score, cross-market linkage, and
risk policy all pass. This script itself remains side-effect free: no wallet
secret reads, no order sends, no executor loop, and no MT5 mutation.
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
    safe_int,
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

RESEARCH_NAME = "QuantGod_PolymarketResearch.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
RADAR_WORKER_NAME = "QuantGod_PolymarketRadarWorkerV2.json"
RADAR_QUEUE_NAME = "QuantGod_PolymarketRadarCandidateQueue.json"
RETUNE_NAME = "QuantGod_PolymarketRetunePlanner.json"
AI_SCORE_NAME = "QuantGod_PolymarketAiScoreV1.json"
OUTCOME_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"
CROSS_LINKAGE_NAME = "QuantGod_PolymarketCrossMarketLinkage.json"
CANARY_CONTRACT_NAME = "QuantGod_PolymarketCanaryExecutorContract.json"

OUTPUT_NAME = "QuantGod_PolymarketAutoGovernance.json"
LEDGER_NAME = "QuantGod_PolymarketAutoGovernanceLedger.csv"
SCHEMA_VERSION = "POLYMARKET_AUTO_GOVERNANCE_V2"

LEDGER_FIELDS = [
    "generated_at",
    "schema_version",
    "governance_id",
    "market_id",
    "question",
    "track",
    "current_state",
    "governance_state",
    "recommended_action",
    "risk_level",
    "score",
    "ai_score",
    "source_score",
    "samples",
    "win_rate_pct",
    "profit_factor",
    "stop_loss_rate_pct",
    "avg_return_pct",
    "blockers",
    "next_test",
    "can_promote_to_live_execution",
    "wallet_write_allowed",
    "order_send_allowed",
    "starts_executor",
    "mutates_mt5",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--research-path", default="")
    parser.add_argument("--radar-path", default="")
    parser.add_argument("--radar-worker-path", default="")
    parser.add_argument("--radar-queue-path", default="")
    parser.add_argument("--retune-path", default="")
    parser.add_argument("--ai-score-path", default="")
    parser.add_argument("--outcome-path", default="")
    parser.add_argument("--cross-linkage-path", default="")
    parser.add_argument("--canary-path", default="")
    parser.add_argument("--max-decisions", type=int, default=60)
    parser.add_argument("--promotion-review-score", type=float, default=78.0)
    parser.add_argument("--keep-shadow-score", type=float, default=58.0)
    parser.add_argument("--demote-score", type=float, default=35.0)
    parser.add_argument("--min-dry-run-outcomes", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["minDryRunOutcomeSamples"]))
    parser.add_argument("--min-dry-run-win-rate-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunWinRatePct"]))
    parser.add_argument("--min-dry-run-profit-factor", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunProfitFactor"]))
    parser.add_argument("--max-dry-run-stop-loss-rate-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["maxDryRunStopLossRatePct"]))
    parser.add_argument("--max-dry-run-consecutive-losses", type=int, default=int(DEFAULT_REAL_MONEY_POLICY["maxDryRunConsecutiveLosses"]))
    parser.add_argument("--min-dry-run-average-return-pct", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minDryRunAverageReturnPct"]))
    parser.add_argument("--min-ai-score", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minAiScore"]))
    parser.add_argument("--min-composite-score", type=float, default=float(DEFAULT_REAL_MONEY_POLICY["minCompositeScore"]))
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
        }
    )


def extract_global_state(research: dict[str, Any]) -> dict[str, Any]:
    summary = research.get("summary") if isinstance(research.get("summary"), dict) else {}
    executed = summary.get("executed") if isinstance(summary.get("executed"), dict) else {}
    shadow = summary.get("shadow") if isinstance(summary.get("shadow"), dict) else {}
    account = research.get("accountSnapshot") if isinstance(research.get("accountSnapshot"), dict) else {}
    risk = research.get("risk") if isinstance(research.get("risk"), dict) else {}
    executed_pnl = safe_number(executed.get("realizedPnl"), safe_number(research.get("latestPnl", {}).get("realizedPnl"), 0.0)) or 0.0
    executed_pf = safe_number(executed.get("profitFactor"), None)
    shadow_pf = safe_number(shadow.get("profitFactor"), None)
    return {
        "executedPnl": executed_pnl,
        "executedProfitFactor": executed_pf,
        "executedClosed": safe_int(executed.get("closed"), 0),
        "shadowPnl": safe_number(shadow.get("realizedPnl"), 0.0) or 0.0,
        "shadowProfitFactor": shadow_pf,
        "shadowClosed": safe_int(shadow.get("closed"), 0),
        "cashUSDC": safe_number(account.get("cashUSDC"), safe_number(account.get("accountCash"), None)),
        "configuredBankrollUSDC": safe_number(account.get("configuredBankrollUSDC"), safe_number(account.get("bankroll"), None)),
        "authState": str(account.get("authState") or ""),
        "riskState": str(risk.get("state") or risk.get("riskState") or ""),
        "lossQuarantine": bool(executed_pnl < 0 or (executed_pf is not None and executed_pf < 1.0)),
    }


def global_blockers(global_state: dict[str, Any], missing_inputs: list[str]) -> list[str]:
    blockers: list[str] = []
    if global_state.get("lossQuarantine"):
        blockers.append("GLOBAL_LOSS_QUARANTINE")
    if global_state.get("executedProfitFactor") is not None and float(global_state["executedProfitFactor"]) < 1.0:
        blockers.append("EXECUTED_PF_BELOW_1")
    cash = global_state.get("cashUSDC")
    bankroll = global_state.get("configuredBankrollUSDC")
    if cash is not None and bankroll is not None and float(cash) < min(float(bankroll), 1.0):
        blockers.append("ACCOUNT_CASH_BELOW_BANKROLL")
    blockers.extend(f"MISSING_{name}" for name in missing_inputs)
    return unique(blockers)


def make_seed_rows(
    canary: dict[str, Any],
    ai_score: dict[str, Any],
    retune: dict[str, Any],
    radar_queue: dict[str, Any],
    radar_worker: dict[str, Any],
    radar: dict[str, Any],
) -> list[dict[str, Any]]:
    seeds: dict[str, dict[str, Any]] = {}

    def add(row: dict[str, Any], source: str) -> None:
        if not isinstance(row, dict):
            return
        key = market_key(row) or first_text(row.get("question"), row.get("track"), row.get("candidateId"))
        if not key:
            return
        current = seeds.setdefault(key, {"sourceTypes": []})
        current.update({k: v for k, v in row.items() if v not in (None, "")})
        current["sourceTypes"] = unique([*(current.get("sourceTypes") or []), source])

    for row in get_rows(canary, "candidateContracts"):
        add(row, "canary")
    for row in get_rows(ai_score, "scores"):
        add(row, "ai-score")
    for row in get_rows(retune, "recommendations", "retuneRecommendations"):
        add(row, "retune")
    for row in get_rows(radar_queue, "queue", "candidateQueue", "candidates"):
        add(row, "worker-queue")
    for row in radar_worker.get("candidateQueue") if isinstance(radar_worker.get("candidateQueue"), list) else []:
        if isinstance(row, dict):
            add(row, "worker-v2")
    for row in get_rows(radar, "radar"):
        add(row, "radar")
    return list(seeds.values())


def score_for(seed: dict[str, Any], ai: dict[str, Any]) -> float:
    score = safe_number(seed.get("score"), safe_number(seed.get("sourceScore"), None))
    if score is None:
        score = safe_number(seed.get("aiRuleScore"), safe_number(seed.get("radarScore"), 0.0)) or 0.0
    ai_value = safe_number(ai.get("score"), safe_number(seed.get("aiScore"), None))
    if ai_value is not None:
        score = (float(score) * 0.45) + (float(ai_value) * 0.55)
    return round(float(score or 0.0), 3)


def classify_decision(
    score: float,
    real_money_ready: bool,
    readiness_blockers: list[str],
    global_blocker_list: list[str],
    args: argparse.Namespace,
) -> tuple[str, str, str, str]:
    all_blockers = set(readiness_blockers + global_blocker_list)
    if {"GLOBAL_LOSS_QUARANTINE", "ACCOUNT_CASH_BELOW_BANKROLL", "EXECUTED_PF_BELOW_1"}.intersection(all_blockers):
        return (
            "QUARANTINE_NO_PROMOTION",
            "进入隔离：不允许真钱 canary，继续只读研究和 dry-run。",
            "high",
            "风险隔离：历史哨兵/模拟表现为负，先复盘亏损来源并补齐退出后验；继续只读/dry-run，禁止自动下注。",
        )
    if real_money_ready:
        return (
            "AUTO_CANARY_EXECUTION_ELIGIBLE",
            "证据达标：允许 isolated executor 在开关与钱包适配器全部通过后自动开小额 canary。",
            "low",
            "只允许 0/1 个小额 canary，继续跟踪 TP/SL、撤单、退出与日亏预算。",
        )
    if score < args.demote_score or "AI_COLOR_RED_BLOCKED" in all_blockers:
        return (
            "DEMOTE_TO_RESEARCH_ONLY",
            "降级到 research-only：停止 canary 候选，重新设计筛选或题材边界。",
            "high",
            "回到机会雷达和单市场分析，先做反例归因。",
        )
    if score < args.keep_shadow_score or "SIM_PROFIT_FACTOR_LT_MIN" in all_blockers or "SIM_WIN_RATE_LT_MIN" in all_blockers:
        return (
            "RETUNE_REQUIRED",
            "继续模拟重调：当前 dry-run 胜率/PF/收益风险未达到真钱 canary 门槛。",
            "medium",
            "优先调整筛选、价格边界、止损止盈和超时退出参数。",
        )
    if score >= args.promotion_review_score:
        return (
            "PROMOTION_REVIEW_DRY_RUN",
            "评分较强但证据不完整：继续 dry-run，不开放真钱。",
            "watch",
            "补齐 outcome 样本、AI 风险和 cross-market 联动后再复核。",
        )
    return (
        "KEEP_SHADOW_COLLECT_EVIDENCE",
        "保持 shadow/dry-run：样本还不够或缺关键证据。",
        "watch",
        "继续收集 Worker/AI/dry-run/outcome 证据。",
    )


def build_decisions(
    args: argparse.Namespace,
    policy: dict[str, Any],
    seeds: list[dict[str, Any]],
    ai_index: dict[str, dict[str, Any]],
    cross_index: dict[str, dict[str, Any]],
    outcome_index: dict[str, dict[str, Any]],
    outcome_profiles: dict[str, dict[str, Any]],
    global_blocker_list: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in seeds[: max(1, args.max_decisions)]:
        market_id = market_key(seed)
        track = first_text(track_key(seed), "poly_shadow")
        tracking_key = str(seed.get("trackingKey") or "").strip()
        ai = ai_index.get(market_id) or {}
        cross = cross_index.get(market_id) or {}
        outcome = outcome_index.get(tracking_key) or outcome_index.get(market_id) or {}
        score = score_for(seed, ai)
        profile = choose_evidence_profile(seed, outcome_profiles, int(policy["minDryRunOutcomeSamples"]))
        real_ready, readiness_blockers = evaluate_real_money_readiness(
            candidate=seed,
            ai=ai,
            cross=cross,
            evidence_profile=profile,
            composite_score=score,
            policy=policy,
            global_blockers=global_blocker_list,
        )
        governance_state, action, risk_level, next_test = classify_decision(
            score, real_ready, readiness_blockers, global_blocker_list, args
        )
        row_id = "GOV-" + stable_id(market_id, seed.get("question"), track, governance_state)
        row = {
            "governanceId": row_id,
            "schemaVersion": SCHEMA_VERSION,
            "marketId": market_id,
            "question": first_text(seed.get("question"), ai.get("question"), cross.get("question"), seed.get("eventTitle")),
            "polymarketUrl": first_text(seed.get("polymarketUrl"), seed.get("url"), ai.get("polymarketUrl"), cross.get("polymarketUrl")),
            "track": track,
            "currentState": first_text(seed.get("canaryState"), seed.get("queueState"), seed.get("state"), "SHADOW_OR_RESEARCH"),
            "governanceState": governance_state,
            "recommendedAction": action,
            "riskLevel": risk_level,
            "score": score,
            "aiScore": safe_number(ai.get("score"), safe_number(seed.get("aiScore"), None)),
            "sourceScore": safe_number(seed.get("sourceScore"), safe_number(seed.get("aiRuleScore"), None)),
            "aiColor": first_text(ai.get("color"), seed.get("aiColor")),
            "canaryState": first_text(seed.get("canaryState")),
            "dryRunState": first_text(seed.get("dryRunState"), seed.get("decision")),
            "outcomeState": first_text(outcome.get("state")),
            "wouldExitReason": first_text(outcome.get("wouldExitReason")),
            "crossRiskTag": first_text(cross.get("primaryRiskTag"), seed.get("crossRiskTag")),
            "macroRiskState": first_text(cross.get("macroRiskState"), seed.get("macroRiskState")),
            "evidenceProfile": profile,
            "blockers": readiness_blockers,
            "sourceTypes": seed.get("sourceTypes") or [],
            "nextTest": next_test,
            "autoExecutorPermission": "CANARY_EXECUTOR_ALLOWED_WHEN_RUNTIME_SWITCHES_ON" if real_ready else "BLOCKED",
            "canPromoteToLiveExecution": real_ready,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "auditLedger": LEDGER_NAME,
        }
        rows.append(row)
    rows.sort(key=lambda item: (0 if item["canPromoteToLiveExecution"] else 1, str(item["governanceState"]), -float(item.get("score") or 0.0)))
    return rows


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    research, research_path = read_json_candidate(RESEARCH_NAME, runtime_dir, dashboard_dir, args.research_path)
    radar, radar_path = read_json_candidate(RADAR_NAME, runtime_dir, dashboard_dir, args.radar_path)
    radar_worker, radar_worker_path = read_json_candidate(RADAR_WORKER_NAME, runtime_dir, dashboard_dir, args.radar_worker_path)
    radar_queue, radar_queue_path = read_json_candidate(RADAR_QUEUE_NAME, runtime_dir, dashboard_dir, args.radar_queue_path)
    retune, retune_path = read_json_candidate(RETUNE_NAME, runtime_dir, dashboard_dir, args.retune_path)
    ai_score, ai_path = read_json_candidate(AI_SCORE_NAME, runtime_dir, dashboard_dir, args.ai_score_path)
    outcome, outcome_path = read_json_candidate(OUTCOME_NAME, runtime_dir, dashboard_dir, args.outcome_path)
    cross, cross_path = read_json_candidate(CROSS_LINKAGE_NAME, runtime_dir, dashboard_dir, args.cross_linkage_path)
    canary, canary_path = read_json_candidate(CANARY_CONTRACT_NAME, runtime_dir, dashboard_dir, args.canary_path)

    source_files = {
        RESEARCH_NAME: research_path,
        RADAR_NAME: radar_path,
        RADAR_WORKER_NAME: radar_worker_path,
        RADAR_QUEUE_NAME: radar_queue_path,
        RETUNE_NAME: retune_path,
        AI_SCORE_NAME: ai_path,
        OUTCOME_NAME: outcome_path,
        CROSS_LINKAGE_NAME: cross_path,
        CANARY_CONTRACT_NAME: canary_path,
    }
    missing_inputs = [name for name, path in source_files.items() if not path]
    policy = policy_from_args(args)
    seeds = make_seed_rows(canary, ai_score, retune, radar_queue, radar_worker, radar)
    ai_index = index_by_market(get_rows(ai_score, "scores"))
    cross_index = index_by_market(get_rows(cross, "linkages"))
    outcome_rows = get_rows(outcome, "outcomes")
    outcome_index = index_outcomes(outcome_rows)
    outcome_profiles = build_outcome_profiles(outcome_rows)
    global_state = extract_global_state(research)
    global_blocker_list = global_blockers(global_state, missing_inputs)
    decisions = build_decisions(
        args,
        policy,
        seeds,
        ai_index,
        cross_index,
        outcome_index,
        outcome_profiles,
        global_blocker_list,
    )
    counts = {
        "totalDecisions": len(decisions),
        "autoCanaryEligible": sum(1 for row in decisions if row["governanceState"] == "AUTO_CANARY_EXECUTION_ELIGIBLE"),
        "promotionReview": sum(1 for row in decisions if row["governanceState"] == "PROMOTION_REVIEW_DRY_RUN"),
        "keepShadow": sum(1 for row in decisions if row["governanceState"] == "KEEP_SHADOW_COLLECT_EVIDENCE"),
        "retune": sum(1 for row in decisions if row["governanceState"] == "RETUNE_REQUIRED"),
        "demote": sum(1 for row in decisions if row["governanceState"] == "DEMOTE_TO_RESEARCH_ONLY"),
        "quarantine": sum(1 for row in decisions if row["governanceState"] == "QUARANTINE_NO_PROMOTION"),
    }
    generated = utc_now_iso()
    return {
        "mode": "POLYMARKET_AUTO_GOVERNANCE_V2",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated,
        "status": "OK",
        "decision": "AUTO_GOVERNANCE_WITH_REAL_MONEY_CANARY_GATE_NO_WALLET_WRITE",
        "sourceFiles": source_files,
        "globalState": global_state,
        "globalBlockers": global_blocker_list,
        "realMoneyPromotionPolicy": policy,
        "summary": {
            **counts,
            "inputSeeds": len(seeds),
            "aiScoreRows": len(get_rows(ai_score, "scores")),
            "crossLinkageRows": len(get_rows(cross, "linkages")),
            "dryRunOutcomeRows": len(outcome_rows),
            "canaryContractRows": len(get_rows(canary, "candidateContracts")),
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
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
            "boundary": "Governance writes eligibility only. Executor must independently re-check all guardrails.",
        },
        "governanceDecisions": decisions,
        "nextActions": [
            "AUTO_CANARY_EXECUTION_ELIGIBLE 才允许 isolated executor 在 runtime 开关通过后考虑真钱 canary。",
            "RETUNE_REQUIRED 和 DEMOTE_TO_RESEARCH_ONLY 不得下注，只能进入重调与研究。",
            "QUARANTINE_NO_PROMOTION 会阻断所有真钱权限。",
            "真钱 executor 必须再次验证样本、AI 风险、预算、kill switch 和钱包适配器。",
        ],
    }


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    for row in snapshot.get("governanceDecisions") or []:
        profile = row.get("evidenceProfile") if isinstance(row.get("evidenceProfile"), dict) else {}
        writer.writerow(
            {
                "generated_at": generated,
                "schema_version": row.get("schemaVersion", SCHEMA_VERSION),
                "governance_id": row.get("governanceId", ""),
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("track", ""),
                "current_state": row.get("currentState", ""),
                "governance_state": row.get("governanceState", ""),
                "recommended_action": row.get("recommendedAction", ""),
                "risk_level": row.get("riskLevel", ""),
                "score": row.get("score", ""),
                "ai_score": row.get("aiScore", ""),
                "source_score": row.get("sourceScore", ""),
                "samples": profile.get("samples", 0),
                "win_rate_pct": profile.get("winRatePct", 0),
                "profit_factor": profile.get("profitFactor", 0),
                "stop_loss_rate_pct": profile.get("stopLossRatePct", 0),
                "avg_return_pct": profile.get("averageReturnPct", 0),
                "blockers": " / ".join(row.get("blockers") or []),
                "next_test": row.get("nextTest", ""),
                "can_promote_to_live_execution": row.get("canPromoteToLiveExecution", False),
                "wallet_write_allowed": row.get("walletWriteAllowed", False),
                "order_send_allowed": row.get("orderSendAllowed", False),
                "starts_executor": row.get("startsExecutor", False),
                "mutates_mt5": row.get("mutatesMt5", False),
            }
        )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = to_csv(snapshot)
    targets = [runtime_dir]
    if dashboard_dir:
        targets.append(dashboard_dir)
    written: list[str] = []
    for target_dir in targets:
        atomic_write_text(target_dir / OUTPUT_NAME, json_text)
        atomic_write_text(target_dir / LEDGER_NAME, csv_text)
        written.extend([str(target_dir / OUTPUT_NAME), str(target_dir / LEDGER_NAME)])
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
        f"{snapshot['mode']} | decisions={summary['totalDecisions']} "
        f"| auto_canary={summary['autoCanaryEligible']} | quarantine={summary['quarantine']} "
        f"| wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
