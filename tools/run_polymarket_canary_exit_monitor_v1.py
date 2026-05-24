#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXECUTOR_RUN_NAME = "QuantGod_PolymarketCanaryExecutorRun.json"
COPY_DISCOVERY_NAME = "QuantGod_PolymarketCopyTraderDiscovery.json"
OUTPUT_NAME = "QuantGod_PolymarketCanaryExitMonitorRun.json"
ORDER_AUDIT_LEDGER = "QuantGod_PolymarketCanaryOrderAuditLedger.csv"
EXIT_LEDGER = "QuantGod_PolymarketCanaryExitLedger.csv"
POSITION_LEDGER = "QuantGod_PolymarketCanaryPositionLedger.csv"
SCHEMA_VERSION = "1.0"


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def str_to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as fh:
        fh.write(text)
        tmp = Path(fh.name)
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def read_first_json(name: str, runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    for base in (dashboard_dir, runtime_dir):
        path = base / name
        if path.exists():
            return read_json(path), str(path)
    return {}, ""


def read_first_csv(name: str, runtime_dir: Path, dashboard_dir: Path) -> tuple[list[dict[str, str]], str]:
    for base in (dashboard_dir, runtime_dir):
        path = base / name
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                return [dict(row) for row in csv.DictReader(fh)], str(path)
        except Exception:
            continue
    return [], ""


def make_client():
    from py_clob_client_v2 import ClobClient  # type: ignore

    private_key = os.environ.get("QG_POLYMARKET_PRIVATE_KEY") or ""
    if not private_key:
        raise RuntimeError("QG_POLYMARKET_PRIVATE_KEY missing")
    client = ClobClient(
        host=os.environ.get("QG_POLYMARKET_CLOB_HOST") or "https://clob.polymarket.com",
        chain_id=safe_int(os.environ.get("QG_POLYMARKET_CHAIN_ID"), 137),
        key=private_key,
        signature_type=safe_int(os.environ.get("QG_POLYMARKET_SIGNATURE_TYPE"), 0),
        funder=os.environ.get("QG_POLYMARKET_FUNDER") or None,
        retry_on_error=True,
    )
    try:
        client.set_api_creds(client.create_or_derive_api_key())
    except Exception as exc:
        setattr(client, "_qg_api_creds_error", f"{type(exc).__name__}:{str(exc)[:160]}")
    return client


def latest_trade_for_order(client: Any, order_id: str) -> dict[str, Any]:
    if not order_id:
        return {}
    try:
        trades = client.get_trades(only_first_page=True)
    except Exception:
        return {}
    for trade in trades or []:
        if str(trade.get("taker_order_id") or trade.get("maker_order_id") or trade.get("order_id") or "").lower() == order_id.lower():
            return trade if isinstance(trade, dict) else {}
    return {}


def current_position_size(client: Any, token_id: str) -> float:
    from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams  # type: ignore

    try:
        payload = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
        )
    except Exception:
        return 0.0
    return safe_number(payload.get("balance"), 0.0) / 1_000_000.0


def current_exit_price(client: Any, token_id: str) -> float:
    for side in ("SELL", "BUY"):
        try:
            payload = client.get_price(token_id, side)
            price = safe_number(payload.get("price") if isinstance(payload, dict) else payload, 0.0)
            if price > 0:
                return price
        except Exception:
            continue
    try:
        payload = client.get_midpoint(token_id)
        return safe_number(payload.get("mid") if isinstance(payload, dict) else payload, 0.0)
    except Exception:
        return 0.0


def previous_highs(runtime_dir: Path, dashboard_dir: Path) -> dict[str, float]:
    data, _ = read_first_json(OUTPUT_NAME, runtime_dir, dashboard_dir)
    highs: dict[str, float] = {}
    for row in data.get("positions") or []:
        if isinstance(row, dict) and row.get("tokenId"):
            highs[str(row["tokenId"])] = safe_number(row.get("highWatermarkPrice"), 0.0)
    return highs


