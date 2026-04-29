#!/usr/bin/env python3
"""Guarded MT5 pending-order worker.

The worker converts approved research artifacts into pending-order intents and
passes them through the guarded trading bridge.  Live pending-order placement
is possible only when the same bridge guards approve it; the default behavior is
dry-run audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import mt5_symbol_registry
    import mt5_trading_client
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parent))
    import mt5_symbol_registry  # type: ignore
    import mt5_trading_client  # type: ignore


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
INTENTS_NAME = "QuantGod_MT5PendingOrderIntents.json"
OUTPUT_NAME = "QuantGod_MT5PendingOrderWorker.json"
LEDGER_NAME = "QuantGod_MT5PendingOrderLedger.csv"
MODE = "MT5_PENDING_ORDER_WORKER_V1"
WORKER_VERSION = "mt5-pending-order-worker-v1"

LEDGER_FIELDS = [
    "LedgerId",
    "IntentId",
    "EventTimeIso",
    "State",
    "Decision",
    "DryRun",
    "LiveAllowed",
    "Route",
    "CanonicalSymbol",
    "BrokerSymbol",
    "OrderType",
    "Side",
    "Lots",
    "EntryPrice",
    "StopLoss",
    "TakeProfit",
    "ExpirationTimeIso",
    "SourceCandidateId",
    "Reason",
    "TradingLedgerId",
    "BrokerOrderTicket",
    "RiskSnapshotJson",
    "WorkerVersion",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path).replace("\ufeff", ""))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def clean(value: Any, max_len: int = 160) -> str:
    return " ".join(str(value or "").split())[:max_len]


def canonical_symbol(symbol: str) -> str:
    row = mt5_symbol_registry.normalize_symbol_row({"name": clean(symbol, 80).upper()})
    return clean(row.get("canonicalSymbol") or symbol, 80).upper()


def load_intents(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    raw = payload.get("intents") or payload.get("orders") or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    return [item for item in raw if isinstance(item, dict)]


def normalize_intent(row: dict[str, Any]) -> dict[str, Any]:
    broker_symbol = clean(row.get("brokerSymbol") or row.get("symbol"), 80)
    side = clean(row.get("side"), 20).lower()
    order_type = clean(row.get("orderType") or row.get("type"), 40).lower()
    if order_type in {"buy", "sell", "market"}:
        order_type = f"{side}_limit" if row.get("entryPrice") else side
    canonical = canonical_symbol(clean(row.get("canonicalSymbol") or broker_symbol, 80))
    normalized = {
        "sourceCandidateId": clean(row.get("sourceCandidateId") or row.get("candidateId") or row.get("id"), 120),
        "route": clean(row.get("route") or row.get("strategy"), 80),
        "canonicalSymbol": canonical,
        "symbol": broker_symbol,
        "brokerSymbol": broker_symbol,
        "side": side,
        "orderType": order_type,
        "lots": as_float(row.get("lots") or row.get("volume"), 0.0),
        "price": as_float(row.get("entryPrice") or row.get("price"), 0.0),
        "sl": as_float(row.get("stopLoss") or row.get("sl"), 0.0),
        "tp": as_float(row.get("takeProfit") or row.get("tp"), 0.0),
        "expirationTimeIso": clean(row.get("expirationTimeIso") or row.get("expiration"), 64),
        "reason": clean(row.get("reason") or row.get("note"), 240),
        "dryRun": as_bool(row.get("dryRun"), True),
        "comment": clean(row.get("comment") or f"QG_PEND_{clean(row.get('route') or row.get('strategy'), 12)}", 31),
    }
    normalized["intentId"] = clean(row.get("intentId"), 160) or build_intent_id(normalized)
    return normalized


def build_intent_id(intent: dict[str, Any]) -> str:
    key = "|".join(
        [
            clean(intent.get("sourceCandidateId"), 120),
            clean(intent.get("route"), 80),
            clean(intent.get("canonicalSymbol"), 80),
            clean(intent.get("brokerSymbol") or intent.get("symbol"), 80),
            clean(intent.get("side"), 20),
            clean(intent.get("orderType"), 40),
            str(intent.get("lots") or ""),
            str(intent.get("price") or ""),
            str(intent.get("sl") or ""),
            str(intent.get("tp") or ""),
            clean(intent.get("expirationTimeIso"), 64),
        ]
    )
    return "qg-mt5-intent-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def read_existing_intent_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                intent_id = clean(row.get("IntentId"), 160)
                state = clean(row.get("State"), 80)
                if intent_id and state:
                    states[intent_id] = state
    except Exception:
        return {}
    return states


def append_worker_ledger(runtime_dir: Path, row: dict[str, Any]) -> None:
    path = runtime_dir / LEDGER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in LEDGER_FIELDS})


def ledger_row(intent: dict[str, Any], *, state: str, decision: str, result: dict[str, Any], reason: str = "") -> dict[str, Any]:
    audit = result.get("audit") or {}
    response = result.get("response") or {}
    return {
        "LedgerId": str(uuid.uuid4()),
        "IntentId": intent.get("intentId", ""),
        "EventTimeIso": utc_now(),
        "State": state,
        "Decision": decision,
        "DryRun": str(bool(result.get("safety", {}).get("dryRun", intent.get("dryRun", True)))).lower(),
        "LiveAllowed": str(bool(result.get("safety", {}).get("orderSendAllowed"))).lower(),
        "Route": intent.get("route", ""),
        "CanonicalSymbol": intent.get("canonicalSymbol", ""),
        "BrokerSymbol": intent.get("brokerSymbol") or intent.get("symbol") or "",
        "OrderType": intent.get("orderType", ""),
        "Side": intent.get("side", ""),
        "Lots": intent.get("lots", ""),
        "EntryPrice": intent.get("price", ""),
        "StopLoss": intent.get("sl", ""),
        "TakeProfit": intent.get("tp", ""),
        "ExpirationTimeIso": intent.get("expirationTimeIso", ""),
        "SourceCandidateId": intent.get("sourceCandidateId", ""),
        "Reason": reason or result.get("reason", ""),
        "TradingLedgerId": audit.get("postLedgerId") or audit.get("ledgerId") or "",
        "BrokerOrderTicket": response.get("order", ""),
        "RiskSnapshotJson": json.dumps(
            {
                "safety": result.get("safety", {}),
                "authLock": result.get("authLock", {}),
                "decision": result.get("decision", ""),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "WorkerVersion": WORKER_VERSION,
    }


def validate_pending_intent(intent: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not intent.get("route"):
        reasons.append("route_required")
    if not intent.get("brokerSymbol"):
        reasons.append("broker_symbol_required")
    if intent.get("side") not in {"buy", "sell"}:
        reasons.append("side_required")
    if intent.get("orderType") not in {"buy_limit", "sell_limit", "buy_stop", "sell_stop", "buy_stop_limit", "sell_stop_limit"}:
        reasons.append("pending_order_type_required")
    if as_float(intent.get("lots"), 0.0) <= 0:
        reasons.append("lots_required")
    if as_float(intent.get("price"), 0.0) <= 0:
        reasons.append("entry_price_required")
    return reasons


def run_worker(
    runtime_dir: Path,
    *,
    config_path: Path | None = None,
    intents_path: Path | None = None,
    max_intents: int = 20,
    force_dry_run: bool = False,
) -> dict[str, Any]:
    config = mt5_trading_client.load_config(runtime_dir, config_path)
    source_path = intents_path or (runtime_dir / INTENTS_NAME)
    raw_intents = load_intents(source_path)
    existing = read_existing_intent_states(runtime_dir / LEDGER_NAME)
    rows: list[dict[str, Any]] = []
    accepted = 0
    rejected = 0
    skipped = 0

    for raw in raw_intents[: max(0, max_intents)]:
        intent = normalize_intent(raw)
        if force_dry_run:
            intent["dryRun"] = True

        if existing.get(intent["intentId"]) in {"ORDER_SEND_ACCEPTED", "DRY_RUN_ACCEPTED", "AUTHORIZED", "BROKER_ORDER_OPEN"}:
            skipped += 1
            result = {
                "decision": "DUPLICATE_SKIPPED",
                "reason": "intent_already_processed",
                "safety": mt5_trading_client.public_safety(config, dry_run=True),
            }
            row = ledger_row(intent, state="DUPLICATE_SKIPPED", decision="DUPLICATE_SKIPPED", result=result, reason="intent_already_processed")
            append_worker_ledger(runtime_dir, row)
            rows.append(row)
            continue

        validation_reasons = validate_pending_intent(intent)
        if validation_reasons:
            rejected += 1
            result = {
                "decision": "DRY_RUN_REJECTED",
                "reason": ",".join(validation_reasons),
                "safety": mt5_trading_client.public_safety(config, dry_run=True),
            }
            row = ledger_row(intent, state="DRY_RUN_REJECTED", decision="DRY_RUN_REJECTED", result=result, reason=result["reason"])
            append_worker_ledger(runtime_dir, row)
            rows.append(row)
            continue

        request = {
            **intent,
            "endpoint": "order",
            "action": "order",
            "dryRun": as_bool(intent.get("dryRun"), as_bool(config.get("dryRun"), True)),
        }
        result = mt5_trading_client.execute_endpoint(
            "order",
            request,
            runtime_dir=runtime_dir,
            config_path=config_path,
        )
        decision = clean(result.get("decision"), 80)
        if decision in {"ORDER_SEND_ACCEPTED", "DRY_RUN_ACCEPTED"}:
            accepted += 1
            state = decision
        else:
            rejected += 1
            state = "KILL_SWITCH_BLOCKED" if "kill_switch_on" in str(result.get("reason", "")) else decision or "REJECTED"
        row = ledger_row(intent, state=state, decision=decision or "REJECTED", result=result)
        append_worker_ledger(runtime_dir, row)
        rows.append(row)

    payload = {
        "ok": True,
        "mode": MODE,
        "generatedAtIso": utc_now(),
        "source": str(source_path),
        "safety": {
            "readOnly": False,
            "pendingOrderWorker": True,
            "dryRun": force_dry_run or as_bool(config.get("dryRun"), True),
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "usesTradingBridgeGuards": True,
            "auditLedgerRequired": True,
            "livePresetMutationAllowed": False,
            "mutatesMt5": False,
        },
        "summary": {
            "intentCount": len(raw_intents),
            "processed": len(rows),
            "accepted": accepted,
            "rejected": rejected,
            "skipped": skipped,
            "ledger": str(runtime_dir / LEDGER_NAME),
        },
        "rows": rows[-50:],
    }
    write_json(runtime_dir / OUTPUT_NAME, payload)
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantGod guarded MT5 pending-order worker")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--config", default="")
    parser.add_argument("--intents", default="")
    parser.add_argument("--max-intents", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = run_worker(
        Path(args.runtime_dir),
        config_path=Path(args.config) if args.config else None,
        intents_path=Path(args.intents) if args.intents else None,
        max_intents=args.max_intents,
        force_dry_run=args.dry_run,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
