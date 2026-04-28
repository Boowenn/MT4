#!/usr/bin/env python3
"""Build dry-run Polymarket order plans and an execution-ledger schema.

This simulator consumes the Polymarket Execution Gate contract and market
radar evidence, then writes a no-wallet, no-order-send execution plan. It is
designed as the audit layer before any future order executor exists.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
GATE_NAME = "QuantGod_PolymarketExecutionGate.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
OUTPUT_NAME = "QuantGod_PolymarketDryRunOrders.json"
LEDGER_NAME = "QuantGod_PolymarketExecutionLedger.csv"
SCHEMA_VERSION = "POLY_EXEC_LEDGER_V1"


LEDGER_FIELDS = [
    "generated_at",
    "schema_version",
    "mode",
    "dry_run_order_id",
    "tracking_key",
    "market_id",
    "question",
    "track",
    "side",
    "decision",
    "can_open_dry_run",
    "gate_decision",
    "entry_price",
    "limit_price",
    "hypothetical_stake_usdc",
    "simulated_stake_usdc",
    "token_quantity",
    "take_profit_pct",
    "take_profit_price",
    "stop_loss_pct",
    "stop_loss_price",
    "trailing_profit_pct",
    "trailing_trigger_price",
    "cancel_after_minutes",
    "max_hold_until",
    "exit_before_resolution_at",
    "blockers",
    "wallet_write",
    "order_send",
    "audit_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--gate-path", default="")
    parser.add_argument("--radar-path", default="")
    parser.add_argument("--max-orders", type=int, default=24)
    parser.add_argument("--default-side", default="YES")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


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


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    runtime_dir = Path(args.runtime_dir)
    gate = Path(args.gate_path) if args.gate_path else runtime_dir / GATE_NAME
    radar = Path(args.radar_path) if args.radar_path else runtime_dir / RADAR_NAME
    return gate, radar


def make_radar_index(radar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in radar.get("radar") or []:
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("marketId") or "").strip()
        if market_id:
            index[market_id] = item
    return index


def price_from_probability(value: Any) -> float:
    probability = safe_number(value, 0.0)
    if probability > 1:
        probability = probability / 100.0
    return round(clamp(probability, 0.01, 0.99), 4)


def build_exit_plan(
    now: datetime,
    entry_price: float,
    gate_contract: dict[str, Any],
    radar_item: dict[str, Any],
) -> dict[str, Any]:
    exit_policy = gate_contract.get("takeProfitStopLoss") or {}
    cancel_policy = gate_contract.get("cancelExitRules") or {}
    take_profit_pct = safe_number(exit_policy.get("takeProfitPct"), 18.0)
    stop_loss_pct = safe_number(exit_policy.get("stopLossPct"), 10.0)
    trailing_pct = safe_number(exit_policy.get("trailingProfitPct"), 8.0)
    max_hold_hours = safe_number(exit_policy.get("maxHoldHours"), 36.0)
    exit_before_hours = safe_number(exit_policy.get("exitBeforeResolutionHours"), 12.0)
    end_dt = parse_dt(radar_item.get("endDate"))
    max_hold_until = now + timedelta(hours=max_hold_hours)
    exit_before_resolution_at = end_dt - timedelta(hours=exit_before_hours) if end_dt else None
    return {
        "takeProfitPct": round(take_profit_pct, 2),
        "takeProfitPrice": round(clamp(entry_price * (1.0 + take_profit_pct / 100.0), 0.01, 0.99), 4),
        "stopLossPct": round(stop_loss_pct, 2),
        "stopLossPrice": round(clamp(entry_price * (1.0 - stop_loss_pct / 100.0), 0.01, 0.99), 4),
        "trailingProfitPct": round(trailing_pct, 2),
        "trailingTriggerPrice": round(clamp(entry_price * (1.0 + trailing_pct / 100.0), 0.01, 0.99), 4),
        "cancelUnfilledAfterMinutes": safe_int(cancel_policy.get("cancelUnfilledAfterMinutes"), 15),
        "maxHoldHours": round(max_hold_hours, 2),
        "maxHoldUntil": max_hold_until.isoformat(),
        "exitBeforeResolutionHours": round(exit_before_hours, 2),
        "exitBeforeResolutionAt": exit_before_resolution_at.isoformat() if exit_before_resolution_at else "",
        "exitReasons": [
            "TAKE_PROFIT_PRICE_HIT",
            "STOP_LOSS_PRICE_HIT",
            "TRAILING_STOP_ARMED_AND_REVERSED",
            "MAX_HOLD_TIME_REACHED",
            "EXIT_BEFORE_RESOLUTION",
            "GOVERNANCE_DEMOTION",
            "KILL_SWITCH",
        ],
    }


def build_order_plan(
    now: datetime,
    row: dict[str, Any],
    radar_item: dict[str, Any],
    gate: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    contract = gate.get("executionContract") or {}
    stake_policy = contract.get("stakePolicy") or {}
    market_id = str(row.get("marketId") or radar_item.get("marketId") or "").strip()
    track = row.get("suggestedShadowTrack") or radar_item.get("suggestedShadowTrack") or ""
    side = str(args.default_side or "YES").upper()
    tracking_key = f"{market_id}|{track}|{side}"
    blockers = unique([str(item) for item in (row.get("blockers") or [])])
    gate_can_bet = bool(row.get("canBet")) and not blockers
    entry_price = price_from_probability(row.get("probability", radar_item.get("probability")))
    max_single = safe_number(stake_policy.get("maxSingleBetUSDC"), 0.0)
    max_exposure = safe_number(stake_policy.get("maxMarketExposureUSDC"), 0.0)
    reference_stake = safe_number(row.get("referenceStakeUSDC"), safe_number(stake_policy.get("referenceSingleBetUSDC"), 0.0))
    hypothetical_stake = round(clamp(reference_stake, 0.0, min(v for v in [max_single, max_exposure] if v > 0) if (max_single > 0 or max_exposure > 0) else reference_stake), 2)
    simulated_stake = hypothetical_stake if gate_can_bet else 0.0
    token_quantity = round(simulated_stake / entry_price, 6) if simulated_stake > 0 and entry_price > 0 else 0.0
    exit_plan = build_exit_plan(now, entry_price, contract, radar_item)
    decision = "DRY_RUN_READY_NO_WALLET_WRITE" if gate_can_bet else "DRY_RUN_BLOCKED_BY_GATE"
    return {
        "dryRunOrderId": f"DRYRUN-{market_id or 'UNKNOWN'}-{now.strftime('%Y%m%d%H%M%S')}",
        "trackingKey": tracking_key,
        "marketId": market_id,
        "question": row.get("question") or radar_item.get("question") or "",
        "polymarketUrl": row.get("polymarketUrl") or radar_item.get("polymarketUrl") or "",
        "track": track,
        "side": side,
        "decision": decision,
        "canOpenDryRun": gate_can_bet,
        "walletWrite": False,
        "orderSend": False,
        "gateDecision": row.get("gateDecision") or gate.get("decision") or "UNKNOWN",
        "entryPrice": entry_price,
        "limitPrice": entry_price,
        "hypotheticalStakeUSDC": hypothetical_stake,
        "simulatedStakeUSDC": simulated_stake,
        "tokenQuantity": token_quantity,
        "radarRank": row.get("radarRank") or radar_item.get("rank"),
        "radarScore": row.get("aiRuleScore") or radar_item.get("aiRuleScore"),
        "risk": row.get("risk") or radar_item.get("risk") or "",
        "exitPlan": exit_plan,
        "blockers": blockers,
        "auditStatus": "SCHEMA_READY_NO_WALLET_WRITE",
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    gate_path, radar_path = resolve_inputs(args)
    gate = load_json(gate_path)
    radar = load_json(radar_path)
    now = utc_now()
    now_iso = now.isoformat()
    radar_index = make_radar_index(radar)
    gate_contract = gate.get("executionContract") or {}
    decisions = [item for item in (gate.get("marketDecisions") or []) if isinstance(item, dict)]
    orders = [
        build_order_plan(now, row, radar_index.get(str(row.get("marketId") or ""), {}), gate, args)
        for row in decisions[: max(0, args.max_orders)]
    ]
    ready = sum(1 for item in orders if item.get("canOpenDryRun"))
    blocked = len(orders) - ready
    simulated_total = round(sum(safe_number(item.get("simulatedStakeUSDC"), 0.0) for item in orders), 2)
    hypothetical_total = round(sum(safe_number(item.get("hypotheticalStakeUSDC"), 0.0) for item in orders), 2)
    stake_policy = gate_contract.get("stakePolicy") or {}
    return {
        "mode": "POLYMARKET_DRY_RUN_ORDER_SIMULATOR_V1",
        "generatedAt": now_iso,
        "status": "OK" if gate else "MISSING_GATE",
        "decision": "DRY_RUN_ONLY_NO_WALLET_WRITE",
        "summary": {
            "candidateOrders": len(orders),
            "readyDryRunOrders": ready,
            "blockedByGate": blocked,
            "simulatedStakeTotalUSDC": simulated_total,
            "hypotheticalStakeTotalUSDC": hypothetical_total,
            "maxDailyLossUSDC": safe_number(stake_policy.get("maxDailyLossUSDC"), 0.0),
            "ledgerSchemaVersion": SCHEMA_VERSION,
        },
        "safety": {
            "loadsEnv": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "runtimeDir": str(runtime_dir),
            "sourceGate": str(gate_path),
        },
        "ledgerSchema": {
            "name": LEDGER_NAME,
            "version": SCHEMA_VERSION,
            "mode": "dry_run_first_real_executor_later",
            "fields": LEDGER_FIELDS,
            "primaryKey": "dry_run_order_id",
            "realExecutorBoundary": "Future real orders must use the same fields plus real order ids, but this V1 never writes wallet or sends orders.",
        },
        "policyEcho": {
            "stakePolicy": stake_policy,
            "takeProfitStopLoss": gate_contract.get("takeProfitStopLoss") or {},
            "cancelExitRules": gate_contract.get("cancelExitRules") or {},
        },
        "dryRunOrders": orders,
        "nextActions": [
            "Keep this dry-run ledger active until Governance produces green candidates.",
            "Compare simulated exits against later market movement before connecting wallet writes.",
            "Only build a real order executor after ledger, TP/SL exits, cancel rules, and kill switch are proven in dry-run.",
        ],
    }


def ledger_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS)
    writer.writeheader()
    generated_at = snapshot.get("generatedAt", "")
    for row in snapshot.get("dryRunOrders") or []:
        exit_plan = row.get("exitPlan") or {}
        writer.writerow(
            {
                "generated_at": generated_at,
                "schema_version": SCHEMA_VERSION,
                "mode": snapshot.get("mode", ""),
                "dry_run_order_id": row.get("dryRunOrderId", ""),
                "tracking_key": row.get("trackingKey", ""),
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("track", ""),
                "side": row.get("side", ""),
                "decision": row.get("decision", ""),
                "can_open_dry_run": row.get("canOpenDryRun", False),
                "gate_decision": row.get("gateDecision", ""),
                "entry_price": row.get("entryPrice", ""),
                "limit_price": row.get("limitPrice", ""),
                "hypothetical_stake_usdc": row.get("hypotheticalStakeUSDC", ""),
                "simulated_stake_usdc": row.get("simulatedStakeUSDC", ""),
                "token_quantity": row.get("tokenQuantity", ""),
                "take_profit_pct": exit_plan.get("takeProfitPct", ""),
                "take_profit_price": exit_plan.get("takeProfitPrice", ""),
                "stop_loss_pct": exit_plan.get("stopLossPct", ""),
                "stop_loss_price": exit_plan.get("stopLossPrice", ""),
                "trailing_profit_pct": exit_plan.get("trailingProfitPct", ""),
                "trailing_trigger_price": exit_plan.get("trailingTriggerPrice", ""),
                "cancel_after_minutes": exit_plan.get("cancelUnfilledAfterMinutes", ""),
                "max_hold_until": exit_plan.get("maxHoldUntil", ""),
                "exit_before_resolution_at": exit_plan.get("exitBeforeResolutionAt", ""),
                "blockers": " / ".join(row.get("blockers") or []),
                "wallet_write": row.get("walletWrite", False),
                "order_send": row.get("orderSend", False),
                "audit_status": row.get("auditStatus", ""),
            }
        )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = ledger_csv(snapshot)
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
        "Polymarket dry-run orders "
        f"{snapshot.get('decision')} | candidates={summary.get('candidateOrders', 0)} "
        f"| ready={summary.get('readyDryRunOrders', 0)} "
        f"| simulatedStake={summary.get('simulatedStakeTotalUSDC', 0)} | outputs={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
