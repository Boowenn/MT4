"""SQLite schema and query layer for QuantGod P2-3 state persistence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence

from .config import StateStoreConfig
from .safety import assert_state_store_safety, safety_payload

SCHEMA_VERSION = 1

TABLES = (
    "schema_migrations",
    "qg_events",
    "ai_analysis_runs",
    "vibe_strategies",
    "vibe_backtest_runs",
    "notification_events",
    "api_contract_versions",
    "frontend_dist_releases",
    "state_ingest_runs",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def loads_json(value: str | bytes | None) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class StateStore:
    """Small standard-library SQLite wrapper for local evidence state."""

    def __init__(self, config: StateStoreConfig):
        self.config = config

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.config.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> Dict[str, Any]:
        assert_state_store_safety()
        with self.connect() as conn:
            create_schema(conn)
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self.connect() as conn:
            create_schema(conn)
            counts = {table: count_rows(conn, table) for table in TABLES}
            migrations = [dict(row) for row in conn.execute("SELECT * FROM schema_migrations ORDER BY migration_id")]
        return {
            "ok": True,
            "schemaVersion": SCHEMA_VERSION,
            "dbPath": str(self.config.db_path),
            "exists": self.config.db_path.exists(),
            "tables": counts,
            "migrations": migrations,
            "safety": safety_payload(),
        }

    def upsert_event(self, event: Mapping[str, Any]) -> None:
        payload = dict(event.get("payload") or {})
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO qg_events (
                    event_id, event_type, source, source_path, entity_id, symbol,
                    route, severity, occurred_at, inserted_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_type=excluded.event_type,
                    source=excluded.source,
                    source_path=excluded.source_path,
                    entity_id=excluded.entity_id,
                    symbol=excluded.symbol,
                    route=excluded.route,
                    severity=excluded.severity,
                    occurred_at=excluded.occurred_at,
                    inserted_at=excluded.inserted_at,
                    payload_json=excluded.payload_json
                """,
                (
                    event["event_id"],
                    event.get("event_type") or "STATE_EVENT",
                    event.get("source") or "unknown",
                    event.get("source_path") or "",
                    event.get("entity_id") or event["event_id"],
                    event.get("symbol") or "",
                    event.get("route") or "",
                    event.get("severity") or "info",
                    event.get("occurred_at") or utc_now_iso(),
                    utc_now_iso(),
                    dumps_json(payload),
                ),
            )

    def upsert_ai_analysis_run(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO ai_analysis_runs (
                    run_id, status, symbol, route, provider, model, advisory_only,
                    generated_at, source_path, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    symbol=excluded.symbol,
                    route=excluded.route,
                    provider=excluded.provider,
                    model=excluded.model,
                    advisory_only=excluded.advisory_only,
                    generated_at=excluded.generated_at,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["run_id"],
                    item.get("status") or "unknown",
                    item.get("symbol") or "",
                    item.get("route") or "",
                    item.get("provider") or "",
                    item.get("model") or "",
                    1 if item.get("advisory_only", True) else 0,
                    item.get("generated_at") or utc_now_iso(),
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def upsert_vibe_strategy(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO vibe_strategies (
                    strategy_id, name, version, status, research_only,
                    generated_at, source_path, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    status=excluded.status,
                    research_only=excluded.research_only,
                    generated_at=excluded.generated_at,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["strategy_id"],
                    item.get("name") or item["strategy_id"],
                    item.get("version") or "",
                    item.get("status") or "unknown",
                    1 if item.get("research_only", True) else 0,
                    item.get("generated_at") or utc_now_iso(),
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def upsert_vibe_backtest_run(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO vibe_backtest_runs (
                    run_id, strategy_id, status, generated_at,
                    source_path, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    strategy_id=excluded.strategy_id,
                    status=excluded.status,
                    generated_at=excluded.generated_at,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["run_id"],
                    item.get("strategy_id") or "",
                    item.get("status") or "unknown",
                    item.get("generated_at") or utc_now_iso(),
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def upsert_notification_event(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO notification_events (
                    event_id, event_type, channel, status, push_only,
                    generated_at, source_path, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_type=excluded.event_type,
                    channel=excluded.channel,
                    status=excluded.status,
                    push_only=excluded.push_only,
                    generated_at=excluded.generated_at,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["event_id"],
                    item.get("event_type") or "UNKNOWN",
                    item.get("channel") or "telegram",
                    item.get("status") or "unknown",
                    1 if item.get("push_only", True) else 0,
                    item.get("generated_at") or utc_now_iso(),
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def upsert_api_contract_version(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO api_contract_versions (
                    contract_id, schema_version, project, reviewed_at,
                    endpoint_count, source_path, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    project=excluded.project,
                    reviewed_at=excluded.reviewed_at,
                    endpoint_count=excluded.endpoint_count,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["contract_id"],
                    item.get("schema_version") or "",
                    item.get("project") or "QuantGod",
                    item.get("reviewed_at") or "",
                    int(item.get("endpoint_count") or 0),
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def upsert_frontend_dist_release(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO frontend_dist_releases (
                    release_id, frontend_commit, build_time, source_path,
                    payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    frontend_commit=excluded.frontend_commit,
                    build_time=excluded.build_time,
                    source_path=excluded.source_path,
                    payload_json=excluded.payload_json,
                    inserted_at=excluded.inserted_at
                """,
                (
                    item["release_id"],
                    item.get("frontend_commit") or "",
                    item.get("build_time") or "",
                    item.get("source_path") or "",
                    dumps_json(item.get("payload") or {}),
                    utc_now_iso(),
                ),
            )

    def insert_ingest_run(self, item: Mapping[str, Any]) -> None:
        with self.connect() as conn:
            create_schema(conn)
            conn.execute(
                """
                INSERT INTO state_ingest_runs (
                    run_id, started_at, finished_at, status, sources,
                    counts_json, error, safety_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    finished_at=excluded.finished_at,
                    status=excluded.status,
                    counts_json=excluded.counts_json,
                    error=excluded.error,
                    safety_json=excluded.safety_json
                """,
                (
                    item["run_id"],
                    item.get("started_at") or utc_now_iso(),
                    item.get("finished_at") or utc_now_iso(),
                    item.get("status") or "ok",
                    ",".join(item.get("sources") or []),
                    dumps_json(item.get("counts") or {}),
                    item.get("error") or "",
                    dumps_json(safety_payload()),
                ),
            )

    def query_events(self, *, limit: int = 50, event_type: str = "", source: str = "") -> List[Dict[str, Any]]:
        where: list[str] = []
        args: list[Any] = []
        if event_type:
            where.append("event_type = ?")
            args.append(event_type)
        if source:
            where.append("source = ?")
            args.append(source)
        sql = "SELECT * FROM qg_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY occurred_at DESC, inserted_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return self._query(sql, args)

    def query_ai_runs(self, *, limit: int = 50, symbol: str = "") -> List[Dict[str, Any]]:
        where: list[str] = []
        args: list[Any] = []
        if symbol:
            where.append("LOWER(symbol) = LOWER(?)")
            args.append(symbol)
        sql = "SELECT * FROM ai_analysis_runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY generated_at DESC, inserted_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return self._query(sql, args)

    def query_vibe_strategies(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        return self._query(
            "SELECT * FROM vibe_strategies ORDER BY generated_at DESC, inserted_at DESC LIMIT ?",
            [max(1, min(int(limit), 500))],
        )

    def query_notifications(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        return self._query(
            "SELECT * FROM notification_events ORDER BY generated_at DESC, inserted_at DESC LIMIT ?",
            [max(1, min(int(limit), 500))],
        )

    def _query(self, sql: str, args: Sequence[Any]) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            create_schema(conn)
            rows = [row_to_dict(row) for row in conn.execute(sql, args)]
        return rows


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    for key in list(data.keys()):
        if key.endswith("_json"):
            data[key[:-5]] = loads_json(data.pop(key))
    for bool_key in ("advisory_only", "research_only", "push_only"):
        if bool_key in data:
            data[bool_key] = bool(data[bool_key])
    return data


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qg_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            symbol TEXT NOT NULL DEFAULT '',
            route TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'info',
            occurred_at TEXT NOT NULL,
            inserted_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_qg_events_type_time ON qg_events(event_type, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_qg_events_source_time ON qg_events(source, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_qg_events_symbol_time ON qg_events(symbol, occurred_at DESC);

        CREATE TABLE IF NOT EXISTS ai_analysis_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'unknown',
            symbol TEXT NOT NULL DEFAULT '',
            route TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            advisory_only INTEGER NOT NULL DEFAULT 1,
            generated_at TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_runs_symbol_time ON ai_analysis_runs(symbol, generated_at DESC);

        CREATE TABLE IF NOT EXISTS vibe_strategies (
            strategy_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            research_only INTEGER NOT NULL DEFAULT 1,
            generated_at TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vibe_strategies_time ON vibe_strategies(generated_at DESC);

        CREATE TABLE IF NOT EXISTS vibe_backtest_runs (
            run_id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            generated_at TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vibe_backtest_time ON vibe_backtest_runs(generated_at DESC);

        CREATE TABLE IF NOT EXISTS notification_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT 'UNKNOWN',
            channel TEXT NOT NULL DEFAULT 'telegram',
            status TEXT NOT NULL DEFAULT 'unknown',
            push_only INTEGER NOT NULL DEFAULT 1,
            generated_at TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_time ON notification_events(generated_at DESC);

        CREATE TABLE IF NOT EXISTS api_contract_versions (
            contract_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL DEFAULT '',
            project TEXT NOT NULL DEFAULT 'QuantGod',
            reviewed_at TEXT NOT NULL DEFAULT '',
            endpoint_count INTEGER NOT NULL DEFAULT 0,
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS frontend_dist_releases (
            release_id TEXT PRIMARY KEY,
            frontend_commit TEXT NOT NULL DEFAULT '',
            build_time TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            inserted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS state_ingest_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            status TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '',
            counts_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            safety_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_state_ingest_time ON state_ingest_runs(started_at DESC);
        """
    )
    migration_id = f"p2_3_schema_v{SCHEMA_VERSION}"
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
        (migration_id, utc_now_iso()),
    )
