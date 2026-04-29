#!/usr/bin/env python3
"""Read-only Polymarket history API helper for the local dashboard server.

This script intentionally does not load wallet credentials, mutate MT5 files,
or write to the Polymarket SQLite database. It is a small query facade that the
Node dashboard server can spawn without adding a native sqlite dependency.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


TABLES: Mapping[str, Dict[str, Any]] = {
    "opportunities": {
        "table": "qd_polymarket_asset_opportunities",
        "order": "last_seen_at",
        "summary": "assetOpportunities",
        "search": (
            "market_id",
            "question",
            "event_title",
            "slug",
            "category",
            "risk",
            "recommended_action",
            "suggested_shadow_track",
        ),
    },
    "analyses": {
        "table": "qd_polymarket_market_analysis",
        "order": "generated_at",
        "summary": "marketAnalyses",
        "search": (
            "market_id",
            "query",
            "question",
            "event_title",
            "recommendation",
            "risk",
            "suggested_shadow_track",
            "ai_scoring_mode",
        ),
    },
    "simulations": {
        "table": "qd_polymarket_execution_simulations",
        "order": "generated_at",
        "summary": "executionSimulations",
        "search": (
            "market_id",
            "question",
            "track",
            "side",
            "decision",
            "state",
            "would_exit_reason",
        ),
    },
    "runs": {
        "table": "qd_polymarket_runs",
        "order": "generated_at",
        "summary": "runs",
        "search": ("run_id", "schema_version", "db_path"),
    },
    "snapshots": {
        "table": "qd_polymarket_research_snapshots",
        "order": "generated_at",
        "summary": "researchSnapshots",
        "search": ("mode", "auth_state"),
    },
    "worker-runs": {
        "table": "qd_polymarket_radar_worker_runs",
        "order": "generated_at",
        "summary": "radarWorkerRuns",
        "search": (
            "run_id",
            "status",
            "decision",
            "top_market",
            "top_risk",
        ),
    },
    "worker-trends": {
        "table": "qd_polymarket_radar_trends",
        "order": "generated_at",
        "summary": "radarTrendRows",
        "search": (
            "run_id",
            "market_id",
            "question",
            "category",
            "risk",
            "suggested_shadow_track",
            "trend_direction",
        ),
    },
    "worker-queue": {
        "table": "qd_polymarket_radar_queue",
        "order": "generated_at",
        "summary": "radarQueueRows",
        "search": (
            "candidate_id",
            "run_id",
            "market_id",
            "question",
            "category",
            "risk",
            "suggested_shadow_track",
            "queue_state",
            "next_action",
        ),
    },
    "cross-linkage": {
        "table": "qd_polymarket_cross_market_linkage",
        "order": "generated_at",
        "summary": "crossMarketLinkages",
        "search": (
            "market_id",
            "event_id",
            "question",
            "event_title",
            "category",
            "primary_risk_tag",
            "risk_tags_json",
            "matched_keywords_json",
            "linked_mt5_symbols_json",
            "macro_risk_state",
            "suggested_shadow_track",
        ),
    },
    "canary-contracts": {
        "table": "qd_polymarket_canary_contracts",
        "order": "generated_at",
        "summary": "canaryContracts",
        "search": (
            "canary_contract_id",
            "market_id",
            "question",
            "track",
            "side",
            "canary_state",
            "decision",
            "ai_color",
            "cross_risk_tag",
            "macro_risk_state",
            "dry_run_state",
            "outcome_state",
            "would_exit_reason",
            "blockers_json",
        ),
    },
    "auto-governance": {
        "table": "qd_polymarket_auto_governance",
        "order": "generated_at",
        "summary": "autoGovernanceDecisions",
        "search": (
            "governance_id",
            "market_id",
            "question",
            "track",
            "current_state",
            "governance_state",
            "recommended_action",
            "risk_level",
            "ai_color",
            "canary_state",
            "dry_run_state",
            "outcome_state",
            "would_exit_reason",
            "cross_risk_tag",
            "macro_risk_state",
            "blockers_json",
            "source_types_json",
            "next_test",
        ),
    },
    "canary-executor-runs": {
        "table": "qd_polymarket_canary_executor_runs",
        "order": "generated_at",
        "summary": "canaryExecutorRuns",
        "search": (
            "run_id",
            "execution_mode",
            "decision",
            "preflight_blockers_json",
        ),
    },
    "canary-order-audit": {
        "table": "qd_polymarket_canary_order_audit",
        "order": "generated_at",
        "summary": "canaryOrderAuditRows",
        "search": (
            "run_id",
            "candidate_id",
            "governance_id",
            "market_id",
            "question",
            "track",
            "side",
            "decision",
            "blockers_json",
            "adapter_status",
        ),
    },
    "markets": {
        "table": "qd_polymarket_markets",
        "order": "last_seen_at",
        "summary": "marketCatalogRows",
        "search": (
            "market_id",
            "event_id",
            "question",
            "event_title",
            "slug",
            "polymarket_url",
            "category",
            "risk",
            "recommended_action",
            "suggested_shadow_track",
            "related_assets_json",
        ),
    },
    "related-assets": {
        "table": "qd_polymarket_related_asset_opportunities",
        "order": "last_seen_at",
        "summary": "relatedAssetOpportunities",
        "search": (
            "opportunity_id",
            "market_id",
            "question",
            "event_title",
            "polymarket_url",
            "category",
            "market_risk",
            "asset_symbol",
            "asset_market",
            "asset_family",
            "bias",
            "directional_hint",
            "suggested_action",
            "suggested_shadow_track",
            "rationale",
        ),
    },
}

RECENT_TABLES = (
    "opportunities",
    "analyses",
    "simulations",
    "worker-runs",
    "worker-trends",
    "worker-queue",
    "cross-linkage",
    "canary-contracts",
    "auto-governance",
    "canary-executor-runs",
    "canary-order-audit",
    "markets",
    "related-assets",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def compact_row(row: sqlite3.Row, table_key: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"historyType": table_key}
    for key in row.keys():
        if key == "raw_json":
            continue
        value = row[key]
        out[snake_to_camel(key)] = value
    if table_key == "opportunities":
        out.setdefault("seenAt", out.get("lastSeenAt") or out.get("snapshotGeneratedAt") or out.get("firstSeenAt"))
        out.setdefault("generatedAt", out.get("lastSeenAt") or out.get("firstSeenAt"))
    else:
        out.setdefault("generatedAt", out.get("generatedAt") or out.get("lastSeenAt") or out.get("firstSeenAt"))
    return out


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, parsed))


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri_path = db_path.resolve().as_posix()
    con = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def count_rows(con: sqlite3.Connection, table_name: str, where_sql: str = "", params: Sequence[Any] = ()) -> int:
    row = con.execute(f"SELECT COUNT(*) AS c FROM {table_name} {where_sql}", params).fetchone()
    return int(row["c"] if row else 0)


def build_search_clause(table_key: str, query: str) -> tuple[str, List[str]]:
    if not query:
        return "", []
    columns = TABLES[table_key]["search"]
    clause = " OR ".join(f"CAST({column} AS TEXT) LIKE ?" for column in columns)
    like = f"%{query}%"
    return f"WHERE ({clause})", [like for _ in columns]


def query_table(
    con: sqlite3.Connection,
    table_key: str,
    query: str,
    limit: int,
    offset: int = 0,
) -> Dict[str, Any]:
    meta = TABLES[table_key]
    table_name = meta["table"]
    order_column = meta["order"]
    where_sql, params = build_search_clause(table_key, query)
    total = count_rows(con, table_name)
    matched = count_rows(con, table_name, where_sql, params) if query else total
    rows = [
        compact_row(row, table_key)
        for row in con.execute(
            f"""
            SELECT *
            FROM {table_name}
            {where_sql}
            ORDER BY {order_column} DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    ]
    return {
        "table": table_key,
        "total": total,
        "matched": matched,
        "rows": rows,
    }


