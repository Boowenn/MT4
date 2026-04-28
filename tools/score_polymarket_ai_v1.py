#!/usr/bin/env python3
"""Build history-aware Polymarket AI Score V1 for QuantGod.

This scorer reads the local Polymarket history SQLite database and produces a
research-only score for each market/track. It does not import Polymarket runtime
modules, read private keys, write wallets, place/cancel orders, start executors,
or mutate MT5. The score is a transparent feature model over historical radar,
single-market analysis, dry-run/outcome, and global research evidence.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parents[1] / "archive" / "polymarket" / "history"
DEFAULT_DB_PATH = DEFAULT_HISTORY_DIR / "QuantGod_PolymarketHistory.sqlite"
OUTPUT_NAME = "QuantGod_PolymarketAiScoreV1.json"
CSV_NAME = "QuantGod_PolymarketAiScoreV1.csv"
SCHEMA_VERSION = "POLYMARKET_AI_SCORE_V1"


WEIGHTS = {
    "radar_score": 0.28,
    "liquidity_score": 0.14,
    "divergence_score": 0.14,
    "risk_score": 0.16,
    "single_analysis_score": 0.16,
    "outcome_score": 0.12,
}


RISK_SCORE = {
    "low": 88.0,
    "medium": 55.0,
    "med": 55.0,
    "high": 18.0,
    "unknown": 45.0,
    "": 45.0,
}


RECOMMENDATION_BONUS = {
    "SHADOW_REVIEW_HIGH_PRIORITY": 12.0,
    "SHADOW_REVIEW": 8.0,
    "WATCHLIST": 2.0,
    "NO_BET": -22.0,
    "AVOID": -30.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--top", type=int, default=20)
    return parser.parse_args()


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
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"History DB not found: {db_path}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def fetch_rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def latest_research_snapshot(con: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_rows(
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
        """,
    )
    return rows[0] if rows else {}


