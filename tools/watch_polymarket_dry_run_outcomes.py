#!/usr/bin/env python3
"""Watch dry-run Polymarket order outcomes without wallet writes.

The watcher reads dry-run order plans plus the latest market radar snapshot,
then updates each simulated order with current price, MFE/MAE, and whether it
would have triggered TP, SL, trailing exit, max-hold exit, or pre-resolution
exit. It never connects to a wallet, sends an order, or mutates MT5.
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
DRY_RUN_NAME = "QuantGod_PolymarketDryRunOrders.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
OUTPUT_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"
LEDGER_NAME = "QuantGod_PolymarketDryRunOutcomeLedger.csv"


LEDGER_FIELDS = [
    "generated_at",
    "tracking_key",
    "dry_run_order_id",
    "market_id",
    "question",
    "track",
    "side",
    "state",
    "would_exit_reason",
    "triggered_reasons",
    "can_open_dry_run",
    "entry_price",
    "current_price",
    "max_observed_price",
    "min_observed_price",
    "unrealized_pct",
    "mfe_pct",
    "mae_pct",
    "take_profit_price",
    "stop_loss_price",
    "trailing_trigger_price",
    "trailing_stop_price",
    "first_seen_at",
    "max_hold_until",
    "exit_before_resolution_at",
    "blockers",
    "wallet_write",
    "order_send",
    "observation_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--dry-run-path", default="")
    parser.add_argument("--radar-path", default="")
    parser.add_argument("--previous-path", default="")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


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


def dt_iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


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
    dry_run = Path(args.dry_run_path) if args.dry_run_path else runtime_dir / DRY_RUN_NAME
    radar = Path(args.radar_path) if args.radar_path else runtime_dir / RADAR_NAME
    previous = Path(args.previous_path) if args.previous_path else runtime_dir / OUTPUT_NAME
    return dry_run, radar, previous


def make_radar_index(radar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in radar.get("radar") or []:
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("marketId") or "").strip()
        if market_id:
            index[market_id] = item
    return index


def side_price(probability: Any, side: str) -> float | None:
    if probability is None or probability == "":
        return None
    price = safe_number(probability, -1.0)
    if price < 0:
        return None
    if price > 1:
        price = price / 100.0
    price = clamp(price, 0.01, 0.99)
    if str(side or "YES").upper() == "NO":
        price = 1.0 - price
    return round(clamp(price, 0.01, 0.99), 4)


def previous_state_index(previous: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in previous.get("outcomes") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("trackingKey") or "").strip()
        if key:
            index[key] = item
    return index


def stable_tracking_key(order: dict[str, Any]) -> str:
    existing = str(order.get("trackingKey") or "").strip()
    if existing:
        return existing
    return "|".join(
        [
            str(order.get("marketId") or "").strip(),
            str(order.get("track") or "").strip(),
            str(order.get("side") or "YES").upper(),
        ]
    )


def pct_change(current: float | None, entry: float) -> float | None:
    if current is None or entry <= 0:
        return None
    return round((current - entry) / entry * 100.0, 3)


def build_outcome(
    now: datetime,
    order: dict[str, Any],
    radar_item: dict[str, Any],
    previous: dict[str, Any] | None,
    dry_run_generated_at: datetime | None,
) -> dict[str, Any]:
    key = stable_tracking_key(order)
    side = str(order.get("side") or "YES").upper()
    entry_price = safe_number(order.get("entryPrice"), 0.0)
    current_price = side_price(radar_item.get("probability"), side) if radar_item else None
    previous = previous or {}
    first_seen = parse_dt(previous.get("firstSeenAt")) or dry_run_generated_at or now
    exit_plan = order.get("exitPlan") or {}
    max_hold_hours = safe_number(exit_plan.get("maxHoldHours"), 36.0)
    max_hold_until = first_seen + timedelta(hours=max_hold_hours)
    exit_before_resolution_at = parse_dt(exit_plan.get("exitBeforeResolutionAt"))

    observed_prices = [entry_price]
    if current_price is not None:
        observed_prices.append(current_price)
    prev_max = safe_number(previous.get("maxObservedPrice"), 0.0)
    prev_min = safe_number(previous.get("minObservedPrice"), 0.0)
    if prev_max > 0:
        observed_prices.append(prev_max)
    if prev_min > 0:
        observed_prices.append(prev_min)

    max_observed = round(max(observed_prices), 4) if observed_prices else 0.0
    min_observed = round(min(value for value in observed_prices if value > 0), 4) if observed_prices else 0.0
    take_profit_price = safe_number(exit_plan.get("takeProfitPrice"), 0.0)
    stop_loss_price = safe_number(exit_plan.get("stopLossPrice"), 0.0)
    trailing_trigger = safe_number(exit_plan.get("trailingTriggerPrice"), 0.0)
    trailing_pct = safe_number(exit_plan.get("trailingProfitPct"), 0.0)
    trailing_stop = round(clamp(max_observed * (1.0 - trailing_pct / 100.0), 0.01, 0.99), 4) if max_observed > 0 and trailing_pct > 0 else 0.0

    triggered: list[str] = []
    if current_price is None:
        triggered.append("WAITING_CURRENT_PRICE")
    if take_profit_price > 0 and max_observed >= take_profit_price:
        triggered.append("TAKE_PROFIT_PRICE_HIT")
    if stop_loss_price > 0 and min_observed <= stop_loss_price:
        triggered.append("STOP_LOSS_PRICE_HIT")
    if (
        current_price is not None
        and trailing_trigger > 0
        and trailing_stop > 0
        and max_observed >= trailing_trigger
        and current_price <= trailing_stop
    ):
        triggered.append("TRAILING_STOP_ARMED_AND_REVERSED")
    if exit_before_resolution_at and now >= exit_before_resolution_at:
        triggered.append("EXIT_BEFORE_RESOLUTION")
    if max_hold_until and now >= max_hold_until:
        triggered.append("MAX_HOLD_TIME_REACHED")

    exit_reasons = [item for item in triggered if item != "WAITING_CURRENT_PRICE"]
    if "TAKE_PROFIT_PRICE_HIT" in exit_reasons and "STOP_LOSS_PRICE_HIT" in exit_reasons:
        state = "AMBIGUOUS_TP_SL_TRIGGER"
        would_exit_reason = "AMBIGUOUS_TP_SL_TRIGGER"
    elif exit_reasons:
        priority = [
            "STOP_LOSS_PRICE_HIT",
            "TAKE_PROFIT_PRICE_HIT",
            "TRAILING_STOP_ARMED_AND_REVERSED",
            "EXIT_BEFORE_RESOLUTION",
            "MAX_HOLD_TIME_REACHED",
        ]
        would_exit_reason = next((item for item in priority if item in exit_reasons), exit_reasons[0])
        state = f"WOULD_EXIT_{would_exit_reason}"
    elif current_price is None:
        state = "WAITING_CURRENT_PRICE"
        would_exit_reason = ""
    elif not safe_bool(order.get("canOpenDryRun")):
        state = "GATE_BLOCKED_PRICE_WATCH_ONLY"
        would_exit_reason = ""
    else:
        state = "HOLD_DRY_RUN"
        would_exit_reason = ""

    return {
        "trackingKey": key,
        "dryRunOrderId": order.get("dryRunOrderId", ""),
        "marketId": order.get("marketId", ""),
        "question": order.get("question", ""),
        "track": order.get("track", ""),
        "side": side,
        "state": state,
        "wouldExitReason": would_exit_reason,
        "triggeredReasons": unique(triggered),
        "canOpenDryRun": safe_bool(order.get("canOpenDryRun")),
        "entryPrice": round(entry_price, 4),
        "currentPrice": current_price,
        "maxObservedPrice": max_observed,
        "minObservedPrice": min_observed,
        "unrealizedPct": pct_change(current_price, entry_price),
        "mfePct": pct_change(max_observed, entry_price),
        "maePct": pct_change(min_observed, entry_price),
        "takeProfitPrice": take_profit_price,
        "stopLossPrice": stop_loss_price,
        "trailingTriggerPrice": trailing_trigger,
        "trailingStopPrice": trailing_stop,
        "firstSeenAt": dt_iso(first_seen),
        "lastObservedAt": dt_iso(now),
        "maxHoldUntil": dt_iso(max_hold_until),
        "exitBeforeResolutionAt": dt_iso(exit_before_resolution_at),
        "blockers": unique([str(item) for item in (order.get("blockers") or [])]),
        "walletWrite": False,
        "orderSend": False,
        "observationStatus": "OUTCOME_WATCH_ONLY_NO_WALLET_WRITE",
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dry_run_path, radar_path, previous_path = resolve_inputs(args)
    dashboard_previous = Path(args.dashboard_dir) / OUTPUT_NAME if args.dashboard_dir else Path()
    dry_run = load_json(dry_run_path)
    radar = load_json(radar_path)
    previous = load_json(previous_path) or (load_json(dashboard_previous) if dashboard_previous else {})
    previous_index = previous_state_index(previous)
    radar_index = make_radar_index(radar)
    now = utc_now()
    dry_run_generated_at = parse_dt(dry_run.get("generatedAt"))
    orders = [item for item in (dry_run.get("dryRunOrders") or []) if isinstance(item, dict)]
    outcomes = [
        build_outcome(
            now,
            order,
            radar_index.get(str(order.get("marketId") or ""), {}),
            previous_index.get(stable_tracking_key(order)),
            dry_run_generated_at,
        )
        for order in orders
    ]
    would_exit = [item for item in outcomes if str(item.get("state") or "").startswith("WOULD_EXIT_") or item.get("state") == "AMBIGUOUS_TP_SL_TRIGGER"]
    summary = {
        "watchedOrders": len(outcomes),
        "wouldExit": len(would_exit),
        "takeProfit": sum(1 for item in outcomes if "TAKE_PROFIT_PRICE_HIT" in (item.get("triggeredReasons") or [])),
        "stopLoss": sum(1 for item in outcomes if "STOP_LOSS_PRICE_HIT" in (item.get("triggeredReasons") or [])),
        "trailingExit": sum(1 for item in outcomes if "TRAILING_STOP_ARMED_AND_REVERSED" in (item.get("triggeredReasons") or [])),
        "timeExit": sum(1 for item in outcomes if "MAX_HOLD_TIME_REACHED" in (item.get("triggeredReasons") or [])),
        "preResolutionExit": sum(1 for item in outcomes if "EXIT_BEFORE_RESOLUTION" in (item.get("triggeredReasons") or [])),
        "waitingPrice": sum(1 for item in outcomes if item.get("state") == "WAITING_CURRENT_PRICE"),
        "gateBlockedWatchOnly": sum(1 for item in outcomes if item.get("state") == "GATE_BLOCKED_PRICE_WATCH_ONLY"),
    }
    return {
        "mode": "POLYMARKET_DRY_RUN_OUTCOME_WATCHER_V1",
        "generatedAt": now.isoformat(),
        "status": "OK" if dry_run else "MISSING_DRY_RUN_ORDERS",
        "decision": "OUTCOME_WATCH_ONLY_NO_WALLET_WRITE",
        "summary": summary,
        "safety": {
            "loadsEnv": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "runtimeDir": str(runtime_dir),
            "sourceDryRun": str(dry_run_path),
            "sourceRadar": str(radar_path),
        },
        "outcomeRules": {
            "priceSource": "QuantGod_PolymarketMarketRadar.json latest probability",
            "trackingKey": "market_id + track + side",
            "historyCarryForward": "max/min observed prices are carried from previous watcher output",
            "realExecutorBoundary": "Future executor may consume this only after separate wallet gate promotion; V1 never writes wallet.",
        },
        "outcomes": outcomes,
    }


def ledger_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS)
    writer.writeheader()
    generated_at = snapshot.get("generatedAt", "")
    for row in snapshot.get("outcomes") or []:
        writer.writerow(
            {
                "generated_at": generated_at,
                "tracking_key": row.get("trackingKey", ""),
                "dry_run_order_id": row.get("dryRunOrderId", ""),
                "market_id": row.get("marketId", ""),
                "question": row.get("question", ""),
                "track": row.get("track", ""),
                "side": row.get("side", ""),
                "state": row.get("state", ""),
                "would_exit_reason": row.get("wouldExitReason", ""),
                "triggered_reasons": " / ".join(row.get("triggeredReasons") or []),
                "can_open_dry_run": row.get("canOpenDryRun", False),
                "entry_price": row.get("entryPrice", ""),
                "current_price": row.get("currentPrice", ""),
                "max_observed_price": row.get("maxObservedPrice", ""),
                "min_observed_price": row.get("minObservedPrice", ""),
                "unrealized_pct": row.get("unrealizedPct", ""),
                "mfe_pct": row.get("mfePct", ""),
                "mae_pct": row.get("maePct", ""),
                "take_profit_price": row.get("takeProfitPrice", ""),
                "stop_loss_price": row.get("stopLossPrice", ""),
                "trailing_trigger_price": row.get("trailingTriggerPrice", ""),
                "trailing_stop_price": row.get("trailingStopPrice", ""),
                "first_seen_at": row.get("firstSeenAt", ""),
                "max_hold_until": row.get("maxHoldUntil", ""),
                "exit_before_resolution_at": row.get("exitBeforeResolutionAt", ""),
                "blockers": " / ".join(row.get("blockers") or []),
                "wallet_write": row.get("walletWrite", False),
                "order_send": row.get("orderSend", False),
                "observation_status": row.get("observationStatus", ""),
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
        "Polymarket dry-run outcome watcher "
        f"{snapshot.get('decision')} | watched={summary.get('watchedOrders', 0)} "
        f"| wouldExit={summary.get('wouldExit', 0)} | tp/sl={summary.get('takeProfit', 0)}/{summary.get('stopLoss', 0)} "
        f"| outputs={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