def exit_decision(
    entry: float,
    current: float,
    high: float,
    size: float,
    tp_pct: float,
    tp_usdc: float,
    sl_pct: float,
    trailing_pct: float,
) -> tuple[str, str, dict[str, float]]:
    take_profit = min(0.99, entry * (1.0 + tp_pct / 100.0)) if entry > 0 else 0.0
    stop_loss = max(0.01, entry * (1.0 - sl_pct / 100.0)) if entry > 0 else 0.0
    trailing_stop = max(0.01, high * (1.0 - trailing_pct / 100.0)) if high > entry and trailing_pct > 0 else 0.0
    unrealized_pnl = (current - entry) * size if current > 0 and entry > 0 and size > 0 else 0.0
    take_profit_usdc_price = entry + (tp_usdc / size) if entry > 0 and size > 0 and tp_usdc > 0 else 0.0
    levels = {
        "takeProfitPrice": round(take_profit, 4),
        "takeProfitUSDC": round(tp_usdc, 4),
        "takeProfitUSDCPrice": round(take_profit_usdc_price, 4),
        "stopLossPrice": round(stop_loss, 4),
        "trailingStopPrice": round(trailing_stop, 4),
        "unrealizedPnlUSDC": round(unrealized_pnl, 4),
    }
    if current > 0 and tp_usdc > 0 and unrealized_pnl >= tp_usdc:
        return "EXIT_TAKE_PROFIT_USDC", "take_profit_usdc_reached", levels
    if current > 0 and take_profit > 0 and current >= take_profit:
        return "EXIT_TAKE_PROFIT", "take_profit_reached", levels
    if current > 0 and stop_loss > 0 and current <= stop_loss:
        return "EXIT_STOP_LOSS", "stop_loss_reached", levels
    if current > 0 and trailing_stop > 0 and current <= trailing_stop:
        return "EXIT_TRAILING_STOP", "trailing_stop_reached", levels
    return "HOLD", "exit_not_triggered", levels


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def row_matches_position(row: dict[str, Any], plan: dict[str, Any], token_id: str) -> bool:
    if token_id and normalized(row.get("asset")) == normalized(token_id):
        return True
    market_id = normalized(plan.get("marketId"))
    outcome = normalized(plan.get("outcome"))
    if market_id and normalized(row.get("conditionId")) == market_id:
        return not outcome or normalized(row.get("outcome")) == outcome
    return False


def row_matches_plan_identity(row: dict[str, Any], plan: dict[str, Any]) -> bool:
    market_id = normalized(plan.get("marketId"))
    outcome = normalized(plan.get("outcome"))
    if market_id and normalized(row.get("conditionId")) != market_id:
        return False
    if outcome and normalized(row.get("outcome")) != outcome:
        return False
    return bool(market_id or outcome)


def source_position_size(row: dict[str, Any]) -> float:
    for key in ("size", "positionSize", "quantity"):
        size = safe_number(row.get(key), 0.0)
        if size > 0:
            return size
    value = safe_number(row.get("currentValue") or row.get("value"), 0.0)
    price = safe_number(row.get("curPrice") or row.get("price"), 0.0)
    return value / price if value > 0 and price > 0 else 0.0


