#!/usr/bin/env python3
"""Build a contract-only Polymarket canary executor design.

This is not an executor. V1 only records the isolation design, small canary
budget, TP/SL contract, kill switches, and per-market blockers that a future
wallet executor must obey. It never imports Polymarket app modules, reads
private keys, reads env secret values, calls CLOB/order APIs, starts a canary
loop, writes wallets, or mutates MT5.
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

GATE_NAME = "QuantGod_PolymarketExecutionGate.json"
DRY_RUN_NAME = "QuantGod_PolymarketDryRunOrders.json"
OUTCOME_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"
AI_SCORE_NAME = "QuantGod_PolymarketAiScoreV1.json"
CROSS_LINKAGE_NAME = "QuantGod_PolymarketCrossMarketLinkage.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"

OUTPUT_NAME = "QuantGod_PolymarketCanaryExecutorContract.json"
LEDGER_NAME = "QuantGod_PolymarketCanaryExecutorLedger.csv"
SCHEMA_VERSION = "POLYMARKET_CANARY_EXECUTOR_CONTRACT_V1"


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
    "canary_eligible_now",
    "reference_stake_usdc",
    "canary_stake_usdc",
    "max_single_bet_usdc",
    "max_daily_loss_usdc",
    "take_profit_pct",
    "stop_loss_pct",
    "trailing_profit_pct",
    "cancel_unfilled_minutes",
    "max_hold_hours",
    "exit_before_resolution_hours",
    "source_score",
    "ai_score",
    "cross_risk_tag",
    "dry_run_state",
    "outcome_state",
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
    parser.add_argument("--min-ai-score", type=float, default=65.0)
    parser.add_argument("--max-single-bet-usdc", type=float, default=1.0)
    parser.add_argument("--max-daily-loss-usdc", type=float, default=3.0)
    parser.add_argument("--max-open-canary-positions", type=int, default=1)
    parser.add_argument("--take-profit-pct", type=float, default=18.0)
    parser.add_argument("--stop-loss-pct", type=float, default=10.0)
    parser.add_argument("--trailing-profit-pct", type=float, default=8.0)
    parser.add_argument("--cancel-unfilled-minutes", type=int, default=15)
    parser.add_argument("--max-hold-hours", type=float, default=36.0)
    parser.add_argument("--exit-before-resolution-hours", type=float, default=12.0)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


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


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def by_market(rows: list[dict[str, Any]], market_keys: tuple[str, ...] = ("marketId", "market_id")) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in market_keys:
            market_id = str(row.get(key) or "").strip()
            if market_id:
                out.setdefault(market_id, row)
                break
    return out


def get_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def make_candidate_seed(gate: dict[str, Any], dry_run: dict[str, Any], radar: dict[str, Any]) -> list[dict[str, Any]]:
    dry_orders = get_rows(dry_run, "dryRunOrders", "orders")
    if dry_orders:
        return dry_orders
    gate_rows = get_rows(gate, "marketDecisions")
    if gate_rows:
        return gate_rows
    return get_rows(radar, "radar")


def get_ai_score(ai_index: dict[str, dict[str, Any]], market_id: str) -> dict[str, Any]:
    return ai_index.get(market_id) or {}


def get_cross_link(cross_index: dict[str, dict[str, Any]], market_id: str) -> dict[str, Any]:
    return cross_index.get(market_id) or {}


def get_outcome(outcome_index: dict[str, dict[str, Any]], market_id: str, tracking_key: str) -> dict[str, Any]:
    if tracking_key and tracking_key in outcome_index:
        return outcome_index[tracking_key]
    if market_id and market_id in outcome_index:
        return outcome_index[market_id]
    return {}


def build_global_blockers(gate: dict[str, Any], dry_run: dict[str, Any], outcome: dict[str, Any]) -> list[str]:
    blockers = [
        "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
        "REAL_WALLET_EXECUTOR_NOT_WIRED",
        "CANARY_ENABLE_SWITCH_FALSE",
        "WALLET_WRITE_DISABLED",
        "ORDER_SEND_DISABLED",
        "OPERATOR_PROMOTION_REQUIRED",
    ]
    if not gate:
        blockers.append("EXECUTION_GATE_MISSING")
    if not dry_run:
        blockers.append("DRY_RUN_ORDER_LAYER_MISSING")
    if not outcome:
        blockers.append("DRY_RUN_OUTCOME_LAYER_MISSING")
    blockers.extend(str(item) for item in (gate.get("globalBlockers") or []))
    return unique(blockers)


def evidence_blockers(
    seed: dict[str, Any],
    ai: dict[str, Any],
    cross: dict[str, Any],
    outcome: dict[str, Any],
    args: argparse.Namespace,
) -> list[str]:
    blockers: list[str] = []
    if seed.get("canOpenDryRun") is False or seed.get("canBet") is False:
        blockers.append("DRY_RUN_OR_GATE_NOT_OPEN")
    if not outcome:
        blockers.append("NO_DRY_RUN_OUTCOME_EVIDENCE")
    elif str(outcome.get("state") or "").startswith("WOULD_EXIT"):
        blockers.append("DRY_RUN_EXIT_TRIGGERED_REVIEW")
    ai_score = safe_number(ai.get("score"), None)
    ai_color = str(ai.get("color") or "").lower()
    if ai and ai_score is not None and ai_score < args.min_ai_score:
        blockers.append("AI_SCORE_BELOW_CANARY_MIN")
    if ai_color in {"red", "yellow"}:
        blockers.append(f"AI_SCORE_{ai_color.upper()}_REVIEW")
    risk = str(seed.get("risk") or ai.get("risk") or cross.get("sourceRisk") or "").lower()
    if risk and risk not in {"low", "green"}:
        blockers.append("MARKET_RISK_NOT_LOW")
    macro_state = str(cross.get("macroRiskState") or "").upper()
    if macro_state in {"HIGH", "RISK_ON", "REVIEW"}:
        blockers.append("CROSS_MARKET_RISK_REVIEW")
    if cross and cross.get("mt5ExecutionAllowed") is not False:
        blockers.append("CROSS_LINKAGE_BOUNDARY_UNCLEAR")
    return unique(blockers)


def build_isolation_contract(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
        "schemaVersion": SCHEMA_VERSION,
        "canStartExecutor": False,
        "canaryLoopAllowed": False,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "readsPrivateKey": False,
        "readsEnvSecretValues": False,
        "callsClobApi": False,
        "mutatesMt5": False,
        "isolatedRuntime": {
            "requiredRoot": "runtime/Polymarket_Canary_Isolated",
            "separateProcessRequired": True,
            "sharedMt5RuntimeAllowed": False,
            "sharedPolymarketExecutorAllowed": False,
            "allowedInputs": [
                "QuantGod_PolymarketExecutionGate.json",
                "QuantGod_PolymarketDryRunOrders.json",
                "QuantGod_PolymarketDryRunOutcomeWatcher.json",
                "QuantGod_PolymarketAiScoreV1.json",
                "QuantGod_PolymarketCrossMarketLinkage.json",
            ],
            "forbiddenInputs": [
                "MT5 account equity as Polymarket bankroll",
                "D:\\polymarket live executor loop as shared authority",
                "raw wallet/private-key values in dashboard JSON",
            ],
        },
        "operatorSwitchContract": {
            "requiredFutureEnvNames": [
                "QG_POLYMARKET_CANARY_ENABLE",
                "QG_POLYMARKET_CANARY_MAX_STAKE_USDC",
                "QG_POLYMARKET_CANARY_DAILY_LOSS_USDC",
                "QG_POLYMARKET_CANARY_MARKET_ALLOWLIST",
                "QG_POLYMARKET_CANARY_KILL_SWITCH",
            ],
            "note": "V1 records variable names only and does not read env values.",
        },
        "stakeContract": {
            "maxSingleBetUSDC": round(args.max_single_bet_usdc, 2),
            "maxDailyLossUSDC": round(args.max_daily_loss_usdc, 2),
            "maxOpenCanaryPositions": max(0, args.max_open_canary_positions),
            "perMarketExposureUSDC": round(args.max_single_bet_usdc, 2),
            "currentCanaryStakeUSDC": 0.0,
        },
        "exitContract": {
            "takeProfitPct": round(args.take_profit_pct, 2),
            "stopLossPct": round(args.stop_loss_pct, 2),
            "trailingProfitPct": round(args.trailing_profit_pct, 2),
            "cancelUnfilledAfterMinutes": max(1, args.cancel_unfilled_minutes),
            "maxHoldHours": round(args.max_hold_hours, 2),
            "exitBeforeResolutionHours": round(args.exit_before_resolution_hours, 2),
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
            "futureRequiredLedgers": [
                "QuantGod_PolymarketCanaryOrderAuditLedger.csv",
                "QuantGod_PolymarketCanaryPositionLedger.csv",
                "QuantGod_PolymarketCanaryExitLedger.csv",
            ],
        },
    }


def build_candidate_contracts(
    args: argparse.Namespace,
    seeds: list[dict[str, Any]],
    global_blockers: list[str],
    ai_index: dict[str, dict[str, Any]],
    cross_index: dict[str, dict[str, Any]],
    outcome_index: dict[str, dict[str, Any]],
    isolation: dict[str, Any],
) -> list[dict[str, Any]]:
    stake = isolation["stakeContract"]
    exit_contract = isolation["exitContract"]
    rows: list[dict[str, Any]] = []
    for seed in seeds[: max(0, args.max_candidates)]:
        market_id = str(seed.get("marketId") or seed.get("market_id") or "").strip()
        tracking_key = str(seed.get("trackingKey") or "").strip()
        ai = get_ai_score(ai_index, market_id)
        cross = get_cross_link(cross_index, market_id)
        outcome = get_outcome(outcome_index, market_id, tracking_key)
        blockers = unique([*global_blockers, *evidence_blockers(seed, ai, cross, outcome, args)])
        row_id = "CANARY-" + stable_id(market_id, seed.get("question"), seed.get("track"), seed.get("suggestedShadowTrack"))
        reference_stake = safe_number(seed.get("hypotheticalStakeUSDC"), None)
        if reference_stake is None:
            reference_stake = safe_number(seed.get("referenceStakeUSDC"), stake["maxSingleBetUSDC"]) or 0.0
        reference_stake = min(float(reference_stake), float(stake["maxSingleBetUSDC"]))
        source_score = safe_number(seed.get("radarScore"), None)
        if source_score is None:
            source_score = safe_number(seed.get("aiRuleScore"), None)
        return_row = {
            "canaryContractId": row_id,
            "schemaVersion": SCHEMA_VERSION,
            "marketId": market_id,
            "question": seed.get("question") or "",
            "polymarketUrl": seed.get("polymarketUrl") or "",
            "track": seed.get("track") or seed.get("suggestedShadowTrack") or "",
            "side": seed.get("side") or "YES",
            "canaryState": "CONTRACT_READY_BUT_BLOCKED",
            "decision": "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
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
            "sourceScore": source_score,
            "aiScore": safe_number(ai.get("score"), None),
            "aiColor": ai.get("color") or "",
            "crossRiskTag": cross.get("primaryRiskTag") or "",
            "macroRiskState": cross.get("macroRiskState") or "",
            "dryRunState": seed.get("decision") or seed.get("gateDecision") or "",
            "outcomeState": outcome.get("state") or "",
            "wouldExitReason": outcome.get("wouldExitReason") or "",
            "blockers": blockers,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "auditLedger": LEDGER_NAME,
        }
        rows.append(return_row)
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
    seeds = make_candidate_seed(gate, dry_run, radar)
    ai_index = by_market(get_rows(ai_score, "scores"))
    cross_index = by_market(get_rows(cross, "linkages"))
    outcome_rows = get_rows(outcome, "outcomes")
    outcome_index = by_market(outcome_rows)
    for row in outcome_rows:
        key = str(row.get("trackingKey") or "").strip()
        if key:
            outcome_index.setdefault(key, row)
    global_blockers = build_global_blockers(gate, dry_run, outcome)
    isolation = build_isolation_contract(args)
    contracts = build_candidate_contracts(args, seeds, global_blockers, ai_index, cross_index, outcome_index, isolation)
    generated = utc_now_iso()
    return {
        "mode": "POLYMARKET_CANARY_EXECUTOR_CONTRACT_V1",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated,
        "status": "OK",
        "decision": "CANARY_CONTRACT_ONLY_NO_WALLET_WRITE",
        "summary": {
            "candidateContracts": len(contracts),
            "eligibleNow": 0,
            "blocked": len(contracts),
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
            "boundary": "Contract-only canary design. No wallet/order side effects.",
        },
        "globalBlockers": global_blockers,
        "isolationContract": isolation,
        "candidateContracts": contracts,
        "nextActions": [
            "Keep this contract blocked until Governance promotes a specific Polymarket track.",
            "Before any canary run, implement a separate order-audit, position, and exit ledger.",
            "Require dry-run outcome evidence proving TP/SL and kill-switch behavior before wallet wiring.",
            "Do not share MT5 equity, MT5 loops, or D:\\polymarket live executor state with canary execution.",
        ],
    }


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    for row in snapshot.get("candidateContracts") or []:
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
                "canary_eligible_now": row.get("canaryEligibleNow", False),
                "reference_stake_usdc": row.get("referenceStakeUSDC", ""),
                "canary_stake_usdc": row.get("canaryStakeUSDC", ""),
                "max_single_bet_usdc": row.get("maxSingleBetUSDC", ""),
                "max_daily_loss_usdc": row.get("maxDailyLossUSDC", ""),
                "take_profit_pct": row.get("takeProfitPct", ""),
                "stop_loss_pct": row.get("stopLossPct", ""),
                "trailing_profit_pct": row.get("trailingProfitPct", ""),
                "cancel_unfilled_minutes": row.get("cancelUnfilledAfterMinutes", ""),
                "max_hold_hours": row.get("maxHoldHours", ""),
                "exit_before_resolution_hours": row.get("exitBeforeResolutionHours", ""),
                "source_score": row.get("sourceScore", ""),
                "ai_score": row.get("aiScore", ""),
                "cross_risk_tag": row.get("crossRiskTag", ""),
                "dry_run_state": row.get("dryRunState", ""),
                "outcome_state": row.get("outcomeState", ""),
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
        json_path = base_dir / OUTPUT_NAME
        csv_path = base_dir / LEDGER_NAME
        atomic_write_text(json_path, json_text)
        atomic_write_text(csv_path, csv_text)
        written.extend([str(json_path), str(csv_path)])
    return written


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | contracts={summary['candidateContracts']} "
        f"| eligible={summary['eligibleNow']} | walletWrite=false | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