def recent_tables(con: sqlite3.Connection, limit: int) -> Dict[str, List[Dict[str, Any]]]:
    return {
        table_key: query_table(con, table_key, "", min(limit, 24), 0)["rows"]
        for table_key in RECENT_TABLES
    }


def latest_research_snapshot(con: sqlite3.Connection) -> Dict[str, Any]:
    meta = TABLES["snapshots"]
    rows = query_table(con, "snapshots", "", 1, 0)["rows"]
    return rows[0] if rows else {}


def summarize(con: sqlite3.Connection) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    total = 0
    for table_key, meta in TABLES.items():
        count = count_rows(con, meta["table"])
        summary[str(meta["summary"])] = count
        total += count
    summary["totalRows"] = total
    return summary


def query_all_search(con: sqlite3.Connection, query: str, limit: int) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    matched = 0
    for table_key in TABLES:
        result = query_table(con, table_key, query, limit, 0)
        matched += int(result["matched"])
        rows.extend(result["rows"])
    rows.sort(key=lambda row: str(row.get("generatedAt") or row.get("seenAt") or ""), reverse=True)
    return {
        "table": "all",
        "query": query,
        "count": matched,
        "rows": rows[:limit],
    }


def build_payload(repo_root: Path, table_key: str, query: str, limit: int, offset: int) -> Dict[str, Any]:
    db_path = repo_root / "archive" / "polymarket" / "history" / "QuantGod_PolymarketHistory.sqlite"
    base = {
        "mode": "POLYMARKET_HISTORY_API_V1",
        "generatedAt": utc_now(),
        "source": "sqlite_api",
        "schemaVersion": "POLYMARKET_HISTORY_DB_V7_REAL_CANARY_GOVERNANCE",
        "decision": "LOCAL_HISTORY_DB_READ_ONLY_NO_WALLET_WRITE",
        "api": {"table": table_key, "query": query, "limit": limit, "offset": offset},
        "database": {"path": str(db_path), "exists": db_path.exists(), "readOnly": True},
        "safety": {
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "mutatesMt5": False,
            "publicReadOnly": True,
        },
    }
    if not db_path.exists():
        return {
            **base,
            "status": "MISSING_DB",
            "summary": {"totalRows": 0},
            "recent": {},
            "search": {"table": table_key, "query": query, "count": 0, "rows": []},
        }

    with connect_read_only(db_path) as con:
        summary = summarize(con)
        recent = recent_tables(con, limit)
        recent["research"] = latest_research_snapshot(con)
        if table_key == "all":
            search = query_all_search(con, query, limit) if query else {"table": "all", "query": "", "count": 0, "rows": []}
        else:
            result = query_table(con, table_key, query, limit, offset)
            search = {
                "table": table_key,
                "query": query,
                "count": result["matched"],
                "rows": result["rows"],
            }
    return {
        **base,
        "status": "OK",
        "summary": summary,
        "recent": recent,
        "search": search,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query QuantGod Polymarket history SQLite read-only.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--table", default="all", choices=("all", *TABLES.keys()))
    parser.add_argument("--q", default="")
    parser.add_argument("--limit", default="50")
    parser.add_argument("--offset", default="0")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    query = str(args.q or "").strip()[:240]
    limit = clamp_int(args.limit, 50, 1, 200)
    offset = clamp_int(args.offset, 0, 0, 100000)
    payload = build_payload(repo_root, args.table, query, limit, offset)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
