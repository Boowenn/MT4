#!/usr/bin/env python3
"""Run the Polymarket Gamma radar as a controlled shadow-only worker.

The worker is intentionally research-only. It may call the public Gamma API and
write QuantGod JSON/CSV evidence files, but it never loads wallet secrets,
places orders, starts a CLOB executor, or mutates MT5 state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from build_polymarket_market_radar import (
    DEFAULT_DASHBOARD_DIR,
    DEFAULT_ENDPOINT,
    DEFAULT_RUNTIME_DIR,
    atomic_write_text,
    build_snapshot,
    safe_number,
    write_outputs as write_radar_v1_outputs,
)


WORKER_NAME = "QuantGod_PolymarketRadarWorkerV2.json"
WORKER_LEDGER_NAME = "QuantGod_PolymarketRadarWorkerV2.csv"
TREND_CACHE_NAME = "QuantGod_PolymarketRadarTrendCache.json"
CANDIDATE_QUEUE_NAME = "QuantGod_PolymarketRadarCandidateQueue.json"
CANDIDATE_QUEUE_LEDGER_NAME = "QuantGod_PolymarketRadarCandidateQueue.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--limit", type=int, default=160)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--min-volume", type=float, default=5000.0)
    parser.add_argument("--min-liquidity", type=float, default=1000.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--max-cycles", type=int, default=24)
    parser.add_argument("--interval-seconds", type=float, default=900.0)
    parser.add_argument("--queue-top", type=int, default=25)
    parser.add_argument("--queue-min-score", type=float, default=45.0)
    parser.add_argument("--queue-risk", default="low,medium")
    parser.add_argument("--stale-retention-cycles", type=int, default=12)
    parser.add_argument("--input-radar", default="", help="Optional existing radar JSON for offline validation.")
    parser.add_argument("--skip-clob-depth", action="store_true", help="Skip public CLOB order-book depth enrichment.")
    parser.add_argument("--clob-depth-limit", type=int, default=12)
    parser.add_argument("--clob-timeout", type=float, default=4.0)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def stable_hash(*parts: Any, length: int = 16) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:length]


def market_key(item: dict[str, Any]) -> str:
    for key in ("marketId", "polymarketUrl", "slug", "question"):
        value = str(item.get(key) or "").strip().lower()
        if value:
            return value
    return stable_hash(json.dumps(item, sort_keys=True, ensure_ascii=False))


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def none_if_missing_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def delta(current: Any, previous: Any) -> float | None:
    current_num = none_if_missing_number(current)
    previous_num = none_if_missing_number(previous)
    if current_num is None or previous_num is None:
        return None
    return round(current_num - previous_num, 4)


def compact_question(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").replace("\ufeff", ""))


def read_optional_json(paths: list[Path]) -> tuple[dict[str, Any], str]:
    for path in paths:
        if not path or not path.exists():
            continue
        try:
            payload = read_json_file(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload, str(path)
    return {}, ""


def build_gamma_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_radar:
        path = Path(args.input_radar)
        snapshot = read_json_file(path)
        if not isinstance(snapshot, dict):
            raise ValueError(f"input radar is not a JSON object: {path}")
        snapshot = dict(snapshot)
        snapshot.setdefault("generatedAt", utc_now_iso())
        snapshot.setdefault("status", "OK")
        snapshot.setdefault("mode", "POLYMARKET_OPPORTUNITY_RADAR_V1_IMPORTED")
        snapshot.setdefault("source", {})
        snapshot["source"] = {
            **snapshot.get("source", {}),
            "scanner": "imported_radar_json",
            "inputRadar": str(path),
            "publicReadOnly": True,
            "walletWrite": False,
            "orderExecution": False,
            "mutatesMt5": False,
        }
        return snapshot

    radar_args = SimpleNamespace(
        endpoint=args.endpoint,
        limit=args.limit,
        top=args.top,
        min_volume=args.min_volume,
        min_liquidity=args.min_liquidity,
        timeout=args.timeout,
        skip_clob_depth=args.skip_clob_depth,
        clob_depth_limit=args.clob_depth_limit,
        clob_timeout=args.clob_timeout,
    )
    return build_snapshot(radar_args)


def dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    best_by_key: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for item in rows:
        key = market_key(item)
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = dict(item)
            continue
        duplicates += 1
        current_score = safe_number(current.get("aiRuleScore"), 0.0)
        next_score = safe_number(item.get("aiRuleScore"), 0.0)
        if next_score > current_score:
            best_by_key[key] = dict(item)
    deduped = list(best_by_key.values())
    deduped.sort(
        key=lambda row: (
            safe_number(row.get("aiRuleScore"), 0.0),
            safe_number(row.get("liquidity"), 0.0),
            safe_number(row.get("volume24h"), 0.0),
        ),
        reverse=True,
    )
    for index, item in enumerate(deduped, start=1):
        item["workerRank"] = index
    return deduped, duplicates


def load_trend_cache(runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    return read_optional_json([dashboard_dir / TREND_CACHE_NAME, runtime_dir / TREND_CACHE_NAME])


def update_trend_cache(
    previous_cache: dict[str, Any],
    rows: list[dict[str, Any]],
    generated_at: str,
    run_id: str,
    stale_retention_cycles: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    previous_markets = previous_cache.get("markets") if isinstance(previous_cache.get("markets"), dict) else {}
    next_markets: dict[str, dict[str, Any]] = {}
    seen_keys: set[str] = set()
    counts = {
        "newMarkets": 0,
        "recurringMarkets": 0,
        "scoreImproved": 0,
        "scoreDeteriorated": 0,
        "probabilityMovedUp": 0,
        "probabilityMovedDown": 0,
        "staleTracked": 0,
    }
    for item in rows:
        key = market_key(item)
        seen_keys.add(key)
        previous = previous_markets.get(key) if isinstance(previous_markets.get(key), dict) else {}
        score_delta = delta(item.get("aiRuleScore"), previous.get("lastAiRuleScore"))
        probability_delta = delta(item.get("probability"), previous.get("lastProbability"))
        volume_delta = delta(item.get("volume24h"), previous.get("lastVolume24h"))
        if previous:
            counts["recurringMarkets"] += 1
        else:
            counts["newMarkets"] += 1
        if score_delta is not None and score_delta > 0:
            counts["scoreImproved"] += 1
        elif score_delta is not None and score_delta < 0:
            counts["scoreDeteriorated"] += 1
        if probability_delta is not None and probability_delta > 0:
            counts["probabilityMovedUp"] += 1
        elif probability_delta is not None and probability_delta < 0:
            counts["probabilityMovedDown"] += 1
        trend_direction = "new"
        if previous:
            if score_delta is not None and score_delta >= 3:
                trend_direction = "score_up"
            elif score_delta is not None and score_delta <= -3:
                trend_direction = "score_down"
            elif probability_delta is not None and abs(probability_delta) >= 3:
                trend_direction = "probability_move"
            else:
                trend_direction = "flat"
        seen_count = safe_int(previous.get("seenCount"), 0) + 1
        state = {
            "key": key,
            "marketId": str(item.get("marketId") or ""),
            "eventId": str(item.get("eventId") or ""),
            "question": compact_question(item.get("question")),
            "polymarketUrl": str(item.get("polymarketUrl") or ""),
            "category": str(item.get("category") or ""),
            "suggestedShadowTrack": str(item.get("suggestedShadowTrack") or ""),
            "risk": str(item.get("risk") or ""),
            "riskFlags": item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else [],
            "firstSeenAt": previous.get("firstSeenAt") or generated_at,
            "lastSeenAt": generated_at,
            "seenCount": seen_count,
            "staleCycles": 0,
            "lastProbability": item.get("probability"),
            "previousProbability": previous.get("lastProbability"),
            "probabilityDelta": probability_delta,
            "lastAiRuleScore": item.get("aiRuleScore"),
            "previousAiRuleScore": previous.get("lastAiRuleScore"),
            "aiRuleScoreDelta": score_delta,
            "bestAiRuleScore": max(
                safe_number(item.get("aiRuleScore"), 0.0),
                safe_number(previous.get("bestAiRuleScore"), 0.0),
            ),
            "lastVolume24h": item.get("volume24h"),
            "previousVolume24h": previous.get("lastVolume24h"),
            "volume24hDelta": volume_delta,
            "lastLiquidity": item.get("liquidity"),
            "yesTokenId": item.get("yesTokenId"),
            "noTokenId": item.get("noTokenId"),
            "clobStatus": item.get("clobStatus"),
            "clobSpread": item.get("clobSpread"),
            "clobLiquidityUsd": item.get("clobLiquidityUsd"),
            "clobDepthScore": item.get("clobDepthScore"),
            "trendDirection": trend_direction,
            "lastRunId": run_id,
        }
        next_markets[key] = state
        item.update(
            {
                "trendDirection": trend_direction,
                "seenCount": seen_count,
                "firstSeenAt": state["firstSeenAt"],
                "lastSeenAt": generated_at,
                "probabilityDelta": probability_delta,
                "aiRuleScoreDelta": score_delta,
                "volume24hDelta": volume_delta,
                "bestAiRuleScore": state["bestAiRuleScore"],
            }
        )

    for key, previous in previous_markets.items():
        if key in seen_keys or not isinstance(previous, dict):
            continue
        stale_cycles = safe_int(previous.get("staleCycles"), 0) + 1
        if stale_cycles > max(0, stale_retention_cycles):
            continue
        stale_state = dict(previous)
        stale_state["staleCycles"] = stale_cycles
        stale_state["trendDirection"] = "stale"
        next_markets[key] = stale_state
        counts["staleTracked"] += 1

    cache = {
        "mode": "POLYMARKET_RADAR_TREND_CACHE_V1",
        "updatedAt": generated_at,
        "runId": run_id,
        "summary": {
            **counts,
            "trackedMarkets": len(next_markets),
            "activeMarkets": len(rows),
        },
        "markets": next_markets,
        "safety": {
            "publicReadOnly": True,
            "loadsEnv": False,
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "mutatesMt5": False,
        },
    }
    return cache, counts


def priority_score(item: dict[str, Any]) -> float:
    score = safe_number(item.get("aiRuleScore"), 0.0)
    abs_score_delta = abs(safe_number(item.get("aiRuleScoreDelta"), 0.0))
    abs_prob_delta = abs(safe_number(item.get("probabilityDelta"), 0.0))
    liquidity_bonus = min(8.0, safe_number(item.get("liquidity"), 0.0) / 25000.0)
    volume_bonus = min(8.0, safe_number(item.get("volume24h"), 0.0) / 25000.0)
    clob_bonus = min(8.0, safe_number(item.get("clobDepthScore"), 0.0) / 12.5)
    recurrence_bonus = min(6.0, safe_number(item.get("seenCount"), 0.0))
    risk_penalty = {"low": 0.0, "medium": 4.0, "high": 20.0}.get(str(item.get("risk") or "").lower(), 10.0)
    return round(score + abs_score_delta * 0.5 + abs_prob_delta * 0.35 + liquidity_bonus + volume_bonus + clob_bonus + recurrence_bonus - risk_penalty, 3)


def build_candidate_queue(rows: list[dict[str, Any]], args: argparse.Namespace, generated_at: str, run_id: str) -> list[dict[str, Any]]:
    allowed_risks = {part.strip().lower() for part in str(args.queue_risk or "").split(",") if part.strip()}
    queue: list[dict[str, Any]] = []
    for item in rows:
        risk = str(item.get("risk") or "").lower()
        score = safe_number(item.get("aiRuleScore"), 0.0)
        action = str(item.get("recommendedAction") or "")
        if risk not in allowed_risks:
            continue
        if score < args.queue_min_score:
            continue
        if action == "OBSERVE_ONLY":
            continue
        candidate_id = "PMRADAR-" + stable_hash(market_key(item), item.get("suggestedShadowTrack"), item.get("aiRuleScore"))
        queue.append(
            {
                "candidateId": candidate_id,
                "runId": run_id,
                "generatedAt": generated_at,
                "queueState": "SHADOW_ANALYSIS_READY",
                "executionMode": "SHADOW_ONLY_NO_WALLET_WRITE",
                "marketId": item.get("marketId"),
                "eventId": item.get("eventId"),
                "question": item.get("question"),
                "polymarketUrl": item.get("polymarketUrl"),
                "category": item.get("category"),
                "probability": item.get("probability"),
                "divergence": item.get("divergence"),
                "volume": item.get("volume"),
                "volume24h": item.get("volume24h"),
                "liquidity": item.get("liquidity"),
                "yesTokenId": item.get("yesTokenId"),
                "noTokenId": item.get("noTokenId"),
                "clobStatus": item.get("clobStatus"),
                "clobSpread": item.get("clobSpread"),
                "clobLiquidityUsd": item.get("clobLiquidityUsd"),
                "clobDepthScore": item.get("clobDepthScore"),
                "risk": item.get("risk"),
                "riskFlags": item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else [],
                "aiRuleScore": item.get("aiRuleScore"),
                "ruleScore": item.get("ruleScore"),
                "priorityScore": priority_score(item),
                "suggestedShadowTrack": item.get("suggestedShadowTrack"),
                "trendDirection": item.get("trendDirection"),
                "seenCount": item.get("seenCount"),
                "probabilityDelta": item.get("probabilityDelta"),
                "aiRuleScoreDelta": item.get("aiRuleScoreDelta"),
                "analysisRequest": {
                    "query": item.get("polymarketUrl") or item.get("question") or item.get("marketId"),
                    "marketId": item.get("marketId"),
                    "source": "radar_worker_v2_shadow_queue",
                },
                "nextAction": "RUN_SINGLE_MARKET_ANALYSIS_OR_AI_SCORE_REVIEW",
                "walletWriteAllowed": False,
                "orderSendAllowed": False,
            }
        )
    queue.sort(key=lambda row: safe_number(row.get("priorityScore"), 0.0), reverse=True)
    return queue[: max(0, args.queue_top)]


def queue_json(queue: list[dict[str, Any]], generated_at: str, run_id: str) -> dict[str, Any]:
    return {
        "mode": "POLYMARKET_RADAR_CANDIDATE_QUEUE_V1",
        "generatedAt": generated_at,
        "runId": run_id,
        "status": "OK",
        "decision": "SHADOW_ONLY_ANALYSIS_QUEUE_NO_BETTING",
        "summary": {
            "queued": len(queue),
            "highPriority": sum(1 for item in queue if safe_number(item.get("priorityScore"), 0.0) >= 70),
            "mediumRisk": sum(1 for item in queue if item.get("risk") == "medium"),
            "lowRisk": sum(1 for item in queue if item.get("risk") == "low"),
        },
        "safety": {
            "publicReadOnly": True,
            "loadsEnv": False,
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "mutatesMt5": False,
        },
        "candidates": queue,
        "nextActions": [
            "Use queued candidates for single-market analysis and AI score review only.",
            "Do not place Polymarket orders from this queue; real execution must pass Execution Gate and canary controls.",
        ],
    }


def queue_csv(queue: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "generated_at",
            "candidate_id",
            "priority_score",
            "market_id",
            "question",
            "risk",
            "clob_status",
            "clob_depth_score",
            "clob_spread",
            "ai_rule_score",
            "probability",
            "probability_delta",
            "ai_rule_score_delta",
            "seen_count",
            "suggested_shadow_track",
            "queue_state",
            "polymarket_url",
        ],
    )
    writer.writeheader()
    for item in queue:
        writer.writerow(
            {
                "generated_at": item.get("generatedAt", ""),
                "candidate_id": item.get("candidateId", ""),
                "priority_score": item.get("priorityScore", ""),
                "market_id": item.get("marketId", ""),
                "question": item.get("question", ""),
                "risk": item.get("risk", ""),
                "clob_status": item.get("clobStatus", ""),
                "clob_depth_score": item.get("clobDepthScore", ""),
                "clob_spread": item.get("clobSpread", ""),
                "ai_rule_score": item.get("aiRuleScore", ""),
                "probability": item.get("probability", ""),
                "probability_delta": item.get("probabilityDelta", ""),
                "ai_rule_score_delta": item.get("aiRuleScoreDelta", ""),
                "seen_count": item.get("seenCount", ""),
                "suggested_shadow_track": item.get("suggestedShadowTrack", ""),
                "queue_state": item.get("queueState", ""),
                "polymarket_url": item.get("polymarketUrl", ""),
            }
        )
    return output.getvalue()


def worker_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "generated_at",
            "run_id",
            "status",
            "cycles_completed",
            "unique_markets",
            "queue_size",
            "new_markets",
            "recurring_markets",
            "score_improved",
            "score_deteriorated",
            "wallet_write_allowed",
            "order_send_allowed",
            "top_market",
        ],
    )
    writer.writeheader()
    summary = snapshot.get("summary", {})
    safety = snapshot.get("safety", {})
    writer.writerow(
        {
            "generated_at": snapshot.get("generatedAt", ""),
            "run_id": snapshot.get("runId", ""),
            "status": snapshot.get("status", ""),
            "cycles_completed": snapshot.get("worker", {}).get("cyclesCompleted", ""),
            "unique_markets": summary.get("uniqueMarkets", ""),
            "queue_size": summary.get("candidateQueueSize", ""),
            "new_markets": summary.get("newMarkets", ""),
            "recurring_markets": summary.get("recurringMarkets", ""),
            "score_improved": summary.get("scoreImproved", ""),
            "score_deteriorated": summary.get("scoreDeteriorated", ""),
            "wallet_write_allowed": safety.get("walletWriteAllowed", False),
            "order_send_allowed": safety.get("orderSendAllowed", False),
            "top_market": summary.get("topMarket", ""),
        }
    )
    return output.getvalue()


def write_text_outputs(files: dict[str, str], runtime_dir: Path, dashboard_dir: Path) -> list[str]:
    written: list[str] = []
    for base_dir in [runtime_dir, dashboard_dir]:
        if not base_dir:
            continue
        for name, text in files.items():
            path = base_dir / name
            atomic_write_text(path, text)
            written.append(str(path))
    return written


def build_worker_snapshot(
    args: argparse.Namespace,
    run_id: str,
    started_at: str,
    finished_at: str,
    cycles: list[dict[str, Any]],
    latest_radar: dict[str, Any],
    deduped_rows: list[dict[str, Any]],
    duplicate_count: int,
    trend_cache: dict[str, Any],
    trend_counts: dict[str, int],
    queue: list[dict[str, Any]],
    cache_source: str,
) -> dict[str, Any]:
    error_cycles = [cycle for cycle in cycles if cycle.get("status") == "ERROR"]
    latest_summary = latest_radar.get("summary") if isinstance(latest_radar.get("summary"), dict) else {}
    top = deduped_rows[0] if deduped_rows else {}
    status = "ERROR" if cycles and len(error_cycles) == len(cycles) else ("PARTIAL" if error_cycles else "OK")
    return {
        "mode": "POLYMARKET_OPPORTUNITY_RADAR_WORKER_V2",
        "schemaVersion": "POLYMARKET_RADAR_WORKER_V2_SHADOW_ONLY",
        "generatedAt": finished_at,
        "runId": run_id,
        "status": status,
        "decision": "SHADOW_ONLY_BATCH_RADAR_WORKER_NO_BETTING",
        "worker": {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "cyclesRequested": max(1, min(args.cycles, args.max_cycles)),
            "cyclesCompleted": len(cycles),
            "intervalSeconds": args.interval_seconds,
            "defaultMode": "once" if args.cycles <= 1 else "bounded_worker",
            "maxCyclesGuard": args.max_cycles,
            "endpoint": args.endpoint,
            "inputRadar": args.input_radar or "",
        },
        "source": {
            "scanner": "Gamma API active events via Radar V1",
            "publicReadOnly": True,
            "loadsEnv": False,
            "readsPrivateKey": False,
            "walletWrite": False,
            "orderExecution": False,
            "mutatesMt5": False,
        },
        "safety": {
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "canStartExecutor": False,
            "canMutateMt5": False,
            "reason": "Worker V2 only refreshes public-market evidence and shadow analysis queue.",
        },
        "summary": {
            "marketsScanned": latest_summary.get("rankedMarkets", len(deduped_rows)),
            "uniqueMarkets": len(deduped_rows),
            "duplicateMarkets": duplicate_count,
            "candidateQueueSize": len(queue),
            "topScore": top.get("aiRuleScore"),
            "topMarket": top.get("question", ""),
            "topRisk": top.get("risk", ""),
            **trend_counts,
        },
        "trend": {
            "cacheFile": TREND_CACHE_NAME,
            "cacheSource": cache_source,
            "summary": trend_cache.get("summary", {}),
        },
        "candidateQueue": queue,
        "latestRadar": deduped_rows[:20],
        "cycles": cycles,
        "nextActions": [
            "Feed queued candidates into single-market analysis and AI score review; keep wallet execution disabled.",
            "Use trend deltas to decide which markets deserve repeated observation or retune planning.",
            "A future long-running scheduler may invoke this with bounded cycles; default invocation stays one-shot and safe.",
        ],
    }


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    cycles_requested = max(1, min(args.cycles, args.max_cycles))
    run_id = "POLYRADARV2-" + utc_now().strftime("%Y%m%d-%H%M%S") + "-" + stable_hash(args.endpoint, args.limit, args.top, length=6)
    started_at = utc_now_iso()
    previous_cache, cache_source = load_trend_cache(runtime_dir, dashboard_dir)

    cycles: list[dict[str, Any]] = []
    latest_radar: dict[str, Any] = {}
    deduped_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    trend_cache: dict[str, Any] = {}
    trend_counts: dict[str, int] = {
        "newMarkets": 0,
        "recurringMarkets": 0,
        "scoreImproved": 0,
        "scoreDeteriorated": 0,
        "probabilityMovedUp": 0,
        "probabilityMovedDown": 0,
        "staleTracked": 0,
    }
    queue: list[dict[str, Any]] = []

    for cycle_index in range(1, cycles_requested + 1):
        cycle_started = utc_now_iso()
        try:
            latest_radar = build_gamma_snapshot(args)
            rows = latest_radar.get("radar") if isinstance(latest_radar.get("radar"), list) else []
            deduped_rows, duplicate_count = dedupe_rows([row for row in rows if isinstance(row, dict)])
            generated_at = str(latest_radar.get("generatedAt") or utc_now_iso())
            trend_cache, trend_counts = update_trend_cache(
                previous_cache,
                deduped_rows,
                generated_at,
                run_id,
                args.stale_retention_cycles,
            )
            previous_cache = trend_cache
            queue = build_candidate_queue(deduped_rows, args, generated_at, run_id)
            latest_radar = dict(latest_radar)
            latest_radar["mode"] = "POLYMARKET_OPPORTUNITY_RADAR_V1_WITH_WORKER_V2_TRENDS"
            latest_radar["radar"] = deduped_rows[: max(1, args.top)]
            latest_radar["workerV2"] = {
                "runId": run_id,
                "cycle": cycle_index,
                "candidateQueueSize": len(queue),
                "duplicateMarkets": duplicate_count,
                "trendSummary": trend_counts,
            }
            if latest_radar.get("summary"):
                latest_radar["summary"] = {
                    **latest_radar.get("summary", {}),
                    "rankedMarkets": len(latest_radar["radar"]),
                    "candidateQueueSize": len(queue),
                    "duplicateMarkets": duplicate_count,
                }
            write_radar_v1_outputs(latest_radar, runtime_dir, dashboard_dir)
            cycles.append(
                {
                    "cycle": cycle_index,
                    "startedAt": cycle_started,
                    "finishedAt": utc_now_iso(),
                    "status": latest_radar.get("status", "OK"),
                    "rankedMarkets": len(deduped_rows),
                    "candidateQueueSize": len(queue),
                    "topMarket": deduped_rows[0].get("question", "") if deduped_rows else "",
                    "error": latest_radar.get("error", ""),
                }
            )
        except Exception as exc:  # noqa: BLE001 - worker must emit a diagnostic snapshot.
            cycles.append(
                {
                    "cycle": cycle_index,
                    "startedAt": cycle_started,
                    "finishedAt": utc_now_iso(),
                    "status": "ERROR",
                    "rankedMarkets": 0,
                    "candidateQueueSize": 0,
                    "topMarket": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if cycle_index < cycles_requested:
            time.sleep(max(0.0, args.interval_seconds))

    finished_at = utc_now_iso()
    worker = build_worker_snapshot(
        args,
        run_id,
        started_at,
        finished_at,
        cycles,
        latest_radar,
        deduped_rows,
        duplicate_count,
        trend_cache,
        trend_counts,
        queue,
        cache_source,
    )
    queue_payload = queue_json(queue, finished_at, run_id)
    files = {
        WORKER_NAME: json.dumps(worker, ensure_ascii=False, indent=2, sort_keys=True),
        WORKER_LEDGER_NAME: worker_csv(worker),
        TREND_CACHE_NAME: json.dumps(trend_cache, ensure_ascii=False, indent=2, sort_keys=True),
        CANDIDATE_QUEUE_NAME: json.dumps(queue_payload, ensure_ascii=False, indent=2, sort_keys=True),
        CANDIDATE_QUEUE_LEDGER_NAME: queue_csv(queue),
    }
    written = write_text_outputs(files, runtime_dir, dashboard_dir)
    summary = worker.get("summary", {})
    print(
        "POLYMARKET_RADAR_WORKER_V2 "
        f"| status={worker.get('status')} | cycles={len(cycles)}/{cycles_requested} "
        f"| unique={summary.get('uniqueMarkets', 0)} | queue={summary.get('candidateQueueSize', 0)} "
        f"| wrote={len(written)} | wallet=false | orders=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
