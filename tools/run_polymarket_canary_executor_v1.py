#!/usr/bin/env python3
"""Run the guarded Polymarket canary executor preflight.

Default behavior is plan/audit only. Real orders are possible only when every
runtime switch, lock file, evidence gate, stake budget, token id, and wallet
adapter preflight passes. This script never touches MT5.
"""

from __future__ import annotations

import argparse
import contextlib
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
COPY_DISCOVERY_NAME = "QuantGod_PolymarketCopyTraderDiscovery.json"
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
    "take_profit_usdc",
    "decision",
    "order_sent",
    "wallet_write_allowed",
    "order_send_allowed",
    "blockers",
    "adapter_status",
    "response_id",
    "response_status",
    "tx_hash",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--governance-path", default="")
    parser.add_argument("--canary-contract-path", default="")
    parser.add_argument("--copy-discovery-path", default="")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--max-orders", type=int, default=1)
    parser.add_argument("--default-limit-price", type=float, default=0.50)
    parser.add_argument("--min-order-size", type=float, default=safe_number(os.environ.get("QG_POLYMARKET_MIN_ORDER_SIZE"), 5.0) or 5.0)
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


def compact_env_state(lock_file: Path, plan_only: bool, wallet_policy: dict[str, Any], wallet_policy_path: str) -> dict[str, Any]:
    autonomous_policy_allowed = (
        bool(wallet_policy.get("realWalletExecutionAllowed"))
        and wallet_policy.get("humanApprovalRequired") is False
        and wallet_policy.get("operatorApprovalRequired") is False
        and bool(wallet_policy.get("autonomousUnlockAllowed"))
    )
    return {
        "planOnlyForced": bool(plan_only),
        "realExecutionSwitch": env_bool("QG_POLYMARKET_REAL_EXECUTION"),
        "ackMatches": os.environ.get("QG_POLYMARKET_CANARY_ACK") == "REAL_MONEY_CANARY_OK",
        "autonomousPolicyAllowed": autonomous_policy_allowed,
        "autonomousPolicyPath": wallet_policy_path,
        "autonomousPolicyStatus": wallet_policy.get("status", ""),
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
    if not env_state["ackMatches"] and not env_state["autonomousPolicyAllowed"]:
        blockers.append("CANARY_ACK_MISSING")
    if not env_state["killSwitchOff"]:
        blockers.append("CANARY_KILL_SWITCH_ON_OR_UNSET")
    if not env_state["lockFileOk"] and not env_state["autonomousPolicyAllowed"]:
        blockers.append("REAL_MONEY_LOCK_FILE_MISSING")
    if env_state["walletAdapter"] != "isolated_clob":
        blockers.append("WALLET_ADAPTER_NOT_ISOLATED_CLOB")
    if not env_state["privateKeyConfigured"]:
        blockers.append("PRIVATE_KEY_ENV_MISSING")
    if not env_state["clobHostConfigured"]:
        blockers.append("CLOB_HOST_ENV_MISSING")
    return blockers


def clob_v2_signature_type() -> int:
    explicit = os.environ.get("QG_POLYMARKET_CLOB_V2_SIGNATURE_TYPE")
    if explicit not in (None, ""):
        return safe_int(explicit, 0)
    legacy = os.environ.get("QG_POLYMARKET_SIGNATURE_TYPE")
    if legacy not in (None, ""):
        return safe_int(legacy, 0)
    return 1 if os.environ.get("QG_POLYMARKET_FUNDER") else 0


def clob_legacy_signature_type() -> int:
    return safe_int(os.environ.get("QG_POLYMARKET_SIGNATURE_TYPE"), 0)


def mask_address(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > 12:
        return text[:6] + "..." + text[-4:]
    return "configured" if text else ""


def clob_signer_preflight(client: Any, signature_type: int, funder: str | None) -> dict[str, Any]:
    signer = ""
    with contextlib.suppress(Exception):
        signer = str(client.get_address() or "")
    order_signer = str(funder or signer) if int(signature_type) == 3 else signer
    signer_matches = bool(signer) and bool(order_signer) and signer.lower() == order_signer.lower()
    return {
        "effectiveV2SignatureType": int(signature_type),
        "apiKeySignerMasked": mask_address(signer),
        "orderSignerMasked": mask_address(order_signer),
        "funderMasked": mask_address(funder),
        "apiKeySignerMatchesOrderSigner": signer_matches,
        "status": "OK" if signer_matches else "SIGNER_MISMATCH",
    }


def str_to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def configure_v2_api_creds(client: Any, *, force_create: bool = False) -> None:
    if force_create:
        with contextlib.redirect_stderr(io.StringIO()):
            client.set_api_creds(client.create_api_key())
        return
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            client.set_api_creds(client.derive_api_key())
    except Exception as derive_exc:
        if not str_to_bool(os.environ.get("QG_POLYMARKET_CLOB_ALLOW_CREATE_API_KEY"), False):
            raise derive_exc
        with contextlib.redirect_stderr(io.StringIO()):
            client.set_api_creds(client.create_api_key())


def is_v2_api_key_signer_mismatch(exc: Exception) -> bool:
    text = str(exc).lower()
    return "order signer address" in text and "api key" in text


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
                "takeProfitUSDC": c_row.get("takeProfitUSDC"),
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


def copy_candidate_token_id(row: dict[str, Any]) -> str:
    return first_text(
        row.get("tokenId"),
        row.get("asset"),
        row.get("clobTokenId"),
        row.get("outcomeTokenId"),
    )


def copy_candidate_price(row: dict[str, Any], default: float) -> float:
    risk = row.get("riskPlan") if isinstance(row.get("riskPlan"), dict) else {}
    for value in (
        row.get("limitPrice"),
        row.get("curPrice"),
        row.get("avgPrice"),
        risk.get("entryReferencePrice"),
        default,
    ):
        price = safe_number(value, None)
        if price is not None and price > 0:
            price = price / 100.0 if price > 1 else price
            return max(0.01, min(0.99, round(float(price), 4)))
    return max(0.01, min(0.99, round(float(default), 4)))


def copy_candidate_blockers(row: dict[str, Any], token_id: str, stake: float, size: float, args: argparse.Namespace) -> list[str]:
    risk = row.get("riskPlan") if isinstance(row.get("riskPlan"), dict) else {}
    blockers = [str(item) for item in (risk.get("blockers") or row.get("blockers") or []) if str(item)]
    if risk.get("realWalletEligibleNow") is not True:
        blockers.append("COPY_CANDIDATE_NOT_REAL_WALLET_ELIGIBLE")
    if risk.get("orderSendAllowed") is not True or risk.get("walletWriteAllowed") is not True:
        blockers.append("COPY_CANDIDATE_WALLET_WRITE_BLOCKED")
    if not token_id:
        blockers.append("CLOB_TOKEN_ID_MISSING")
    if stake <= 0:
        blockers.append("STAKE_NOT_POSITIVE")
    if size < args.min_order_size:
        blockers.append("ORDER_SIZE_LT_MIN")
    return unique(blockers)


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def active_existing_order_for_plan(plan: dict[str, Any], existing_rows: list[dict[str, str]]) -> dict[str, str]:
    candidate_id = str(plan.get("candidateId") or "").strip().lower()
    market_id = str(plan.get("marketId") or "").strip().lower()
    live_statuses = {"live", "open", "pending", "unmatched"}
    for row in reversed(existing_rows):
        if not boolish(row.get("order_sent") or row.get("orderSent")):
            continue
        row_candidate = str(row.get("candidate_id") or row.get("candidateId") or "").strip().lower()
        row_market = str(row.get("market_id") or row.get("marketId") or "").strip().lower()
        if candidate_id and row_candidate and candidate_id != row_candidate:
            continue
        if not candidate_id and market_id and row_market and market_id != row_market:
            continue
        status = str(row.get("response_status") or row.get("status") or row.get("adapter_status") or "").strip().lower()
        if status in live_statuses or "live" in status or "open" in status:
            return row
    return {}


def attach_existing_live_order(plan: dict[str, Any], row: dict[str, str]) -> None:
    response_id = first_text(row.get("response_id"), row.get("orderID"), row.get("orderId"))
    plan["orderSent"] = True
    plan["adapterStatus"] = "EXISTING_LIVE_ORDER"
    plan["response"] = {
        "orderID": response_id,
        "status": first_text(row.get("response_status"), row.get("status"), "live"),
        "source": "order_audit_ledger",
    }
    plan["blockers"] = unique([*(plan.get("blockers") or []), "EXISTING_LIVE_ORDER"])


def build_copy_candidate_plan(
    args: argparse.Namespace,
    copy_discovery: dict[str, Any],
    env_state: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = [
        row for row in get_rows(copy_discovery, "shadowCandidates")
        if isinstance(row.get("riskPlan"), dict)
        and (row.get("riskPlan") or {}).get("realWalletEligibleNow") is True
    ]
    candidates.sort(
        key=lambda row: (
            safe_number(row.get("copyScore"), 0.0) or 0.0,
            safe_number(row.get("candidateScore"), 0.0) or 0.0,
            safe_number(row.get("currentValue"), 0.0) or 0.0,
        ),
        reverse=True,
    )
    plans: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for row in candidates:
        risk = row.get("riskPlan") if isinstance(row.get("riskPlan"), dict) else {}
        token_id = copy_candidate_token_id(row)
        if token_id and token_id in seen_tokens:
            continue
        if token_id:
            seen_tokens.add(token_id)
        price = copy_candidate_price(row, args.default_limit_price)
        stake = safe_number(risk.get("maxStakeUSDC"), 0.0) or 0.0
        size = round(stake / price, 6) if price > 0 else 0.0
        blockers = unique([*runtime_blockers(env_state), *copy_candidate_blockers(row, token_id, stake, size, args)])
        market_id = first_text(row.get("conditionId"), row.get("marketSlug"), row.get("eventSlug"))
        trader = first_text(row.get("trader"), row.get("proxyWallet"))
        plans.append({
            "candidateId": "COPY-" + stable_id(token_id, market_id, trader, row.get("outcome")),
            "governanceId": "",
            "marketId": market_id,
            "question": first_text(row.get("marketTitle"), row.get("question"), row.get("marketSlug")),
            "polymarketUrl": row.get("url", ""),
            "track": "copy_trader",
            "side": "BUY",
            "_tokenId": token_id,
            "tokenId": token_id,
            "tokenIdPresent": bool(token_id),
            "tokenIdMasked": token_id[:6] + "..." + token_id[-4:] if len(token_id) > 10 else ("present" if token_id else ""),
            "limitPrice": price,
            "stakeUSDC": round(stake, 2),
            "size": size,
            "takeProfitPct": risk.get("takeProfitPct"),
            "takeProfitUSDC": risk.get("takeProfitUSDC"),
            "stopLossPct": risk.get("stopLossPct"),
            "trailingProfitPct": first_text(risk.get("trailingStopPct"), risk.get("trailingProfitPct")),
            "copiedTrader": trader,
            "sourceProxyWallet": row.get("proxyWallet", ""),
            "copyScore": row.get("copyScore"),
            "outcome": row.get("outcome", ""),
            "decision": "READY_TO_SEND_IF_ADAPTER_OK" if not blockers else "BLOCKED_PRE_ORDER",
            "blockers": blockers,
            "orderSent": False,
            "adapterStatus": "NOT_ATTEMPTED",
            "response": {},
        })
        if len(plans) >= max(0, args.max_orders):
            break
    return plans


def try_send_order(plan: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Attempt a real CLOB order only after all outer guardrails passed."""
    token_id = str(plan.get("_tokenId") or os.environ.get("QG_POLYMARKET_CANARY_TOKEN_ID") or "")
    private_key = os.environ.get("QG_POLYMARKET_PRIVATE_KEY") or ""
    host = os.environ.get("QG_POLYMARKET_CLOB_HOST") or "https://clob.polymarket.com"
    chain_id = safe_int(os.environ.get("QG_POLYMARKET_CHAIN_ID"), 137)
    signature_type = clob_v2_signature_type()
    funder = os.environ.get("QG_POLYMARKET_FUNDER") or None
    if not token_id or not private_key:
        return False, "CLOB_TOKEN_OR_PRIVATE_KEY_MISSING", {}
    def send_v2_order(*, force_create_api_key: bool = False) -> tuple[bool, str, dict[str, Any]]:
        from py_clob_client_v2 import ClobClient, OrderArgs, OrderType  # type: ignore

        client = ClobClient(
            host=host,
            chain_id=chain_id,
            key=private_key,
            signature_type=signature_type,
            funder=funder,
            use_server_time=True,
            retry_on_error=True,
        )
        signer_preflight = clob_signer_preflight(client, signature_type, funder)
        if signer_preflight["status"] != "OK":
            return False, "CLOB_SIGNER_PREFLIGHT_MISMATCH", {
                "sdk": "py-clob-client-v2",
                "signerPreflight": signer_preflight,
                "hint": "Use POLY_PROXY signature type 1 for EOA private key + Polymarket proxy/funder wallets, or explicitly configure a matching CLOB v2 signature type.",
            }
        configure_v2_api_creds(client, force_create=force_create_api_key)
        side = "BUY" if str(plan.get("side") or "BUY").upper() in {"YES", "BUY"} else "SELL"
        order_args = OrderArgs(
            price=float(plan["limitPrice"]),
            size=float(plan["size"]),
            side=side,
            token_id=token_id,
        )
        response = client.create_and_post_order(order_args, order_type=OrderType.GTC)
        status_text = "ORDER_SENT_V2"
        if isinstance(response, dict) and response.get("success") is False:
            return False, "CLOB_ORDER_FAILED_V2:REJECTED", {"sdk": "py-clob-client-v2", **response}
        return True, status_text, response if isinstance(response, dict) else {"sdk": "py-clob-client-v2", "response": str(response)[:500]}

    try:  # pragma: no cover - intentionally guarded and not exercised by tests
        return send_v2_order()
    except Exception as exc:
        if is_v2_api_key_signer_mismatch(exc):
            try:
                sent, status, response = send_v2_order(force_create_api_key=True)
                if isinstance(response, dict):
                    response.setdefault("apiKeyRecovery", "created_new_current_signer_api_key")
                return sent, status, response
            except Exception as retry_exc:
                return False, f"CLOB_API_KEY_SIGNER_MISMATCH:{type(retry_exc).__name__}", {
                    "sdk": "py-clob-client-v2",
                    "recovery": "create_api_key_retry_failed",
                    "originalError": str(exc)[:180],
                    "retryError": str(retry_exc)[:220],
                }
        v2_error = f"{type(exc).__name__}:{str(exc)[:180]}"
        if os.environ.get("QG_POLYMARKET_CLOB_DISABLE_V1_FALLBACK", "").strip().lower() in {"1", "true", "yes"}:
            return False, f"CLOB_ORDER_FAILED_V2:{type(exc).__name__}", {"sdk": "py-clob-client-v2", "error": str(exc)[:240]}

    try:
        from py_clob_client.client import ClobClient  # type: ignore
        from py_clob_client.clob_types import OrderArgs, OrderType  # type: ignore
        from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"CLOB_ADAPTER_IMPORT_FAILED:{type(exc).__name__}", {"v2Error": v2_error}
    try:  # pragma: no cover - intentionally guarded and not exercised by tests
        client = ClobClient(host, key=private_key, chain_id=chain_id, signature_type=clob_legacy_signature_type(), funder=funder)
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
        return False, f"CLOB_ORDER_FAILED:{type(exc).__name__}", {"sdk": "py-clob-client", "v2Error": v2_error, "error": str(exc)[:240]}
    return True, "ORDER_SENT", response if isinstance(response, dict) else {"sdk": "py-clob-client", "response": str(response)[:500]}


def to_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ORDER_AUDIT_FIELDS, lineterminator="\n")
    writer.writeheader()
    generated = snapshot.get("generatedAt", "")
    run_id = snapshot.get("runId", "")
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
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
                "take_profit_usdc": row.get("takeProfitUSDC", ""),
                "decision": row.get("decision", ""),
                "order_sent": row.get("orderSent", False),
                "wallet_write_allowed": summary.get("walletWriteAllowed", snapshot.get("walletWriteAllowed", False)),
                "order_send_allowed": summary.get("orderSendAllowed", snapshot.get("orderSendAllowed", False)),
                "blockers": " / ".join(row.get("blockers") or []),
                "adapter_status": row.get("adapterStatus", ""),
                "response_id": first_text(row.get("response", {}).get("orderID"), row.get("response", {}).get("id")),
                "response_status": first_text(row.get("response", {}).get("status")),
                "tx_hash": first_text(*(row.get("response", {}).get("transactionsHashes") or [])),
            }
        )
    return output.getvalue()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    except Exception:
        return []


def rows_to_csv(rows: list[dict[str, Any]], fields: list[str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return output.getvalue()


def merged_order_audit_csv(snapshot: dict[str, Any], existing_paths: list[Path]) -> str:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def row_key(row: dict[str, Any]) -> str:
        return str(row.get("response_id") or row.get("candidate_id") or json.dumps(row, sort_keys=True)).lower()

    def normalized_audit_row(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        if boolish(out.get("order_sent") or out.get("orderSent")):
            out["wallet_write_allowed"] = "True"
            out["order_send_allowed"] = "True"
        return out

    for path in existing_paths:
        for row in read_csv_rows(path):
            row = normalized_audit_row(row)
            key = row_key(row)
            if key and key not in seen:
                merged.append(row)
                seen.add(key)

    current_rows_text = to_csv(snapshot)
    current_rows = list(csv.DictReader(io.StringIO(current_rows_text)))
    for row in current_rows:
        row = normalized_audit_row(row)
        key = row_key(row)
        if key and key not in seen:
            merged.append(row)
            seen.add(key)
    return rows_to_csv(merged, ORDER_AUDIT_FIELDS)


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    governance, governance_path = read_json_candidate(GOVERNANCE_NAME, runtime_dir, dashboard_dir, args.governance_path)
    contract, contract_path = read_json_candidate(CANARY_CONTRACT_NAME, runtime_dir, dashboard_dir, args.canary_contract_path)
    copy_discovery, copy_discovery_path = read_json_candidate(COPY_DISCOVERY_NAME, runtime_dir, dashboard_dir, args.copy_discovery_path)
    wallet_policy = copy_discovery.get("walletRiskPolicy") if isinstance(copy_discovery.get("walletRiskPolicy"), dict) else {}
    lock_file = Path(args.lock_file)
    env_state = compact_env_state(lock_file, args.plan_only, wallet_policy, copy_discovery_path)
    plans = build_plan(args, governance, contract, env_state)
    plan_source = "legacy_governance"
    if not plans and wallet_policy.get("realWalletExecutionAllowed") is True:
        plans = build_copy_candidate_plan(args, copy_discovery, env_state)
        plan_source = "copy_trader_shadow_candidates" if plans else "none"
    existing_audit_rows = read_csv_rows(runtime_dir / ORDER_AUDIT_LEDGER) + read_csv_rows(dashboard_dir / ORDER_AUDIT_LEDGER)
    existing_live_orders = 0
    for plan in plans:
        existing = active_existing_order_for_plan(plan, existing_audit_rows)
        if existing:
            attach_existing_live_order(plan, existing)
            existing_live_orders += 1
    preflight_blockers = runtime_blockers(env_state)
    sendable_plans = [plan for plan in plans if plan.get("adapterStatus") != "EXISTING_LIVE_ORDER"]
    wallet_write_allowed = bool(sendable_plans) and not preflight_blockers and all(not plan.get("blockers") for plan in sendable_plans)
    order_send_allowed = wallet_write_allowed
    orders_sent = 0
    if order_send_allowed:
        for plan in sendable_plans:
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
        "executionMode": "REAL_ORDER_ATTEMPTED" if orders_sent else "EXISTING_LIVE_ORDER_TRACKED" if existing_live_orders else "GUARDED_PLAN_ONLY_NO_ORDER",
        "decision": "ORDERS_SENT" if orders_sent else "EXISTING_LIVE_ORDER_TRACKED" if existing_live_orders else "NO_REAL_ORDER_SENT",
        "sourceFiles": {
            GOVERNANCE_NAME: governance_path,
            CANARY_CONTRACT_NAME: contract_path,
            COPY_DISCOVERY_NAME: copy_discovery_path,
        },
        "envPreflight": env_state,
        "preflightBlockers": preflight_blockers,
        "summary": {
            "governanceRows": len(get_rows(governance, "governanceDecisions")),
            "contractRows": len(get_rows(contract, "candidateContracts")),
            "eligibleGovernanceRows": sum(1 for row in get_rows(governance, "governanceDecisions") if row.get("canPromoteToLiveExecution") is True),
            "copyCandidateRows": len(get_rows(copy_discovery, "shadowCandidates")),
            "eligibleCopyCandidateRows": sum(
                1 for row in get_rows(copy_discovery, "shadowCandidates")
                if isinstance(row.get("riskPlan"), dict)
                and (row.get("riskPlan") or {}).get("realWalletEligibleNow") is True
            ),
            "planSource": plan_source,
            "plannedOrders": len(plans),
            "ordersSent": orders_sent,
            "existingLiveOrders": existing_live_orders,
            "sendablePlannedOrders": len(sendable_plans),
            "walletWriteAllowed": wallet_write_allowed,
            "orderSendAllowed": order_send_allowed,
            "maxOrders": args.max_orders,
            "walletPolicyStatus": wallet_policy.get("status", ""),
            "walletPolicyRealExecutionAllowed": bool(wallet_policy.get("realWalletExecutionAllowed")),
        },
        "safety": {
            "readsPrivateKeyValueOnlyInsideFinalAdapter": bool(order_send_allowed),
            "logsPrivateKey": False,
            "walletWriteAllowed": wallet_write_allowed,
            "orderSendAllowed": order_send_allowed,
            "startsExecutorLoop": False,
            "mutatesMt5": False,
            "requiresIndependentGovernanceRecheck": True,
            "humanApprovalRequired": False,
            "autonomousPolicyCanReplaceManualAck": bool(env_state.get("autonomousPolicyAllowed")),
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
    existing_audit_paths = [runtime_dir / ORDER_AUDIT_LEDGER]
    if dashboard_dir is not None:
        existing_audit_paths.append(dashboard_dir / ORDER_AUDIT_LEDGER)
    csv_text = merged_order_audit_csv(snapshot, existing_audit_paths)
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
