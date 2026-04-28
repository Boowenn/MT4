#!/usr/bin/env python3
"""Build a Polymarket execution-gate contract without wallet writes.

V1 is an empty-shell contract: it defines when betting could be allowed, how
stake sizing and TP/SL would be controlled, and why every current candidate is
blocked. It never imports the Polymarket runtime, loads private keys, places
orders, cancels orders, or mutates MT5 state.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
RESEARCH_NAME = "QuantGod_PolymarketResearch.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
RETUNE_NAME = "QuantGod_PolymarketRetunePlanner.json"
OUTPUT_NAME = "QuantGod_PolymarketExecutionGate.json"
LEDGER_NAME = "QuantGod_PolymarketExecutionGateLedger.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--research-path", default="")
    parser.add_argument("--radar-path", default="")
    parser.add_argument("--retune-path", default="")
    parser.add_argument("--min-single-bet-usdc", type=float, default=0.50)
    parser.add_argument("--max-single-bet-usdc", type=float, default=1.00)
    parser.add_argument("--max-market-exposure-usdc", type=float, default=1.00)
    parser.add_argument("--max-daily-loss-usdc", type=float, default=2.00)
    parser.add_argument("--max-open-positions", type=int, default=1)
    parser.add_argument("--take-profit-pct", type=float, default=18.0)
    parser.add_argument("--stop-loss-pct", type=float, default=10.0)
    parser.add_argument("--trailing-profit-pct", type=float, default=8.0)
    parser.add_argument("--cancel-unfilled-minutes", type=int, default=15)
    parser.add_argument("--max-hold-hours", type=float, default=36.0)
    parser.add_argument("--exit-before-resolution-hours", type=float, default=12.0)
    parser.add_argument("--min-radar-score", type=float, default=70.0)
    parser.add_argument("--max-candidates", type=int, default=24)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_number(value: Any, default: float = 0.0) -> float:
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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    runtime_dir = Path(args.runtime_dir)
    research = Path(args.research_path) if args.research_path else runtime_dir / RESEARCH_NAME
    radar = Path(args.radar_path) if args.radar_path else runtime_dir / RADAR_NAME
    retune = Path(args.retune_path) if args.retune_path else runtime_dir / RETUNE_NAME
    return research, radar, retune


def reference_stake(account: dict[str, Any], args: argparse.Namespace) -> float:
    cash = safe_number(account.get("accountCash"), 0.0)
    bankroll = safe_number(account.get("bankroll"), 0.0)
    base = cash if cash > 0 else bankroll
    if base <= 0:
        return 0.0
    raw = max(args.min_single_bet_usdc, base * 0.03)
    return round(clamp(raw, args.min_single_bet_usdc, args.max_single_bet_usdc), 2)


def build_global_blockers(
    research: dict[str, Any],
    retune: dict[str, Any],
    account: dict[str, Any],
) -> list[str]:
    blockers: list[str] = [
        "CONTRACT_ONLY_NO_WALLET_WRITE",
        "LIVE_BETTING_SWITCH_FALSE",
        "OPERATOR_PROMOTION_REQUIRED",
    ]
    governance = research.get("governance") or {}
    blockers.extend(str(item) for item in (governance.get("blockers") or []))
    if governance.get("resumePolymarketExecution") is not True:
        blockers.append("RESEARCH_GOVERNANCE_BLOCKS_LIVE")
    if account.get("authState") not in (None, "", "read_only_ok"):
        blockers.append("ACCOUNT_SNAPSHOT_NOT_READY")
    if safe_number(account.get("accountCash"), 0.0) <= 0:
        blockers.append("POLYMARKET_CASH_NOT_AVAILABLE")
    latest = research.get("latestPnl") or {}
    if safe_number(latest.get("realizedPnl"), 0.0) < 0:
        blockers.append("LOCAL_PNL_NEGATIVE_QUARANTINE")
    counts = retune.get("recommendationCounts") or {}
    if safe_int(counts.get("red")) > 0:
        blockers.append("RETUNE_RED_ROUTES_PRESENT")
    if safe_int(counts.get("yellow")) > 0:
        blockers.append("RETUNE_YELLOW_ROUTES_PRESENT")
    return unique(blockers)


def market_blockers(item: dict[str, Any], args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    risk = str(item.get("risk") or "").lower()
    flags = [str(flag) for flag in (item.get("riskFlags") or [])]
    score = safe_number(item.get("aiRuleScore"), 0.0)
    if risk != "low":
        blockers.append("RADAR_RISK_NOT_LOW")
    if score < args.min_radar_score:
        blockers.append("RADAR_SCORE_BELOW_MIN")
    for flag in flags:
        if flag in {
            "probability_missing",
            "price_extreme",
            "volume_below_floor",
            "liquidity_low",
            "thin_book_or_unknown_liquidity",
            "near_resolution_lt_24h",
            "end_date_passed_or_stale",
            "accepting_orders_false",
            "wide_spread",
        }:
            blockers.append(f"MARKET_FLAG_{flag.upper()}")
    if item.get("suggestedShadowTrack") == "poly_observation_only":
        blockers.append("OBSERVATION_ONLY_TRACK")
    return unique(blockers)


def build_contract(
    args: argparse.Namespace,
    research: dict[str, Any],
    radar: dict[str, Any],
    retune: dict[str, Any],
) -> dict[str, Any]:
    account = research.get("accountSnapshot") or {}
    stake = reference_stake(account, args)
    return {
        "executionMode": "CONTRACT_ONLY_NO_WALLET_WRITE",
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "liveBettingEnabled": False,
        "allowBetWhenAllTrue": [
            "operator explicitly promotes Polymarket execution in QuantGod",
            "wallet write switch is enabled in a separate execution module",
            "Strategy Version Registry marks the track as promoted",
            "Governance Advisor has no red/yellow live blockers",
            "Radar risk is low and AI/rule score is above threshold",
            "Retune Planner has no red route for the target track",
            "account cash is isolated from MT5 and daily loss budget remains positive",
            "TP/SL, cancel, exit, order audit, and kill switch are configured",
        ],
        "stakePolicy": {
            "bankrollSource": "Polymarket account snapshot only, never MT5 equity",
            "accountCashUSDC": round(safe_number(account.get("accountCash"), 0.0), 6),
            "bankrollUSDC": round(safe_number(account.get("bankroll"), 0.0), 6),
            "referenceSingleBetUSDC": stake,
            "orderStakeUSDC": 0.0,
            "minSingleBetUSDC": round(args.min_single_bet_usdc, 2),
            "maxSingleBetUSDC": round(args.max_single_bet_usdc, 2),
            "maxMarketExposureUSDC": round(args.max_market_exposure_usdc, 2),
            "maxDailyLossUSDC": round(args.max_daily_loss_usdc, 2),
            "maxOpenPositions": max(0, args.max_open_positions),
        },
        "takeProfitStopLoss": {
            "takeProfitPct": round(args.take_profit_pct, 2),
            "stopLossPct": round(args.stop_loss_pct, 2),
            "trailingProfitPct": round(args.trailing_profit_pct, 2),
            "maxHoldHours": round(args.max_hold_hours, 2),
            "exitBeforeResolutionHours": round(args.exit_before_resolution_hours, 2),
            "note": "Future execution must create managed exits; V1 does not place or close orders.",
        },
        "marketBlocklist": {
            "riskFlags": [
                "probability_missing",
                "price_extreme",
                "volume_below_floor",
                "liquidity_low",
                "thin_book_or_unknown_liquidity",
                "near_resolution_lt_24h",
                "end_date_passed_or_stale",
                "accepting_orders_false",
                "wide_spread",
            ],
            "track": ["poly_observation_only"],
            "retuneSeverity": ["red"],
        },
        "cancelExitRules": {
            "cancelUnfilledAfterMinutes": args.cancel_unfilled_minutes,
            "cancelIfMarketFlagAppears": True,
            "exitIfStopLossHit": True,
            "exitIfTakeProfitHit": True,
            "exitIfKillSwitchTriggered": True,
            "exitIfGovernanceDemotesTrack": True,
        },
        "ledgerAudit": {
            "gateLedger": LEDGER_NAME,
            "requiredFutureLedgers": [
                "QuantGod_PolymarketOrderAuditLedger.csv",
                "QuantGod_PolymarketPositionLedger.csv",
                "QuantGod_PolymarketExitLedger.csv",
            ],
            "requiredFields": [
                "run_id",
                "market_id",
                "track",
                "decision",
                "stake_usdc",
                "entry_price",
                "tp_price",
                "sl_price",
                "exit_reason",
                "wallet_write_tx_or_order_id",
            ],
        },
        "inputs": {
            "researchStatus": research.get("status", "MISSING"),
            "radarStatus": radar.get("status", "MISSING"),
            "retuneDecision": retune.get("decision", "MISSING"),
        },
    }


def build_market_decisions(
    radar: dict[str, Any],
    global_blockers: list[str],
    contract: dict[str, Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    stake = safe_number((contract.get("stakePolicy") or {}).get("referenceSingleBetUSDC"), 0.0)
    exit_policy = contract.get("takeProfitStopLoss") or {}
    rows: list[dict[str, Any]] = []
    for item in (radar.get("radar") or [])[: max(0, args.max_candidates)]:
        if not isinstance(item, dict):
            continue
        blockers = unique([*global_blockers, *market_blockers(item, args)])
        rows.append(
            {
                "marketId": item.get("marketId", ""),
                "question": item.get("question", ""),
                "polymarketUrl": item.get("polymarketUrl", ""),
                "suggestedShadowTrack": item.get("suggestedShadowTrack", ""),
                "radarRank": item.get("rank"),
                "probability": item.get("probability"),
                "divergence": item.get("divergence"),
                "aiRuleScore": item.get("aiRuleScore"),
                "risk": item.get("risk"),
                "canBet": False,
                "gateDecision": "BLOCKED_CONTRACT_ONLY",
                "referenceStakeUSDC": stake,
                "orderStakeUSDC": 0.0,
                "takeProfitPct": exit_policy.get("takeProfitPct"),
                "stopLossPct": exit_policy.get("stopLossPct"),
                "cancelUnfilledAfterMinutes": (contract.get("cancelExitRules") or {}).get("cancelUnfilledAfterMinutes"),
                "blockers": blockers,
                "auditRequired": True,
                "auditLedger": LEDGER_NAME,
            }
        )
    return rows


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    research_path, radar_path, retune_path = resolve_inputs(args)
    research = load_json(research_path)
    radar = load_json(radar_path)
    retune = load_json(retune_path)
    account = research.get("accountSnapshot") or {}
    global_blockers = build_global_blockers(research, retune, account)
    contract = build_contract(args, research, radar, retune)
    decisions = build_market_decisions(radar, global_blockers, contract, args)
    blocked = sum(1 for item in decisions if not item.get("canBet"))
    return {
        "mode": "POLYMARKET_EXECUTION_GATE_V1",
        "generatedAt": utc_now_iso(),
        "status": "OK",
        "decision": "BLOCKED_CONTRACT_ONLY_NO_WALLET_WRITE",
        "summary": {
            "candidateMarkets": len(decisions),
            "canBet": 0,
            "blocked": blocked,
            "globalBlockers": len(global_blockers),
            "referenceSingleBetUSDC": (contract.get("stakePolicy") or {}).get("referenceSingleBetUSDC"),
            "maxDailyLossUSDC": (contract.get("stakePolicy") or {}).get("maxDailyLossUSDC"),
        },
        "safety": {
            "loadsEnv": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "runtimeDir": str(runtime_dir),
        },
        "globalBlockers": global_blockers,
        "executionContract": contract,
        "marketDecisions": decisions,
        "nextActions": [
            "Keep Polymarket betting disabled until this Gate has green candidates and explicit operator promotion.",
            "Before connecting an order executor, implement order audit, position ledger, TP/SL exits, and kill-switch handling.",
            "Retune red/yellow routes and require fresh shadow evidence before considering wallet-write activation.",
        ],
    }


def gate_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "generated_at",
            "market_id",
            "question",
            "track",
            "gate_decision",
            "can_bet",
            "reference_stake_usdc",
            "order_stake_usdc",
            "take_profit_pct",
            "stop_loss_pct",
            "risk",
            "ai_rule_score",
            "blockers",
            "audit_ledger",
        ],
    )
    writer.writeheader()
    generated_at = snapshot.get("generatedAt", "")
    for row in snapshot.get("marketDecisions") or []:
        writer.writerow(
            {
                "generated_at": generated_at,
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("suggestedShadowTrack", ""),
                "gate_decision": row.get("gateDecision", ""),
                "can_bet": row.get("canBet", False),
                "reference_stake_usdc": row.get("referenceStakeUSDC", ""),
                "order_stake_usdc": row.get("orderStakeUSDC", ""),
                "take_profit_pct": row.get("takeProfitPct", ""),
                "stop_loss_pct": row.get("stopLossPct", ""),
                "risk": row.get("risk", ""),
                "ai_rule_score": row.get("aiRuleScore", ""),
                "blockers": " / ".join(row.get("blockers") or []),
                "audit_ledger": row.get("auditLedger", ""),
            }
        )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = gate_csv(snapshot)
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
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot.get("summary", {})
    print(
        "Polymarket execution gate "
        f"{snapshot.get('decision')} | candidates={summary.get('candidateMarkets', 0)} "
        f"| canBet={summary.get('canBet', 0)} | outputs={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
