#!/usr/bin/env python3
"""Build history-aware Polymarket AI Score V1 for QuantGod.

This scorer reads the local Polymarket history SQLite database and produces a
research-only score for each market/track. It can optionally ask an
OpenAI-compatible LLM for a semantic review of market wording, event ambiguity,
and next-test direction, then blends that with the transparent history feature
model. It does not import Polymarket runtime modules, read wallet private keys,
write wallets, place/cancel orders, start executors, or mutate MT5.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parents[1] / "archive" / "polymarket" / "history"
DEFAULT_DB_PATH = DEFAULT_HISTORY_DIR / "QuantGod_PolymarketHistory.sqlite"
OUTPUT_NAME = "QuantGod_PolymarketAiScoreV1.json"
CSV_NAME = "QuantGod_PolymarketAiScoreV1.csv"
LLM_AUDIT_NAME = "QuantGod_PolymarketAiSemanticReview.json"
SCHEMA_VERSION = "POLYMARKET_AI_SCORE_V1_LLM_SEMANTIC_OPTIONAL"
DEFAULT_LLM_ENV_FILE = Path(r"D:\polymarket\.env")
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
LLM_WEIGHT = 0.32


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
    parser.add_argument("--llm-mode", choices=["auto", "off", "required"], default="auto")
    parser.add_argument("--llm-provider", default="openai")
    parser.add_argument("--llm-model", default=os.environ.get("QG_POLYMARKET_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
    parser.add_argument("--llm-env-file", default=str(DEFAULT_LLM_ENV_FILE))
    parser.add_argument("--llm-max-candidates", type=int, default=8)
    parser.add_argument("--llm-timeout", type=float, default=35.0)
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


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def load_allowed_env_file(path: Path) -> dict[str, str]:
    """Load only LLM-related keys from an env file without exposing secrets."""
    allowed = {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "QG_POLYMARKET_LLM_MODEL",
        "QG_POLYMARKET_OPENAI_API_KEY",
        "QG_POLYMARKET_OPENAI_BASE_URL",
    }
    loaded: dict[str, str] = {}
    if not path or not str(path) or not path.exists() or path.is_dir():
        return loaded
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed:
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            loaded[key] = value
            os.environ.setdefault(key, value)
    return loaded


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


def normalize_llm_risk(value: Any) -> str:
    risk = str(value or "").strip().lower()
    if risk in {"low", "green", "safe"}:
        return "low"
    if risk in {"high", "red", "danger"}:
        return "high"
    if risk in {"medium", "med", "yellow", "watch"}:
        return "medium"
    return "unknown"


def normalize_llm_recommendation(value: Any) -> str:
    recommendation = str(value or "").strip().upper().replace(" ", "_")
    allowed = {
        "SHADOW_REVIEW_PRIORITY",
        "SHADOW_REVIEW",
        "WATCHLIST",
        "RETUNE_OR_IGNORE",
        "RETUNE_BEFORE_NEXT_BATCH",
        "NO_BET",
        "AVOID",
    }
    return recommendation if recommendation in allowed else "WATCHLIST"


def compact_candidate_for_llm(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "marketId": row.get("marketId", ""),
        "question": str(row.get("question") or row.get("eventTitle") or "")[:260],
        "category": row.get("category", ""),
        "track": row.get("track", ""),
        "baseHistoryScore": row.get("score"),
        "baseColor": row.get("color"),
        "baseAction": row.get("action"),
        "probabilityPct": row.get("probability"),
        "divergencePct": row.get("divergence"),
        "risk": row.get("risk"),
        "liquidity": row.get("liquidity"),
        "components": row.get("components", {}),
        "reasons": row.get("reasons", [])[:10],
        "nextStep": row.get("nextStep", ""),
    }


def get_openai_config(args: argparse.Namespace) -> dict[str, Any]:
    provider = str(args.llm_provider or "openai").strip().lower()
    env_file = Path(str(args.llm_env_file or ""))
    loaded_env = load_allowed_env_file(env_file)
    api_key = (
        os.environ.get("QG_POLYMARKET_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base_url = (
        os.environ.get("QG_POLYMARKET_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = str(args.llm_model or os.environ.get("QG_POLYMARKET_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
    return {
        "provider": provider,
        "mode": args.llm_mode,
        "model": model,
        "baseUrl": base_url,
        "apiKey": api_key,
        "envFileLoaded": bool(loaded_env),
        "envFilePath": str(env_file) if env_file else "",
        "maxCandidates": max(0, int(args.llm_max_candidates or 0)),
        "timeout": max(5.0, float(args.llm_timeout or 35.0)),
    }


def call_openai_semantic_review(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {"ok": True, "status": "skipped_no_candidates", "reviews": [], "raw": {}}
    if config.get("provider") != "openai":
        return {"ok": False, "status": "unsupported_provider", "reviews": [], "error": str(config.get("provider") or "")}
    if not config.get("apiKey"):
        return {"ok": False, "status": "disabled_no_api_key", "reviews": [], "error": "OPENAI_API_KEY not configured"}

    candidates = [compact_candidate_for_llm(row) for row in rows[: int(config.get("maxCandidates") or 0)]]
    system_prompt = (
        "You are QuantGod's Polymarket research reviewer. Score markets for shadow-only research. "
        "Never recommend real wallet execution. Use market question semantics, event risk, liquidity, "
        "probability divergence, history score, dry-run outcome signals, and risk flags. "
        "Return strict JSON only."
    )
    user_prompt = {
        "task": "semantic_polymarket_shadow_scoring",
        "constraints": [
            "No betting, no wallet write, no CLOB order, no MT5 mutation.",
            "Score 0-100 where higher means better shadow/dry-run research priority.",
            "Prefer conservative risk assessment when title semantics imply low information quality, ambiguous resolution, manipulation risk, or event tail risk.",
        ],
        "returnSchema": {
            "reviews": [
                {
                    "marketId": "string",
                    "semanticScore": "0-100",
                    "confidence": "0-100",
                    "risk": "low|medium|high",
                    "recommendation": "SHADOW_REVIEW_PRIORITY|SHADOW_REVIEW|WATCHLIST|RETUNE_OR_IGNORE|NO_BET|AVOID",
                    "reason": "short Chinese explanation",
                    "riskFactors": ["short tags"],
                    "nextTest": "short Chinese next parameter/filter test",
                }
            ],
            "globalNotes": "short Chinese note",
        },
        "candidates": candidates,
    }
    payload = {
        "model": config["model"],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{config['baseUrl']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['apiKey']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(config["timeout"])) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:600]
        return {"ok": False, "status": "http_error", "reviews": [], "error": f"HTTP {error.code}: {body}"}
    except Exception as error:  # noqa: BLE001 - report a safe, non-secret failure reason.
        return {"ok": False, "status": "request_failed", "reviews": [], "error": str(error)}

    try:
        response_payload = json.loads(body)
        content = response_payload["choices"][0]["message"]["content"]
        review_payload = json.loads(content)
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "status": "parse_failed", "reviews": [], "error": str(error)}

    reviews = []
    for raw in review_payload.get("reviews", []):
        if not isinstance(raw, dict):
            continue
        review = {
            "marketId": str(raw.get("marketId") or "").strip(),
            "semanticScore": round(clamp(safe_number(raw.get("semanticScore"), 50.0)), 2),
            "confidence": round(clamp(safe_number(raw.get("confidence"), 50.0)), 2),
            "risk": normalize_llm_risk(raw.get("risk")),
            "recommendation": normalize_llm_recommendation(raw.get("recommendation")),
            "reason": str(raw.get("reason") or "").strip()[:420],
            "riskFactors": [str(item).strip()[:80] for item in parse_json_list(raw.get("riskFactors")) if str(item).strip()][:8],
            "nextTest": str(raw.get("nextTest") or "").strip()[:280],
        }
        reviews.append(review)
    return {
        "ok": True,
        "status": "reviewed",
        "reviews": reviews,
        "globalNotes": str(review_payload.get("globalNotes") or "").strip()[:500],
        "usage": response_payload.get("usage", {}),
    }


def apply_llm_reviews(scored: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    if config.get("mode") == "off":
        return {"ok": True, "status": "disabled_by_flag", "reviews": [], "reviewed": 0}
    if config.get("maxCandidates", 0) <= 0:
        return {"ok": True, "status": "disabled_zero_budget", "reviews": [], "reviewed": 0}

    ranked = sorted(scored, key=lambda row: (row.get("score", 0.0), row.get("liquidity", 0.0)), reverse=True)
    llm_result = call_openai_semantic_review(ranked, config)
    if not llm_result.get("ok"):
        if config.get("mode") == "required":
            raise RuntimeError(f"LLM scoring required but unavailable: {llm_result.get('status')} {llm_result.get('error', '')}")
        return {**llm_result, "reviewed": 0}

    reviews_by_market = {
        str(review.get("marketId") or ""): review
        for review in llm_result.get("reviews", [])
        if str(review.get("marketId") or "")
    }
    reviewed = 0
    for row in scored:
        review = reviews_by_market.get(str(row.get("marketId") or ""))
        if not review:
            continue
        base_score = safe_number(row.get("score"), 0.0)
        semantic_score = safe_number(review.get("semanticScore"), 50.0)
        semantic_confidence = safe_number(review.get("confidence"), 50.0)
        confidence_weight = LLM_WEIGHT * clamp(semantic_confidence, 20.0, 95.0) / 100.0
        blended = round(clamp(base_score * (1.0 - confidence_weight) + semantic_score * confidence_weight), 2)
        row["historyFeatureScore"] = base_score
        row["score"] = blended
        row["llmReview"] = review
        row["llmReviewed"] = True
        row["semanticScore"] = semantic_score
        row["semanticConfidence"] = semantic_confidence
        row["components"]["historyFeatureScore"] = base_score
        row["components"]["semanticScore"] = semantic_score
        row["components"]["semanticConfidence"] = semantic_confidence
        row["components"]["llmWeightApplied"] = round(confidence_weight, 3)
        if review.get("risk") in {"low", "medium", "high"}:
            row["semanticRisk"] = review["risk"]
        row["semanticRecommendation"] = review.get("recommendation", "")
        if review.get("reason"):
            row["reasons"] = list(dict.fromkeys([f"llm:{review['reason']}", *row.get("reasons", [])]))[:16]
        if review.get("riskFactors"):
            row["reasons"] = list(dict.fromkeys([*row.get("reasons", []), *[f"llm_risk:{flag}" for flag in review["riskFactors"]]]))[:18]
        if review.get("nextTest"):
            row["nextStep"] = f"{review['nextTest']}；仍然只进 shadow/dry-run，不允许真钱下注。"
        risk_for_class = normalize_llm_risk(review.get("risk")) if review.get("risk") != "unknown" else row.get("risk", "")
        color, action = classify(blended, risk_for_class, row.get("reasons", []))
        if review.get("recommendation") in {"NO_BET", "AVOID", "RETUNE_OR_IGNORE"}:
            color, action = "red", "RETUNE_OR_IGNORE"
        elif review.get("recommendation") == "SHADOW_REVIEW_PRIORITY" and blended >= 65 and color != "red":
            color, action = "green", "SHADOW_REVIEW_PRIORITY"
        row["color"] = color
        row["action"] = action
        reviewed += 1
    return {**llm_result, "reviewed": reviewed}


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


def build_scores(db_path: Path, top: int, now_iso: str, llm_config: dict[str, Any]) -> dict[str, Any]:
    with connect_readonly(db_path) as con:
        research = latest_research_snapshot(con)
        candidates = load_candidates(con)
        analyses = analysis_index(con)
        simulations = simulation_index(con)
        penalty, global_reasons = global_penalty(research)
        scored = [score_candidate(item, analyses, simulations, penalty, global_reasons) for item in candidates]
    llm_result = apply_llm_reviews(scored, llm_config)
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
            "llmReviewed": safe_int(llm_result.get("reviewed"), 0),
            "llmStatus": llm_result.get("status", "unknown"),
        },
        "scoringModel": {
            "type": "llm_semantic_reviewer_plus_history_feature_model" if safe_int(llm_result.get("reviewed"), 0) else "history_feature_model_llm_ready",
            "semanticReviewer": {
                "enabled": llm_config.get("mode") != "off",
                "provider": llm_config.get("provider"),
                "model": llm_config.get("model"),
                "status": llm_result.get("status", "unknown"),
                "reviewed": safe_int(llm_result.get("reviewed"), 0),
                "maxCandidates": llm_config.get("maxCandidates"),
                "envFileLoaded": bool(llm_config.get("envFileLoaded")),
                "error": str(llm_result.get("error") or "")[:500],
                "note": "No API key or LLM failure falls back to the transparent history feature model; secrets are never written.",
            },
            "weights": WEIGHTS,
            "llmWeight": LLM_WEIGHT,
            "inputs": [
                "radar score and market quality",
                "liquidity and volume",
                "probability divergence",
                "risk flags",
                "single-market analysis confidence and recommendation",
                "dry-run/outcome MFE/MAE and exit triggers",
                "global executed/shadow/account quarantine penalty",
                "optional LLM semantic review of market title, event risk, ambiguity, and next test",
            ],
        },
        "semanticReview": {
            "status": llm_result.get("status", "unknown"),
            "reviewed": safe_int(llm_result.get("reviewed"), 0),
            "globalNotes": llm_result.get("globalNotes", ""),
            "usage": llm_result.get("usage", {}),
            "reviews": llm_result.get("reviews", []),
            "safety": {
                "writesSecrets": False,
                "writesWallet": False,
                "placesOrders": False,
                "mutatesMt5": False,
            },
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
            "Use LLM-reviewed green rows only as high-priority shadow/dry-run candidates.",
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
                "history_feature_score": item.get("historyFeatureScore", item.get("score", "")),
                "semantic_score": item.get("semanticScore", ""),
                "semantic_confidence": item.get("semanticConfidence", ""),
                "semantic_risk": item.get("semanticRisk", ""),
                "semantic_recommendation": item.get("semanticRecommendation", ""),
                "color": item.get("color", ""),
                "action": item.get("action", ""),
                "risk": item.get("risk", ""),
                "probability": item.get("probability", ""),
                "divergence": item.get("divergence", ""),
                "liquidity": item.get("liquidity", ""),
                "live_allowed": "false",
                "llm_reviewed": str(bool(item.get("llmReviewed"))).lower(),
                "llm_reason": (item.get("llmReview") or {}).get("reason", ""),
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
        audit_path = base / LLM_AUDIT_NAME
        atomic_write_text(
            audit_path,
            json.dumps(
                {
                    "generatedAt": snapshot.get("generatedAt"),
                    "schemaVersion": snapshot.get("schemaVersion"),
                    "semanticReview": snapshot.get("semanticReview", {}),
                    "safety": snapshot.get("safety", {}),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        written.append(str(audit_path))
    return written


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    now_iso = utc_now_iso()
    llm_config = get_openai_config(args)
    snapshot = build_scores(db_path, max(1, args.top), now_iso, llm_config)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot["summary"]
    print(
        f"{snapshot['mode']} | candidates={summary['candidates']} | top={summary.get('topScore')} "
        f"| green/yellow/red={summary['green']}/{summary['yellow']}/{summary['red']} "
        f"| llm={summary.get('llmStatus')} reviewed={summary.get('llmReviewed')} | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
