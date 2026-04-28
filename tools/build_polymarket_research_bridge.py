#!/usr/bin/env python3
"""Build a read-only Polymarket research snapshot for the QuantGod dashboard.

This bridge intentionally reads the Polymarket SQLite database directly in
query-only mode instead of importing the Polymarket app. That keeps .env,
wallets, order executors, schedulers, and live canary switches out of the
QuantGod process.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_POLYMARKET_ROOT = Path(r"D:\polymarket")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
OUTPUT_NAME = "QuantGod_PolymarketResearch.json"
LEDGER_NAME = "QuantGod_PolymarketResearchLedger.csv"


@dataclass(frozen=True)
class OutputTargets:
    runtime_dir: Path
    dashboard_dir: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polymarket-root", default=str(DEFAULT_POLYMARKET_ROOT))
    parser.add_argument("--db-path", default="", help="Defaults to <polymarket-root>/copybot.db")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--recent-limit", type=int, default=14)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 2)


def profit_factor(gross_win: float, gross_loss: float) -> float | None:
    loss_abs = abs(gross_loss)
    if loss_abs <= 0:
        return 999.0 if gross_win > 0 else None
    return round(gross_win / loss_abs, 4)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def readme_hint(polymarket_root: Path) -> dict[str, str]:
    readme = polymarket_root / "README.md"
    if not readme.exists():
        return {
            "source": "",
            "summary": "README not found; dashboard uses SQLite evidence only.",
        }
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "source": str(readme),
            "summary": "README unreadable; dashboard uses SQLite evidence only.",
        }
    hints = []
    for needle in [
        "Live entry surface",
        "live canary is disabled",
        "No-money shadow",
        "rolled back",
        "cannot create new entries",
    ]:
        idx = text.lower().find(needle.lower())
        if idx >= 0:
            line = text[idx : text.find("\n", idx) if "\n" in text[idx:] else idx + 180].strip()
            hints.append(line[:220])
    return {
        "source": str(readme),
        "summary": " | ".join(hints[:4]) if hints else "README present; no guardrail hints extracted.",
    }


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = "file:" + db_path.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def aggregate_journal(con: sqlite3.Connection, where_sql: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not table_exists(con, "trade_journal"):
        return []
    query = f"""
        SELECT
            COALESCE(sample_type, '') AS sampleType,
            COALESCE(NULLIF(experiment_key, ''), 'baseline') AS experimentKey,
            COALESCE(market_scope, '') AS marketScope,
            COALESCE(entry_status, '') AS entryStatus,
            COALESCE(signal_source, '') AS signalSource,
            COUNT(*) AS entries,
            SUM(CASE WHEN exit_timestamp IS NOT NULL OR realized_pnl IS NOT NULL THEN 1 ELSE 0 END) AS closed,
            SUM(CASE WHEN exit_timestamp IS NULL AND realized_pnl IS NULL THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) AS grossWin,
            SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END) AS grossLoss,
            SUM(COALESCE(realized_pnl, 0)) AS realizedPnl,
            AVG(CASE WHEN realized_pnl IS NOT NULL THEN realized_pnl END) AS avgPnl,
            MIN(entry_timestamp) AS firstEntryTs,
            MAX(entry_timestamp) AS lastEntryTs,
            MAX(exit_timestamp) AS lastExitTs
        FROM trade_journal
        {where_sql}
        GROUP BY sampleType, experimentKey, marketScope, entryStatus, signalSource
        ORDER BY entries DESC, realizedPnl DESC
    """
    rows = []
    for row in con.execute(query, params):
        closed = safe_int(row["closed"])
        wins = safe_int(row["wins"])
        gross_win = safe_number(row["grossWin"])
        gross_loss = safe_number(row["grossLoss"])
        rows.append(
            {
                "sampleType": row["sampleType"] or "unknown",
                "experimentKey": row["experimentKey"] or "baseline",
                "marketScope": row["marketScope"] or "unknown",
                "entryStatus": row["entryStatus"] or "unknown",
                "signalSource": row["signalSource"] or "unknown",
                "entries": safe_int(row["entries"]),
                "closed": closed,
                "open": safe_int(row["open"]),
                "wins": wins,
                "losses": safe_int(row["losses"]),
                "winRatePct": pct(wins, closed),
                "grossWin": round(gross_win, 4),
                "grossLoss": round(gross_loss, 4),
                "profitFactor": profit_factor(gross_win, gross_loss),
                "realizedPnl": round(safe_number(row["realizedPnl"]), 4),
                "avgPnl": round(safe_number(row["avgPnl"]), 4),
                "firstEntryIso": epoch_to_iso(row["firstEntryTs"]),
                "lastEntryIso": epoch_to_iso(row["lastEntryTs"]),
                "lastExitIso": epoch_to_iso(row["lastExitTs"]),
            }
        )
    return rows


def rollup(rows: list[dict[str, Any]], sample_type: str | None = None) -> dict[str, Any]:
    filtered = [r for r in rows if sample_type is None or r.get("sampleType") == sample_type]
    entries = sum(safe_int(r.get("entries")) for r in filtered)
    closed = sum(safe_int(r.get("closed")) for r in filtered)
    open_entries = sum(safe_int(r.get("open")) for r in filtered)
    wins = sum(safe_int(r.get("wins")) for r in filtered)
    losses = sum(safe_int(r.get("losses")) for r in filtered)
    gross_win = sum(safe_number(r.get("grossWin")) for r in filtered)
    gross_loss = sum(safe_number(r.get("grossLoss")) for r in filtered)
    pnl = sum(safe_number(r.get("realizedPnl")) for r in filtered)
    return {
        "entries": entries,
        "closed": closed,
        "open": open_entries,
        "wins": wins,
        "losses": losses,
        "winRatePct": pct(wins, closed),
        "grossWin": round(gross_win, 4),
        "grossLoss": round(gross_loss, 4),
        "profitFactor": profit_factor(gross_win, gross_loss),
        "realizedPnl": round(pnl, 4),
        "avgPnl": round(pnl / closed, 4) if closed else None,
    }


def aggregate_by_key(rows: list[dict[str, Any]], key: str, sample_type: str | None = None) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if sample_type is not None and row.get("sampleType") != sample_type:
            continue
        buckets.setdefault(str(row.get(key) or "unknown"), []).append(row)
    result = []
    for bucket_key, bucket_rows in buckets.items():
        item = rollup(bucket_rows)
        item[key] = bucket_key
        result.append(item)
    return sorted(result, key=lambda item: (safe_number(item.get("realizedPnl")), safe_int(item.get("entries"))), reverse=True)


def risk_summary(con: sqlite3.Connection, limit: int = 12) -> dict[str, Any]:
    if not table_exists(con, "risk_log"):
        return {"topEvents": [], "recentEvents": []}
    top = []
    for row in con.execute(
        """
        SELECT COALESCE(event, '') AS event, COUNT(*) AS entries, MAX(timestamp) AS latestTs
        FROM risk_log
        GROUP BY event
        ORDER BY entries DESC
        LIMIT ?
        """,
        (limit,),
    ):
        top.append(
            {
                "event": row["event"] or "unknown",
                "entries": safe_int(row["entries"]),
                "latestIso": epoch_to_iso(row["latestTs"]),
            }
        )
    recent = []
    for row in con.execute(
        """
        SELECT timestamp, COALESCE(event, '') AS event, COALESCE(action_taken, '') AS actionTaken,
               COALESCE(details, '') AS details
        FROM risk_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ):
        recent.append(
            {
                "timestampIso": epoch_to_iso(row["timestamp"]),
                "event": row["event"] or "unknown",
                "actionTaken": row["actionTaken"] or "",
                "details": str(row["details"] or "")[:280],
            }
        )
    return {"topEvents": top, "recentEvents": recent}


