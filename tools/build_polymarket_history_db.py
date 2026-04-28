#!/usr/bin/env python3
"""Build the local Polymarket historical analysis database for QuantGod.

The history DB is an evidence store. It consumes already-generated QuantGod
Polymarket research snapshots, radar rows, single-market analysis, dry-run
orders, and dry-run outcomes. It never imports the Polymarket runtime, reads
private keys, writes wallets, starts executors, or mutates MT5.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parents[1] / "archive" / "polymarket" / "history"
DB_NAME = "QuantGod_PolymarketHistory.sqlite"
OUTPUT_NAME = "QuantGod_PolymarketHistoryDb.json"
CSV_NAME = "QuantGod_PolymarketHistoryDb.csv"

RESEARCH_NAME = "QuantGod_PolymarketResearch.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
SINGLE_NAME = "QuantGod_PolymarketSingleMarketAnalysis.json"
DRY_RUN_NAME = "QuantGod_PolymarketDryRunOrders.json"
OUTCOME_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"

SCHEMA_VERSION = "POLYMARKET_HISTORY_DB_V1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--recent-limit", type=int, default=12)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def safe_number(value: Any, default: float | None = None) -> float | None:
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
        return int(value)
    except (TypeError, ValueError):
        return default


def as_bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:24]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def read_json_candidate(name: str, runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    candidates = [dashboard_dir / name, runtime_dir / name]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data, str(path)
    return {}, ""


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS qd_polymarket_runs (
            run_id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            db_path TEXT NOT NULL,
            source_files_json TEXT NOT NULL,
            radar_rows INTEGER NOT NULL DEFAULT 0,
            analysis_rows INTEGER NOT NULL DEFAULT 0,
            simulation_rows INTEGER NOT NULL DEFAULT 0,
            research_rows INTEGER NOT NULL DEFAULT 0,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_asset_opportunities (
            id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            snapshot_generated_at TEXT NOT NULL,
            rank INTEGER,
            market_id TEXT,
            event_id TEXT,
            question TEXT,
            event_title TEXT,
            slug TEXT,
            polymarket_url TEXT,
            category TEXT,
            probability REAL,
            volume REAL,
            volume_24h REAL,
            liquidity REAL,
            spread REAL,
            divergence REAL,
            abs_divergence REAL,
            rule_score REAL,
            ai_rule_score REAL,
            ai_scoring_mode TEXT,
            risk TEXT,
            risk_flags_json TEXT,
            recommended_action TEXT,
            suggested_shadow_track TEXT,
            end_date TEXT,
            accepting_orders INTEGER,
            source TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_market_analysis (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            query TEXT,
            query_source TEXT,
            market_id TEXT,
            question TEXT,
            event_title TEXT,
            polymarket_url TEXT,
            market_probability REAL,
            ai_probability REAL,
            divergence REAL,
            confidence REAL,
            recommendation TEXT,
            risk TEXT,
            suggested_shadow_track TEXT,
            ai_scoring_mode TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_execution_simulations (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            dry_run_order_id TEXT,
            tracking_key TEXT,
            market_id TEXT,
            question TEXT,
            track TEXT,
            side TEXT,
            decision TEXT,
            state TEXT,
            entry_price REAL,
            current_price REAL,
            take_profit_price REAL,
            stop_loss_price REAL,
            simulated_stake_usdc REAL,
            unrealized_pct REAL,
            mfe_pct REAL,
            mae_pct REAL,
            would_exit_reason TEXT,
            blockers_json TEXT,
            wallet_write INTEGER NOT NULL DEFAULT 0,
            order_send INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_research_snapshots (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            mode TEXT,
            executed_closed INTEGER,
            executed_win_rate REAL,
            executed_pf REAL,
            executed_pnl REAL,
            shadow_closed INTEGER,
            shadow_win_rate REAL,
            shadow_pf REAL,
            shadow_pnl REAL,
            account_cash REAL,
            bankroll REAL,
            auth_state TEXT,
            top_risk_events_json TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_poly_asset_market ON qd_polymarket_asset_opportunities(market_id, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_poly_asset_score ON qd_polymarket_asset_opportunities(ai_rule_score, risk);
        CREATE INDEX IF NOT EXISTS idx_poly_analysis_market ON qd_polymarket_market_analysis(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_sim_tracking ON qd_polymarket_execution_simulations(tracking_key, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_research_generated ON qd_polymarket_research_snapshots(generated_at);
        """
    )


