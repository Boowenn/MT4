#!/usr/bin/env python3
"""Local MT5 platform store for QuantGod.

This is the product-layer bridge that the MT5 port was missing: a durable local
SQLite store for users/operators, role permissions, task runs, product features,
and synchronized MT5 audit events.  It remains a governance/control-plane store;
it never places trades.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DB_NAME = "QuantGod_MT5Platform.db"
OUTPUT_NAME = "QuantGod_MT5PlatformState.json"
TRADING_LEDGER_NAME = "QuantGod_MT5TradingAuditLedger.csv"
PENDING_LEDGER_NAME = "QuantGod_MT5PendingOrderLedger.csv"
MODE = "MT5_PLATFORM_STORE_V1"

SAFETY = {
    "readOnly": False,
    "controlPlaneOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "mutatesMt5": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS operators (
            operator_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at_iso TEXT NOT NULL,
            updated_at_iso TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS role_permissions (
            role TEXT NOT NULL,
            permission TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 0,
            updated_at_iso TEXT NOT NULL,
            PRIMARY KEY (role, permission)
        );
        CREATE TABLE IF NOT EXISTS product_features (
            feature_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            description TEXT NOT NULL,
            updated_at_iso TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_runs (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at_iso TEXT NOT NULL,
            finished_at_iso TEXT,
            summary_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            event_time_iso TEXT NOT NULL,
            decision TEXT NOT NULL,
            actor TEXT NOT NULL,
            route TEXT,
            canonical_symbol TEXT,
            broker_symbol TEXT,
            action TEXT,
            dry_run INTEGER NOT NULL DEFAULT 1,
            live_allowed INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL
        );
        """
    )
    now = utc_now()
    defaults = [
        ("admin", "mt5:view", 1),
        ("admin", "mt5:dry_run", 1),
        ("admin", "mt5:request_auth_lock", 1),
        ("admin", "mt5:live_trade", 0),
        ("operator", "mt5:view", 1),
        ("operator", "mt5:dry_run", 1),
        ("operator", "mt5:request_auth_lock", 0),
        ("operator", "mt5:live_trade", 0),
        ("viewer", "mt5:view", 1),
        ("viewer", "mt5:dry_run", 0),
        ("viewer", "mt5:request_auth_lock", 0),
        ("viewer", "mt5:live_trade", 0),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO role_permissions(role, permission, allowed, updated_at_iso)
        VALUES (?, ?, ?, ?)
        """,
        [(role, perm, allowed, now) for role, perm, allowed in defaults],
    )
    features = [
        ("mt5_readonly_bridge", "enabled", "status/account/positions/orders/symbols/quote"),
        ("mt5_symbol_registry", "enabled", "broker symbol to canonical symbol mapping"),
        ("mt5_trading_bridge", "locked", "guarded order/close/cancel/login path"),
        ("mt5_pending_order_worker", "dry_run", "guarded pending-order queue worker"),
        ("mt5_platform_store", "enabled", "local SQLite control-plane store"),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO product_features(feature_key, status, description, updated_at_iso)
        VALUES (?, ?, ?, ?)
        """,
        [(key, status, desc, now) for key, status, desc in features],
    )
    conn.commit()


def clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def bool_int(value: Any) -> int:
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "y", "on"} else 0


def sync_trading_ledger(conn: sqlite3.Connection, path: Path) -> int:
    rows = read_csv_rows(path)
    inserted = 0
    for row in rows:
        event_id = clean(row.get("LedgerId"), 120)
        if not event_id:
            continue
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO audit_events(
                event_id, source, event_time_iso, decision, actor, route,
                canonical_symbol, broker_symbol, action, dry_run, live_allowed, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                "mt5_trading_ledger",
                clean(row.get("EventTimeIso"), 80),
                clean(row.get("Decision"), 80),
                "dashboard_or_bridge",
                clean(row.get("Route"), 80),
                clean(row.get("CanonicalSymbol"), 80),
                clean(row.get("BrokerSymbol"), 80),
                clean(row.get("Action"), 80),
                bool_int(row.get("DryRun", "true")),
                bool_int(row.get("LiveAllowed", "false")),
                payload,
            ),
        )
        inserted += int(cur.rowcount > 0)
    conn.commit()
    return inserted


