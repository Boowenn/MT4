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
RADAR_WORKER_NAME = "QuantGod_PolymarketRadarWorkerV2.json"
RADAR_TREND_CACHE_NAME = "QuantGod_PolymarketRadarTrendCache.json"
RADAR_QUEUE_NAME = "QuantGod_PolymarketRadarCandidateQueue.json"
SINGLE_NAME = "QuantGod_PolymarketSingleMarketAnalysis.json"
DRY_RUN_NAME = "QuantGod_PolymarketDryRunOrders.json"
OUTCOME_NAME = "QuantGod_PolymarketDryRunOutcomeWatcher.json"
CROSS_LINKAGE_NAME = "QuantGod_PolymarketCrossMarketLinkage.json"
CANARY_CONTRACT_NAME = "QuantGod_PolymarketCanaryExecutorContract.json"
AUTO_GOVERNANCE_NAME = "QuantGod_PolymarketAutoGovernance.json"
CANARY_EXECUTOR_RUN_NAME = "QuantGod_PolymarketCanaryExecutorRun.json"
MARKET_CATALOG_NAME = "QuantGod_PolymarketMarketCatalog.json"
RELATED_ASSET_OPPORTUNITY_NAME = "QuantGod_PolymarketAssetOpportunities.json"

SCHEMA_VERSION = "POLYMARKET_HISTORY_DB_V7_REAL_CANARY_GOVERNANCE"


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


