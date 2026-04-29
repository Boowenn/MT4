#!/usr/bin/env python3
"""Run the guarded Polymarket canary executor preflight.

Default behavior is plan/audit only. Real orders are possible only when every
runtime switch, lock file, evidence gate, stake budget, token id, and wallet
adapter preflight passes. This script never touches MT5.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from polymarket_governance_utils import (
    atomic_write_text,
    first_text,
    get_rows,
    read_json_candidate,
    safe_int,
    safe_number,
    stable_id,
    unique,
    utc_now_iso,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_LOCK_FILE = Path(__file__).resolve().parents[1] / "runtime" / "Polymarket_Canary_Isolated" / "REAL_MONEY_CANARY.lock"

GOVERNANCE_NAME = "QuantGod_PolymarketAutoGovernance.json"
CANARY_CONTRACT_NAME = "QuantGod_PolymarketCanaryExecutorContract.json"
OUTPUT_NAME = "QuantGod_PolymarketCanaryExecutorRun.json"
ORDER_AUDIT_LEDGER = "QuantGod_PolymarketCanaryOrderAuditLedger.csv"
POSITION_LEDGER = "QuantGod_PolymarketCanaryPositionLedger.csv"
EXIT_LEDGER = "QuantGod_PolymarketCanaryExitLedger.csv"
SCHEMA_VERSION = "POLYMARKET_CANARY_EXECUTOR_RUN_V1"

ORDER_AUDIT_FIELDS = [
    "generated_at",
    "run_id",
    "mode",
    "candidate_id",
    "governance_id",
    "market_id",
    "question",
    "track",
    "side",
    "token_id_present",
    "limit_price",
    "stake_usdc",
    "size",
    "decision",
    "order_sent",
    "wallet_write_allowed",
    "order_send_allowed",
    "blockers",
    "adapter_status",
    "response_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--governance-path", default="")
    parser.add_argument("--canary-contract-path", default="")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--max-orders", type=int, default=1)
    parser.add_argument("--default-limit-price", type=float, default=0.50)
    parser.add_argument("--min-order-size", type=float, default=1.0)
    parser.add_argument("--plan-only", action="store_true", help="Force no-order audit mode even if env switches are on.")
    return parser.parse_args()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def lock_file_ok(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "REAL_MONEY_CANARY_OK" in text


def compact_env_state(lock_file: Path, plan_only: bool) -> dict[str, Any]:
    return {
        "planOnlyForced": bool(plan_only),
        "realExecutionSwitch": env_bool("QG_POLYMARKET_REAL_EXECUTION"),
        "ackMatches": os.environ.get("QG_POLYMARKET_CANARY_ACK") == "REAL_MONEY_CANARY_OK",
        "killSwitchOff": str(os.environ.get("QG_POLYMARKET_CANARY_KILL_SWITCH", "true")).strip().lower() == "false",
        "walletAdapter": os.environ.get("QG_POLYMARKET_WALLET_ADAPTER", ""),
        "privateKeyConfigured": bool(os.environ.get("QG_POLYMARKET_PRIVATE_KEY")),
        "clobHostConfigured": bool(os.environ.get("QG_POLYMARKET_CLOB_HOST")),
        "lockFile": str(lock_file),
        "lockFileOk": lock_file_ok(lock_file),
        "neverEchoesSecretValues": True,
    }


def runtime_blockers(env_state: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if env_state["planOnlyForced"]:
        blockers.append("PLAN_ONLY_FORCED")
    if not env_state["realExecutionSwitch"]:
        blockers.append("REAL_EXECUTION_SWITCH_FALSE")
    if not env_state["ackMatches"]:
        blockers.append("CANARY_ACK_MISSING")
    if not env_state["killSwitchOff"]:
        blockers.append("CANARY_KILL_SWITCH_ON_OR_UNSET")
    if not env_state["lockFileOk"]:
        blockers.append("REAL_MONEY_LOCK_FILE_MISSING")
    if env_state["walletAdapter"] != "isolated_clob":
        blockers.append("WALLET_ADAPTER_NOT_ISOLATED_CLOB")
    if not env_state["privateKeyConfigured"]:
        blockers.append("PRIVATE_KEY_ENV_MISSING")
    if not env_state["clobHostConfigured"]:
        blockers.append("CLOB_HOST_ENV_MISSING")
    return blockers


def by_market(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        market_id = str(row.get("marketId") or "").strip()
        if market_id and market_id not in out:
            out[market_id] = row
    return out


def token_id_from(row: dict[str, Any], contract: dict[str, Any]) -> str:
    return first_text(
        row.get("tokenId"),
        row.get("yesTokenId"),
        row.get("clobTokenId"),
        row.get("outcomeTokenId"),
        contract.get("tokenId"),
        contract.get("yesTokenId"),
        contract.get("clobTokenId"),
        contract.get("outcomeTokenId"),
    )


def limit_price_from(row: dict[str, Any], contract: dict[str, Any], default: float) -> float:
    for key in ("limitPrice", "entryPrice", "marketProbability", "probability"):
        value = safe_number(row.get(key), None)
        if value is not None:
            price = float(value) / 100.0 if float(value) > 1 else float(value)
            return max(0.01, min(0.99, round(price, 4)))
    value = safe_number(contract.get("entryPrice"), None)
    if value is not None:
        price = float(value) / 100.0 if float(value) > 1 else float(value)
        return max(0.01, min(0.99, round(price, 4)))
    return max(0.01, min(0.99, round(default, 4)))


def stake_from(contract: dict[str, Any]) -> float:
    stake = safe_number(contract.get("canaryStakeUSDC"), None)
    if stake is None or stake <= 0:
        stake = safe_number(contract.get("referenceStakeUSDC"), 0.0) or 0.0
    max_stake = safe_number(contract.get("maxSingleBetUSDC"), 0.0) or 0.0
    if max_stake > 0:
        stake = min(stake, max_stake)
    return round(max(0.0, float(stake)), 2)


def candidate_blockers(row: dict[str, Any], contract: dict[str, Any], token_id: str, stake: float, size: float, args: argparse.Namespace) -> list[str]:
    blockers = []
    if row.get("canPromoteToLiveExecution") is not True:
        blockers.append("GOVERNANCE_NOT_PROMOTED")
    if row.get("autoExecutorPermission") != "CANARY_EXECUTOR_ALLOWED_WHEN_RUNTIME_SWITCHES_ON":
        blockers.append("AUTO_EXECUTOR_PERMISSION_BLOCKED")
    if contract.get("evidenceCanAutoAuthorize") is not True:
        blockers.append("CONTRACT_EVIDENCE_NOT_READY")
    if not token_id:
        blockers.append("CLOB_TOKEN_ID_MISSING")
    if stake <= 0:
        blockers.append("STAKE_NOT_POSITIVE")
    if size < args.min_order_size:
        blockers.append("ORDER_SIZE_LT_MIN")
    if contract.get("walletWriteAllowed") is True or contract.get("orderSendAllowed") is True:
        blockers.append("CONTRACT_BUILDER_SHOULD_NOT_GRANT_WALLET_WRITE")
    blockers.extend(str(item) for item in (row.get("blockers") or []) if str(item).startswith("GLOBAL_"))
    return unique(blockers)


def build_plan(args: argparse.Namespace, governance: dict[str, Any], contract: dict[str, Any], env_state: dict[str, Any]) -> list[dict[str, Any]]:
    contract_by_market = by_market(get_rows(contract, "candidateContracts"))
    plans: list[dict[str, Any]] = []
    for row in get_rows(governance, "governanceDecisions"):
        if row.get("canPromoteToLiveExecution") is not True:
            continue
        market_id = str(row.get("marketId") or "").strip()
        c_row = contract_by_market.get(market_id) or {}
        token_id = token_id_from(row, c_row)
        price = limit_price_from(row, c_row, args.default_limit_price)
        stake = stake_from(c_row)
        size = round(stake / price, 6) if price > 0 else 0.0
        blockers = unique([*runtime_blockers(env_state), *candidate_blockers(row, c_row, token_id, stake, size, args)])
        plans.append(
            {
                "candidateId": first_text(c_row.get("canaryContractId"), row.get("governanceId"), "CANARY-" + stable_id(market_id, row.get("track"))),
                "governanceId": row.get("governanceId", ""),
                "marketId": market_id,
                "question": row.get("question", ""),
                "polymarketUrl": row.get("polymarketUrl", ""),
                "track": row.get("track", ""),
                "side": first_text(row.get("side"), c_row.get("side"), "YES"),
                "_tokenId": token_id,
                "tokenIdPresent": bool(token_id),
                "tokenIdMasked": token_id[:6] + "..." + token_id[-4:] if len(token_id) > 10 else ("present" if token_id else ""),
                "limitPrice": price,
                "stakeUSDC": stake,
                "size": size,
                "takeProfitPct": c_row.get("takeProfitPct"),
                "stopLossPct": c_row.get("stopLossPct"),
                "trailingProfitPct": c_row.get("trailingProfitPct"),
                "decision": "READY_TO_SEND_IF_ADAPTER_OK" if not blockers else "BLOCKED_PRE_ORDER",
                "blockers": blockers,
                "orderSent": False,
                "adapterStatus": "NOT_ATTEMPTED",
                "response": {},
            }
        )
    return plans[: max(0, args.max_orders)]


def try_send_order(plan: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Attempt a real CLOB order only after all outer guardrails passed."""
    try:
        from py_clob_client.client import ClobClient  # type: ignore
        from py_clob_client.clob_types import OrderArgs, OrderType  # type: ignore
        from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"CLOB_ADAPTER_IMPORT_FAILED:{type(exc).__name__}", {}

    token_id = str(plan.get("_tokenId") or os.environ.get("QG_POLYMARKET_CANARY_TOKEN_ID") or "")
    private_key = os.environ.get("QG_POLYMARKET_PRIVATE_KEY") or ""
    host = os.environ.get("QG_POLYMARKET_CLOB_HOST") or "https://clob.polymarket.com"
    chain_id = safe_int(os.environ.get("QG_POLYMARKET_CHAIN_ID"), 137)
    funder = os.environ.get("QG_POLYMARKET_FUNDER") or None
    if not token_id or not private_key:
        return False, "CLOB_TOKEN_OR_PRIVATE_KEY_MISSING", {}
    try:  # pragma: no cover - intentionally guarded and not exercised by tests
        client = ClobClient(host, key=private_key, chain_id=chain_id, funder=funder)
        client.set_api_creds(client.create_or_derive_api_creds())
        side = BUY if str(plan.get("side") or "YES").upper() in {"YES", "BUY"} else SELL
        order_args = OrderArgs(
            price=float(plan["limitPrice"]),
            size=float(plan["size"]),
            side=side,
            token_id=token_id,
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)
    except Exception as exc:
        return False, f"CLOB_ORDER_FAILED:{type(exc).__name__}", {"error": str(exc)[:240]}
    return True, "ORDER_SENT", response if isinstance(response, dict) else {"response": str(response)[:500]}


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ORDER_AUDIT_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    run_id = snapshot.get("runId", "")
    for row in snapshot.get("plannedOrders") or []:
        writer.writerow(
            {
                "generated_at": generated,
                "run_id": run_id,
                "mode": snapshot.get("executionMode", ""),
                "candidate_id": row.get("candidateId", ""),
                "governance_id": row.get("governanceId", ""),
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("track", ""),
                "side": row.get("side", ""),
                "token_id_present": row.get("tokenIdPresent", False),
                "limit_price": row.get("limitPrice", ""),
                "stake_usdc": row.get("stakeUSDC", ""),
                "size": row.get("size", ""),
                "decision": row.get("decision", ""),
                "order_sent": row.get("orderSent", False),
                "wallet_write_allowed": snapshot.get("walletWriteAllowed", False),
                "order_send_allowed": snapshot.get("orderSendAllowed", False),
                "blockers": " / ".join(row.get("blockers") or []),
                "adapter_status": row.get("adapterStatus", ""),
                "response_id": first_text(row.get("response", {}).get("orderID"), row.get("response", {}).get("id")),
            }
        )
    return output.getvalue()


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    governance, governance_path = read_json_candidate(GOVERNANCE_NAME, runtime_dir, dashboard_dir, args.governance_path)
    contract, contract_path = read_json_candidate(CANARY_CONTRACT_NAME, runtime_dir, dashboard_dir, args.canary_contract_path)
    lock_file = Path(args.lock_file)
    env_state = compact_env_state(lock_file, args.plan_only)
    plans = build_plan(args, governance, contract, env_state)
    preflight_blockers = runtime_blockers(env_state)
    wallet_write_allowed = bool(plans) and not preflight_blockers and all(not plan.get("blockers") for plan in plans)
    order_send_allowed = wallet_write_allowed
    orders_sent = 0
    if order_send_allowed:
        for plan in plans:
            sent, status, response = try_send_order(plan)
            plan["orderSent"] = sent
            plan["adapterStatus"] = status
            plan["response"] = response
            if sent:
                orders_sent += 1
            else:
                plan["blockers"] = unique([*(plan.get("blockers") or []), status])
        order_send_allowed = orders_sent > 0
        wallet_write_allowed = orders_sent > 0
    generated = utc_now_iso()
    run_id = "POLYEXEC-" + stable_id(generated, len(plans), orders_sent)
    public_plans = [
        {key: value for key, value in plan.items() if key != "_tokenId"}
        for plan in plans
    ]
    return {
        "mode": "POLYMARKET_CANARY_EXECUTOR_RUN_V1",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated,
        "runId": run_id,
        "status": "OK",
        "executionMode": "REAL_ORDER_ATTEMPTED" if orders_sent else "GUARDED_PLAN_ONLY_NO_ORDER",
        "decision": "ORDERS_SENT" if orders_sent else "NO_REAL_ORDER_SENT",
        "sourceFiles": {
            GOVERNANCE_NAME: governance_path,
            CANARY_CONTRACT_NAME: contract_path,
        },
        "envPreflight": env_state,
        "preflightBlockers": preflight_blockers,
        "summary": {
            "governanceRows": len(get_rows(governance, "governanceDecisions")),
            "contractRows": len(get_rows(contract, "candidateContracts")),
            "eligibleGovernanceRows": sum(1 for row in get_rows(governance, "governanceDecisions") if row.get("canPromoteToLiveExecution") is True),
            "plannedOrders": len(plans),
            "ordersSent": orders_sent,
            "walletWriteAllowed": wallet_write_allowed,
            "orderSendAllowed": order_send_allowed,
            "maxOrders": args.max_orders,
        },
        "safety": {
            "readsPrivateKeyValueOnlyInsideFinalAdapter": bool(order_send_allowed),
            "logsPrivateKey": False,
            "walletWriteAllowed": wallet_write_allowed,
            "orderSendAllowed": order_send_allowed,
            "startsExecutorLoop": False,
            "mutatesMt5": False,
            "requiresIndependentGovernanceRecheck": True,
        },
        "plannedOrders": public_plans,
        "ledgerFiles": {
            "orderAudit": ORDER_AUDIT_LEDGER,
            "positions": POSITION_LEDGER,
            "exits": EXIT_LEDGER,
        },
        "nextActions": [
            "当前没有达到全部前置条件时不会发送真钱订单。",
            "只有 governance canPromoteToLiveExecution=true 且 runtime 开关/锁文件/钱包适配器全部通过才会尝试 canary。",
            "所有真实订单响应只记录订单 id/状态，不记录私钥或钱包密钥。",
        ],
    }


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = to_csv(snapshot)
    position_csv = "generated_at,run_id,market_id,position_state,stake_usdc,notes\n"
    exit_csv = "generated_at,run_id,market_id,exit_state,reason,notes\n"
    written: list[str] = []
    for base_dir in [runtime_dir, dashboard_dir]:
        if base_dir is None:
            continue
        atomic_write_text(base_dir / OUTPUT_NAME, json_text)
        atomic_write_text(base_dir / ORDER_AUDIT_LEDGER, csv_text)
        atomic_write_text(base_dir / POSITION_LEDGER, position_csv)
        atomic_write_text(base_dir / EXIT_LEDGER, exit_csv)
        written.extend(
            [
                str(base_dir / OUTPUT_NAME),
                str(base_dir / ORDER_AUDIT_LEDGER),
                str(base_dir / POSITION_LEDGER),
                str(base_dir / EXIT_LEDGER),
            ]
        )
    return written


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, Path(args.runtime_dir), Path(args.dashboard_dir) if args.dashboard_dir else None)
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | planned={summary['plannedOrders']} | sent={summary['ordersSent']} "
        f"| wallet_write={str(summary['walletWriteAllowed']).lower()} | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