def resolve_plan_token_id(plan: dict[str, Any], copy_discovery: dict[str, Any]) -> str:
    for key in ("_tokenId", "tokenId", "asset", "outcomeTokenId"):
        token_id = str(plan.get(key) or "").strip()
        if token_id and "..." not in token_id.lower() and token_id.lower() != "present":
            return token_id
    copied_trader = normalized(plan.get("copiedTrader"))
    source_wallet = normalized(plan.get("sourceProxyWallet"))
    candidate_id = str(plan.get("candidateId") or "").strip()
    for candidate in copy_discovery.get("shadowCandidates") or []:
        if not isinstance(candidate, dict):
            continue
        candidate_token = str(candidate.get("asset") or "").strip()
        candidate_market = str(candidate.get("conditionId") or candidate.get("marketSlug") or candidate.get("eventSlug") or "")
        candidate_trader = str(candidate.get("trader") or candidate.get("proxyWallet") or "")
        candidate_outcome = str(candidate.get("outcome") or "")
        derived_candidate_id = "COPY-" + stable_id(candidate_token, candidate_market, candidate_trader, candidate_outcome)
        if candidate_id and derived_candidate_id == candidate_id and candidate_token:
            return candidate_token
        if not row_matches_plan_identity(candidate, plan):
            continue
        trader_match = copied_trader and normalized(candidate.get("trader")) == copied_trader
        wallet_match = source_wallet and normalized(candidate.get("proxyWallet")) == source_wallet
        if trader_match or wallet_match:
            if candidate_token:
                return candidate_token
    for trader in copy_discovery.get("traders") or []:
        if not isinstance(trader, dict):
            continue
        trader_match = copied_trader and normalized(trader.get("userName")) == copied_trader
        wallet_match = source_wallet and normalized(trader.get("proxyWallet")) == source_wallet
        if not (trader_match or wallet_match):
            continue
        for position in trader.get("currentPositions") or []:
            if isinstance(position, dict) and row_matches_plan_identity(position, plan):
                token_id = str(position.get("asset") or "").strip()
                if token_id:
                    return token_id
    return ""


def enrich_plan_from_discovery(plan: dict[str, Any], token_id: str, copy_discovery: dict[str, Any]) -> dict[str, Any]:
    if plan.get("copiedTrader") and plan.get("sourceProxyWallet") and plan.get("outcome"):
        return plan
    candidate_id = str(plan.get("candidateId") or "").strip()
    candidates = [row for row in copy_discovery.get("shadowCandidates") or [] if isinstance(row, dict)]
    for candidate in candidates:
        candidate_token = str(candidate.get("asset") or "").strip()
        candidate_market = str(candidate.get("conditionId") or candidate.get("marketSlug") or candidate.get("eventSlug") or "")
        candidate_trader = str(candidate.get("trader") or candidate.get("proxyWallet") or "")
        candidate_outcome = str(candidate.get("outcome") or "")
        derived_candidate_id = "COPY-" + stable_id(candidate_token, candidate_market, candidate_trader, candidate_outcome)
        if candidate_id and derived_candidate_id == candidate_id:
            enriched = dict(plan)
            enriched.setdefault("copiedTrader", candidate.get("trader") or "")
            enriched.setdefault("sourceProxyWallet", candidate.get("proxyWallet") or "")
            enriched.setdefault("outcome", candidate.get("outcome") or "")
            enriched.setdefault("polymarketUrl", candidate.get("url") or "")
            return enriched
    for candidate in copy_discovery.get("shadowCandidates") or []:
        if not isinstance(candidate, dict):
            continue
        candidate_token = str(candidate.get("asset") or "").strip()
        identity_hint = bool(plan.get("copiedTrader") or plan.get("sourceProxyWallet") or plan.get("outcome"))
        token_match = identity_hint and token_id and candidate_token == token_id and row_matches_plan_identity(candidate, plan)
        if token_match:
            enriched = dict(plan)
            enriched.setdefault("copiedTrader", candidate.get("trader") or "")
            enriched.setdefault("sourceProxyWallet", candidate.get("proxyWallet") or "")
            enriched.setdefault("outcome", candidate.get("outcome") or "")
            enriched.setdefault("polymarketUrl", candidate.get("url") or "")
            return enriched
    return plan