def sync_pending_ledger(conn: sqlite3.Connection, path: Path) -> int:
    rows = read_csv_rows(path)
    inserted = 0
    for row in rows:
        event_id = clean(row.get("LedgerId"), 120)
        if not event_id:
            continue
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO audit_events(
                event_id, source, event_time_iso, decision, actor, route,
                canonical_symbol, broker_symbol, action, dry_run, live_allowed, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                "mt5_pending_worker_ledger",
                clean(row.get("EventTimeIso"), 80),
                clean(row.get("Decision"), 80),
                "pending_worker",
                clean(row.get("Route"), 80),
                clean(row.get("CanonicalSymbol"), 80),
                clean(row.get("BrokerSymbol"), 80),
                "pending_order",
                bool_int(row.get("DryRun", "true")),
                bool_int(row.get("LiveAllowed", "false")),
                payload,
            ),
        )
        inserted += int(cur.rowcount > 0)
    conn.commit()
    return inserted


def upsert_operator(conn: sqlite3.Connection, operator_id: str, display_name: str, role: str, status: str) -> dict[str, Any]:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO operators(operator_id, display_name, role, status, created_at_iso, updated_at_iso)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(operator_id) DO UPDATE SET
            display_name=excluded.display_name,
            role=excluded.role,
            status=excluded.status,
            updated_at_iso=excluded.updated_at_iso
        """,
        (operator_id, display_name, role, status, now, now),
    )
    conn.commit()
    return {"operatorId": operator_id, "displayName": display_name, "role": role, "status": status}


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])


def fetch_rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def build_state(conn: sqlite3.Connection, runtime_dir: Path, db_path: Path, sync: bool) -> dict[str, Any]:
    inserted = {"trading": 0, "pending": 0}
    if sync:
        inserted["trading"] = sync_trading_ledger(conn, runtime_dir / TRADING_LEDGER_NAME)
        inserted["pending"] = sync_pending_ledger(conn, runtime_dir / PENDING_LEDGER_NAME)
    recent_events = fetch_rows(
        conn,
        """
        SELECT event_id AS eventId, source, event_time_iso AS eventTimeIso, decision,
               route, canonical_symbol AS canonicalSymbol, broker_symbol AS brokerSymbol,
               action, dry_run AS dryRun, live_allowed AS liveAllowed
        FROM audit_events
        ORDER BY event_time_iso DESC
        LIMIT 50
        """,
    )
    payload = {
        "ok": True,
        "mode": MODE,
        "generatedAtIso": utc_now(),
        "runtimeDir": str(runtime_dir),
        "databasePath": str(db_path),
        "safety": SAFETY,
        "sync": {"enabled": sync, "inserted": inserted},
        "summary": {
            "operators": table_count(conn, "operators"),
            "rolePermissions": table_count(conn, "role_permissions"),
            "productFeatures": table_count(conn, "product_features"),
            "taskRuns": table_count(conn, "task_runs"),
            "auditEvents": table_count(conn, "audit_events"),
            "liveAllowedEvents": int(conn.execute("SELECT COUNT(*) AS c FROM audit_events WHERE live_allowed=1").fetchone()["c"]),
        },
        "features": fetch_rows(conn, "SELECT feature_key AS featureKey, status, description, updated_at_iso AS updatedAtIso FROM product_features ORDER BY feature_key"),
        "operators": fetch_rows(conn, "SELECT operator_id AS operatorId, display_name AS displayName, role, status, updated_at_iso AS updatedAtIso FROM operators ORDER BY operator_id"),
        "recentAuditEvents": recent_events,
    }
    write_path = runtime_dir / OUTPUT_NAME
    write_path.parent.mkdir(parents=True, exist_ok=True)
    write_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run(runtime_dir: Path, *, db_path: Path | None = None, sync: bool = True, operator: dict[str, Any] | None = None) -> dict[str, Any]:
    database = db_path or (runtime_dir / DB_NAME)
    conn = connect(database)
    try:
        init_db(conn)
        if operator:
            upsert_operator(
                conn,
                clean(operator.get("operatorId") or operator.get("id") or "local-operator", 80),
                clean(operator.get("displayName") or operator.get("name") or "Local Operator", 120),
                clean(operator.get("role") or "operator", 40),
                clean(operator.get("status") or "active", 40),
            )
        return build_state(conn, runtime_dir, database, sync)
    finally:
        conn.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantGod MT5 local platform store")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--db", default="")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--operator-json", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    operator = json.loads(args.operator_json) if args.operator_json else None
    payload = run(
        Path(args.runtime_dir),
        db_path=Path(args.db) if args.db else None,
        sync=not args.no_sync,
        operator=operator,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