def upsert_radar(con: sqlite3.Connection, radar: dict[str, Any], now_iso: str) -> int:
    rows = radar.get("radar") if isinstance(radar.get("radar"), list) else []
    snapshot_generated = str(radar.get("generatedAt") or now_iso)
    snapshot_id = stable_id("radar", snapshot_generated, len(rows))
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("marketId") or item.get("slug") or item.get("question") or "")
        track = str(item.get("suggestedShadowTrack") or "")
        row_id = stable_id("asset", market_id, track)
        con.execute(
            """
            INSERT INTO qd_polymarket_asset_opportunities (
                id, first_seen_at, last_seen_at, snapshot_id, snapshot_generated_at,
                rank, market_id, event_id, question, event_title, slug, polymarket_url,
                category, probability, volume, volume_24h, liquidity, spread,
                divergence, abs_divergence, rule_score, ai_rule_score, ai_scoring_mode,
                risk, risk_flags_json, recommended_action, suggested_shadow_track,
                end_date, accepting_orders, source, raw_json
            ) VALUES (
                :id, :first_seen_at, :last_seen_at, :snapshot_id, :snapshot_generated_at,
                :rank, :market_id, :event_id, :question, :event_title, :slug, :polymarket_url,
                :category, :probability, :volume, :volume_24h, :liquidity, :spread,
                :divergence, :abs_divergence, :rule_score, :ai_rule_score, :ai_scoring_mode,
                :risk, :risk_flags_json, :recommended_action, :suggested_shadow_track,
                :end_date, :accepting_orders, :source, :raw_json
            )
            ON CONFLICT(id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                snapshot_id=excluded.snapshot_id,
                snapshot_generated_at=excluded.snapshot_generated_at,
                rank=excluded.rank,
                probability=excluded.probability,
                volume=excluded.volume,
                volume_24h=excluded.volume_24h,
                liquidity=excluded.liquidity,
                spread=excluded.spread,
                divergence=excluded.divergence,
                abs_divergence=excluded.abs_divergence,
                rule_score=excluded.rule_score,
                ai_rule_score=excluded.ai_rule_score,
                risk=excluded.risk,
                risk_flags_json=excluded.risk_flags_json,
                recommended_action=excluded.recommended_action,
                accepting_orders=excluded.accepting_orders,
                raw_json=excluded.raw_json
            """,
            {
                "id": row_id,
                "first_seen_at": now_iso,
                "last_seen_at": now_iso,
                "snapshot_id": snapshot_id,
                "snapshot_generated_at": snapshot_generated,
                "rank": safe_int(item.get("rank"), 0),
                "market_id": str(item.get("marketId") or ""),
                "event_id": str(item.get("eventId") or ""),
                "question": str(item.get("question") or ""),
                "event_title": str(item.get("eventTitle") or ""),
                "slug": str(item.get("slug") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "category": str(item.get("category") or ""),
                "probability": safe_number(item.get("probability")),
                "volume": safe_number(item.get("volume")),
                "volume_24h": safe_number(item.get("volume24h")),
                "liquidity": safe_number(item.get("liquidity")),
                "spread": safe_number(item.get("spread")),
                "divergence": safe_number(item.get("divergence")),
                "abs_divergence": safe_number(item.get("absDivergence")),
                "rule_score": safe_number(item.get("ruleScore")),
                "ai_rule_score": safe_number(item.get("aiRuleScore")),
                "ai_scoring_mode": str(item.get("aiScoringMode") or ""),
                "risk": str(item.get("risk") or ""),
                "risk_flags_json": compact_json(item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else []),
                "recommended_action": str(item.get("recommendedAction") or ""),
                "suggested_shadow_track": track,
                "end_date": str(item.get("endDate") or ""),
                "accepting_orders": as_bool_int(item.get("acceptingOrders")),
                "source": str(item.get("source") or ""),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_single_analysis(con: sqlite3.Connection, single: dict[str, Any], now_iso: str) -> int:
    if not single:
        return 0
    generated = str(single.get("generatedAt") or now_iso)
    request = single.get("request") if isinstance(single.get("request"), dict) else {}
    market = single.get("market") if isinstance(single.get("market"), dict) else {}
    analysis = single.get("analysis") if isinstance(single.get("analysis"), dict) else {}
    market_id = str(market.get("marketId") or "")
    query = str(request.get("query") or market.get("question") or "")
    row_id = stable_id("analysis", generated, market_id, query)
    con.execute(
        """
        INSERT OR REPLACE INTO qd_polymarket_market_analysis (
            id, generated_at, query, query_source, market_id, question, event_title,
            polymarket_url, market_probability, ai_probability, divergence, confidence,
            recommendation, risk, suggested_shadow_track, ai_scoring_mode,
            wallet_write_allowed, order_send_allowed, raw_json
        ) VALUES (
            :id, :generated_at, :query, :query_source, :market_id, :question, :event_title,
            :polymarket_url, :market_probability, :ai_probability, :divergence, :confidence,
            :recommendation, :risk, :suggested_shadow_track, :ai_scoring_mode,
            :wallet_write_allowed, :order_send_allowed, :raw_json
        )
        """,
        {
            "id": row_id,
            "generated_at": generated,
            "query": query,
            "query_source": str(request.get("source") or ""),
            "market_id": market_id,
            "question": str(market.get("question") or single.get("summary", {}).get("market") or ""),
            "event_title": str(market.get("eventTitle") or ""),
            "polymarket_url": str(market.get("polymarketUrl") or ""),
            "market_probability": safe_number(analysis.get("marketProbabilityPct")),
            "ai_probability": safe_number(analysis.get("aiProbabilityPct")),
            "divergence": safe_number(analysis.get("divergencePct")),
            "confidence": safe_number(analysis.get("confidencePct")),
            "recommendation": str(analysis.get("recommendation") or single.get("summary", {}).get("recommendation") or ""),
            "risk": str(analysis.get("riskLevel") or single.get("summary", {}).get("risk") or ""),
            "suggested_shadow_track": str(analysis.get("suggestedShadowTrack") or single.get("summary", {}).get("suggestedShadowTrack") or ""),
            "ai_scoring_mode": str(analysis.get("aiScoringMode") or ""),
            "wallet_write_allowed": as_bool_int(single.get("safety", {}).get("walletWriteAllowed")),
            "order_send_allowed": as_bool_int(single.get("safety", {}).get("orderSendAllowed")),
            "raw_json": compact_json(single),
        },
    )
    return 1


def upsert_dry_runs(con: sqlite3.Connection, dry_run: dict[str, Any], now_iso: str) -> int:
    rows = dry_run.get("dryRunOrders") if isinstance(dry_run.get("dryRunOrders"), list) else []
    generated = str(dry_run.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        exit_plan = item.get("exitPlan") if isinstance(item.get("exitPlan"), dict) else {}
        row_id = stable_id("dry_run_order", generated, item.get("trackingKey"), item.get("dryRunOrderId"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_execution_simulations (
                id, generated_at, source_type, dry_run_order_id, tracking_key, market_id,
                question, track, side, decision, state, entry_price, current_price,
                take_profit_price, stop_loss_price, simulated_stake_usdc,
                unrealized_pct, mfe_pct, mae_pct, would_exit_reason, blockers_json,
                wallet_write, order_send, raw_json
            ) VALUES (
                :id, :generated_at, :source_type, :dry_run_order_id, :tracking_key, :market_id,
                :question, :track, :side, :decision, :state, :entry_price, :current_price,
                :take_profit_price, :stop_loss_price, :simulated_stake_usdc,
                :unrealized_pct, :mfe_pct, :mae_pct, :would_exit_reason, :blockers_json,
                :wallet_write, :order_send, :raw_json
            )
            """,
            {
                "id": row_id,
                "generated_at": generated,
                "source_type": "dry_run_order",
                "dry_run_order_id": str(item.get("dryRunOrderId") or ""),
                "tracking_key": str(item.get("trackingKey") or ""),
                "market_id": str(item.get("marketId") or ""),
                "question": str(item.get("question") or ""),
                "track": str(item.get("track") or ""),
                "side": str(item.get("side") or ""),
                "decision": str(item.get("decision") or ""),
                "state": str(item.get("gateDecision") or ""),
                "entry_price": safe_number(item.get("entryPrice")),
                "current_price": None,
                "take_profit_price": safe_number(exit_plan.get("takeProfitPrice")),
                "stop_loss_price": safe_number(exit_plan.get("stopLossPrice")),
                "simulated_stake_usdc": safe_number(item.get("simulatedStakeUSDC")),
                "unrealized_pct": None,
                "mfe_pct": None,
                "mae_pct": None,
                "would_exit_reason": "",
                "blockers_json": compact_json(item.get("blockers") if isinstance(item.get("blockers"), list) else []),
                "wallet_write": as_bool_int(item.get("walletWrite")),
                "order_send": as_bool_int(item.get("orderSend")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_outcomes(con: sqlite3.Connection, watcher: dict[str, Any], now_iso: str) -> int:
    rows = watcher.get("outcomes") if isinstance(watcher.get("outcomes"), list) else []
    generated = str(watcher.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        row_id = stable_id("dry_run_outcome", generated, item.get("trackingKey"), item.get("dryRunOrderId"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_execution_simulations (
                id, generated_at, source_type, dry_run_order_id, tracking_key, market_id,
                question, track, side, decision, state, entry_price, current_price,
                take_profit_price, stop_loss_price, simulated_stake_usdc,
                unrealized_pct, mfe_pct, mae_pct, would_exit_reason, blockers_json,
                wallet_write, order_send, raw_json
            ) VALUES (
                :id, :generated_at, :source_type, :dry_run_order_id, :tracking_key, :market_id,
                :question, :track, :side, :decision, :state, :entry_price, :current_price,
                :take_profit_price, :stop_loss_price, :simulated_stake_usdc,
                :unrealized_pct, :mfe_pct, :mae_pct, :would_exit_reason, :blockers_json,
                :wallet_write, :order_send, :raw_json
            )
            """,
            {
                "id": row_id,
                "generated_at": generated,
                "source_type": "dry_run_outcome",
                "dry_run_order_id": str(item.get("dryRunOrderId") or ""),
                "tracking_key": str(item.get("trackingKey") or ""),
                "market_id": str(item.get("marketId") or ""),
                "question": str(item.get("question") or ""),
                "track": str(item.get("track") or ""),
                "side": str(item.get("side") or ""),
                "decision": str(item.get("observationStatus") or ""),
                "state": str(item.get("state") or ""),
                "entry_price": safe_number(item.get("entryPrice")),
                "current_price": safe_number(item.get("currentPrice")),
                "take_profit_price": safe_number(item.get("takeProfitPrice")),
                "stop_loss_price": safe_number(item.get("stopLossPrice")),
                "simulated_stake_usdc": None,
                "unrealized_pct": safe_number(item.get("unrealizedPct")),
                "mfe_pct": safe_number(item.get("mfePct")),
                "mae_pct": safe_number(item.get("maePct")),
                "would_exit_reason": str(item.get("wouldExitReason") or ""),
                "blockers_json": compact_json(item.get("blockers") if isinstance(item.get("blockers"), list) else []),
                "wallet_write": as_bool_int(item.get("walletWrite")),
                "order_send": as_bool_int(item.get("orderSend")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_research(con: sqlite3.Connection, research: dict[str, Any], now_iso: str) -> int:
    if not research:
        return 0
    generated = str(research.get("generatedAtIso") or research.get("generatedAt") or now_iso)
    summary = research.get("summary") if isinstance(research.get("summary"), dict) else {}
    executed = summary.get("executed") if isinstance(summary.get("executed"), dict) else {}
    shadow = summary.get("shadow") if isinstance(summary.get("shadow"), dict) else {}
    account = research.get("accountSnapshot") if isinstance(research.get("accountSnapshot"), dict) else {}
    risk = research.get("risk") if isinstance(research.get("risk"), dict) else {}
    row_id = stable_id("research", generated)
    con.execute(
        """
        INSERT OR REPLACE INTO qd_polymarket_research_snapshots (
            id, generated_at, mode, executed_closed, executed_win_rate, executed_pf,
            executed_pnl, shadow_closed, shadow_win_rate, shadow_pf, shadow_pnl,
            account_cash, bankroll, auth_state, top_risk_events_json, raw_json
        ) VALUES (
            :id, :generated_at, :mode, :executed_closed, :executed_win_rate, :executed_pf,
            :executed_pnl, :shadow_closed, :shadow_win_rate, :shadow_pf, :shadow_pnl,
            :account_cash, :bankroll, :auth_state, :top_risk_events_json, :raw_json
        )
        """,
        {
            "id": row_id,
            "generated_at": generated,
            "mode": str(research.get("mode") or ""),
            "executed_closed": safe_int(executed.get("closed"), 0),
            "executed_win_rate": safe_number(executed.get("winRatePct")),
            "executed_pf": safe_number(executed.get("profitFactor")),
            "executed_pnl": safe_number(executed.get("realizedPnl")),
            "shadow_closed": safe_int(shadow.get("closed"), 0),
            "shadow_win_rate": safe_number(shadow.get("winRatePct")),
            "shadow_pf": safe_number(shadow.get("profitFactor")),
            "shadow_pnl": safe_number(shadow.get("realizedPnl")),
            "account_cash": safe_number(account.get("accountCash")),
            "bankroll": safe_number(account.get("bankroll")),
            "auth_state": str(account.get("authState") or ""),
            "top_risk_events_json": compact_json(risk.get("topEvents") if isinstance(risk.get("topEvents"), list) else []),
            "raw_json": compact_json(research),
        },
    )
    return 1


def table_summary(con: sqlite3.Connection, table: str, latest_col: str = "generated_at") -> dict[str, Any]:
    row = con.execute(f"SELECT COUNT(*) AS rows, MAX({latest_col}) AS latest_at FROM {table}").fetchone()
    return {"rows": int(row["rows"] or 0), "latestAt": row["latest_at"] or ""}


def fetch_rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def build_summary(con: sqlite3.Connection, db_path: Path, source_files: dict[str, str], now_iso: str, recent_limit: int) -> dict[str, Any]:
    tables = {
        "qd_polymarket_asset_opportunities": table_summary(con, "qd_polymarket_asset_opportunities", "last_seen_at"),
        "qd_polymarket_market_analysis": table_summary(con, "qd_polymarket_market_analysis"),
        "qd_polymarket_execution_simulations": table_summary(con, "qd_polymarket_execution_simulations"),
        "qd_polymarket_research_snapshots": table_summary(con, "qd_polymarket_research_snapshots"),
    }
    total_rows = sum(item["rows"] for item in tables.values())
    recent_opportunities = fetch_rows(
        con,
        """
        SELECT last_seen_at AS seenAt, rank, market_id AS marketId, question, category,
               probability, volume, liquidity, divergence, ai_rule_score AS aiRuleScore,
               risk, recommended_action AS recommendedAction,
               suggested_shadow_track AS suggestedShadowTrack
        FROM qd_polymarket_asset_opportunities
        ORDER BY last_seen_at DESC, ai_rule_score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_analyses = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, market_id AS marketId, question, query,
               market_probability AS marketProbability, ai_probability AS aiProbability,
               divergence, confidence, recommendation, risk,
               suggested_shadow_track AS suggestedShadowTrack, ai_scoring_mode AS aiScoringMode
        FROM qd_polymarket_market_analysis
        ORDER BY generated_at DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_simulations = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, source_type AS sourceType, tracking_key AS trackingKey,
               market_id AS marketId, question, track, side, decision, state,
               entry_price AS entryPrice, current_price AS currentPrice,
               take_profit_price AS takeProfitPrice, stop_loss_price AS stopLossPrice,
               unrealized_pct AS unrealizedPct, mfe_pct AS mfePct, mae_pct AS maePct,
               would_exit_reason AS wouldExitReason, wallet_write AS walletWrite, order_send AS orderSend
        FROM qd_polymarket_execution_simulations
        ORDER BY generated_at DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    latest_research = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, executed_closed AS executedClosed,
               executed_win_rate AS executedWinRate, executed_pf AS executedPf,
               executed_pnl AS executedPnl, shadow_closed AS shadowClosed,
               shadow_win_rate AS shadowWinRate, shadow_pf AS shadowPf,
               shadow_pnl AS shadowPnl, account_cash AS accountCash,
               bankroll, auth_state AS authState
        FROM qd_polymarket_research_snapshots
        ORDER BY generated_at DESC
        LIMIT 1
        """
    )
    return {
        "generatedAt": now_iso,
        "mode": "POLYMARKET_HISTORY_DB_V1",
        "schemaVersion": SCHEMA_VERSION,
        "decision": "LOCAL_HISTORY_DB_NO_WALLET_WRITE",
        "database": {
            "path": str(db_path),
            "tables": list(tables.keys()),
            "purpose": "Long-lived local Polymarket research memory for radar, analysis, dry-run, outcome, and bridge snapshots.",
        },
        "sourceFiles": source_files,
        "summary": {
            "totalRows": total_rows,
            "assetOpportunities": tables["qd_polymarket_asset_opportunities"]["rows"],
            "marketAnalyses": tables["qd_polymarket_market_analysis"]["rows"],
            "executionSimulations": tables["qd_polymarket_execution_simulations"]["rows"],
            "researchSnapshots": tables["qd_polymarket_research_snapshots"]["rows"],
            "latestAt": max((item["latestAt"] for item in tables.values() if item["latestAt"]), default=""),
        },
        "tables": tables,
        "recent": {
            "opportunities": recent_opportunities,
            "analyses": recent_analyses,
            "simulations": recent_simulations,
            "research": latest_research[0] if latest_research else {},
        },
        "safety": {
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "source": "Consumes QuantGod generated snapshots only.",
        },
        "nextActions": [
            "Use this DB as the source for future search/history API.",
            "Add real AI scoring only after historical rows are stable and queryable.",
            "Do not promote Polymarket betting from history rows alone; route through Execution Gate and dry-run outcome evidence.",
        ],
    }


def write_outputs(snapshot: dict[str, Any], csv_rows: list[dict[str, Any]], runtime_dir: Path, dashboard_dir: Path) -> list[str]:
    written: list[str] = []
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    for base in [runtime_dir, dashboard_dir]:
        if not base:
            continue
        json_path = base / OUTPUT_NAME
        csv_path = base / CSV_NAME
        atomic_write_text(json_path, json_text)
        written.append(str(json_path))
        if csv_rows:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(csv_rows[0].keys()), lineterminator="\n")
            writer.writeheader()
            writer.writerows(csv_rows)
            atomic_write_text(csv_path, output.getvalue())
            written.append(str(csv_path))
    return written


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    history_dir = Path(args.history_dir)
    db_path = Path(args.db_path) if args.db_path else history_dir / DB_NAME
    now_iso = utc_now_iso()

    research, research_path = read_json_candidate(RESEARCH_NAME, runtime_dir, dashboard_dir)
    radar, radar_path = read_json_candidate(RADAR_NAME, runtime_dir, dashboard_dir)
    single, single_path = read_json_candidate(SINGLE_NAME, runtime_dir, dashboard_dir)
    dry_run, dry_run_path = read_json_candidate(DRY_RUN_NAME, runtime_dir, dashboard_dir)
    outcome, outcome_path = read_json_candidate(OUTCOME_NAME, runtime_dir, dashboard_dir)
    source_files = {
        RESEARCH_NAME: research_path,
        RADAR_NAME: radar_path,
        SINGLE_NAME: single_path,
        DRY_RUN_NAME: dry_run_path,
        OUTCOME_NAME: outcome_path,
    }

    con = connect_db(db_path)
    try:
        init_schema(con)
        radar_rows = upsert_radar(con, radar, now_iso)
        analysis_rows = upsert_single_analysis(con, single, now_iso)
        dry_run_rows = upsert_dry_runs(con, dry_run, now_iso)
        outcome_rows = upsert_outcomes(con, outcome, now_iso)
        research_rows = upsert_research(con, research, now_iso)
        simulation_rows = dry_run_rows + outcome_rows
        run_id = "POLYHIST-" + utc_now().strftime("%Y%m%d-%H%M%S")
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_runs (
                run_id, generated_at, schema_version, db_path, source_files_json,
                radar_rows, analysis_rows, simulation_rows, research_rows,
                wallet_write_allowed, order_send_allowed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                run_id,
                now_iso,
                SCHEMA_VERSION,
                str(db_path),
                compact_json(source_files),
                radar_rows,
                analysis_rows,
                simulation_rows,
                research_rows,
            ),
        )
        con.commit()
        snapshot = build_summary(con, db_path, source_files, now_iso, max(1, args.recent_limit))
    finally:
        con.close()

    csv_rows = [
        {
            "generated_at": now_iso,
            "table": table,
            "rows": meta["rows"],
            "latest_at": meta["latestAt"],
            "database_path": str(db_path),
            "wallet_write_allowed": "false",
            "order_send_allowed": "false",
        }
        for table, meta in snapshot["tables"].items()
    ]
    written = write_outputs(snapshot, csv_rows, runtime_dir, dashboard_dir)
    print(
        f"{snapshot['mode']} | rows={snapshot['summary']['totalRows']} "
        f"| db={db_path} | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
