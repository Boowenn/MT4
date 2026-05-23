#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXECUTOR_RUN_NAME = "QuantGod_PolymarketCanaryExecutorRun.json"
OUTPUT_NAME = "QuantGod_PolymarketCanaryExitMonitorRun.json"
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


def read_first_json(name: str, runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    for base in (dashboard_dir, runtime_dir):
        path = base / name
        if path.exists():
            return read_json(path), str(path)
    return {}, ""


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
    client.set_api_creds(client.create_or_derive_api_key())
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


def exit_decision(entry: float, current: float, high: float, tp_pct: float, sl_pct: float, trailing_pct: float) -> tuple[str, str, dict[str, float]]:
    take_profit = min(0.99, entry * (1.0 + tp_pct / 100.0)) if entry > 0 else 0.0
    stop_loss = max(0.01, entry * (1.0 - sl_pct / 100.0)) if entry > 0 else 0.0
    trailing_stop = max(0.01, high * (1.0 - trailing_pct / 100.0)) if high > entry and trailing_pct > 0 else 0.0
    levels = {
        "takeProfitPrice": round(take_profit, 4),
        "stopLossPrice": round(stop_loss, 4),
        "trailingStopPrice": round(trailing_stop, 4),
    }
    if current > 0 and take_profit > 0 and current >= take_profit:
        return "EXIT_TAKE_PROFIT", "take_profit_reached", levels
    if current > 0 and stop_loss > 0 and current <= stop_loss:
        return "EXIT_STOP_LOSS", "stop_loss_reached", levels
    if current > 0 and trailing_stop > 0 and current <= trailing_stop:
        return "EXIT_TRAILING_STOP", "trailing_stop_reached", levels
    return "HOLD", "exit_not_triggered", levels


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


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    executor, executor_path = read_first_json(EXECUTOR_RUN_NAME, runtime_dir, dashboard_dir)
    client = make_client()
    highs = previous_highs(runtime_dir, dashboard_dir)
    positions: list[dict[str, Any]] = []
    exits_sent = 0
    plan_only = args.plan_only or str_to_bool(os.environ.get("QG_POLYMARKET_CANARY_EXIT_MONITOR_PLAN_ONLY"), False)
    min_size = safe_number(os.environ.get("QG_POLYMARKET_MIN_ORDER_SIZE"), 5.0) or 5.0
    for plan in executor.get("plannedOrders") or []:
        if not isinstance(plan, dict) or not plan.get("orderSent"):
            continue
        response = plan.get("response") if isinstance(plan.get("response"), dict) else {}
        order_id = str(response.get("orderID") or response.get("id") or "")
        trade = latest_trade_for_order(client, order_id)
        token_id = str(trade.get("asset_id") or "")
        if not token_id:
            continue
        entry = safe_number(trade.get("price"), safe_number(plan.get("limitPrice"), 0.0))
        current = current_exit_price(client, token_id)
        size = current_position_size(client, token_id)
        high = max(entry, current, highs.get(token_id, 0.0))
        decision, reason, levels = exit_decision(
            entry=entry,
            current=current,
            high=high,
            tp_pct=safe_number(plan.get("takeProfitPct"), 35.0),
            sl_pct=safe_number(plan.get("stopLossPct"), 18.0),
            trailing_pct=safe_number(plan.get("trailingProfitPct"), 12.0),
        )
        exit_sent = False
        adapter_status = "NOT_ATTEMPTED"
        exit_response: dict[str, Any] = {}
        if decision.startswith("EXIT_"):
            if plan_only:
                adapter_status = "PLAN_ONLY_EXIT_SIGNAL"
            elif size < min_size:
                adapter_status = "EXIT_SIZE_BELOW_MIN"
            else:
                exit_sent, adapter_status, exit_response = send_exit_order(client, token_id, size, current)
                exits_sent += int(exit_sent)
        positions.append({
            "candidateId": plan.get("candidateId"),
            "orderID": order_id,
            "marketId": plan.get("marketId"),
            "question": plan.get("question"),
            "tokenId": token_id,
            "entryPrice": round(entry, 4),
            "currentExitPrice": round(current, 4),
            "highWatermarkPrice": round(high, 4),
            "positionSize": round(size, 6),
            **levels,
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
        "sourceFiles": {EXECUTOR_RUN_NAME: executor_path},
        "planOnly": plan_only,
        "summary": {
            "positionsTracked": len(positions),
            "exitSignals": sum(1 for row in positions if str(row.get("decision", "")).startswith("EXIT_")),
            "exitsSent": exits_sent,
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
        "tokenId",
        "entryPrice",
        "currentExitPrice",
        "highWatermarkPrice",
        "positionSize",
        "takeProfitPrice",
        "stopLossPrice",
        "trailingStopPrice",
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