def source_trader_position_state(
    plan: dict[str, Any],
    token_id: str,
    copy_discovery: dict[str, Any],
) -> dict[str, Any]:
    copied_trader = str(plan.get("copiedTrader") or "").strip()
    source_wallet = str(plan.get("sourceProxyWallet") or "").strip().lower()
    state = {
        "sourceTrader": copied_trader,
        "sourceProxyWallet": source_wallet,
        "sourcePositionStatus": "SOURCE_CHECK_UNAVAILABLE",
        "sourcePositionPresent": None,
        "sourcePositionSize": 0.0,
        "sourcePositionValue": 0.0,
        "sourcePositionPrice": 0.0,
        "sourcePositionUrl": "",
    }
    if not copied_trader and not source_wallet:
        return state

    for candidate in copy_discovery.get("shadowCandidates") or []:
        if not isinstance(candidate, dict) or not row_matches_position(candidate, plan, token_id):
            continue
        trader_match = copied_trader and normalized(candidate.get("trader")) == normalized(copied_trader)
        wallet_match = source_wallet and normalized(candidate.get("proxyWallet")) == source_wallet
        if trader_match or wallet_match:
            return {
                **state,
                "sourceTrader": str(candidate.get("trader") or copied_trader),
                "sourceProxyWallet": str(candidate.get("proxyWallet") or source_wallet).lower(),
                "sourcePositionStatus": "SOURCE_POSITION_STILL_HELD",
                "sourcePositionPresent": True,
                "sourcePositionSize": round(source_position_size(candidate), 6),
                "sourcePositionValue": round(safe_number(candidate.get("currentValue")), 4),
                "sourcePositionPrice": round(safe_number(candidate.get("curPrice")), 4),
                "sourcePositionUrl": str(candidate.get("url") or ""),
            }

    matched_trader: dict[str, Any] = {}
    for trader in copy_discovery.get("traders") or []:
        if not isinstance(trader, dict):
            continue
        trader_match = copied_trader and normalized(trader.get("userName")) == normalized(copied_trader)
        wallet_match = source_wallet and normalized(trader.get("proxyWallet")) == source_wallet
        if trader_match or wallet_match:
            matched_trader = trader
            break
    if not matched_trader:
        return state

    state = {
        **state,
        "sourceTrader": str(matched_trader.get("userName") or copied_trader),
        "sourceProxyWallet": str(matched_trader.get("proxyWallet") or source_wallet).lower(),
    }
    for position in matched_trader.get("currentPositions") or []:
        if isinstance(position, dict) and row_matches_position(position, plan, token_id):
            return {
                **state,
                "sourcePositionStatus": "SOURCE_POSITION_STILL_HELD",
                "sourcePositionPresent": True,
                "sourcePositionSize": round(source_position_size(position), 6),
                "sourcePositionValue": round(safe_number(position.get("currentValue")), 4),
                "sourcePositionPrice": round(safe_number(position.get("curPrice")), 4),
                "sourcePositionUrl": str(position.get("url") or ""),
            }
    return {
        **state,
        "sourcePositionStatus": "SOURCE_POSITION_NOT_HELD",
        "sourcePositionPresent": False,
    }


def send_exit_order(client: Any, token_id: str, size: float, price: float) -> tuple[bool, str, dict[str, Any]]:
    from py_clob_client_v2 import OrderArgs, OrderType  # type: ignore

    try:
        response = client.create_and_post_order(
            OrderArgs(price=float(price), size=float(size), side="SELL", token_id=token_id),
            order_type=OrderType.GTC,
        )
    except Exception as exc:
        return False, f"EXIT_ORDER_FAILED:{type(exc).__name__}", {"error": str(exc)[:240]}
    if isinstance(response, dict) and response.get("success") is False:
        return False, "EXIT_ORDER_REJECTED", response
    return True, "EXIT_ORDER_SENT_V2", response if isinstance(response, dict) else {"response": str(response)[:500]}


