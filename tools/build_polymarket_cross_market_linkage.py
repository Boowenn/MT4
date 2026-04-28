#!/usr/bin/env python3
"""Build read-only cross-market linkage evidence for Polymarket research.

This tool maps Polymarket market text into macro/FX/metal/geopolitical risk
tags so QuantGod can reason about cross-market awareness without touching MT5
execution or Polymarket wallet code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
OUTPUT_NAME = "QuantGod_PolymarketCrossMarketLinkage.json"
LEDGER_NAME = "QuantGod_PolymarketCrossMarketLinkage.csv"

RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
RADAR_WORKER_NAME = "QuantGod_PolymarketRadarWorkerV2.json"
RADAR_TREND_CACHE_NAME = "QuantGod_PolymarketRadarTrendCache.json"
RADAR_QUEUE_NAME = "QuantGod_PolymarketRadarCandidateQueue.json"
SINGLE_NAME = "QuantGod_PolymarketSingleMarketAnalysis.json"
AI_SCORE_NAME = "QuantGod_PolymarketAiScoreV1.json"

RISK_TAGS: dict[str, dict[str, Any]] = {
    "USD": {
        "label": "美元 / USD",
        "mt5Symbols": ["USDJPYc", "EURUSDc", "XAUUSDc"],
        "keywords": [
            "dollar", "usd", "us dollar", "federal reserve", "fomc", "fed ",
            "treasury", "us treasury", "united states", "u.s.", "america",
            "trump", "biden", "congress", "senate", "white house", "tariff",
        ],
    },
    "JPY": {
        "label": "日元 / JPY",
        "mt5Symbols": ["USDJPYc"],
        "keywords": [
            "japan", "japanese", "yen", "jpy", "boj", "bank of japan",
            "tokyo", "nikkei", "ishiba", "ueda",
        ],
    },
    "XAU": {
        "label": "黄金 / XAU",
        "mt5Symbols": ["XAUUSDc"],
        "keywords": [
            "gold", "xau", "precious metal", "safe haven", "inflation",
            "war", "missile", "nuclear", "geopolitical", "iran", "israel",
            "russia", "ukraine", "china", "taiwan",
        ],
    },
    "RATES": {
        "label": "利率 / Rates",
        "mt5Symbols": ["USDJPYc", "EURUSDc", "XAUUSDc"],
        "keywords": [
            "interest rate", "rates", "rate cut", "rate hike", "fed",
            "fomc", "cpi", "inflation", "pce", "jobs report",
            "unemployment", "treasury", "yield", "bond", "central bank",
            "ecb", "boj",
        ],
    },
    "WAR_GEOPOLITICS": {
        "label": "战争 / 地缘",
        "mt5Symbols": ["XAUUSDc", "USDJPYc"],
        "keywords": [
            "war", "ceasefire", "missile", "strike", "invasion", "nato",
            "russia", "ukraine", "sumy", "crimea", "israel", "gaza",
            "hamas", "iran", "china", "taiwan", "north korea", "korea",
            "red sea", "houthi", "military", "nuclear", "sanction",
        ],
    },
    "MACRO_RISK": {
        "label": "宏观风险",
        "mt5Symbols": ["USDJPYc", "EURUSDc", "XAUUSDc"],
        "keywords": [
            "recession", "gdp", "inflation", "deflation", "cpi", "pce",
            "unemployment", "jobs", "payroll", "oil", "opec", "tariff",
            "election", "politics", "stock market", "s&p", "nasdaq",
            "bank crisis", "default", "debt ceiling", "shutdown",
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--top", type=int, default=40)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def read_json_candidate(name: str, runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    for path in (dashboard_dir / name, runtime_dir / name):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8").replace("\ufeff", ""))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload, str(path)
    return {}, ""


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def stable_id(*parts: Any, length: int = 20) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]


def clean_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts if part not in (None, "")).strip()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower())


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    haystack = normalize_text(text)
    found: list[str] = []
    for keyword in keywords:
        key = keyword.lower().strip()
        if not key:
            continue
        if key.endswith(" "):
            if key in haystack and keyword.strip() not in found:
                found.append(keyword.strip())
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack):
            found.append(keyword)
    return found


def market_key(item: dict[str, Any]) -> str:
    for key in ("marketId", "market_id", "polymarketUrl", "url", "question", "title"):
        value = str(item.get(key) or "").strip().lower()
        if value:
            return value
    return stable_id(json.dumps(item, ensure_ascii=False, sort_keys=True))


def add_market(markets: dict[str, dict[str, Any]], item: dict[str, Any], source_type: str, generated_at: str = "") -> None:
    question = clean_text(item.get("question"), item.get("title"), item.get("query"))
    if not question and not item.get("marketId"):
        return
    key = market_key(item)
    current = markets.get(key)
    if current is None:
        current = {
            "marketId": str(item.get("marketId") or item.get("market_id") or ""),
            "eventId": str(item.get("eventId") or item.get("event_id") or ""),
            "question": question,
            "eventTitle": str(item.get("eventTitle") or item.get("event_title") or ""),
            "category": str(item.get("category") or ""),
            "polymarketUrl": str(item.get("polymarketUrl") or item.get("url") or ""),
            "probability": safe_number(item.get("probability", item.get("marketProbability")), 0.0),
            "risk": str(item.get("risk") or ""),
            "score": safe_number(item.get("priorityScore", item.get("aiRuleScore", item.get("score"))), 0.0),
            "suggestedShadowTrack": str(item.get("suggestedShadowTrack") or item.get("track") or ""),
            "generatedAt": str(item.get("generatedAt") or item.get("seenAt") or generated_at),
            "sourceTypes": [],
            "rawSources": [],
        }
        markets[key] = current
    else:
        current["score"] = max(safe_number(current.get("score")), safe_number(item.get("priorityScore", item.get("aiRuleScore", item.get("score")))))
        current["probability"] = current.get("probability") or safe_number(item.get("probability", item.get("marketProbability")), 0.0)
        current["risk"] = current.get("risk") or str(item.get("risk") or "")
        current["suggestedShadowTrack"] = current.get("suggestedShadowTrack") or str(item.get("suggestedShadowTrack") or item.get("track") or "")
        current["category"] = current.get("category") or str(item.get("category") or "")
        current["polymarketUrl"] = current.get("polymarketUrl") or str(item.get("polymarketUrl") or item.get("url") or "")

    if source_type not in current["sourceTypes"]:
        current["sourceTypes"].append(source_type)
    current["rawSources"].append(
        {
            "sourceType": source_type,
            "generatedAt": str(item.get("generatedAt") or item.get("seenAt") or generated_at),
            "candidateId": item.get("candidateId"),
            "runId": item.get("runId"),
            "trendDirection": item.get("trendDirection"),
            "queueState": item.get("queueState"),
        }
    )


def collect_markets(payloads: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    markets: dict[str, dict[str, Any]] = {}
    radar = payloads.get(RADAR_NAME, {})
    for item in radar.get("radar") if isinstance(radar.get("radar"), list) else []:
        if isinstance(item, dict):
            add_market(markets, item, "radar", str(radar.get("generatedAt") or ""))

    worker = payloads.get(RADAR_WORKER_NAME, {})
    for item in worker.get("candidateQueue") if isinstance(worker.get("candidateQueue"), list) else []:
        if isinstance(item, dict):
            add_market(markets, item, "worker-queue", str(worker.get("generatedAt") or ""))

    trend_cache = payloads.get(RADAR_TREND_CACHE_NAME, {})
    trend_markets = trend_cache.get("markets") if isinstance(trend_cache.get("markets"), dict) else {}
    for item in trend_markets.values():
        if isinstance(item, dict):
            add_market(markets, item, "worker-trend", str(trend_cache.get("updatedAt") or ""))

    queue = payloads.get(RADAR_QUEUE_NAME, {})
    for item in queue.get("candidateQueue") if isinstance(queue.get("candidateQueue"), list) else []:
        if isinstance(item, dict):
            add_market(markets, item, "candidate-queue", str(queue.get("generatedAt") or ""))

    single = payloads.get(SINGLE_NAME, {})
    if single:
        market = single.get("market") if isinstance(single.get("market"), dict) else {}
        analysis = single.get("analysis") if isinstance(single.get("analysis"), dict) else {}
        add_market(
            markets,
            {
                "marketId": market.get("marketId"),
                "question": market.get("question"),
                "eventTitle": market.get("eventTitle"),
                "category": market.get("category"),
                "polymarketUrl": market.get("polymarketUrl"),
                "probability": analysis.get("marketProbabilityPct") or market.get("probability"),
                "risk": analysis.get("riskLevel"),
                "score": analysis.get("confidencePct"),
                "suggestedShadowTrack": analysis.get("suggestedShadowTrack"),
                "generatedAt": single.get("generatedAt"),
            },
            "single-analysis",
            str(single.get("generatedAt") or ""),
        )

    ai_score = payloads.get(AI_SCORE_NAME, {})
    for item in ai_score.get("scores") if isinstance(ai_score.get("scores"), list) else []:
        if isinstance(item, dict):
            add_market(markets, item, "ai-score", str(ai_score.get("generatedAt") or ""))
    return markets


def infer_category_tags(category: str) -> list[str]:
    normalized = category.lower()
    if normalized == "macro_finance":
        return ["USD", "RATES", "MACRO_RISK"]
    if normalized == "crypto":
        return ["USD", "MACRO_RISK"]
    if normalized == "politics":
        return ["USD", "MACRO_RISK"]
    return []


def build_linkage_row(item: dict[str, Any], generated_at: str) -> dict[str, Any] | None:
    text = clean_text(
        item.get("question"),
        item.get("eventTitle"),
        item.get("category"),
        item.get("suggestedShadowTrack"),
    )
    matches: dict[str, list[str]] = {}
    for tag, meta in RISK_TAGS.items():
        found = match_keywords(text, meta["keywords"])
        if found:
            matches[tag] = found
    for tag in infer_category_tags(str(item.get("category") or "")):
        matches.setdefault(tag, ["category"])
    if not matches:
        return None

    linked_symbols = sorted({symbol for tag in matches for symbol in RISK_TAGS[tag]["mt5Symbols"]})
    high_tags = {"WAR_GEOPOLITICS", "RATES", "MACRO_RISK"}
    risk_state = "high" if "WAR_GEOPOLITICS" in matches else ("medium" if high_tags.intersection(matches) else "watch")
    if str(item.get("risk") or "").lower() == "high":
        risk_state = "high"

    confidence = min(
        100.0,
        25.0
        + len(matches) * 12.0
        + min(20.0, len(linked_symbols) * 4.0)
        + min(20.0, safe_number(item.get("score"), 0.0) * 0.18),
    )
    linkage_id = stable_id(item.get("marketId"), item.get("question"), ",".join(sorted(matches)))
    primary_tag = sorted(matches.keys(), key=lambda tag: (tag != "WAR_GEOPOLITICS", tag != "RATES", tag))[0]
    return {
        "linkageId": linkage_id,
        "generatedAt": generated_at,
        "marketId": item.get("marketId") or "",
        "eventId": item.get("eventId") or "",
        "question": item.get("question") or "",
        "eventTitle": item.get("eventTitle") or "",
        "category": item.get("category") or "",
        "polymarketUrl": item.get("polymarketUrl") or "",
        "riskTags": sorted(matches.keys()),
        "primaryRiskTag": primary_tag,
        "matchedKeywords": matches,
        "linkedMt5Symbols": linked_symbols,
        "macroRiskState": risk_state,
        "confidence": round(confidence, 2),
        "probability": item.get("probability") or 0.0,
        "sourceScore": item.get("score") or 0.0,
        "sourceRisk": item.get("risk") or "",
        "sourceTypes": item.get("sourceTypes") or [],
        "suggestedShadowTrack": item.get("suggestedShadowTrack") or "",
        "awarenessOnly": True,
        "mt5ExecutionAllowed": False,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "rawSources": item.get("rawSources") or [],
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    generated_at = utc_now_iso()
    payloads: dict[str, dict[str, Any]] = {}
    source_files: dict[str, str] = {}
    for name in (RADAR_NAME, RADAR_WORKER_NAME, RADAR_TREND_CACHE_NAME, RADAR_QUEUE_NAME, SINGLE_NAME, AI_SCORE_NAME):
        payload, path = read_json_candidate(name, runtime_dir, dashboard_dir)
        payloads[name] = payload
        source_files[name] = path
    markets = collect_markets(payloads)
    rows = [row for item in markets.values() if (row := build_linkage_row(item, generated_at))]
    rows.sort(key=lambda row: (safe_number(row.get("confidence")), safe_number(row.get("sourceScore"))), reverse=True)
    rows = rows[: max(1, args.top)]
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    tag_counts = {tag: sum(1 for row in rows if tag in row.get("riskTags", [])) for tag in RISK_TAGS}
    symbol_counts: dict[str, int] = {}
    for row in rows:
        for symbol in row.get("linkedMt5Symbols", []):
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    top_row = rows[0] if rows else {}
    return {
        "mode": "POLYMARKET_CROSS_MARKET_LINKAGE_V1",
        "generatedAt": generated_at,
        "status": "OK",
        "decision": "AWARENESS_ONLY_NO_MT5_EXECUTION_NO_BETTING",
        "sourceFiles": source_files,
        "summary": {
            "inputMarkets": len(markets),
            "linkedMarkets": len(rows),
            "tagCounts": tag_counts,
            "linkedSymbolCounts": symbol_counts,
            "topMarket": top_row.get("question", ""),
            "topTags": top_row.get("riskTags", []),
            "topConfidence": top_row.get("confidence"),
        },
        "riskCatalog": {
            tag: {
                "label": meta["label"],
                "mt5Symbols": meta["mt5Symbols"],
                "keywordCount": len(meta["keywords"]),
            }
            for tag, meta in RISK_TAGS.items()
        },
        "linkages": rows,
        "safety": {
            "readsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "mt5ExecutionAllowed": False,
            "boundary": "Polymarket events may only produce cross-market awareness tags; they cannot change MT5 trading permissions.",
        },
        "nextActions": [
            "Use linked tags as dashboard evidence for USD/JPY/XAU/rates/geopolitical awareness only.",
            "Do not use a cross-market tag to open MT5 trades or Polymarket bets.",
            "If execution is ever considered, route through separate governance, dry-run outcomes, budget, and kill-switch gates.",
        ],
    }


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path) -> list[str]:
    written: list[str] = []
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    fieldnames = [
        "rank",
        "generated_at",
        "linkage_id",
        "market_id",
        "question",
        "category",
        "primary_risk_tag",
        "risk_tags",
        "linked_mt5_symbols",
        "macro_risk_state",
        "confidence",
        "probability",
        "source_score",
        "source_types",
        "wallet_write_allowed",
        "order_send_allowed",
        "mt5_execution_allowed",
    ]
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in snapshot.get("linkages", []):
        writer.writerow(
            {
                "rank": row.get("rank"),
                "generated_at": row.get("generatedAt"),
                "linkage_id": row.get("linkageId"),
                "market_id": row.get("marketId"),
                "question": row.get("question"),
                "category": row.get("category"),
                "primary_risk_tag": row.get("primaryRiskTag"),
                "risk_tags": "|".join(row.get("riskTags", [])),
                "linked_mt5_symbols": "|".join(row.get("linkedMt5Symbols", [])),
                "macro_risk_state": row.get("macroRiskState"),
                "confidence": row.get("confidence"),
                "probability": row.get("probability"),
                "source_score": row.get("sourceScore"),
                "source_types": "|".join(row.get("sourceTypes", [])),
                "wallet_write_allowed": "false",
                "order_send_allowed": "false",
                "mt5_execution_allowed": "false",
            }
        )
    for base in (runtime_dir, dashboard_dir):
        if not base:
            continue
        atomic_write_text(base / OUTPUT_NAME, json_text)
        atomic_write_text(base / LEDGER_NAME, csv_buffer.getvalue())
        written.extend([str(base / OUTPUT_NAME), str(base / LEDGER_NAME)])
    return written


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, Path(args.runtime_dir), Path(args.dashboard_dir))
    print(
        f"{snapshot['mode']} | linked={snapshot['summary']['linkedMarkets']} "
        f"| input={snapshot['summary']['inputMarkets']} | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