def ensure_columns(con: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, ddl in columns.items():
        if column in existing:
            continue
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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
            worker_rows INTEGER NOT NULL DEFAULT 0,
            trend_rows INTEGER NOT NULL DEFAULT 0,
            queue_rows INTEGER NOT NULL DEFAULT 0,
            cross_linkage_rows INTEGER NOT NULL DEFAULT 0,
            canary_contract_rows INTEGER NOT NULL DEFAULT 0,
            auto_governance_rows INTEGER NOT NULL DEFAULT 0,
            market_catalog_rows INTEGER NOT NULL DEFAULT 0,
            related_asset_opportunity_rows INTEGER NOT NULL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS qd_polymarket_radar_worker_runs (
            run_id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            status TEXT,
            decision TEXT,
            started_at TEXT,
            finished_at TEXT,
            cycles_requested INTEGER,
            cycles_completed INTEGER,
            interval_seconds REAL,
            unique_markets INTEGER,
            duplicate_markets INTEGER,
            candidate_queue_size INTEGER,
            new_markets INTEGER,
            recurring_markets INTEGER,
            score_improved INTEGER,
            score_deteriorated INTEGER,
            probability_moved_up INTEGER,
            probability_moved_down INTEGER,
            stale_tracked INTEGER,
            top_market TEXT,
            top_score REAL,
            top_risk TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            can_start_executor INTEGER NOT NULL DEFAULT 0,
            can_mutate_mt5 INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_radar_trends (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            market_key TEXT NOT NULL,
            market_id TEXT,
            event_id TEXT,
            question TEXT,
            polymarket_url TEXT,
            category TEXT,
            suggested_shadow_track TEXT,
            risk TEXT,
            risk_flags_json TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            seen_count INTEGER,
            stale_cycles INTEGER,
            last_probability REAL,
            previous_probability REAL,
            probability_delta REAL,
            last_ai_rule_score REAL,
            previous_ai_rule_score REAL,
            ai_rule_score_delta REAL,
            best_ai_rule_score REAL,
            last_volume_24h REAL,
            previous_volume_24h REAL,
            volume_24h_delta REAL,
            last_liquidity REAL,
            trend_direction TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_radar_queue (
            id TEXT PRIMARY KEY,
            candidate_id TEXT,
            run_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            queue_state TEXT,
            execution_mode TEXT,
            market_id TEXT,
            event_id TEXT,
            question TEXT,
            polymarket_url TEXT,
            category TEXT,
            probability REAL,
            divergence REAL,
            volume REAL,
            volume_24h REAL,
            liquidity REAL,
            risk TEXT,
            risk_flags_json TEXT,
            ai_rule_score REAL,
            rule_score REAL,
            priority_score REAL,
            suggested_shadow_track TEXT,
            trend_direction TEXT,
            seen_count INTEGER,
            probability_delta REAL,
            ai_rule_score_delta REAL,
            next_action TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_cross_market_linkage (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            market_id TEXT,
            event_id TEXT,
            question TEXT,
            event_title TEXT,
            polymarket_url TEXT,
            category TEXT,
            primary_risk_tag TEXT,
            risk_tags_json TEXT,
            matched_keywords_json TEXT,
            linked_mt5_symbols_json TEXT,
            macro_risk_state TEXT,
            confidence REAL,
            probability REAL,
            source_score REAL,
            source_risk TEXT,
            source_types_json TEXT,
            suggested_shadow_track TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            mt5_execution_allowed INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_canary_contracts (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            canary_contract_id TEXT,
            market_id TEXT,
            question TEXT,
            polymarket_url TEXT,
            track TEXT,
            side TEXT,
            canary_state TEXT,
            decision TEXT,
            canary_eligible_now INTEGER NOT NULL DEFAULT 0,
            reference_stake_usdc REAL,
            canary_stake_usdc REAL,
            max_single_bet_usdc REAL,
            max_daily_loss_usdc REAL,
            take_profit_pct REAL,
            stop_loss_pct REAL,
            trailing_profit_pct REAL,
            cancel_unfilled_minutes INTEGER,
            max_hold_hours REAL,
            exit_before_resolution_hours REAL,
            source_score REAL,
            ai_score REAL,
            ai_color TEXT,
            cross_risk_tag TEXT,
            macro_risk_state TEXT,
            dry_run_state TEXT,
            outcome_state TEXT,
            would_exit_reason TEXT,
            blockers_json TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            starts_executor INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_auto_governance (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            governance_id TEXT,
            market_id TEXT,
            question TEXT,
            polymarket_url TEXT,
            track TEXT,
            current_state TEXT,
            governance_state TEXT,
            recommended_action TEXT,
            risk_level TEXT,
            score REAL,
            ai_score REAL,
            source_score REAL,
            ai_color TEXT,
            canary_state TEXT,
            dry_run_state TEXT,
            outcome_state TEXT,
            would_exit_reason TEXT,
            cross_risk_tag TEXT,
            macro_risk_state TEXT,
            blockers_json TEXT,
            source_types_json TEXT,
            next_test TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            starts_executor INTEGER NOT NULL DEFAULT 0,
            mutates_mt5 INTEGER NOT NULL DEFAULT 0,
            can_promote_to_live_execution INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_canary_executor_runs (
            run_id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            execution_mode TEXT,
            decision TEXT,
            planned_orders INTEGER NOT NULL DEFAULT 0,
            orders_sent INTEGER NOT NULL DEFAULT 0,
            eligible_governance_rows INTEGER NOT NULL DEFAULT 0,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            preflight_blockers_json TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_canary_order_audit (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            candidate_id TEXT,
            governance_id TEXT,
            market_id TEXT,
            question TEXT,
            track TEXT,
            side TEXT,
            token_id_present INTEGER NOT NULL DEFAULT 0,
            limit_price REAL,
            stake_usdc REAL,
            size REAL,
            decision TEXT,
            order_sent INTEGER NOT NULL DEFAULT 0,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            blockers_json TEXT,
            adapter_status TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_markets (
            id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            catalog_generated_at TEXT NOT NULL,
            catalog_rank INTEGER,
            catalog_id TEXT,
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
            risk TEXT,
            risk_flags_json TEXT,
            recommended_action TEXT,
            suggested_shadow_track TEXT,
            related_asset_count INTEGER,
            related_assets_json TEXT,
            end_date TEXT,
            accepting_orders INTEGER,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qd_polymarket_related_asset_opportunities (
            id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            rank INTEGER,
            opportunity_id TEXT,
            market_id TEXT,
            event_id TEXT,
            question TEXT,
            event_title TEXT,
            polymarket_url TEXT,
            category TEXT,
            probability REAL,
            market_score REAL,
            market_risk TEXT,
            asset_symbol TEXT,
            asset_market TEXT,
            asset_family TEXT,
            bias TEXT,
            directional_hint TEXT,
            confidence REAL,
            suggested_action TEXT,
            suggested_shadow_track TEXT,
            matched_keywords_json TEXT,
            rationale TEXT,
            wallet_write_allowed INTEGER NOT NULL DEFAULT 0,
            order_send_allowed INTEGER NOT NULL DEFAULT 0,
            mt5_execution_allowed INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_poly_asset_market ON qd_polymarket_asset_opportunities(market_id, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_poly_asset_score ON qd_polymarket_asset_opportunities(ai_rule_score, risk);
        CREATE INDEX IF NOT EXISTS idx_poly_analysis_market ON qd_polymarket_market_analysis(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_sim_tracking ON qd_polymarket_execution_simulations(tracking_key, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_research_generated ON qd_polymarket_research_snapshots(generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_worker_generated ON qd_polymarket_radar_worker_runs(generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_trend_market ON qd_polymarket_radar_trends(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_trend_direction ON qd_polymarket_radar_trends(trend_direction, risk);
        CREATE INDEX IF NOT EXISTS idx_poly_queue_priority ON qd_polymarket_radar_queue(priority_score, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_queue_market ON qd_polymarket_radar_queue(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_cross_market ON qd_polymarket_cross_market_linkage(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_cross_tag ON qd_polymarket_cross_market_linkage(primary_risk_tag, macro_risk_state);
        CREATE INDEX IF NOT EXISTS idx_poly_canary_market ON qd_polymarket_canary_contracts(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_canary_state ON qd_polymarket_canary_contracts(canary_state, decision);
        CREATE INDEX IF NOT EXISTS idx_poly_auto_gov_market ON qd_polymarket_auto_governance(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_auto_gov_state ON qd_polymarket_auto_governance(governance_state, risk_level);
        CREATE INDEX IF NOT EXISTS idx_poly_executor_generated ON qd_polymarket_canary_executor_runs(generated_at, execution_mode);
        CREATE INDEX IF NOT EXISTS idx_poly_order_audit_market ON qd_polymarket_canary_order_audit(market_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_order_audit_decision ON qd_polymarket_canary_order_audit(decision, order_sent);
        CREATE INDEX IF NOT EXISTS idx_poly_markets_market ON qd_polymarket_markets(market_id, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_poly_markets_score ON qd_polymarket_markets(ai_rule_score, risk);
        CREATE INDEX IF NOT EXISTS idx_poly_related_asset_symbol ON qd_polymarket_related_asset_opportunities(asset_symbol, generated_at);
        CREATE INDEX IF NOT EXISTS idx_poly_related_asset_market ON qd_polymarket_related_asset_opportunities(market_id, generated_at);
        """
    )
    ensure_columns(
        con,
        "qd_polymarket_runs",
        {
            "worker_rows": "INTEGER NOT NULL DEFAULT 0",
            "trend_rows": "INTEGER NOT NULL DEFAULT 0",
            "queue_rows": "INTEGER NOT NULL DEFAULT 0",
            "cross_linkage_rows": "INTEGER NOT NULL DEFAULT 0",
            "canary_contract_rows": "INTEGER NOT NULL DEFAULT 0",
            "auto_governance_rows": "INTEGER NOT NULL DEFAULT 0",
            "canary_executor_run_rows": "INTEGER NOT NULL DEFAULT 0",
            "canary_order_audit_rows": "INTEGER NOT NULL DEFAULT 0",
            "market_catalog_rows": "INTEGER NOT NULL DEFAULT 0",
            "related_asset_opportunity_rows": "INTEGER NOT NULL DEFAULT 0",
        },
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


def upsert_radar_worker_run(con: sqlite3.Connection, worker_payload: dict[str, Any], now_iso: str) -> int:
    if not worker_payload:
        return 0
    generated = str(worker_payload.get("generatedAt") or now_iso)
    worker = worker_payload.get("worker") if isinstance(worker_payload.get("worker"), dict) else {}
    summary = worker_payload.get("summary") if isinstance(worker_payload.get("summary"), dict) else {}
    safety = worker_payload.get("safety") if isinstance(worker_payload.get("safety"), dict) else {}
    run_id = str(worker_payload.get("runId") or stable_id("radar_worker", generated))
    con.execute(
        """
        INSERT OR REPLACE INTO qd_polymarket_radar_worker_runs (
            run_id, generated_at, status, decision, started_at, finished_at,
            cycles_requested, cycles_completed, interval_seconds, unique_markets,
            duplicate_markets, candidate_queue_size, new_markets, recurring_markets,
            score_improved, score_deteriorated, probability_moved_up,
            probability_moved_down, stale_tracked, top_market, top_score, top_risk,
            wallet_write_allowed, order_send_allowed, can_start_executor,
            can_mutate_mt5, raw_json
        ) VALUES (
            :run_id, :generated_at, :status, :decision, :started_at, :finished_at,
            :cycles_requested, :cycles_completed, :interval_seconds, :unique_markets,
            :duplicate_markets, :candidate_queue_size, :new_markets, :recurring_markets,
            :score_improved, :score_deteriorated, :probability_moved_up,
            :probability_moved_down, :stale_tracked, :top_market, :top_score, :top_risk,
            :wallet_write_allowed, :order_send_allowed, :can_start_executor,
            :can_mutate_mt5, :raw_json
        )
        """,
        {
            "run_id": run_id,
            "generated_at": generated,
            "status": str(worker_payload.get("status") or ""),
            "decision": str(worker_payload.get("decision") or ""),
            "started_at": str(worker.get("startedAt") or ""),
            "finished_at": str(worker.get("finishedAt") or generated),
            "cycles_requested": safe_int(worker.get("cyclesRequested"), 0),
            "cycles_completed": safe_int(worker.get("cyclesCompleted"), 0),
            "interval_seconds": safe_number(worker.get("intervalSeconds")),
            "unique_markets": safe_int(summary.get("uniqueMarkets"), 0),
            "duplicate_markets": safe_int(summary.get("duplicateMarkets"), 0),
            "candidate_queue_size": safe_int(summary.get("candidateQueueSize"), 0),
            "new_markets": safe_int(summary.get("newMarkets"), 0),
            "recurring_markets": safe_int(summary.get("recurringMarkets"), 0),
            "score_improved": safe_int(summary.get("scoreImproved"), 0),
            "score_deteriorated": safe_int(summary.get("scoreDeteriorated"), 0),
            "probability_moved_up": safe_int(summary.get("probabilityMovedUp"), 0),
            "probability_moved_down": safe_int(summary.get("probabilityMovedDown"), 0),
            "stale_tracked": safe_int(summary.get("staleTracked"), 0),
            "top_market": str(summary.get("topMarket") or ""),
            "top_score": safe_number(summary.get("topScore")),
            "top_risk": str(summary.get("topRisk") or ""),
            "wallet_write_allowed": as_bool_int(safety.get("walletWriteAllowed")),
            "order_send_allowed": as_bool_int(safety.get("orderSendAllowed")),
            "can_start_executor": as_bool_int(safety.get("canStartExecutor")),
            "can_mutate_mt5": as_bool_int(safety.get("canMutateMt5")),
            "raw_json": compact_json(worker_payload),
        },
    )
    return 1


def upsert_radar_trends(
    con: sqlite3.Connection,
    trend_cache: dict[str, Any],
    worker_payload: dict[str, Any],
    now_iso: str,
) -> int:
    markets = trend_cache.get("markets") if isinstance(trend_cache.get("markets"), dict) else {}
    generated = str(trend_cache.get("updatedAt") or worker_payload.get("generatedAt") or now_iso)
    run_id = str(trend_cache.get("runId") or worker_payload.get("runId") or stable_id("radar_trends", generated))
    count = 0
    for key, item in markets.items():
        if not isinstance(item, dict):
            continue
        market_key = str(item.get("key") or key)
        row_id = stable_id("trend", run_id, market_key)
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_radar_trends (
                id, run_id, generated_at, market_key, market_id, event_id, question,
                polymarket_url, category, suggested_shadow_track, risk, risk_flags_json,
                first_seen_at, last_seen_at, seen_count, stale_cycles, last_probability,
                previous_probability, probability_delta, last_ai_rule_score,
                previous_ai_rule_score, ai_rule_score_delta, best_ai_rule_score,
                last_volume_24h, previous_volume_24h, volume_24h_delta, last_liquidity,
                trend_direction, raw_json
            ) VALUES (
                :id, :run_id, :generated_at, :market_key, :market_id, :event_id, :question,
                :polymarket_url, :category, :suggested_shadow_track, :risk, :risk_flags_json,
                :first_seen_at, :last_seen_at, :seen_count, :stale_cycles, :last_probability,
                :previous_probability, :probability_delta, :last_ai_rule_score,
                :previous_ai_rule_score, :ai_rule_score_delta, :best_ai_rule_score,
                :last_volume_24h, :previous_volume_24h, :volume_24h_delta, :last_liquidity,
                :trend_direction, :raw_json
            )
            """,
            {
                "id": row_id,
                "run_id": run_id,
                "generated_at": generated,
                "market_key": market_key,
                "market_id": str(item.get("marketId") or ""),
                "event_id": str(item.get("eventId") or ""),
                "question": str(item.get("question") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "category": str(item.get("category") or ""),
                "suggested_shadow_track": str(item.get("suggestedShadowTrack") or ""),
                "risk": str(item.get("risk") or ""),
                "risk_flags_json": compact_json(item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else []),
                "first_seen_at": str(item.get("firstSeenAt") or ""),
                "last_seen_at": str(item.get("lastSeenAt") or generated),
                "seen_count": safe_int(item.get("seenCount"), 0),
                "stale_cycles": safe_int(item.get("staleCycles"), 0),
                "last_probability": safe_number(item.get("lastProbability")),
                "previous_probability": safe_number(item.get("previousProbability")),
                "probability_delta": safe_number(item.get("probabilityDelta")),
                "last_ai_rule_score": safe_number(item.get("lastAiRuleScore")),
                "previous_ai_rule_score": safe_number(item.get("previousAiRuleScore")),
                "ai_rule_score_delta": safe_number(item.get("aiRuleScoreDelta")),
                "best_ai_rule_score": safe_number(item.get("bestAiRuleScore")),
                "last_volume_24h": safe_number(item.get("lastVolume24h")),
                "previous_volume_24h": safe_number(item.get("previousVolume24h")),
                "volume_24h_delta": safe_number(item.get("volume24hDelta")),
                "last_liquidity": safe_number(item.get("lastLiquidity")),
                "trend_direction": str(item.get("trendDirection") or ""),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_radar_queue(
    con: sqlite3.Connection,
    queue_payload: dict[str, Any],
    worker_payload: dict[str, Any],
    now_iso: str,
) -> int:
    rows = queue_payload.get("candidates") if isinstance(queue_payload.get("candidates"), list) else []
    generated = str(queue_payload.get("generatedAt") or worker_payload.get("generatedAt") or now_iso)
    run_id = str(queue_payload.get("runId") or worker_payload.get("runId") or stable_id("radar_queue", generated))
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidateId") or "")
        row_id = stable_id("queue", run_id, candidate_id or item.get("marketId") or item.get("question"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_radar_queue (
                id, candidate_id, run_id, generated_at, queue_state, execution_mode,
                market_id, event_id, question, polymarket_url, category, probability,
                divergence, volume, volume_24h, liquidity, risk, risk_flags_json,
                ai_rule_score, rule_score, priority_score, suggested_shadow_track,
                trend_direction, seen_count, probability_delta, ai_rule_score_delta,
                next_action, wallet_write_allowed, order_send_allowed, raw_json
            ) VALUES (
                :id, :candidate_id, :run_id, :generated_at, :queue_state, :execution_mode,
                :market_id, :event_id, :question, :polymarket_url, :category, :probability,
                :divergence, :volume, :volume_24h, :liquidity, :risk, :risk_flags_json,
                :ai_rule_score, :rule_score, :priority_score, :suggested_shadow_track,
                :trend_direction, :seen_count, :probability_delta, :ai_rule_score_delta,
                :next_action, :wallet_write_allowed, :order_send_allowed, :raw_json
            )
            """,
            {
                "id": row_id,
                "candidate_id": candidate_id,
                "run_id": run_id,
                "generated_at": str(item.get("generatedAt") or generated),
                "queue_state": str(item.get("queueState") or ""),
                "execution_mode": str(item.get("executionMode") or ""),
                "market_id": str(item.get("marketId") or ""),
                "event_id": str(item.get("eventId") or ""),
                "question": str(item.get("question") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "category": str(item.get("category") or ""),
                "probability": safe_number(item.get("probability")),
                "divergence": safe_number(item.get("divergence")),
                "volume": safe_number(item.get("volume")),
                "volume_24h": safe_number(item.get("volume24h")),
                "liquidity": safe_number(item.get("liquidity")),
                "risk": str(item.get("risk") or ""),
                "risk_flags_json": compact_json(item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else []),
                "ai_rule_score": safe_number(item.get("aiRuleScore")),
                "rule_score": safe_number(item.get("ruleScore")),
                "priority_score": safe_number(item.get("priorityScore")),
                "suggested_shadow_track": str(item.get("suggestedShadowTrack") or ""),
                "trend_direction": str(item.get("trendDirection") or ""),
                "seen_count": safe_int(item.get("seenCount"), 0),
                "probability_delta": safe_number(item.get("probabilityDelta")),
                "ai_rule_score_delta": safe_number(item.get("aiRuleScoreDelta")),
                "next_action": str(item.get("nextAction") or ""),
                "wallet_write_allowed": as_bool_int(item.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(item.get("orderSendAllowed")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_cross_market_linkage(con: sqlite3.Connection, cross_payload: dict[str, Any], now_iso: str) -> int:
    rows = cross_payload.get("linkages") if isinstance(cross_payload.get("linkages"), list) else []
    generated_default = str(cross_payload.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("linkageId") or stable_id("cross", item.get("marketId"), item.get("question")))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_cross_market_linkage (
                id, generated_at, market_id, event_id, question, event_title,
                polymarket_url, category, primary_risk_tag, risk_tags_json,
                matched_keywords_json, linked_mt5_symbols_json, macro_risk_state,
                confidence, probability, source_score, source_risk,
                source_types_json, suggested_shadow_track, wallet_write_allowed,
                order_send_allowed, mt5_execution_allowed, raw_json
            ) VALUES (
                :id, :generated_at, :market_id, :event_id, :question, :event_title,
                :polymarket_url, :category, :primary_risk_tag, :risk_tags_json,
                :matched_keywords_json, :linked_mt5_symbols_json, :macro_risk_state,
                :confidence, :probability, :source_score, :source_risk,
                :source_types_json, :suggested_shadow_track, :wallet_write_allowed,
                :order_send_allowed, :mt5_execution_allowed, :raw_json
            )
            """,
            {
                "id": row_id,
                "generated_at": str(item.get("generatedAt") or generated_default),
                "market_id": str(item.get("marketId") or ""),
                "event_id": str(item.get("eventId") or ""),
                "question": str(item.get("question") or ""),
                "event_title": str(item.get("eventTitle") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "category": str(item.get("category") or ""),
                "primary_risk_tag": str(item.get("primaryRiskTag") or ""),
                "risk_tags_json": compact_json(item.get("riskTags") if isinstance(item.get("riskTags"), list) else []),
                "matched_keywords_json": compact_json(item.get("matchedKeywords") if isinstance(item.get("matchedKeywords"), dict) else {}),
                "linked_mt5_symbols_json": compact_json(item.get("linkedMt5Symbols") if isinstance(item.get("linkedMt5Symbols"), list) else []),
                "macro_risk_state": str(item.get("macroRiskState") or ""),
                "confidence": safe_number(item.get("confidence")),
                "probability": safe_number(item.get("probability")),
                "source_score": safe_number(item.get("sourceScore")),
                "source_risk": str(item.get("sourceRisk") or ""),
                "source_types_json": compact_json(item.get("sourceTypes") if isinstance(item.get("sourceTypes"), list) else []),
                "suggested_shadow_track": str(item.get("suggestedShadowTrack") or ""),
                "wallet_write_allowed": as_bool_int(item.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(item.get("orderSendAllowed")),
                "mt5_execution_allowed": as_bool_int(item.get("mt5ExecutionAllowed")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_canary_contracts(con: sqlite3.Connection, canary_payload: dict[str, Any], now_iso: str) -> int:
    rows = canary_payload.get("candidateContracts") if isinstance(canary_payload.get("candidateContracts"), list) else []
    generated_default = str(canary_payload.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        contract_id = str(item.get("canaryContractId") or "")
        row_id = contract_id or stable_id("canary", item.get("marketId"), item.get("question"), item.get("track"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_canary_contracts (
                id, generated_at, canary_contract_id, market_id, question,
                polymarket_url, track, side, canary_state, decision,
                canary_eligible_now, reference_stake_usdc, canary_stake_usdc,
                max_single_bet_usdc, max_daily_loss_usdc, take_profit_pct,
                stop_loss_pct, trailing_profit_pct, cancel_unfilled_minutes,
                max_hold_hours, exit_before_resolution_hours, source_score,
                ai_score, ai_color, cross_risk_tag, macro_risk_state,
                dry_run_state, outcome_state, would_exit_reason, blockers_json,
                wallet_write_allowed, order_send_allowed, starts_executor, raw_json
            ) VALUES (
                :id, :generated_at, :canary_contract_id, :market_id, :question,
                :polymarket_url, :track, :side, :canary_state, :decision,
                :canary_eligible_now, :reference_stake_usdc, :canary_stake_usdc,
                :max_single_bet_usdc, :max_daily_loss_usdc, :take_profit_pct,
                :stop_loss_pct, :trailing_profit_pct, :cancel_unfilled_minutes,
                :max_hold_hours, :exit_before_resolution_hours, :source_score,
                :ai_score, :ai_color, :cross_risk_tag, :macro_risk_state,
                :dry_run_state, :outcome_state, :would_exit_reason, :blockers_json,
                :wallet_write_allowed, :order_send_allowed, :starts_executor, :raw_json
            )
            """,
            {
                "id": row_id,
                "generated_at": str(item.get("generatedAt") or generated_default),
                "canary_contract_id": contract_id,
                "market_id": str(item.get("marketId") or ""),
                "question": str(item.get("question") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "track": str(item.get("track") or ""),
                "side": str(item.get("side") or ""),
                "canary_state": str(item.get("canaryState") or ""),
                "decision": str(item.get("decision") or ""),
                "canary_eligible_now": as_bool_int(item.get("canaryEligibleNow")),
                "reference_stake_usdc": safe_number(item.get("referenceStakeUSDC")),
                "canary_stake_usdc": safe_number(item.get("canaryStakeUSDC")),
                "max_single_bet_usdc": safe_number(item.get("maxSingleBetUSDC")),
                "max_daily_loss_usdc": safe_number(item.get("maxDailyLossUSDC")),
                "take_profit_pct": safe_number(item.get("takeProfitPct")),
                "stop_loss_pct": safe_number(item.get("stopLossPct")),
                "trailing_profit_pct": safe_number(item.get("trailingProfitPct")),
                "cancel_unfilled_minutes": safe_int(item.get("cancelUnfilledAfterMinutes"), 0),
                "max_hold_hours": safe_number(item.get("maxHoldHours")),
                "exit_before_resolution_hours": safe_number(item.get("exitBeforeResolutionHours")),
                "source_score": safe_number(item.get("sourceScore")),
                "ai_score": safe_number(item.get("aiScore")),
                "ai_color": str(item.get("aiColor") or ""),
                "cross_risk_tag": str(item.get("crossRiskTag") or ""),
                "macro_risk_state": str(item.get("macroRiskState") or ""),
                "dry_run_state": str(item.get("dryRunState") or ""),
                "outcome_state": str(item.get("outcomeState") or ""),
                "would_exit_reason": str(item.get("wouldExitReason") or ""),
                "blockers_json": compact_json(item.get("blockers") if isinstance(item.get("blockers"), list) else []),
                "wallet_write_allowed": as_bool_int(item.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(item.get("orderSendAllowed")),
                "starts_executor": as_bool_int(item.get("startsExecutor")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_auto_governance(con: sqlite3.Connection, governance_payload: dict[str, Any], now_iso: str) -> int:
    rows = governance_payload.get("governanceDecisions") if isinstance(governance_payload.get("governanceDecisions"), list) else []
    generated_default = str(governance_payload.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        governance_id = str(item.get("governanceId") or "")
        row_id = governance_id or stable_id("auto_governance", item.get("marketId"), item.get("question"), item.get("track"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_auto_governance (
                id, generated_at, governance_id, market_id, question,
                polymarket_url, track, current_state, governance_state,
                recommended_action, risk_level, score, ai_score, source_score,
                ai_color, canary_state, dry_run_state, outcome_state,
                would_exit_reason, cross_risk_tag, macro_risk_state,
                blockers_json, source_types_json, next_test,
                wallet_write_allowed, order_send_allowed, starts_executor,
                mutates_mt5, can_promote_to_live_execution, raw_json
            ) VALUES (
                :id, :generated_at, :governance_id, :market_id, :question,
                :polymarket_url, :track, :current_state, :governance_state,
                :recommended_action, :risk_level, :score, :ai_score, :source_score,
                :ai_color, :canary_state, :dry_run_state, :outcome_state,
                :would_exit_reason, :cross_risk_tag, :macro_risk_state,
                :blockers_json, :source_types_json, :next_test,
                :wallet_write_allowed, :order_send_allowed, :starts_executor,
                :mutates_mt5, :can_promote_to_live_execution, :raw_json
            )
            """,
            {
                "id": row_id,
                "generated_at": str(item.get("generatedAt") or generated_default),
                "governance_id": governance_id,
                "market_id": str(item.get("marketId") or ""),
                "question": str(item.get("question") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "track": str(item.get("track") or ""),
                "current_state": str(item.get("currentState") or ""),
                "governance_state": str(item.get("governanceState") or ""),
                "recommended_action": str(item.get("recommendedAction") or ""),
                "risk_level": str(item.get("riskLevel") or ""),
                "score": safe_number(item.get("score")),
                "ai_score": safe_number(item.get("aiScore")),
                "source_score": safe_number(item.get("sourceScore")),
                "ai_color": str(item.get("aiColor") or ""),
                "canary_state": str(item.get("canaryState") or ""),
                "dry_run_state": str(item.get("dryRunState") or ""),
                "outcome_state": str(item.get("outcomeState") or ""),
                "would_exit_reason": str(item.get("wouldExitReason") or ""),
                "cross_risk_tag": str(item.get("crossRiskTag") or ""),
                "macro_risk_state": str(item.get("macroRiskState") or ""),
                "blockers_json": compact_json(item.get("blockers") if isinstance(item.get("blockers"), list) else []),
                "source_types_json": compact_json(item.get("sourceTypes") if isinstance(item.get("sourceTypes"), list) else []),
                "next_test": str(item.get("nextTest") or ""),
                "wallet_write_allowed": as_bool_int(item.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(item.get("orderSendAllowed")),
                "starts_executor": as_bool_int(item.get("startsExecutor")),
                "mutates_mt5": as_bool_int(item.get("mutatesMt5")),
                "can_promote_to_live_execution": as_bool_int(item.get("canPromoteToLiveExecution")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_canary_executor_run(con: sqlite3.Connection, run_payload: dict[str, Any], now_iso: str) -> tuple[int, int]:
    if not run_payload:
        return 0, 0
    generated = str(run_payload.get("generatedAt") or now_iso)
    run_id = str(run_payload.get("runId") or stable_id("canary_executor_run", generated))
    summary = run_payload.get("summary") if isinstance(run_payload.get("summary"), dict) else {}
    con.execute(
        """
        INSERT OR REPLACE INTO qd_polymarket_canary_executor_runs (
            run_id, generated_at, execution_mode, decision, planned_orders,
            orders_sent, eligible_governance_rows, wallet_write_allowed,
            order_send_allowed, preflight_blockers_json, raw_json
        ) VALUES (
            :run_id, :generated_at, :execution_mode, :decision, :planned_orders,
            :orders_sent, :eligible_governance_rows, :wallet_write_allowed,
            :order_send_allowed, :preflight_blockers_json, :raw_json
        )
        """,
        {
            "run_id": run_id,
            "generated_at": generated,
            "execution_mode": str(run_payload.get("executionMode") or ""),
            "decision": str(run_payload.get("decision") or ""),
            "planned_orders": safe_int(summary.get("plannedOrders"), 0),
            "orders_sent": safe_int(summary.get("ordersSent"), 0),
            "eligible_governance_rows": safe_int(summary.get("eligibleGovernanceRows"), 0),
            "wallet_write_allowed": as_bool_int(summary.get("walletWriteAllowed")),
            "order_send_allowed": as_bool_int(summary.get("orderSendAllowed")),
            "preflight_blockers_json": compact_json(run_payload.get("preflightBlockers") if isinstance(run_payload.get("preflightBlockers"), list) else []),
            "raw_json": compact_json(run_payload),
        },
    )
    audit_count = 0
    for item in run_payload.get("plannedOrders") if isinstance(run_payload.get("plannedOrders"), list) else []:
        if not isinstance(item, dict):
            continue
        audit_id = stable_id("canary_order_audit", run_id, item.get("candidateId"), item.get("marketId"), item.get("decision"))
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_canary_order_audit (
                id, run_id, generated_at, candidate_id, governance_id, market_id,
                question, track, side, token_id_present, limit_price, stake_usdc,
                size, decision, order_sent, wallet_write_allowed, order_send_allowed,
                blockers_json, adapter_status, raw_json
            ) VALUES (
                :id, :run_id, :generated_at, :candidate_id, :governance_id, :market_id,
                :question, :track, :side, :token_id_present, :limit_price, :stake_usdc,
                :size, :decision, :order_sent, :wallet_write_allowed, :order_send_allowed,
                :blockers_json, :adapter_status, :raw_json
            )
            """,
            {
                "id": audit_id,
                "run_id": run_id,
                "generated_at": generated,
                "candidate_id": str(item.get("candidateId") or ""),
                "governance_id": str(item.get("governanceId") or ""),
                "market_id": str(item.get("marketId") or ""),
                "question": str(item.get("question") or ""),
                "track": str(item.get("track") or ""),
                "side": str(item.get("side") or ""),
                "token_id_present": as_bool_int(item.get("tokenIdPresent")),
                "limit_price": safe_number(item.get("limitPrice")),
                "stake_usdc": safe_number(item.get("stakeUSDC")),
                "size": safe_number(item.get("size")),
                "decision": str(item.get("decision") or ""),
                "order_sent": as_bool_int(item.get("orderSent")),
                "wallet_write_allowed": as_bool_int(summary.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(summary.get("orderSendAllowed")),
                "blockers_json": compact_json(item.get("blockers") if isinstance(item.get("blockers"), list) else []),
                "adapter_status": str(item.get("adapterStatus") or ""),
                "raw_json": compact_json(item),
            },
        )
        audit_count += 1
    return 1, audit_count


def upsert_market_catalog(con: sqlite3.Connection, catalog_payload: dict[str, Any], now_iso: str) -> int:
    rows = catalog_payload.get("marketCatalog") if isinstance(catalog_payload.get("marketCatalog"), list) else []
    if not rows:
        rows = catalog_payload.get("markets") if isinstance(catalog_payload.get("markets"), list) else []
    generated = str(catalog_payload.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("marketId") or "")
        row_id = str(item.get("catalogId") or stable_id("market_catalog", market_id, item.get("polymarketUrl"), item.get("question")))
        con.execute(
            """
            INSERT INTO qd_polymarket_markets (
                id, first_seen_at, last_seen_at, catalog_generated_at, catalog_rank,
                catalog_id, market_id, event_id, question, event_title, slug,
                polymarket_url, category, probability, volume, volume_24h,
                liquidity, spread, divergence, abs_divergence, rule_score,
                ai_rule_score, risk, risk_flags_json, recommended_action,
                suggested_shadow_track, related_asset_count, related_assets_json,
                end_date, accepting_orders, raw_json
            ) VALUES (
                :id, :first_seen_at, :last_seen_at, :catalog_generated_at, :catalog_rank,
                :catalog_id, :market_id, :event_id, :question, :event_title, :slug,
                :polymarket_url, :category, :probability, :volume, :volume_24h,
                :liquidity, :spread, :divergence, :abs_divergence, :rule_score,
                :ai_rule_score, :risk, :risk_flags_json, :recommended_action,
                :suggested_shadow_track, :related_asset_count, :related_assets_json,
                :end_date, :accepting_orders, :raw_json
            )
            ON CONFLICT(id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                catalog_generated_at=excluded.catalog_generated_at,
                catalog_rank=excluded.catalog_rank,
                question=excluded.question,
                event_title=excluded.event_title,
                polymarket_url=excluded.polymarket_url,
                category=excluded.category,
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
                suggested_shadow_track=excluded.suggested_shadow_track,
                related_asset_count=excluded.related_asset_count,
                related_assets_json=excluded.related_assets_json,
                end_date=excluded.end_date,
                accepting_orders=excluded.accepting_orders,
                raw_json=excluded.raw_json
            """,
            {
                "id": row_id,
                "first_seen_at": now_iso,
                "last_seen_at": now_iso,
                "catalog_generated_at": generated,
                "catalog_rank": safe_int(item.get("catalogRank") or item.get("rank"), 0),
                "catalog_id": str(item.get("catalogId") or row_id),
                "market_id": market_id,
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
                "risk": str(item.get("risk") or ""),
                "risk_flags_json": compact_json(item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else []),
                "recommended_action": str(item.get("recommendedAction") or ""),
                "suggested_shadow_track": str(item.get("suggestedShadowTrack") or ""),
                "related_asset_count": safe_int(item.get("relatedAssetCount"), 0),
                "related_assets_json": compact_json(item.get("relatedAssets") if isinstance(item.get("relatedAssets"), list) else []),
                "end_date": str(item.get("endDate") or ""),
                "accepting_orders": as_bool_int(item.get("acceptingOrders")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def upsert_related_asset_opportunities(con: sqlite3.Connection, payload: dict[str, Any], now_iso: str) -> int:
    rows = payload.get("relatedAssetOpportunities") if isinstance(payload.get("relatedAssetOpportunities"), list) else []
    if not rows:
        rows = payload.get("assetOpportunities") if isinstance(payload.get("assetOpportunities"), list) else []
    generated_default = str(payload.get("generatedAt") or now_iso)
    count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        opportunity_id = str(item.get("opportunityId") or "")
        row_id = opportunity_id or stable_id("related_asset", item.get("marketId"), item.get("assetSymbol"), item.get("question"))
        con.execute(
            """
            INSERT INTO qd_polymarket_related_asset_opportunities (
                id, first_seen_at, last_seen_at, generated_at, rank,
                opportunity_id, market_id, event_id, question, event_title,
                polymarket_url, category, probability, market_score, market_risk,
                asset_symbol, asset_market, asset_family, bias, directional_hint,
                confidence, suggested_action, suggested_shadow_track,
                matched_keywords_json, rationale, wallet_write_allowed,
                order_send_allowed, mt5_execution_allowed, raw_json
            ) VALUES (
                :id, :first_seen_at, :last_seen_at, :generated_at, :rank,
                :opportunity_id, :market_id, :event_id, :question, :event_title,
                :polymarket_url, :category, :probability, :market_score, :market_risk,
                :asset_symbol, :asset_market, :asset_family, :bias, :directional_hint,
                :confidence, :suggested_action, :suggested_shadow_track,
                :matched_keywords_json, :rationale, :wallet_write_allowed,
                :order_send_allowed, :mt5_execution_allowed, :raw_json
            )
            ON CONFLICT(id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                generated_at=excluded.generated_at,
                rank=excluded.rank,
                probability=excluded.probability,
                market_score=excluded.market_score,
                market_risk=excluded.market_risk,
                confidence=excluded.confidence,
                suggested_action=excluded.suggested_action,
                suggested_shadow_track=excluded.suggested_shadow_track,
                matched_keywords_json=excluded.matched_keywords_json,
                rationale=excluded.rationale,
                raw_json=excluded.raw_json
            """,
            {
                "id": row_id,
                "first_seen_at": now_iso,
                "last_seen_at": now_iso,
                "generated_at": str(item.get("generatedAt") or generated_default),
                "rank": safe_int(item.get("rank"), 0),
                "opportunity_id": opportunity_id or row_id,
                "market_id": str(item.get("marketId") or ""),
                "event_id": str(item.get("eventId") or ""),
                "question": str(item.get("question") or ""),
                "event_title": str(item.get("eventTitle") or ""),
                "polymarket_url": str(item.get("polymarketUrl") or ""),
                "category": str(item.get("category") or ""),
                "probability": safe_number(item.get("probability")),
                "market_score": safe_number(item.get("marketScore")),
                "market_risk": str(item.get("marketRisk") or ""),
                "asset_symbol": str(item.get("assetSymbol") or ""),
                "asset_market": str(item.get("assetMarket") or ""),
                "asset_family": str(item.get("assetFamily") or ""),
                "bias": str(item.get("bias") or ""),
                "directional_hint": str(item.get("directionalHint") or ""),
                "confidence": safe_number(item.get("confidence")),
                "suggested_action": str(item.get("suggestedAction") or ""),
                "suggested_shadow_track": str(item.get("suggestedShadowTrack") or ""),
                "matched_keywords_json": compact_json(item.get("matchedKeywords") if isinstance(item.get("matchedKeywords"), list) else []),
                "rationale": str(item.get("rationale") or ""),
                "wallet_write_allowed": as_bool_int(item.get("walletWriteAllowed")),
                "order_send_allowed": as_bool_int(item.get("orderSendAllowed")),
                "mt5_execution_allowed": as_bool_int(item.get("mt5ExecutionAllowed")),
                "raw_json": compact_json(item),
            },
        )
        count += 1
    return count


def table_summary(con: sqlite3.Connection, table: str, latest_col: str = "generated_at") -> dict[str, Any]:
    row = con.execute(f"SELECT COUNT(*) AS rows, MAX({latest_col}) AS latest_at FROM {table}").fetchone()
    return {"rows": int(row["rows"] or 0), "latestAt": row["latest_at"] or ""}


def fetch_rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def build_summary(con: sqlite3.Connection, db_path: Path, source_files: dict[str, str], now_iso: str, recent_limit: int) -> dict[str, Any]:
    tables = {
        "qd_polymarket_runs": table_summary(con, "qd_polymarket_runs"),
        "qd_polymarket_asset_opportunities": table_summary(con, "qd_polymarket_asset_opportunities", "last_seen_at"),
        "qd_polymarket_market_analysis": table_summary(con, "qd_polymarket_market_analysis"),
        "qd_polymarket_execution_simulations": table_summary(con, "qd_polymarket_execution_simulations"),
        "qd_polymarket_research_snapshots": table_summary(con, "qd_polymarket_research_snapshots"),
        "qd_polymarket_radar_worker_runs": table_summary(con, "qd_polymarket_radar_worker_runs"),
        "qd_polymarket_radar_trends": table_summary(con, "qd_polymarket_radar_trends"),
        "qd_polymarket_radar_queue": table_summary(con, "qd_polymarket_radar_queue"),
        "qd_polymarket_cross_market_linkage": table_summary(con, "qd_polymarket_cross_market_linkage"),
        "qd_polymarket_canary_contracts": table_summary(con, "qd_polymarket_canary_contracts"),
        "qd_polymarket_auto_governance": table_summary(con, "qd_polymarket_auto_governance"),
        "qd_polymarket_canary_executor_runs": table_summary(con, "qd_polymarket_canary_executor_runs"),
        "qd_polymarket_canary_order_audit": table_summary(con, "qd_polymarket_canary_order_audit"),
        "qd_polymarket_markets": table_summary(con, "qd_polymarket_markets", "last_seen_at"),
        "qd_polymarket_related_asset_opportunities": table_summary(con, "qd_polymarket_related_asset_opportunities", "last_seen_at"),
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
    recent_worker_runs = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, run_id AS runId, status, decision,
               cycles_completed AS cyclesCompleted, unique_markets AS uniqueMarkets,
               duplicate_markets AS duplicateMarkets, candidate_queue_size AS candidateQueueSize,
               new_markets AS newMarkets, recurring_markets AS recurringMarkets,
               score_improved AS scoreImproved, score_deteriorated AS scoreDeteriorated,
               probability_moved_up AS probabilityMovedUp, probability_moved_down AS probabilityMovedDown,
               stale_tracked AS staleTracked, top_market AS topMarket, top_score AS topScore,
               top_risk AS topRisk, wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed, can_start_executor AS canStartExecutor
        FROM qd_polymarket_radar_worker_runs
        ORDER BY generated_at DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_worker_trends = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, run_id AS runId, market_id AS marketId,
               question, category, suggested_shadow_track AS suggestedShadowTrack,
               risk, seen_count AS seenCount, stale_cycles AS staleCycles,
               last_probability AS lastProbability, probability_delta AS probabilityDelta,
               last_ai_rule_score AS lastAiRuleScore, ai_rule_score_delta AS aiRuleScoreDelta,
               best_ai_rule_score AS bestAiRuleScore, last_volume_24h AS lastVolume24h,
               volume_24h_delta AS volume24hDelta, last_liquidity AS lastLiquidity,
               trend_direction AS trendDirection
        FROM qd_polymarket_radar_trends
        ORDER BY generated_at DESC, best_ai_rule_score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_worker_queue = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, candidate_id AS candidateId, run_id AS runId,
               queue_state AS queueState, execution_mode AS executionMode, market_id AS marketId,
               question, category, probability, divergence, volume_24h AS volume24h,
               liquidity, risk, ai_rule_score AS aiRuleScore, priority_score AS priorityScore,
               suggested_shadow_track AS suggestedShadowTrack, trend_direction AS trendDirection,
               seen_count AS seenCount, probability_delta AS probabilityDelta,
               ai_rule_score_delta AS aiRuleScoreDelta, next_action AS nextAction,
               wallet_write_allowed AS walletWriteAllowed, order_send_allowed AS orderSendAllowed
        FROM qd_polymarket_radar_queue
        ORDER BY generated_at DESC, priority_score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_cross_linkage = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, market_id AS marketId, event_id AS eventId,
               question, event_title AS eventTitle, polymarket_url AS polymarketUrl,
               category, primary_risk_tag AS primaryRiskTag, risk_tags_json AS riskTagsJson,
               matched_keywords_json AS matchedKeywordsJson,
               linked_mt5_symbols_json AS linkedMt5SymbolsJson,
               macro_risk_state AS macroRiskState, confidence, probability,
               source_score AS sourceScore, source_risk AS sourceRisk,
               source_types_json AS sourceTypesJson,
               suggested_shadow_track AS suggestedShadowTrack,
               wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed,
               mt5_execution_allowed AS mt5ExecutionAllowed
        FROM qd_polymarket_cross_market_linkage
        ORDER BY generated_at DESC, confidence DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_canary_contracts = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, canary_contract_id AS canaryContractId,
               market_id AS marketId, question, polymarket_url AS polymarketUrl,
               track, side, canary_state AS canaryState, decision,
               canary_eligible_now AS canaryEligibleNow,
               reference_stake_usdc AS referenceStakeUSDC,
               canary_stake_usdc AS canaryStakeUSDC,
               max_single_bet_usdc AS maxSingleBetUSDC,
               max_daily_loss_usdc AS maxDailyLossUSDC,
               take_profit_pct AS takeProfitPct,
               stop_loss_pct AS stopLossPct,
               trailing_profit_pct AS trailingProfitPct,
               cancel_unfilled_minutes AS cancelUnfilledAfterMinutes,
               max_hold_hours AS maxHoldHours,
               exit_before_resolution_hours AS exitBeforeResolutionHours,
               source_score AS sourceScore, ai_score AS aiScore,
               ai_color AS aiColor, cross_risk_tag AS crossRiskTag,
               macro_risk_state AS macroRiskState, dry_run_state AS dryRunState,
               outcome_state AS outcomeState, would_exit_reason AS wouldExitReason,
               blockers_json AS blockersJson,
               wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed,
               starts_executor AS startsExecutor
        FROM qd_polymarket_canary_contracts
        ORDER BY generated_at DESC, source_score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_auto_governance = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, governance_id AS governanceId,
               market_id AS marketId, question, polymarket_url AS polymarketUrl,
               track, current_state AS currentState, governance_state AS governanceState,
               recommended_action AS recommendedAction, risk_level AS riskLevel,
               score, ai_score AS aiScore, source_score AS sourceScore,
               ai_color AS aiColor, canary_state AS canaryState,
               dry_run_state AS dryRunState, outcome_state AS outcomeState,
               would_exit_reason AS wouldExitReason,
               cross_risk_tag AS crossRiskTag, macro_risk_state AS macroRiskState,
               blockers_json AS blockersJson, source_types_json AS sourceTypesJson,
               next_test AS nextTest, wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed, starts_executor AS startsExecutor,
               mutates_mt5 AS mutatesMt5,
               can_promote_to_live_execution AS canPromoteToLiveExecution
        FROM qd_polymarket_auto_governance
        ORDER BY generated_at DESC, score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_executor_runs = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, run_id AS runId, execution_mode AS executionMode,
               decision, planned_orders AS plannedOrders, orders_sent AS ordersSent,
               eligible_governance_rows AS eligibleGovernanceRows,
               wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed,
               preflight_blockers_json AS preflightBlockersJson
        FROM qd_polymarket_canary_executor_runs
        ORDER BY generated_at DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_order_audit = fetch_rows(
        con,
        """
        SELECT generated_at AS generatedAt, run_id AS runId, candidate_id AS candidateId,
               governance_id AS governanceId, market_id AS marketId, question, track, side,
               token_id_present AS tokenIdPresent, limit_price AS limitPrice,
               stake_usdc AS stakeUSDC, size, decision, order_sent AS orderSent,
               wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed,
               blockers_json AS blockersJson, adapter_status AS adapterStatus
        FROM qd_polymarket_canary_order_audit
        ORDER BY generated_at DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_market_catalog = fetch_rows(
        con,
        """
        SELECT last_seen_at AS seenAt, catalog_generated_at AS generatedAt,
               catalog_rank AS catalogRank, catalog_id AS catalogId,
               market_id AS marketId, event_id AS eventId, question,
               event_title AS eventTitle, slug, polymarket_url AS polymarketUrl,
               category, probability, volume, volume_24h AS volume24h, liquidity,
               spread, divergence, abs_divergence AS absDivergence,
               rule_score AS ruleScore, ai_rule_score AS aiRuleScore,
               risk, risk_flags_json AS riskFlagsJson,
               recommended_action AS recommendedAction,
               suggested_shadow_track AS suggestedShadowTrack,
               related_asset_count AS relatedAssetCount,
               related_assets_json AS relatedAssetsJson,
               end_date AS endDate, accepting_orders AS acceptingOrders
        FROM qd_polymarket_markets
        ORDER BY last_seen_at DESC, ai_rule_score DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    recent_related_assets = fetch_rows(
        con,
        """
        SELECT last_seen_at AS seenAt, generated_at AS generatedAt, rank,
               opportunity_id AS opportunityId, market_id AS marketId,
               event_id AS eventId, question, event_title AS eventTitle,
               polymarket_url AS polymarketUrl, category, probability,
               market_score AS marketScore, market_risk AS marketRisk,
               asset_symbol AS assetSymbol, asset_market AS assetMarket,
               asset_family AS assetFamily, bias, directional_hint AS directionalHint,
               confidence, suggested_action AS suggestedAction,
               suggested_shadow_track AS suggestedShadowTrack,
               matched_keywords_json AS matchedKeywordsJson, rationale,
               wallet_write_allowed AS walletWriteAllowed,
               order_send_allowed AS orderSendAllowed,
               mt5_execution_allowed AS mt5ExecutionAllowed
        FROM qd_polymarket_related_asset_opportunities
        ORDER BY last_seen_at DESC, confidence DESC
        LIMIT ?
        """,
        (recent_limit,),
    )
    return {
        "generatedAt": now_iso,
        "mode": "POLYMARKET_HISTORY_DB_V7",
        "schemaVersion": SCHEMA_VERSION,
        "decision": "LOCAL_HISTORY_DB_NO_WALLET_WRITE",
        "database": {
            "path": str(db_path),
            "tables": list(tables.keys()),
            "purpose": "Long-lived local Polymarket research memory for radar, QuantDinger-style market catalog, related asset opportunities, worker trend cache, worker queue, cross-market linkage, canary contracts, auto-governance, guarded canary executor audit, analysis, dry-run, outcome, and bridge snapshots.",
        },
        "sourceFiles": source_files,
        "summary": {
            "totalRows": total_rows,
            "runs": tables["qd_polymarket_runs"]["rows"],
            "assetOpportunities": tables["qd_polymarket_asset_opportunities"]["rows"],
            "marketAnalyses": tables["qd_polymarket_market_analysis"]["rows"],
            "executionSimulations": tables["qd_polymarket_execution_simulations"]["rows"],
            "researchSnapshots": tables["qd_polymarket_research_snapshots"]["rows"],
            "radarWorkerRuns": tables["qd_polymarket_radar_worker_runs"]["rows"],
            "radarTrendRows": tables["qd_polymarket_radar_trends"]["rows"],
            "radarQueueRows": tables["qd_polymarket_radar_queue"]["rows"],
            "crossMarketLinkages": tables["qd_polymarket_cross_market_linkage"]["rows"],
            "canaryContracts": tables["qd_polymarket_canary_contracts"]["rows"],
            "autoGovernanceDecisions": tables["qd_polymarket_auto_governance"]["rows"],
            "canaryExecutorRuns": tables["qd_polymarket_canary_executor_runs"]["rows"],
            "canaryOrderAuditRows": tables["qd_polymarket_canary_order_audit"]["rows"],
            "marketCatalogRows": tables["qd_polymarket_markets"]["rows"],
            "relatedAssetOpportunities": tables["qd_polymarket_related_asset_opportunities"]["rows"],
            "latestAt": max((item["latestAt"] for item in tables.values() if item["latestAt"]), default=""),
        },
        "tables": tables,
        "recent": {
            "opportunities": recent_opportunities,
            "analyses": recent_analyses,
            "simulations": recent_simulations,
            "workerRuns": recent_worker_runs,
            "workerTrends": recent_worker_trends,
            "workerQueue": recent_worker_queue,
            "crossMarketLinkage": recent_cross_linkage,
            "canaryContracts": recent_canary_contracts,
            "autoGovernance": recent_auto_governance,
            "canaryExecutorRuns": recent_executor_runs,
            "canaryOrderAudit": recent_order_audit,
            "marketCatalog": recent_market_catalog,
            "relatedAssetOpportunities": recent_related_assets,
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
            "Use this DB as the source for Worker V2 trend and queue governance evidence.",
            "Use cross-market linkage as awareness-only evidence for USD/JPY/XAU/rates/geopolitical risk.",
            "Add future promotion/demotion rules only after trend cache and queue rows have enough history.",
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
    radar_worker, radar_worker_path = read_json_candidate(RADAR_WORKER_NAME, runtime_dir, dashboard_dir)
    radar_trend_cache, radar_trend_cache_path = read_json_candidate(RADAR_TREND_CACHE_NAME, runtime_dir, dashboard_dir)
    radar_queue, radar_queue_path = read_json_candidate(RADAR_QUEUE_NAME, runtime_dir, dashboard_dir)
    single, single_path = read_json_candidate(SINGLE_NAME, runtime_dir, dashboard_dir)
    dry_run, dry_run_path = read_json_candidate(DRY_RUN_NAME, runtime_dir, dashboard_dir)
    outcome, outcome_path = read_json_candidate(OUTCOME_NAME, runtime_dir, dashboard_dir)
    cross_linkage, cross_linkage_path = read_json_candidate(CROSS_LINKAGE_NAME, runtime_dir, dashboard_dir)
    canary_contract, canary_contract_path = read_json_candidate(CANARY_CONTRACT_NAME, runtime_dir, dashboard_dir)
    auto_governance, auto_governance_path = read_json_candidate(AUTO_GOVERNANCE_NAME, runtime_dir, dashboard_dir)
    canary_executor_run, canary_executor_run_path = read_json_candidate(CANARY_EXECUTOR_RUN_NAME, runtime_dir, dashboard_dir)
    market_catalog, market_catalog_path = read_json_candidate(MARKET_CATALOG_NAME, runtime_dir, dashboard_dir)
    related_asset_opportunities, related_asset_opportunities_path = read_json_candidate(
        RELATED_ASSET_OPPORTUNITY_NAME,
        runtime_dir,
        dashboard_dir,
    )
    source_files = {
        RESEARCH_NAME: research_path,
        RADAR_NAME: radar_path,
        RADAR_WORKER_NAME: radar_worker_path,
        RADAR_TREND_CACHE_NAME: radar_trend_cache_path,
        RADAR_QUEUE_NAME: radar_queue_path,
        SINGLE_NAME: single_path,
        DRY_RUN_NAME: dry_run_path,
        OUTCOME_NAME: outcome_path,
        CROSS_LINKAGE_NAME: cross_linkage_path,
        CANARY_CONTRACT_NAME: canary_contract_path,
        AUTO_GOVERNANCE_NAME: auto_governance_path,
        CANARY_EXECUTOR_RUN_NAME: canary_executor_run_path,
        MARKET_CATALOG_NAME: market_catalog_path,
        RELATED_ASSET_OPPORTUNITY_NAME: related_asset_opportunities_path,
    }

    con = connect_db(db_path)
    try:
        init_schema(con)
        radar_rows = upsert_radar(con, radar, now_iso)
        analysis_rows = upsert_single_analysis(con, single, now_iso)
        dry_run_rows = upsert_dry_runs(con, dry_run, now_iso)
        outcome_rows = upsert_outcomes(con, outcome, now_iso)
        research_rows = upsert_research(con, research, now_iso)
        worker_rows = upsert_radar_worker_run(con, radar_worker, now_iso)
        trend_rows = upsert_radar_trends(con, radar_trend_cache, radar_worker, now_iso)
        queue_rows = upsert_radar_queue(con, radar_queue, radar_worker, now_iso)
        cross_linkage_rows = upsert_cross_market_linkage(con, cross_linkage, now_iso)
        canary_contract_rows = upsert_canary_contracts(con, canary_contract, now_iso)
        auto_governance_rows = upsert_auto_governance(con, auto_governance, now_iso)
        canary_executor_run_rows, canary_order_audit_rows = upsert_canary_executor_run(con, canary_executor_run, now_iso)
        market_catalog_rows = upsert_market_catalog(con, market_catalog, now_iso)
        related_asset_opportunity_rows = upsert_related_asset_opportunities(con, related_asset_opportunities, now_iso)
        simulation_rows = dry_run_rows + outcome_rows
        run_id = "POLYHIST-" + utc_now().strftime("%Y%m%d-%H%M%S")
        con.execute(
            """
            INSERT OR REPLACE INTO qd_polymarket_runs (
                run_id, generated_at, schema_version, db_path, source_files_json,
                radar_rows, analysis_rows, simulation_rows, research_rows,
                worker_rows, trend_rows, queue_rows, cross_linkage_rows,
                canary_contract_rows, auto_governance_rows,
                canary_executor_run_rows, canary_order_audit_rows,
                market_catalog_rows, related_asset_opportunity_rows,
                wallet_write_allowed, order_send_allowed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
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
                worker_rows,
                trend_rows,
                queue_rows,
                cross_linkage_rows,
                canary_contract_rows,
                auto_governance_rows,
                canary_executor_run_rows,
                canary_order_audit_rows,
                market_catalog_rows,
                related_asset_opportunity_rows,
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