def fallback_plans_from_order_audit(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for row in reversed(rows):
        if not str_to_bool(row.get("order_sent"), False):
            continue
        order_id = str(row.get("response_id") or "").strip()
        if not order_id:
            continue
        plans.append({
            "candidateId": row.get("candidate_id", ""),
            "governanceId": row.get("governance_id", ""),
            "marketId": row.get("market_id", ""),
            "question": row.get("question", ""),
            "track": row.get("track", ""),
            "side": row.get("side", "BUY"),
            "limitPrice": safe_number(row.get("limit_price"), 0.0),
            "stakeUSDC": safe_number(row.get("stake_usdc"), 0.0),
            "size": safe_number(row.get("size"), 0.0),
            "takeProfitPct": safe_number(os.environ.get("QG_POLYMARKET_REAL_WALLET_TAKE_PROFIT_PCT"), 2.0),
            "takeProfitUSDC": safe_number(
                row.get("take_profit_usdc"),
                safe_number(os.environ.get("QG_POLYMARKET_REAL_WALLET_TAKE_PROFIT_USDC"), 0.05),
            ),
            "stopLossPct": safe_number(os.environ.get("QG_POLYMARKET_REAL_WALLET_STOP_LOSS_PCT"), 4.0),
            "trailingProfitPct": safe_number(os.environ.get("QG_POLYMARKET_REAL_WALLET_TRAILING_STOP_PCT"), 2.0),
            "decision": row.get("decision", ""),
            "orderSent": True,
            "adapterStatus": row.get("adapter_status", ""),
            "response": {
                "orderID": order_id,
                "status": row.get("response_status", ""),
                "transactionsHashes": [row.get("tx_hash", "")] if row.get("tx_hash") else [],
            },
        })
    return plans


def active_order_plans(executor: dict[str, Any], order_audit_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    plans = [plan for plan in executor.get("plannedOrders") or [] if isinstance(plan, dict) and plan.get("orderSent")]
    seen_order_ids = {
        str((plan.get("response") if isinstance(plan.get("response"), dict) else {}).get("orderID") or "").lower()
        for plan in plans
    }
    for plan in fallback_plans_from_order_audit(order_audit_rows):
        order_id = str((plan.get("response") or {}).get("orderID") or "").lower()
        if order_id and order_id not in seen_order_ids:
            plans.append(plan)
            seen_order_ids.add(order_id)
    return plans


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    executor, executor_path = read_first_json(EXECUTOR_RUN_NAME, runtime_dir, dashboard_dir)
    copy_discovery, copy_discovery_path = read_first_json(COPY_DISCOVERY_NAME, runtime_dir, dashboard_dir)
    order_audit_rows, order_audit_path = read_first_csv(ORDER_AUDIT_LEDGER, runtime_dir, dashboard_dir)
    client = make_client()
    highs = previous_highs(runtime_dir, dashboard_dir)
    positions: list[dict[str, Any]] = []
    exits_sent = 0
    plan_only = args.plan_only or str_to_bool(os.environ.get("QG_POLYMARKET_CANARY_EXIT_MONITOR_PLAN_ONLY"), False)
    min_size = safe_number(os.environ.get("QG_POLYMARKET_MIN_ORDER_SIZE"), 5.0) or 5.0
    for plan in active_order_plans(executor, order_audit_rows):
        response = plan.get("response") if isinstance(plan.get("response"), dict) else {}
        order_id = str(response.get("orderID") or response.get("id") or "")
        trade = latest_trade_for_order(client, order_id)
        token_id = str(trade.get("asset_id") or "") or resolve_plan_token_id(plan, copy_discovery)
        if not token_id:
            continue
        plan = enrich_plan_from_discovery(plan, token_id, copy_discovery)
        entry = safe_number(trade.get("price"), safe_number(plan.get("limitPrice"), 0.0))
        current = current_exit_price(client, token_id)
        size = current_position_size(client, token_id)
        high = max(entry, current, highs.get(token_id, 0.0))
        decision, reason, levels = exit_decision(
            entry=entry,
            current=current,
            high=high,
            size=size,
            tp_pct=safe_number(plan.get("takeProfitPct"), 2.0),
            tp_usdc=safe_number(plan.get("takeProfitUSDC"), 0.05),
            sl_pct=safe_number(plan.get("stopLossPct"), 4.0),
            trailing_pct=safe_number(plan.get("trailingProfitPct"), 2.0),
        )
        source_state = source_trader_position_state(plan, token_id, copy_discovery)
        if source_state.get("sourcePositionPresent") is False:
            decision = "EXIT_SOURCE_TRADER_CLOSED"
            reason = "copied_trader_no_longer_holds_token"
        exit_sent = False
        adapter_status = "NOT_ATTEMPTED"
        exit_response: dict[str, Any] = {}
        if decision.startswith("EXIT_"):
            if plan_only:
                adapter_status = "PLAN_ONLY_EXIT_SIGNAL"
            elif size < min_size:
                adapter_status = "EXIT_SIZE_BELOW_MIN"
            elif current <= 0:
                adapter_status = "EXIT_PRICE_UNAVAILABLE"
            else:
                exit_sent, adapter_status, exit_response = send_exit_order(client, token_id, size, current)
                exits_sent += int(exit_sent)
        positions.append({
            "candidateId": plan.get("candidateId"),
            "orderID": order_id,
            "marketId": plan.get("marketId"),
            "question": plan.get("question"),
            "copiedTrader": plan.get("copiedTrader"),
            "sourceProxyWallet": plan.get("sourceProxyWallet", ""),
            "tokenId": token_id,
            "entryPrice": round(entry, 4),
            "currentExitPrice": round(current, 4),
            "highWatermarkPrice": round(high, 4),
            "positionSize": round(size, 6),
            **levels,
            **source_state,
            "decision": decision,
            "reason": reason,
            "exitSent": exit_sent,
            "adapterStatus": adapter_status,
            "response": exit_response,
        })
    return {
        "mode": "POLYMARKET_CANARY_EXIT_MONITOR_V1",
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now_iso(),
        "status": "OK",
        "sourceFiles": {
            EXECUTOR_RUN_NAME: executor_path,
            COPY_DISCOVERY_NAME: copy_discovery_path,
            ORDER_AUDIT_LEDGER: order_audit_path,
        },
        "planOnly": plan_only,
        "summary": {
            "positionsTracked": len(positions),
            "exitSignals": sum(1 for row in positions if str(row.get("decision", "")).startswith("EXIT_")),
            "exitsSent": exits_sent,
            "sourceExitSignals": sum(1 for row in positions if row.get("reason") == "copied_trader_no_longer_holds_token"),
        },
        "positions": positions,
    }


def rows_to_csv(rows: list[dict[str, Any]], fields: list[str]) -> str:
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path) -> int:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    fields = [
        "candidateId",
        "orderID",
        "marketId",
        "copiedTrader",
        "sourceProxyWallet",
        "tokenId",
        "entryPrice",
        "currentExitPrice",
        "highWatermarkPrice",
        "positionSize",
        "takeProfitPrice",
        "takeProfitUSDC",
        "takeProfitUSDCPrice",
        "stopLossPrice",
        "trailingStopPrice",
        "unrealizedPnlUSDC",
        "sourcePositionStatus",
        "sourcePositionPresent",
        "sourcePositionSize",
        "sourcePositionValue",
        "sourcePositionPrice",
        "decision",
        "reason",
        "exitSent",
        "adapterStatus",
    ]
    csv_text = rows_to_csv(snapshot.get("positions") or [], fields)
    written = 0
    for base in (runtime_dir, dashboard_dir):
        atomic_write_text(base / OUTPUT_NAME, json_text)
        atomic_write_text(base / POSITION_LEDGER, csv_text)
        atomic_write_text(base / EXIT_LEDGER, csv_text)
        written += 3
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--dashboard-dir", required=True)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, Path(args.runtime_dir), Path(args.dashboard_dir))
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | tracked={summary['positionsTracked']} | "
        f"signals={summary['exitSignals']} | exits={summary['exitsSent']} | wrote={written}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
