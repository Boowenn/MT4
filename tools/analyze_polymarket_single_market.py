#!/usr/bin/env python3
"""Analyze one Polymarket market with a read-only AI/rule proxy.

This entrypoint is intentionally research-only. It reads a user supplied
Polymarket URL/title/market id, or falls back to the latest radar candidate,
then writes a dashboard snapshot and an analysis ledger. It never imports the
local Polymarket runtime, never reads wallet secrets, never places orders, and
never mutates MT5 state.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_polymarket_market_radar import (
    DEFAULT_ENDPOINT,
    atomic_write_text,
    enrich_clob_depth,
    flatten_event,
    request_gamma_events,
    safe_number,
)
from polymarket_quantdinger_core import infer_related_assets


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
REQUEST_NAME = "QuantGod_PolymarketSingleMarketRequest.json"
RADAR_NAME = "QuantGod_PolymarketMarketRadar.json"
OUTPUT_NAME = "QuantGod_PolymarketSingleMarketAnalysis.json"
LEDGER_NAME = "QuantGod_PolymarketSingleMarketAnalysisLedger.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--request-path", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--min-volume", type=float, default=5000.0)
    parser.add_argument("--min-liquidity", type=float, default=1000.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-clob-depth", action="store_true")
    parser.add_argument("--clob-timeout", type=float, default=4.0)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def request_candidate_paths(args: argparse.Namespace, runtime_dir: Path, dashboard_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if args.request_path:
        paths.append(Path(args.request_path))
    if dashboard_dir is not None:
        paths.append(dashboard_dir / REQUEST_NAME)
    paths.append(runtime_dir / REQUEST_NAME)
    return paths


def query_from_request(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
    return first_text(
        payload.get("query"),
        payload.get("url"),
        payload.get("marketUrl"),
        payload.get("polymarketUrl"),
        payload.get("marketId"),
        payload.get("slug"),
        payload.get("title"),
        payload.get("question"),
        market.get("polymarketUrl"),
        market.get("marketId"),
        market.get("slug"),
        market.get("question"),
    )


def load_request_query(args: argparse.Namespace, runtime_dir: Path, dashboard_dir: Path | None) -> tuple[str, str]:
    if args.query.strip():
        return args.query.strip(), "cli_query"
    for path in request_candidate_paths(args, runtime_dir, dashboard_dir):
        query = query_from_request(load_json(path))
        if query:
            return query, str(path)
    radar = load_json(runtime_dir / RADAR_NAME)
    if not radar and dashboard_dir is not None:
        radar = load_json(dashboard_dir / RADAR_NAME)
    if isinstance(radar, dict):
        rows = radar.get("radar")
        if isinstance(rows, list) and rows:
            first = rows[0] if isinstance(rows[0], dict) else {}
            return first_text(first.get("polymarketUrl"), first.get("marketId"), first.get("question")), "latest_market_radar_top"
    return "", "none"


def url_target_parts(query: str) -> dict[str, Any]:
    text = str(query or "").strip()
    parts: dict[str, Any] = {"raw": text, "isUrl": False, "marketId": "", "slug": "", "tokens": []}
    if not text:
        return parts
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme and parsed.netloc:
        parts["isUrl"] = True
        path_bits = [urllib.parse.unquote(bit) for bit in parsed.path.split("/") if bit]
        lowered = [bit.lower() for bit in path_bits]
        for marker in ("event", "market"):
            if marker in lowered:
                idx = lowered.index(marker)
                if idx + 1 < len(path_bits):
                    parts["slug"] = path_bits[idx + 1]
                    break
        if not parts["slug"] and path_bits:
            parts["slug"] = path_bits[-1]
        query_bits = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        parts["marketId"] = first_text(query_bits.get("market"), query_bits.get("marketId"), query_bits.get("id"), query_bits.get("tid"))
        text = " ".join([parts["slug"], parts["marketId"]])
    elif re.fullmatch(r"\d+", text):
        parts["marketId"] = text
    elif "/" not in text and len(text) > 8 and re.fullmatch(r"[A-Za-z0-9_-]+", text):
        parts["slug"] = text
    parts["tokens"] = [token for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", text.lower()) if len(token) >= 2][:24]
    return parts


def row_search_text(row: dict[str, Any]) -> str:
    values = [
        row.get("marketId"),
        row.get("eventId"),
        row.get("question"),
        row.get("eventTitle"),
        row.get("slug"),
        row.get("polymarketUrl"),
        row.get("category"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def match_score(row: dict[str, Any], target: dict[str, Any]) -> int:
    if not row:
        return 0
    search = row_search_text(row)
    market_id = str(target.get("marketId") or "").lower()
    slug = str(target.get("slug") or "").lower()
    raw = str(target.get("raw") or "").lower()
    if market_id and market_id in {str(row.get("marketId") or "").lower(), str(row.get("eventId") or "").lower()}:
        return 120
    if slug and slug == str(row.get("slug") or "").lower():
        return 110
    if slug and slug in search:
        return 95
    if raw and raw in search:
        return 80
    tokens = [str(token) for token in target.get("tokens") or []]
    if not tokens:
        return 0
    hits = sum(1 for token in tokens if token in search)
    return min(70, hits * 10) if hits else 0


def fetch_and_rank_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    events = request_gamma_events(args.endpoint, args.limit, args.timeout)
    rows: list[dict[str, Any]] = []
    for event in events:
        rows.extend(flatten_event(event, args.min_volume, args.min_liquidity))
    rows.sort(
        key=lambda item: (
            safe_number(item.get("aiRuleScore")),
            safe_number(item.get("liquidity")),
            safe_number(item.get("volume24h")),
        ),
        reverse=True,
    )
    return rows


def choose_market(rows: list[dict[str, Any]], query: str) -> tuple[dict[str, Any] | None, int]:
    target = url_target_parts(query)
    scored = [(match_score(row, target), row) for row in rows]
    scored = [(score, row) for score, row in scored if score > 0]
    if scored:
        scored.sort(
            key=lambda pair: (
                pair[0],
                safe_number(pair[1].get("aiRuleScore")),
                safe_number(pair[1].get("liquidity")),
            ),
            reverse=True,
        )
        return scored[0][1], scored[0][0]
    return (rows[0], 0) if rows else (None, 0)


def enrich_selected_market(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    selected = dict(row)
    enrich_clob_depth([selected], limit=1, timeout=max(1.0, float(args.clob_timeout or 4.0)), skip=bool(args.skip_clob_depth))
    return selected


def ai_probability_proxy(row: dict[str, Any]) -> tuple[float | None, float | None, float]:
    probability_raw = row.get("probability")
    if probability_raw is None or probability_raw == "":
        return None, None, 0.0
    market_probability = safe_number(probability_raw, default=50.0)
    score = safe_number(row.get("aiRuleScore"), default=0.0)
    risk = str(row.get("risk") or "medium")
    risk_factor = {"low": 1.0, "medium": 0.55, "high": 0.18}.get(risk, 0.4)
    depth_bonus = max(0.0, safe_number(row.get("clobDepthScore"), 0.0) - 50.0) / 100.0
    direction = 1.0 if market_probability >= 50.0 else -1.0
    neutral_gap = abs(market_probability - 50.0)
    score_component = max(0.0, score - 35.0) / 65.0
    adjustment = min(14.0, neutral_gap * 0.18 + score_component * 8.0 + depth_bonus * 2.5) * risk_factor * direction
    ai_probability = clamp(market_probability + adjustment, 1.0, 99.0)
    divergence = ai_probability - market_probability
    confidence = clamp(
        score * 0.68
        + safe_number(row.get("liquidity")) ** 0.12
        + safe_number(row.get("volume")) ** 0.08
        + safe_number(row.get("clobDepthScore")) * 0.08
    )
    return round(ai_probability, 2), round(divergence, 2), round(confidence, 1)


def recommendation_for(row: dict[str, Any], divergence: float | None, confidence: float) -> str:
    risk = str(row.get("risk") or "medium")
    score = safe_number(row.get("aiRuleScore"), default=0.0)
    abs_divergence = abs(divergence or 0.0)
    if risk == "high":
        return "AVOID_OR_OBSERVE"
    if abs_divergence < 2.0:
        return "OBSERVE_ONLY"
    if risk == "low" and score >= 65 and confidence >= 45:
        return "SHADOW_REVIEW_HIGH_PRIORITY"
    if score >= 42:
        return "SHADOW_REVIEW"
    return "NO_TRADE"


def risk_factor_notes(row: dict[str, Any]) -> list[str]:
    flags = [str(item) for item in (row.get("riskFlags") or [])]
    notes: list[str] = []
    if not flags:
        notes.append("Gamma 公共数据暂无硬性风险标记。")
    else:
        notes.extend([f"风险标记：{flag}" for flag in flags[:8]])
    if safe_number(row.get("liquidity")) <= 0:
        notes.append("流动性未知或为 0，只能保留为研究候选。")
    if row.get("acceptingOrders") is False:
        notes.append("市场当前不接受订单，只能保留研究记录。")
    if row.get("clobStatus"):
        notes.append(
            f"CLOB 公共盘口：{row.get('clobStatus')}，spread={row.get('clobSpread', '--')}，深度评分={row.get('clobDepthScore', '--')}。"
        )
    return notes


def build_key_factors(selected: dict[str, Any], related_assets: list[dict[str, Any]]) -> list[str]:
    factors = [
        f"市场概率 {selected.get('probability', '--')}%，雷达评分 {selected.get('aiRuleScore', '--')}。",
        f"成交量 {selected.get('volume', '--')}，24h 成交 {selected.get('volume24h', '--')}，Gamma 流动性 {selected.get('liquidity', '--')}。",
    ]
    if selected.get("clobStatus"):
        factors.append(
            f"CLOB YES 盘口 {selected.get('clobStatus')}，bid/ask {selected.get('clobBestBid', '--')}/{selected.get('clobBestAsk', '--')}，深度 ${selected.get('clobLiquidityUsd', '--')}。"
        )
    if related_assets:
        factors.append("关联资产：" + "、".join(item.get("symbol", "") for item in related_assets[:6] if item.get("symbol")))
    return factors


def build_market_payload(selected: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "marketId",
        "eventId",
        "question",
        "eventTitle",
        "slug",
        "polymarketUrl",
        "category",
        "probability",
        "probabilitySource",
        "yesTokenId",
        "noTokenId",
        "yesPrice",
        "noPrice",
        "volume",
        "volume24h",
        "liquidity",
        "spread",
        "clobStatus",
        "clobBestBid",
        "clobBestAsk",
        "clobMidpoint",
        "clobSpread",
        "clobLiquidityUsd",
        "clobDepthScore",
        "endDate",
        "acceptingOrders",
    ]
    return {field: selected.get(field, "") for field in fields}


def build_analysis(args: argparse.Namespace, runtime_dir: Path, dashboard_dir: Path | None) -> dict[str, Any]:
    generated_at = utc_now_iso()
    query, query_source = load_request_query(args, runtime_dir, dashboard_dir)
    safety = {
        "publicGammaReadOnly": True,
        "publicClobReadOnly": not bool(args.skip_clob_depth),
        "loadsEnv": False,
        "readsPrivateKey": False,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "startsExecutor": False,
        "mutatesMt5": False,
    }
    base_mode = "POLYMARKET_SINGLE_MARKET_AI_ANALYSIS_V2"
    decision = "RESEARCH_ONLY_SINGLE_MARKET_NO_BETTING"
    if not query:
        return {
            "mode": base_mode,
            "generatedAt": generated_at,
            "status": "NO_TARGET",
            "decision": decision,
            "request": {"query": "", "source": query_source},
            "summary": {"market": "", "recommendation": "NO_TARGET", "risk": "unknown", "confidencePct": 0},
            "market": {},
            "analysis": {
                "recommendation": "NO_TARGET",
                "rationale": ["请在 Dashboard 单市场输入框提交 URL、标题或 marketId，或先生成机会雷达。"],
            },
            "safety": safety,
        }
    try:
        rows = fetch_and_rank_rows(args)
        selected, match = choose_market(rows, query)
        if not selected:
            raise RuntimeError("Gamma API returned no active markets to analyze.")
        selected = enrich_selected_market(selected, args)
        related_assets = infer_related_assets(selected)
        ai_probability, divergence, confidence = ai_probability_proxy(selected)
        recommendation = recommendation_for(selected, divergence, confidence)
        probability = selected.get("probability")
        analysis = {
            "aiScoringMode": "RULE_PROXY_PLUS_PUBLIC_CLOB_AND_RELATED_ASSETS",
            "marketProbabilityPct": probability,
            "aiProbabilityPct": ai_probability,
            "divergencePct": divergence,
            "confidencePct": confidence,
            "recommendation": recommendation,
            "riskLevel": selected.get("risk", "unknown"),
            "riskFactors": selected.get("riskFlags") or [],
            "relatedAssets": related_assets,
            "suggestedShadowTrack": selected.get("suggestedShadowTrack") or "poly_single_market_shadow_review_v1",
            "keyFactors": build_key_factors(selected, related_assets),
            "rationale": [
                "这是 Gamma API + 公共 CLOB 盘口的单市场研究分析，不是下注信号。",
                f"AI/规则代理概率 {ai_probability if ai_probability is not None else '--'}%，市场概率 {probability if probability is not None else '--'}%。",
                "所有输出只能进入 shadow track / retune planner；执行层仍由独立 Gate、dry-run 和钱包守卫决定。",
            ],
            "riskNotes": risk_factor_notes(selected),
            "nextActions": [
                "若 recommendation 不是 SHADOW_REVIEW，继续观察或重调筛选，不进入 dry-run。",
                "若后续要模拟订单，先让 Execution Gate 和 dry-run simulator 读取这条 shadow track。",
                "不要从单市场分析直接恢复下注执行。",
            ],
        }
        market = build_market_payload(selected)
        return {
            "mode": base_mode,
            "generatedAt": generated_at,
            "status": "OK",
            "decision": decision,
            "request": {
                "query": query,
                "source": query_source,
                "matchScore": match,
                "fallbackUsed": match == 0,
            },
            "summary": {
                "market": market.get("question") or market.get("slug") or market.get("marketId"),
                "recommendation": recommendation,
                "risk": analysis["riskLevel"],
                "confidencePct": confidence,
                "divergencePct": divergence,
                "suggestedShadowTrack": analysis["suggestedShadowTrack"],
                "clobStatus": market.get("clobStatus"),
                "relatedAssets": [item.get("symbol") for item in related_assets[:8]],
            },
            "market": market,
            "analysis": analysis,
            "safety": safety,
        }
    except Exception as exc:  # noqa: BLE001 - keep dashboard diagnostic instead of failing silently.
        return {
            "mode": base_mode,
            "generatedAt": generated_at,
            "status": "ERROR",
            "decision": decision,
            "request": {"query": query, "source": query_source},
            "summary": {"market": "", "recommendation": "ERROR", "risk": "unknown", "confidencePct": 0},
            "market": {},
            "analysis": {
                "recommendation": "ERROR",
                "rationale": ["单市场分析失败；保持不下注。"],
            },
            "error": f"{type(exc).__name__}: {exc}",
            "safety": safety,
        }


def ledger_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    analysis = snapshot.get("analysis") if isinstance(snapshot.get("analysis"), dict) else {}
    request = snapshot.get("request") if isinstance(snapshot.get("request"), dict) else {}
    return {
        "generated_at": snapshot.get("generatedAt", ""),
        "mode": snapshot.get("mode", ""),
        "status": snapshot.get("status", ""),
        "query": request.get("query", ""),
        "query_source": request.get("source", ""),
        "market_id": market.get("marketId", ""),
        "question": market.get("question", ""),
        "category": market.get("category", ""),
        "market_probability": analysis.get("marketProbabilityPct", ""),
        "ai_probability": analysis.get("aiProbabilityPct", ""),
        "divergence": analysis.get("divergencePct", ""),
        "confidence": analysis.get("confidencePct", ""),
        "recommendation": analysis.get("recommendation", ""),
        "risk": analysis.get("riskLevel", ""),
        "shadow_track": analysis.get("suggestedShadowTrack", ""),
        "clob_status": market.get("clobStatus", ""),
        "clob_spread": market.get("clobSpread", ""),
        "clob_depth_score": market.get("clobDepthScore", ""),
        "related_assets": ";".join(item.get("symbol", "") for item in analysis.get("relatedAssets", []) if isinstance(item, dict)),
        "url": market.get("polymarketUrl", ""),
        "wallet_write": snapshot.get("safety", {}).get("walletWriteAllowed", False),
        "order_send": snapshot.get("safety", {}).get("orderSendAllowed", False),
    }


def append_ledger(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    row = ledger_row(snapshot)
    written: list[str] = []
    for base_dir in [runtime_dir, dashboard_dir]:
        if base_dir is None:
            continue
        json_path = base_dir / OUTPUT_NAME
        ledger_path = base_dir / LEDGER_NAME
        atomic_write_text(json_path, json_text)
        append_ledger(ledger_path, row)
        written.extend([str(json_path), str(ledger_path)])
    return written


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if str(args.dashboard_dir or "").strip() else None
    snapshot = build_analysis(args, runtime_dir, dashboard_dir)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot.get("summary", {})
    print(
        "Polymarket single market analysis "
        f"{snapshot.get('status')} | rec={summary.get('recommendation', '--')} "
        f"| risk={summary.get('risk', '--')} | market={summary.get('market') or '--'} "
        f"| outputs={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
