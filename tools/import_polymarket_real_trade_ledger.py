#!/usr/bin/env python3
"""Import row-level Polymarket real-money trade evidence into QuantGod.

This tool is deliberately read-only with respect to the Polymarket project. It
opens SQLite databases in query-only mode, reads CSV files when present, and
writes a local QuantGod dashboard ledger. It never imports wallet modules,
starts executors, places orders, or mutates MT5.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_POLYMARKET_ROOT = Path(r"D:\polymarket")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
JSON_NAME = "QuantGod_PolymarketRealTradeLedger.json"
CSV_NAME = "QuantGod_PolymarketRealTradeLedger.csv"

FIELDNAMES = [
    "generated_at",
    "source",
    "source_table",
    "trade_id",
    "market_id",
    "question",
    "outcome",
    "side",
    "status",
    "opened_at",
    "closed_at",
    "entry_price",
    "exit_price",
    "stake_usdc",
    "size",
    "realized_pnl_usdc",
    "fees_usdc",
    "return_pct",
    "exit_reason",
    "tx_hash",
    "order_id",
    "wallet_write_source",
    "notes",
]

REAL_SAMPLE_TYPES = {"executed", "live", "real", "real_money", "money", "wallet"}
DRY_MARKERS = {"shadow", "paper", "dry", "dry_run", "simulation", "simulated", "experiment", "blocked"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def number_text(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return safe_text(value)
    return f"{parsed:.6f}".rstrip("0").rstrip(".")


def epoch_to_iso(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None or parsed <= 0:
        return safe_text(value)
    if parsed > 10_000_000_000:
        parsed = parsed / 1000.0
    try:
        return datetime.fromtimestamp(parsed, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return safe_text(value)


def first_value(row: dict[str, Any], *keys: str) -> Any:
    lower_map = {str(key).lower(): key for key in row.keys()}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is None:
            continue
        value = row.get(actual)
        if value is not None and str(value).strip() != "":
            return value
    return ""


def looks_dry(row: dict[str, Any]) -> bool:
    joined = " ".join(
        safe_text(first_value(row, key))
        for key in [
            "sample_type",
            "experiment_key",
            "signal_source",
            "source_type",
            "mode",
            "decision",
            "status",
            "state",
        ]
    ).lower()
    return any(marker in joined for marker in DRY_MARKERS)


def looks_real(row: dict[str, Any], table_name: str) -> bool:
    sample = safe_text(first_value(row, "sample_type", "sampleType")).lower()
    if sample:
        return sample in REAL_SAMPLE_TYPES
    if looks_dry(row):
        return False
    wallet_write = safe_text(first_value(row, "wallet_write", "walletWrite", "wallet_write_allowed")).lower()
    order_sent = safe_text(first_value(row, "order_sent", "orderSent", "order_send", "orderSend")).lower()
    tx_hash = safe_text(first_value(row, "tx_hash", "txHash", "transaction_hash", "transactionHash"))
    order_id = safe_text(first_value(row, "order_id", "orderId", "clob_order_id", "clobOrderId"))
    status = safe_text(first_value(row, "status", "state", "entry_status", "order_status")).lower()
    if wallet_write in {"1", "true", "yes"} or order_sent in {"1", "true", "yes"}:
        return True
    if tx_hash:
        return True
    if order_id and any(token in status for token in ["fill", "filled", "executed", "closed", "settled"]):
        return True
    return table_name.lower() == "trade_journal" and status in {"executed", "closed", "settled"}


def normalize_trade(row: dict[str, Any], source: Path, table_name: str, generated_at: str) -> dict[str, str]:
    opened = first_value(row, "entry_timestamp", "created_at", "createdAt", "timestamp", "opened_at", "open_time", "time")
    closed = first_value(row, "exit_timestamp", "closed_at", "closedAt", "settled_at", "settledAt", "close_time")
    sample = safe_text(first_value(row, "sample_type", "sampleType"))
    notes = " / ".join(
        part
        for part in [
            f"sample={sample}" if sample else "",
            f"experiment={safe_text(first_value(row, 'experiment_key', 'experimentKey'))}" if first_value(row, "experiment_key", "experimentKey") else "",
            f"signal={safe_text(first_value(row, 'signal_source', 'signalSource'))}" if first_value(row, "signal_source", "signalSource") else "",
            f"scope={safe_text(first_value(row, 'market_scope', 'marketScope'))}" if first_value(row, "market_scope", "marketScope") else "",
        ]
        if part
    )
    return {
        "generated_at": generated_at,
        "source": str(source),
        "source_table": table_name,
        "trade_id": safe_text(first_value(row, "id", "trade_id", "tradeId", "deal_id", "dealId")),
        "market_id": safe_text(first_value(row, "market_id", "marketId", "market_slug", "slug", "condition_id", "conditionId")),
        "question": safe_text(first_value(row, "question", "market", "title", "event_title", "market_title", "market_slug", "slug")),
        "outcome": safe_text(first_value(row, "outcome", "token_name", "tokenName", "asset", "asset_name")),
        "side": safe_text(first_value(row, "entry_side", "side", "direction", "order_side", "outcome_side")),
        "status": safe_text(first_value(row, "status", "state", "entry_status", "order_status", "position_state")) or "executed",
        "opened_at": epoch_to_iso(opened),
        "closed_at": epoch_to_iso(closed),
        "entry_price": number_text(first_value(row, "entry_price", "price", "avg_price", "average_price", "limit_price")),
        "exit_price": number_text(first_value(row, "exit_price", "close_price", "settle_price", "settlement_price")),
        "stake_usdc": number_text(first_value(row, "stake_usdc", "stake", "amount", "notional", "cost", "size_usdc")),
        "size": number_text(first_value(row, "size", "shares", "quantity", "qty")),
        "realized_pnl_usdc": number_text(first_value(row, "realized_pnl", "realizedPnl", "pnl", "profit", "profit_usdc")),
        "fees_usdc": number_text(first_value(row, "fees", "fee", "fee_usdc", "fees_usdc")),
        "return_pct": number_text(first_value(row, "return_pct", "returnPct", "roi", "roi_pct")),
        "exit_reason": safe_text(first_value(row, "exit_reason", "exitReason", "reason", "close_reason", "would_exit_reason")),
        "tx_hash": safe_text(first_value(row, "tx_hash", "txHash", "transaction_hash", "transactionHash")),
        "order_id": safe_text(first_value(row, "order_id", "orderId", "clob_order_id", "clobOrderId")),
        "wallet_write_source": "executed_trade_journal" if sample.lower() == "executed" else table_name,
        "notes": notes,
    }


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = "file:" + db_path.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA busy_timeout=3000")
    return con


def sqlite_tables(con: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    ]


def table_columns(con: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in con.execute(f"PRAGMA table_info({quote_ident(table_name)})").fetchall()]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_sqlite_source(path: Path, generated_at: str, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    con = connect_read_only(path)
    try:
        tables = sqlite_tables(con)
        priority_tables = [t for t in tables if t.lower() == "trade_journal"]
        priority_tables += [t for t in tables if t.lower() in {"trades", "orders", "positions"} and t not in priority_tables]
        for table in priority_tables:
            columns = table_columns(con, table)
            order_col = "id" if "id" in {c.lower() for c in columns} else columns[0]
            query = f"SELECT * FROM {quote_ident(table)} ORDER BY {quote_ident(order_col)} DESC LIMIT ?"
            for raw_row in con.execute(query, (max(limit * 4, limit),)):
                row = dict(raw_row)
                if not looks_real(row, table):
                    continue
                rows.append(normalize_trade(row, path, table, generated_at))
                if len(rows) >= limit:
                    return rows
    finally:
        con.close()
    return rows


def read_csv_source(path: Path, generated_at: str, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not looks_real(row, path.stem):
                continue
            rows.append(normalize_trade(row, path, path.stem, generated_at))
            if len(rows) >= limit:
                break
    return rows


def source_candidates(root: Path, explicit_db: str = "") -> list[Path]:
    candidates: list[Path] = []
    if explicit_db:
        candidates.append(Path(explicit_db))
    if root.exists():
        for relative in [
            "copybot.db",
            "data/copybot.db",
            "runtime/copybot.db",
            "polymarket.db",
            "data.db",
            "trade_journal.csv",
            "trades.csv",
            "orders.csv",
        ]:
            candidates.append(root / relative)
        for pattern in ["*.db", "*.sqlite", "*.sqlite3", "*.csv"]:
            try:
                candidates.extend(root.rglob(pattern))
            except OSError:
                continue
    seen: set[str] = set()
    result = []
    for item in candidates:
        key = str(item.resolve()) if item.exists() else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def build_ledger(root: Path, db_path: str, limit: int) -> dict[str, Any]:
    generated_at = utc_now_iso()
    rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    candidates = source_candidates(root, db_path)
    existing = [item for item in candidates if item.exists() and item.is_file()]
    for source in existing:
        try:
            suffix = source.suffix.lower()
            if suffix in {".db", ".sqlite", ".sqlite3"}:
                rows.extend(read_sqlite_source(source, generated_at, max(1, limit - len(rows))))
            elif suffix == ".csv":
                rows.extend(read_csv_source(source, generated_at, max(1, limit - len(rows))))
        except Exception as exc:  # noqa: BLE001 - importer must report all source errors.
            errors.append({"source": str(source), "error": str(exc)})
        if len(rows) >= limit:
            break
    pnl_values = [safe_float(row.get("realized_pnl_usdc")) for row in rows]
    realized = sum(value for value in pnl_values if value is not None)
    closed = [row for row in rows if row.get("closed_at") or safe_float(row.get("realized_pnl_usdc")) is not None]
    wins = [row for row in closed if (safe_float(row.get("realized_pnl_usdc")) or 0) > 0]
    status = "OK" if rows else ("SOURCE_EMPTY" if root.exists() else "SOURCE_MISSING")
    return {
        "schemaVersion": "POLYMARKET_REAL_TRADE_LEDGER_V1",
        "generatedAt": generated_at,
        "status": status,
        "sourceRoot": str(root),
        "sourceFound": bool(existing),
        "sourceCandidates": [str(item) for item in existing[:20]],
        "rowsImported": len(rows),
        "summary": {
            "realTradeRows": len(rows),
            "closedRows": len(closed),
            "openRows": max(0, len(rows) - len(closed)),
            "wins": len(wins),
            "winRatePct": round((len(wins) / len(closed)) * 100, 2) if closed else None,
            "realizedPnlUSDC": round(realized, 6),
        },
        "safety": {
            "readOnly": True,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "mutatesMt5": False,
            "privateKeysRead": False,
            "boundary": "row-level real-money evidence only; no wallet/order executor and no MT5 mutation",
        },
        "errors": errors,
        "rows": rows[:limit],
        "note": "D:\\polymarket is currently empty or has no confirmed real trade source." if not rows else "",
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="")
    temp.replace(path)


def write_outputs(payload: dict[str, Any], dashboard_dir: Path) -> None:
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(dashboard_dir / JSON_NAME, json.dumps(payload, ensure_ascii=False, indent=2))
    csv_path = dashboard_dir / CSV_NAME
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(payload.get("rows") or [])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polymarket-root", default=str(DEFAULT_POLYMARKET_ROOT))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--limit", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_ledger(Path(args.polymarket_root), args.db_path, max(1, args.limit))
    write_outputs(payload, Path(args.dashboard_dir))
    print(
        json.dumps(
            {
                "ok": True,
                "status": payload["status"],
                "rowsImported": payload["rowsImported"],
                "sourceRoot": payload["sourceRoot"],
                "sourceFound": payload["sourceFound"],
                "errors": payload["errors"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
