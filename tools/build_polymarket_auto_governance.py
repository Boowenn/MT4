#!/usr/bin/env python3
"""Build Polymarket automatic promotion/demotion governance recommendations.

This is a governance layer, not an executor. It reads existing research,
history-aware AI score, dry-run outcome, cross-market linkage, Worker V2,
retune, and canary-contract evidence, then writes auditable promotion/demotion
states for shadow tracks. It never reads wallet secrets, writes wallets, calls
CLOB/order APIs, starts an executor, or mutates MT5.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
SCHEMA_VERSION = "POLYMARKET_AUTO_GOVERNANCE_V1"

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
    "canary_state",
    "dry_run_state",
    "outcome_state",
    "cross_risk_tag",
    "macro_risk_state",
    "blockers",
    "next_test",
    "wallet_write_allowed",
    "order_send_allowed",
    "starts_executor",
    "mutates_mt5",
]

HARD_EXECUTION_BLOCKERS = [
    "WALLET_WRITE_DISABLED",
    "ORDER_SEND_DISABLED",
    "REAL_WALLET_EXECUTOR_NOT_WIRED",
    "CANARY_ENABLE_SWITCH_FALSE",
    "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
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
    parser.add_argument("--min-dry-run-outcomes", type=int, default=3)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_json_candidate(name: str, runtime_dir: Path, dashboard_dir: Path, explicit: str = "") -> tuple[dict[str, Any], str]:
    candidates = [Path(explicit)] if explicit else []
    candidates.extend([dashboard_dir / name, runtime_dir / name])
    for path in candidates:
        if not path or not path.exists():
            continue
        data = load_json(path)
        if data:
            return data, str(path)
    return {}, ""


def safe_number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def get_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def market_key(row: dict[str, Any]) -> str:
    return str(row.get("marketId") or row.get("market_id") or "").strip()


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def index_by_market(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = market_key(row)
        if key and key not in out:
            out[key] = row
    return out


def index_outcomes(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in (str(row.get("trackingKey") or "").strip(), market_key(row)):
            if key and key not in out:
                out[key] = row
    return out


def extract_global_state(research: dict[str, Any]) -> dict[str, Any]:
    summary = research.get("summary") if isinstance(research.get("summary"), dict) else {}
    executed = summary.get("executed") if isinstance(summary.get("executed"), dict) else {}
    shadow = summary.get("shadow") if isinstance(summary.get("shadow"), dict) else {}
    account = research.get("accountSnapshot") if isinstance(research.get("accountSnapshot"), dict) else {}
    risk = research.get("risk") if isinstance(research.get("risk"), dict) else {}
    executed_pnl = safe_number(executed.get("realizedPnl"), 0.0) or 0.0
    shadow_pnl = safe_number(shadow.get("realizedPnl"), 0.0) or 0.0
    executed_pf = safe_number(executed.get("profitFactor"), None)
    shadow_pf = safe_number(shadow.get("profitFactor"), None)
    return {
        "executedPnl": executed_pnl,
        "shadowPnl": shadow_pnl,
        "executedProfitFactor": executed_pf,
        "shadowProfitFactor": shadow_pf,
        "executedClosed": safe_int(executed.get("closed"), 0),
        "shadowClosed": safe_int(shadow.get("closed"), 0),
        "cashUSDC": safe_number(account.get("cashUSDC"), None),
        "configuredBankrollUSDC": safe_number(account.get("configuredBankrollUSDC"), None),
        "authState": str(account.get("authState") or ""),
        "riskState": str(risk.get("state") or risk.get("riskState") or ""),
        "lossQuarantine": bool(executed_pnl < 0 or (executed_pf is not None and executed_pf < 1.0)),
    }


def global_blockers(global_state: dict[str, Any], missing_inputs: list[str]) -> list[str]:
    blockers: list[str] = []
    if global_state.get("lossQuarantine"):
        blockers.append("GLOBAL_LOSS_QUARANTINE")
    if (global_state.get("executedProfitFactor") is not None and float(global_state["executedProfitFactor"]) < 1.0):
        blockers.append("EXECUTED_PF_BELOW_1")
    if (global_state.get("shadowProfitFactor") is not None and float(global_state["shadowProfitFactor"]) < 1.0):
        blockers.append("SHADOW_PF_BELOW_1")
    cash = global_state.get("cashUSDC")
    bankroll = global_state.get("configuredBankrollUSDC")
    if cash is not None and bankroll is not None and float(cash) < min(float(bankroll), 1.0):
        blockers.append("ACCOUNT_CASH_BELOW_BANKROLL")
    blockers.extend(f"MISSING_{name}" for name in missing_inputs)
    blockers.extend(HARD_EXECUTION_BLOCKERS)
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
    worker_queue = radar_worker.get("candidateQueue") if isinstance(radar_worker.get("candidateQueue"), list) else []
    for row in worker_queue:
        if isinstance(row, dict):
            add(row, "worker-v2")
    for row in get_rows(radar, "radar"):
        add(row, "radar")
    return list(seeds.values())


def score_for(seed: dict[str, Any], ai: dict[str, Any]) -> float:
    score = safe_number(seed.get("score"), None)
    if score is None:
        score = safe_number(seed.get("sourceScore"), None)
    if score is None:
        score = safe_number(seed.get("aiRuleScore"), None)
    ai_value = safe_number(ai.get("score"), None)
    if score is None and ai_value is not None:
        score = ai_value
    if score is not None and ai_value is not None:
        score = (float(score) * 0.45) + (float(ai_value) * 0.55)
    return round(float(score or 0.0), 3)


def row_blockers(
    seed: dict[str, Any],
    ai: dict[str, Any],
    cross: dict[str, Any],
    outcome: dict[str, Any],
    score: float,
    args: argparse.Namespace,
) -> list[str]:
    blockers: list[str] = []
    ai_color = str(ai.get("color") or seed.get("aiColor") or "").lower()
    ai_score = safe_number(ai.get("score"), safe_number(seed.get("aiScore"), None))
    risk_text = str(seed.get("risk") or ai.get("risk") or cross.get("sourceRisk") or "").lower()
    canary_blockers = seed.get("blockers") if isinstance(seed.get("blockers"), list) else []
    blockers.extend(str(item) for item in canary_blockers)
    if ai_color in {"red", "yellow"}:
        blockers.append(f"AI_SCORE_{ai_color.upper()}_REVIEW")
    if ai_score is not None and float(ai_score) < args.keep_shadow_score:
        blockers.append("AI_SCORE_BELOW_KEEP_SHADOW_MIN")
    if score < args.demote_score:
        blockers.append("COMPOSITE_SCORE_DEMOTE_ZONE")
    if risk_text and risk_text not in {"low", "green"}:
        blockers.append("MARKET_RISK_NOT_LOW")
    macro_state = str(cross.get("macroRiskState") or seed.get("macroRiskState") or "").upper()
    if macro_state in {"HIGH", "RISK_ON", "REVIEW"}:
        blockers.append("CROSS_MARKET_RISK_REVIEW")
    if cross and cross.get("mt5ExecutionAllowed") is not False:
        blockers.append("CROSS_LINKAGE_BOUNDARY_UNCLEAR")
    if not outcome:
        blockers.append("NO_DRY_RUN_OUTCOME_EVIDENCE")
    elif str(outcome.get("state") or "").startswith("WOULD_EXIT"):
        blockers.append("DRY_RUN_EXIT_TRIGGERED_REVIEW")
    if seed.get("canaryEligibleNow") is False:
        blockers.append("CANARY_NOT_ELIGIBLE_NOW")
    return unique(blockers)


def classify_decision(
    score: float,
    blockers: list[str],
    global_blocker_list: list[str],
    args: argparse.Namespace,
) -> tuple[str, str, str, str]:
    all_blockers = set(blockers + global_blocker_list)
    hard_quarantine = {
        "GLOBAL_LOSS_QUARANTINE",
        "ACCOUNT_CASH_BELOW_BANKROLL",
        "EXECUTED_PF_BELOW_1",
        "DRY_RUN_EXIT_TRIGGERED_REVIEW",
    }
    if all_blockers.intersection(hard_quarantine):
        return (
            "QUARANTINE_NO_PROMOTION",
            "禁止提升，保留研究/影子观察",
            "high",
            "先修复亏损隔离、退出后验或资金/风险证据，再重新评分。",
        )
    if score < args.demote_score or "AI_SCORE_RED_REVIEW" in all_blockers:
        return (
            "DEMOTE_TO_RESEARCH_ONLY",
            "降级到 research-only，停止进入 canary 候选",
            "high",
            "重跑单市场分析、重调筛选参数，只有新证据转绿后再回到影子队列。",
        )
    if score < args.keep_shadow_score or "MARKET_RISK_NOT_LOW" in all_blockers or "CROSS_MARKET_RISK_REVIEW" in all_blockers:
        return (
            "RETUNE_REQUIRED",
            "保持影子，进入重调队列",
            "medium",
            "优先调整筛选阈值、风险标签和退出参数，再生成新的 dry-run 样本。",
        )
    promotion_blockers = all_blockers.difference(HARD_EXECUTION_BLOCKERS).difference(
        {
            "CANARY_NOT_ELIGIBLE_NOW",
            "CANARY_ENABLE_SWITCH_FALSE",
            "OPERATOR_PROMOTION_REQUIRED",
            "REAL_WALLET_EXECUTOR_NOT_WIRED",
            "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
            "WALLET_WRITE_DISABLED",
            "ORDER_SEND_DISABLED",
        }
    )
    if score >= args.promotion_review_score and not promotion_blockers:
        return (
            "PROMOTION_REVIEW_SHADOW_ONLY",
            "进入人工提升复核，但仍不允许真实下注",
            "low",
            "补齐人工复核、隔离钱包只读确认、canary 审计账本后，才允许考虑小额执行器。",
        )
    return (
        "KEEP_SHADOW_COLLECT_EVIDENCE",
        "继续影子采样",
        "watch",
        "继续积累 Worker/AI/dry-run/outcome 后验；样本足够后自动重新治理。",
    )


def build_decisions(
    args: argparse.Namespace,
    seeds: list[dict[str, Any]],
    ai_index: dict[str, dict[str, Any]],
    cross_index: dict[str, dict[str, Any]],
    outcome_index: dict[str, dict[str, Any]],
    global_blocker_list: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in seeds[: max(1, args.max_decisions)]:
        market_id = market_key(seed)
        track = first_text(seed.get("track"), seed.get("suggestedShadowTrack"), seed.get("shadowTrack"), "poly_shadow")
        tracking_key = str(seed.get("trackingKey") or "").strip()
        ai = ai_index.get(market_id) or {}
        cross = cross_index.get(market_id) or {}
        outcome = outcome_index.get(tracking_key) or outcome_index.get(market_id) or {}
        score = score_for(seed, ai)
        blockers = unique([*global_blocker_list, *row_blockers(seed, ai, cross, outcome, score, args)])
        governance_state, action, risk_level, next_test = classify_decision(score, blockers, global_blocker_list, args)
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
            "blockers": blockers,
            "sourceTypes": seed.get("sourceTypes") or [],
            "nextTest": next_test,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "canPromoteToLiveExecution": False,
            "auditLedger": LEDGER_NAME,
        }
        rows.append(row)
    rows.sort(key=lambda item: (str(item["governanceState"]), -float(item.get("score") or 0.0)))
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
    seeds = make_seed_rows(canary, ai_score, retune, radar_queue, radar_worker, radar)
    ai_index = index_by_market(get_rows(ai_score, "scores"))
    cross_index = index_by_market(get_rows(cross, "linkages"))
    outcome_rows = get_rows(outcome, "outcomes")
    outcome_index = index_outcomes(outcome_rows)
    global_state = extract_global_state(research)
    global_blocker_list = global_blockers(global_state, missing_inputs)
    decisions = build_decisions(args, seeds, ai_index, cross_index, outcome_index, global_blocker_list)
    counts = {
        "totalDecisions": len(decisions),
        "promotionReview": sum(1 for row in decisions if row["governanceState"] == "PROMOTION_REVIEW_SHADOW_ONLY"),
        "keepShadow": sum(1 for row in decisions if row["governanceState"] == "KEEP_SHADOW_COLLECT_EVIDENCE"),
        "retune": sum(1 for row in decisions if row["governanceState"] == "RETUNE_REQUIRED"),
        "demote": sum(1 for row in decisions if row["governanceState"] == "DEMOTE_TO_RESEARCH_ONLY"),
        "quarantine": sum(1 for row in decisions if row["governanceState"] == "QUARANTINE_NO_PROMOTION"),
    }
    generated = utc_now_iso()
    return {
        "mode": "POLYMARKET_AUTO_GOVERNANCE_V1",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated,
        "status": "OK",
        "decision": "AUTO_GOVERNANCE_RECOMMENDATIONS_ONLY_NO_WALLET_WRITE",
        "sourceFiles": source_files,
        "globalState": global_state,
        "globalBlockers": global_blocker_list,
        "policy": {
            "promotionReviewScore": args.promotion_review_score,
            "keepShadowScore": args.keep_shadow_score,
            "demoteScore": args.demote_score,
            "minDryRunOutcomes": args.min_dry_run_outcomes,
            "promotionNeverEnablesWalletByItself": True,
            "demotionCanBeAutomatic": True,
            "walletExecutorRequiresSeparateModule": True,
        },
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
            "canPromoteToLiveExecution": False,
            "boundary": "Automatic governance only writes recommendations and audit rows.",
        },
        "governanceDecisions": decisions,
        "nextActions": [
            "Use QUARANTINE_NO_PROMOTION and DEMOTE_TO_RESEARCH_ONLY rows to stop weak tracks from entering canary review.",
            "Use RETUNE_REQUIRED rows to create new shadow-only parameter/risk filter experiments.",
            "Use PROMOTION_REVIEW_SHADOW_ONLY only as a human review queue; it does not permit wallet writes.",
            "Before any real executor, require separate wallet isolation, order audit, position ledger, exit ledger, and kill switch verification.",
        ],
    }


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    for row in snapshot.get("governanceDecisions") or []:
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
                "canary_state": row.get("canaryState", ""),
                "dry_run_state": row.get("dryRunState", ""),
                "outcome_state": row.get("outcomeState", ""),
                "cross_risk_tag": row.get("crossRiskTag", ""),
                "macro_risk_state": row.get("macroRiskState", ""),
                "blockers": " / ".join(row.get("blockers") or []),
                "next_test": row.get("nextTest", ""),
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
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | decisions={summary['totalDecisions']} "
        f"| promote_review={summary['promotionReview']} | quarantine={summary['quarantine']} "
        f"| wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