def latest_pnl(con: sqlite3.Connection) -> dict[str, Any]:
    if not table_exists(con, "pnl_log"):
        return {}
    row = con.execute("SELECT * FROM pnl_log ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {}
    return {
        "timestampIso": epoch_to_iso(row["timestamp"]),
        "realizedPnl": round(safe_number(row["realized_pnl"]), 4),
        "unrealizedPnl": round(safe_number(row["unrealized_pnl"]), 4),
        "totalTrades": safe_int(row["total_trades"]),
        "winCount": safe_int(row["win_count"]),
        "lossCount": safe_int(row["loss_count"]),
        "winRatePct": pct(safe_int(row["win_count"]), safe_int(row["win_count"]) + safe_int(row["loss_count"])),
    }


def recent_journal(con: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not table_exists(con, "trade_journal"):
        return []
    rows = []
    for row in con.execute(
        """
        SELECT id, sample_type, experiment_key, signal_source, market_scope, entry_status,
               entry_side, entry_timestamp, exit_timestamp, realized_pnl, market_slug, outcome
        FROM trade_journal
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ):
        rows.append(
            {
                "id": safe_int(row["id"]),
                "sampleType": row["sample_type"] or "",
                "experimentKey": row["experiment_key"] or "baseline",
                "signalSource": row["signal_source"] or "",
                "marketScope": row["market_scope"] or "",
                "entryStatus": row["entry_status"] or "",
                "entrySide": row["entry_side"] or "",
                "entryIso": epoch_to_iso(row["entry_timestamp"]),
                "exitIso": epoch_to_iso(row["exit_timestamp"]),
                "realizedPnl": round(safe_number(row["realized_pnl"]), 4),
                "marketSlug": row["market_slug"] or "",
                "outcome": row["outcome"] or "",
            }
        )
    return rows


def build_governance(snapshot: dict[str, Any]) -> dict[str, Any]:
    executed = snapshot["summary"]["executed"]
    shadow = snapshot["summary"]["shadow"]
    experiments = snapshot["experimentGroups"]
    pnl_latest = snapshot.get("latestPnl") or {}
    executed_pf = executed.get("profitFactor")
    executed_win = executed.get("winRatePct")
    executed_pnl = safe_number(executed.get("realizedPnl"))
    shadow_pnl = safe_number(shadow.get("realizedPnl"))
    blockers = []
    if executed.get("closed", 0) and executed_pnl < 0:
        blockers.append("executed_realized_pnl_negative")
    if executed_win is not None and executed_win < 45:
        blockers.append("executed_win_rate_low")
    if executed_pf is not None and executed_pf < 1:
        blockers.append("executed_profit_factor_below_1")
    if shadow.get("closed", 0) and shadow_pnl < 0:
        blockers.append("shadow_recovery_negative")
    if safe_number(pnl_latest.get("realizedPnl")) < 0:
        blockers.append("latest_wallet_pnl_negative")

    retune = []
    for item in experiments:
        if item.get("profitFactor") is not None and item["profitFactor"] < 1:
            retune.append(item.get("experimentKey"))
        elif safe_number(item.get("realizedPnl")) < 0 and safe_int(item.get("closed")) >= 10:
            retune.append(item.get("experimentKey"))

    return {
        "decision": "RESEARCH_ONLY_DO_NOT_ENABLE_LIVE",
        "severity": "high" if blockers else "watch",
        "resumePolymarketExecution": False,
        "mt5Boundary": "NO_SHARED_EXECUTION_NO_MT5_MUTATION",
        "liveCanary": "KEEP_DISABLED_UNLESS_SEPARATE_OPERATOR_APPROVAL",
        "blockers": blockers or ["insufficient_positive_evidence"],
        "retuneExperimentKeys": sorted(set(x for x in retune if x)),
        "promotableExperimentKeys": [],
        "nextActions": [
            "Keep Polymarket evidence in a dashboard-only research workspace.",
            "Retune negative shadow/copy-archive experiments before any canary discussion.",
            "Do not merge Polymarket executor, wallet, or live canary code into QuantGod.",
            "Use separated sports/esports and executed/shadow/experiment buckets when comparing recovery quality.",
        ],
    }


def unavailable_snapshot(polymarket_root: Path, db_path: Path, reason: str) -> dict[str, Any]:
    return {
        "generatedAtIso": utc_now_iso(),
        "mode": "POLYMARKET_READ_ONLY_RESEARCH_BRIDGE",
        "status": "UNAVAILABLE",
        "source": {
            "repoRoot": str(polymarket_root),
            "dbPath": str(db_path),
            "github": "https://github.com/Boowenn/Polymarket",
        },
        "safety": {
            "readOnly": True,
            "loadsEnv": False,
            "startsExecutor": False,
            "placesOrders": False,
            "mutatesMt5": False,
            "boundary": "dashboard evidence only; no MT5 EA/order/config path changes",
        },
        "error": reason,
        "summary": {
            "executed": rollup([]),
            "shadow": rollup([]),
            "all": rollup([]),
        },
        "experimentGroups": [],
        "marketScopes": [],
        "risk": {"topEvents": [], "recentEvents": []},
        "recentJournal": [],
        "latestPnl": {},
        "governance": {
            "decision": "RESEARCH_ONLY_SOURCE_UNAVAILABLE",
            "resumePolymarketExecution": False,
            "blockers": [reason],
            "nextActions": ["Restore/read Polymarket evidence before using it for governance."],
        },
    }


def build_snapshot(polymarket_root: Path, db_path: Path, days: float, recent_limit: int) -> dict[str, Any]:
    if not polymarket_root.exists():
        return unavailable_snapshot(polymarket_root, db_path, "polymarket_root_missing")
    if not db_path.exists():
        return unavailable_snapshot(polymarket_root, db_path, "copybot_db_missing")

    con = connect_read_only(db_path)
    try:
        cutoff = time.time() - (days * 86400.0)
        rows_all = aggregate_journal(con)
        rows_recent = aggregate_journal(con, "WHERE entry_timestamp >= ?", (cutoff,))
        snapshot = {
            "generatedAtIso": utc_now_iso(),
            "mode": "POLYMARKET_READ_ONLY_RESEARCH_BRIDGE",
            "status": "OK",
            "source": {
                "repoRoot": str(polymarket_root),
                "dbPath": str(db_path),
                "github": "https://github.com/Boowenn/Polymarket",
                "readmeHint": readme_hint(polymarket_root),
            },
            "safety": {
                "readOnly": True,
                "loadsEnv": False,
                "startsExecutor": False,
                "placesOrders": False,
                "mutatesMt5": False,
                "boundary": "dashboard evidence only; no MT5 EA/order/config path changes",
            },
            "window": {
                "days": days,
                "cutoffIso": epoch_to_iso(cutoff),
            },
            "summary": {
                "all": rollup(rows_all),
                "executed": rollup(rows_all, "executed"),
                "shadow": rollup(rows_all, "shadow"),
                "recentAll": rollup(rows_recent),
                "recentExecuted": rollup(rows_recent, "executed"),
                "recentShadow": rollup(rows_recent, "shadow"),
            },
            "journalGroups": rows_all,
            "recentJournalGroups": rows_recent,
            "experimentGroups": aggregate_by_key(rows_all, "experimentKey", "shadow"),
            "recentExperimentGroups": aggregate_by_key(rows_recent, "experimentKey", "shadow"),
            "marketScopes": aggregate_by_key(rows_all, "marketScope"),
            "entryStatuses": aggregate_by_key(rows_all, "entryStatus"),
            "signalSources": aggregate_by_key(rows_all, "signalSource"),
            "risk": risk_summary(con),
            "recentJournal": recent_journal(con, max(1, recent_limit)),
            "latestPnl": latest_pnl(con),
        }
        snapshot["governance"] = build_governance(snapshot)
        return snapshot
    finally:
        con.close()


def write_outputs(snapshot: dict[str, Any], targets: OutputTargets) -> None:
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    output_paths = [targets.runtime_dir / OUTPUT_NAME]
    if targets.dashboard_dir:
        output_paths.append(targets.dashboard_dir / OUTPUT_NAME)
    for path in output_paths:
        atomic_write_text(path, text)

    ledger_rows = []
    for item in snapshot.get("experimentGroups") or []:
        ledger_rows.append(
            {
                "generatedAtIso": snapshot.get("generatedAtIso", ""),
                "experimentKey": item.get("experimentKey", ""),
                "entries": item.get("entries", 0),
                "closed": item.get("closed", 0),
                "winRatePct": item.get("winRatePct", ""),
                "profitFactor": item.get("profitFactor", ""),
                "realizedPnl": item.get("realizedPnl", 0),
                "decision": snapshot.get("governance", {}).get("decision", ""),
            }
        )
    for path in [targets.runtime_dir / LEDGER_NAME] + ([targets.dashboard_dir / LEDGER_NAME] if targets.dashboard_dir else []):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            fieldnames = ["generatedAtIso", "experimentKey", "entries", "closed", "winRatePct", "profitFactor", "realizedPnl", "decision"]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(ledger_rows)


def main() -> int:
    args = parse_args()
    polymarket_root = Path(args.polymarket_root)
    db_path = Path(args.db_path) if args.db_path else polymarket_root / "copybot.db"
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    try:
        snapshot = build_snapshot(polymarket_root, db_path, args.days, args.recent_limit)
    except sqlite3.OperationalError as exc:
        snapshot = unavailable_snapshot(polymarket_root, db_path, f"sqlite_read_failed:{exc}")
    write_outputs(snapshot, OutputTargets(runtime_dir=runtime_dir, dashboard_dir=dashboard_dir))
    print(
        f"{OUTPUT_NAME}: {snapshot.get('status')} | "
        f"decision={snapshot.get('governance', {}).get('decision')} | "
        f"runtime={runtime_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