def load_candidates(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return fetch_rows(
        con,
        """
        SELECT id, last_seen_at AS seenAt, rank, market_id AS marketId, event_id AS eventId,
               question, event_title AS eventTitle, slug, polymarket_url AS polymarketUrl,
               category, probability, volume, volume_24h AS volume24h, liquidity, spread,
               divergence, abs_divergence AS absDivergence, rule_score AS ruleScore,
               ai_rule_score AS aiRuleScore, ai_scoring_mode AS aiScoringMode, risk,
               risk_flags_json AS riskFlagsJson, recommended_action AS recommendedAction,
               suggested_shadow_track AS suggestedShadowTrack, end_date AS endDate,
               accepting_orders AS acceptingOrders, source
        FROM qd_polymarket_asset_opportunities
        ORDER BY last_seen_at DESC, ai_rule_score DESC, liquidity DESC
        """,
    )


def analysis_index(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = fetch_rows(
        con,
        """
        SELECT * FROM (
            SELECT generated_at AS generatedAt, market_id AS marketId, question, query,
                   market_probability AS marketProbability, ai_probability AS aiProbability,
                   divergence, confidence, recommendation, risk,
                   suggested_shadow_track AS suggestedShadowTrack, ai_scoring_mode AS aiScoringMode,
                   ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY generated_at DESC) AS rn
            FROM qd_polymarket_market_analysis
        ) WHERE rn = 1
        """,
    )
    return {str(row.get("marketId") or row.get("question") or ""): row for row in rows}


def simulation_index(con: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    rows = fetch_rows(
        con,
        """
        SELECT market_id AS marketId, track,
               COUNT(*) AS rows,
               AVG(COALESCE(mfe_pct, 0)) AS avgMfePct,
               AVG(COALESCE(mae_pct, 0)) AS avgMaePct,
               MAX(COALESCE(mfe_pct, 0)) AS maxMfePct,
               MIN(COALESCE(mae_pct, 0)) AS minMaePct,
               SUM(CASE WHEN would_exit_reason LIKE '%TAKE_PROFIT%' THEN 1 ELSE 0 END) AS takeProfitHits,
               SUM(CASE WHEN would_exit_reason LIKE '%STOP_LOSS%' THEN 1 ELSE 0 END) AS stopLossHits,
               SUM(CASE WHEN would_exit_reason LIKE '%TRAIL%' THEN 1 ELSE 0 END) AS trailingHits,
               SUM(CASE WHEN state LIKE '%BLOCK%' OR decision LIKE '%BLOCK%' THEN 1 ELSE 0 END) AS blockedRows,
               MAX(generated_at) AS latestAt
        FROM qd_polymarket_execution_simulations
        GROUP BY market_id, track
        """,
    )
    return {(str(row.get("marketId") or ""), str(row.get("track") or "")): row for row in rows}


def score_liquidity(volume: float, volume24h: float, liquidity: float) -> float:
    liquidity_part = clamp(math.log10(max(liquidity, 0.0) + 1.0) * 17.0)
    volume_part = clamp(math.log10(max(volume, 0.0) + 1.0) * 13.0)
    active_part = clamp(math.log10(max(volume24h, 0.0) + 1.0) * 15.0)
    return round((liquidity_part * 0.45) + (volume_part * 0.35) + (active_part * 0.20), 2)


def score_divergence(abs_divergence: float, probability: float) -> float:
    if abs_divergence <= 0:
        return 35.0
    base = clamp(abs_divergence * 3.0, 35.0, 92.0)
    if abs_divergence > 45.0:
        base -= 12.0
    if probability <= 3.0 or probability >= 97.0:
        base -= 10.0
    return round(clamp(base), 2)


def score_analysis(row: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not row:
        return 45.0, ["single_analysis_missing"]
    confidence = clamp(safe_number(row.get("confidence"), 45.0))
    risk = str(row.get("risk") or "unknown").lower()
    recommendation = str(row.get("recommendation") or "")
    divergence = abs(safe_number(row.get("divergence"), 0.0))
    score = confidence * 0.62
    score += RISK_SCORE.get(risk, 45.0) * 0.18
    score += clamp(divergence * 2.0, 0.0, 18.0)
    score += RECOMMENDATION_BONUS.get(recommendation, 0.0)
    reasons: list[str] = []
    if confidence >= 70:
        reasons.append("single_analysis_confidence_high")
    if recommendation:
        reasons.append(f"single_analysis_{recommendation.lower()}")
    if risk in ("medium", "high"):
        reasons.append(f"single_analysis_risk_{risk}")
    return round(clamp(score), 2), reasons or ["single_analysis_neutral"]


def score_outcome(row: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not row or safe_int(row.get("rows"), 0) <= 0:
        return 45.0, ["dry_run_outcome_missing"]
    rows = safe_int(row.get("rows"), 0)
    avg_mfe = safe_number(row.get("avgMfePct"), 0.0)
    avg_mae = safe_number(row.get("avgMaePct"), 0.0)
    take_profit = safe_int(row.get("takeProfitHits"), 0)
    stop_loss = safe_int(row.get("stopLossHits"), 0)
    trailing = safe_int(row.get("trailingHits"), 0)
    blocked = safe_int(row.get("blockedRows"), 0)
    score = 50.0
    score += clamp(avg_mfe * 1.8, 0.0, 22.0)
    score += clamp(avg_mae * 1.2, -22.0, 0.0)
    score += min(take_profit * 7.0, 20.0)
    score += min(trailing * 4.0, 12.0)
    score -= min(stop_loss * 9.0, 28.0)
    if rows and blocked / rows > 0.75:
        score -= 8.0
    reasons: list[str] = [f"dry_run_rows_{rows}"]
    if avg_mfe > abs(avg_mae) and avg_mfe > 0:
        reasons.append("mfe_better_than_mae")
    if stop_loss:
        reasons.append("stop_loss_seen")
    if take_profit or trailing:
        reasons.append("positive_exit_seen")
    if blocked:
        reasons.append("gate_blocked_rows_present")
    return round(clamp(score), 2), reasons


def global_penalty(snapshot: dict[str, Any]) -> tuple[float, list[str]]:
    penalty = 0.0
    reasons: list[str] = []
    executed_pf = safe_number(snapshot.get("executedPf"), 0.0)
    executed_pnl = safe_number(snapshot.get("executedPnl"), 0.0)
    executed_closed = safe_int(snapshot.get("executedClosed"), 0)
    shadow_pf = safe_number(snapshot.get("shadowPf"), 0.0)
    shadow_pnl = safe_number(snapshot.get("shadowPnl"), 0.0)
    account_cash = safe_number(snapshot.get("accountCash"), 0.0)
    bankroll = safe_number(snapshot.get("bankroll"), 0.0)
    if executed_closed >= 10 and executed_pf < 1.0:
        penalty -= 8.0
        reasons.append("executed_pf_below_1")
    if executed_pnl < 0:
        penalty -= 6.0
        reasons.append("executed_realized_pnl_negative")
    if shadow_pf and shadow_pf < 1.0:
        penalty -= 4.0
        reasons.append("shadow_pf_below_1")
    if shadow_pnl < 0:
        penalty -= 3.0
        reasons.append("shadow_realized_pnl_negative")
    if bankroll and account_cash < bankroll:
        penalty -= 5.0
        reasons.append("account_cash_below_bankroll")
    return penalty, reasons


def classify(score: float, risk: str, hard_reasons: list[str]) -> tuple[str, str]:
    lowered_reasons = " ".join(hard_reasons).lower()
    if score < 35 or risk == "high" or "stop_loss_seen" in lowered_reasons:
        return "red", "RETUNE_OR_IGNORE"
    if score >= 72 and risk == "low":
        return "green", "SHADOW_REVIEW_PRIORITY"
    if score >= 55:
        return "yellow", "WATCH_SHADOW_AND_COLLECT_OUTCOME"
    return "yellow", "RETUNE_BEFORE_NEXT_BATCH"


def score_candidate(
    item: dict[str, Any],
    analyses: dict[str, dict[str, Any]],
    simulations: dict[tuple[str, str], dict[str, Any]],
    penalty: float,
    global_reasons: list[str],
) -> dict[str, Any]:
    market_id = str(item.get("marketId") or "")
    track = str(item.get("suggestedShadowTrack") or "")
    risk = str(item.get("risk") or "unknown").lower()
    risk_flags = [str(flag) for flag in parse_json_list(item.get("riskFlagsJson"))]
    radar_score = clamp(safe_number(item.get("aiRuleScore"), safe_number(item.get("ruleScore"), 50.0)))
    liquidity_score = score_liquidity(
        safe_number(item.get("volume")),
        safe_number(item.get("volume24h")),
        safe_number(item.get("liquidity")),
    )
    divergence_score = score_divergence(
        safe_number(item.get("absDivergence"), abs(safe_number(item.get("divergence")))),
        safe_number(item.get("probability")),
    )
    risk_score = RISK_SCORE.get(risk, 45.0)
    analysis_row = analyses.get(market_id) or analyses.get(str(item.get("question") or ""))
    analysis_score, analysis_reasons = score_analysis(analysis_row)
    outcome_score, outcome_reasons = score_outcome(simulations.get((market_id, track)))
    weighted = (
        radar_score * WEIGHTS["radar_score"]
        + liquidity_score * WEIGHTS["liquidity_score"]
        + divergence_score * WEIGHTS["divergence_score"]
        + risk_score * WEIGHTS["risk_score"]
        + analysis_score * WEIGHTS["single_analysis_score"]
        + outcome_score * WEIGHTS["outcome_score"]
    )
    if not safe_int(item.get("acceptingOrders"), 0):
        weighted -= 12.0
        risk_flags.append("not_accepting_orders")
    weighted += penalty
    score = round(clamp(weighted), 2)
    reasons: list[str] = []
    if radar_score >= 80:
        reasons.append("radar_score_strong")
    if liquidity_score >= 75:
        reasons.append("liquidity_volume_strong")
    if divergence_score >= 75:
        reasons.append("divergence_large_enough_for_shadow")
    if risk == "low":
        reasons.append("risk_low")
    if risk_flags:
        reasons.extend(risk_flags[:4])
    reasons.extend(analysis_reasons[:4])
    reasons.extend(outcome_reasons[:4])
    reasons.extend(global_reasons[:5])
    color, action = classify(score, risk, reasons)
    live_allowed = False
    if color == "green" and score >= 72:
        suggested = "只进入高优先 shadow/dry-run 观察；不允许真钱下注。"
    elif action.startswith("RETUNE"):
        suggested = "先重调筛选条件，再收集下一批 shadow 样本。"
    else:
        suggested = "继续观察历史与 outcome 后验，暂不进入执行层。"
    components = {
        "radarScore": round(radar_score, 2),
        "liquidityScore": liquidity_score,
        "divergenceScore": divergence_score,
        "riskScore": round(risk_score, 2),
        "singleAnalysisScore": analysis_score,
        "outcomeScore": outcome_score,
        "globalPenalty": round(penalty, 2),
    }
    return {
        "marketId": market_id,
        "question": item.get("question") or "",
        "eventTitle": item.get("eventTitle") or "",
        "polymarketUrl": item.get("polymarketUrl") or "",
        "category": item.get("category") or "",
        "track": track,
        "probability": safe_number(item.get("probability")),
        "volume": safe_number(item.get("volume")),
        "liquidity": safe_number(item.get("liquidity")),
        "divergence": safe_number(item.get("divergence")),
        "risk": risk,
        "score": score,
        "color": color,
        "action": action,
        "liveAllowed": live_allowed,
        "executionMode": "AI_SCORE_ONLY_NO_WALLET_WRITE",
        "suggestedShadowTrack": track,
        "components": components,
        "reasons": list(dict.fromkeys(reasons))[:14],
        "nextStep": suggested,
        "seenAt": item.get("seenAt") or "",
        "analysisGeneratedAt": analysis_row.get("generatedAt") if analysis_row else "",
    }


def build_scores(db_path: Path, top: int, now_iso: str) -> dict[str, Any]:
    with connect_readonly(db_path) as con:
        research = latest_research_snapshot(con)
        candidates = load_candidates(con)
        analyses = analysis_index(con)
        simulations = simulation_index(con)
        penalty, global_reasons = global_penalty(research)
        scored = [score_candidate(item, analyses, simulations, penalty, global_reasons) for item in candidates]
    scored.sort(key=lambda row: (row["score"], row.get("liquidity", 0.0)), reverse=True)
    top_rows = scored[: max(1, top)]
    color_counts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
    for row in scored:
        color_counts[row["color"]] = color_counts.get(row["color"], 0) + 1
    best = top_rows[0] if top_rows else {}
    return {
        "generatedAt": now_iso,
        "mode": "POLYMARKET_AI_SCORE_V1",
        "schemaVersion": SCHEMA_VERSION,
        "decision": "AI_SCORE_ONLY_NO_BETTING",
        "database": {"path": str(db_path), "source": "QuantGod_PolymarketHistory.sqlite"},
        "summary": {
            "candidates": len(scored),
            "topShown": len(top_rows),
            "green": color_counts.get("green", 0),
            "yellow": color_counts.get("yellow", 0),
            "red": color_counts.get("red", 0),
            "topScore": best.get("score"),
            "topMarket": best.get("question", ""),
            "globalPenalty": round(penalty, 2),
        },
        "scoringModel": {
            "type": "transparent_history_feature_model",
            "weights": WEIGHTS,
            "inputs": [
                "radar score and market quality",
                "liquidity and volume",
                "probability divergence",
                "risk flags",
                "single-market analysis confidence and recommendation",
                "dry-run/outcome MFE/MAE and exit triggers",
                "global executed/shadow/account quarantine penalty",
            ],
        },
        "globalEvidence": {
            "executedClosed": safe_int(research.get("executedClosed")),
            "executedPf": safe_number(research.get("executedPf")),
            "executedPnl": safe_number(research.get("executedPnl")),
            "shadowClosed": safe_int(research.get("shadowClosed")),
            "shadowPf": safe_number(research.get("shadowPf")),
            "shadowPnl": safe_number(research.get("shadowPnl")),
            "accountCash": safe_number(research.get("accountCash")),
            "bankroll": safe_number(research.get("bankroll")),
            "penaltyReasons": global_reasons,
        },
        "scores": top_rows,
        "safety": {
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "livePromotionAllowed": False,
            "note": "AI Score V1 is research-only and cannot trigger betting by itself.",
        },
        "nextActions": [
            "Use green rows only as high-priority shadow/dry-run candidates.",
            "Use yellow/red rows to drive retune planner filters.",
            "Do not enable wallet executor until separate canary executor and loss controls are promoted.",
        ],
    }


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path) -> list[str]:
    written: list[str] = []
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    rows = []
    for item in snapshot.get("scores", []):
        rows.append(
            {
                "generated_at": snapshot.get("generatedAt", ""),
                "market_id": item.get("marketId", ""),
                "question": item.get("question", ""),
                "track": item.get("track", ""),
                "score": item.get("score", ""),
                "color": item.get("color", ""),
                "action": item.get("action", ""),
                "risk": item.get("risk", ""),
                "probability": item.get("probability", ""),
                "divergence": item.get("divergence", ""),
                "liquidity": item.get("liquidity", ""),
                "live_allowed": "false",
                "top_reasons": ";".join(item.get("reasons", [])[:8]),
            }
        )
    for base in [runtime_dir, dashboard_dir]:
        base.mkdir(parents=True, exist_ok=True)
        json_path = base / OUTPUT_NAME
        csv_path = base / CSV_NAME
        atomic_write_text(json_path, json_text)
        written.append(str(json_path))
        output = io.StringIO()
        fieldnames = list(rows[0].keys()) if rows else ["generated_at", "market_id", "score", "color", "action"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        atomic_write_text(csv_path, output.getvalue())
        written.append(str(csv_path))
    return written


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    now_iso = utc_now_iso()
    snapshot = build_scores(db_path, max(1, args.top), now_iso)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | candidates={summary['candidates']} | top={summary.get('topScore')} "
        f"| green/yellow/red={summary['green']}/{summary['yellow']}/{summary['red']} | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
