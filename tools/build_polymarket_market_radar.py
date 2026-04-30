#!/usr/bin/env python3
"""Build a public read-only Polymarket opportunity radar for QuantGod.

This scanner only calls the public Gamma API. It does not import the local
Polymarket runtime, load wallet secrets, place orders, or mutate MT5 state.
The output is intended to seed shadow-only research tracks and governance
review before any future execution module is considered.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polymarket_clob_public import (
    fetch_order_book,
    normalize_outcome_tokens,
    summarize_order_book,
)


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_ENDPOINT = "https://gamma-api.polymarket.com/events"
OUTPUT_NAME = "QuantGod_PolymarketMarketRadar.json"
LEDGER_NAME = "QuantGod_PolymarketMarketRadar.csv"

try:
    import certifi  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency.
    certifi = None

_CERTIFI_SSL_CONTEXT: ssl.SSLContext | None = None


def certifi_ssl_context() -> ssl.SSLContext | None:
    global _CERTIFI_SSL_CONTEXT
    if certifi is None:
        return None
    if _CERTIFI_SSL_CONTEXT is None:
        _CERTIFI_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    return _CERTIFI_SSL_CONTEXT


def public_urlopen(request: urllib.request.Request, timeout: float):
    context = certifi_ssl_context()
    if context is not None:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    return urllib.request.urlopen(request, timeout=timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-volume", type=float, default=5000.0)
    parser.add_argument("--min-liquidity", type=float, default=1000.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-clob-depth", action="store_true", help="Skip public CLOB order-book depth enrichment.")
    parser.add_argument("--clob-depth-limit", type=int, default=12, help="How many ranked markets to enrich with public CLOB book depth.")
    parser.add_argument("--clob-timeout", type=float, default=4.0)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def first_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def request_gamma_events(endpoint: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    parsed = urllib.parse.urlparse(endpoint)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("active", "true")
    query.setdefault("closed", "false")
    query.setdefault("limit", str(max(1, min(limit, 500))))
    url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "QuantGod-Polymarket-Opportunity-Radar/1.0",
        },
        method="GET",
    )
    with public_urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def yes_probability(market: dict[str, Any]) -> float | None:
    outcomes = [str(item).strip().lower() for item in parse_json_list(market.get("outcomes"))]
    prices = parse_json_list(market.get("outcomePrices"))
    if prices:
        idx = 0
        if "yes" in outcomes:
            idx = outcomes.index("yes")
        if idx < len(prices):
            price = safe_number(prices[idx], default=-1.0)
            if 0.0 <= price <= 1.0:
                return round(price * 100.0, 2)
            if 0.0 <= price <= 100.0:
                return round(price, 2)
    bid = market.get("bestBid")
    ask = market.get("bestAsk")
    if bid not in (None, "") and ask not in (None, ""):
        midpoint = (safe_number(bid) + safe_number(ask)) / 2.0
        if 0.0 <= midpoint <= 1.0:
            return round(midpoint * 100.0, 2)
    for key in ("lastTradePrice", "price", "probability"):
        value = market.get(key)
        if value in (None, ""):
            continue
        price = safe_number(value, default=-1.0)
        if 0.0 <= price <= 1.0:
            return round(price * 100.0, 2)
        if 0.0 <= price <= 100.0:
            return round(price, 2)
    return None


def infer_category(event: dict[str, Any], market: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("category", "categorySlug", "title", "slug", "description"):
        pieces.append(str(event.get(key) or ""))
    for key in ("question", "slug", "description"):
        pieces.append(str(market.get(key) or ""))
    for tag in event.get("tags") or []:
        if isinstance(tag, dict):
            pieces.append(str(tag.get("label") or tag.get("slug") or ""))
        else:
            pieces.append(str(tag))
    text = " ".join(pieces).lower()
    if any(token in text for token in ("nba", "nfl", "mlb", "nhl", "soccer", "ufc", "tennis", "sports")):
        return "sports"
    if any(token in text for token in ("bitcoin", "crypto", "ethereum", "solana", "btc", "eth")):
        return "crypto"
    if any(token in text for token in ("election", "trump", "biden", "congress", "senate", "politic")):
        return "politics"
    if any(token in text for token in ("fed", "cpi", "inflation", "rate", "economy", "finance", "stock", "ipo")):
        return "macro_finance"
    if any(token in text for token in ("ai", "tech", "company", "earnings")):
        return "tech_business"
    return "general"


def market_url(event: dict[str, Any], market: dict[str, Any]) -> str:
    event_slug = str(event.get("slug") or "").strip()
    market_slug = str(market.get("slug") or "").strip()
    slug = event_slug or market_slug
    if slug:
        return f"https://polymarket.com/event/{urllib.parse.quote(slug)}"
    market_id = str(market.get("id") or event.get("id") or "").strip()
    return f"https://polymarket.com/market/{urllib.parse.quote(market_id)}" if market_id else "https://polymarket.com"


def risk_and_flags(
    probability: float | None,
    volume: float,
    volume24h: float,
    liquidity: float,
    end_date: datetime | None,
    market: dict[str, Any],
    min_volume: float,
    min_liquidity: float,
) -> tuple[str, list[str]]:
    flags: list[str] = []
    if probability is None:
        flags.append("probability_missing")
    elif probability <= 10.0 or probability >= 90.0:
        flags.append("price_extreme")
    if volume < min_volume:
        flags.append("volume_below_floor")
    if liquidity < min_liquidity:
        flags.append("liquidity_low")
    if liquidity <= 0:
        flags.append("thin_book_or_unknown_liquidity")
    if volume24h <= 0:
        flags.append("no_24h_volume")
    now = datetime.now(timezone.utc)
    if end_date:
        hours_left = (end_date - now).total_seconds() / 3600.0
        if hours_left < 0:
            flags.append("end_date_passed_or_stale")
        elif hours_left < 24:
            flags.append("near_resolution_lt_24h")
    accepting = market.get("acceptingOrders")
    if accepting is False:
        flags.append("accepting_orders_false")
    spread = first_number(market.get("spread"), default=0.0)
    if spread >= 0.08:
        flags.append("wide_spread")
    token_info = normalize_outcome_tokens(market)
    if not token_info.get("yesTokenId"):
        flags.append("clob_yes_token_missing")
    high_flags = {
        "probability_missing",
        "end_date_passed_or_stale",
        "accepting_orders_false",
        "thin_book_or_unknown_liquidity",
    }
    if any(flag in high_flags for flag in flags) or len(flags) >= 4:
        return "high", flags
    if flags:
        return "medium", flags
    return "low", flags


def score_market(
    probability: float | None,
    volume: float,
    volume24h: float,
    liquidity: float,
    risk: str,
    flags: list[str],
) -> tuple[int, int, float]:
    divergence = abs((probability if probability is not None else 50.0) - 50.0)
    volume_score = min(24.0, math.log10(max(volume, 0.0) + 1.0) * 4.0)
    volume24h_score = min(14.0, math.log10(max(volume24h, 0.0) + 1.0) * 3.0)
    liquidity_score = min(24.0, math.log10(max(liquidity, 0.0) + 1.0) * 4.2)
    divergence_score = min(28.0, divergence * 1.12)
    risk_penalty = {"low": 0.0, "medium": 12.0, "high": 32.0}.get(risk, 18.0)
    flag_penalty = min(16.0, len(flags) * 4.0)
    rule_score = clamp(10.0 + volume_score + volume24h_score + liquidity_score + divergence_score - risk_penalty - flag_penalty)
    confidence = clamp((volume_score + liquidity_score + volume24h_score) * 1.45)
    ai_rule_score = clamp(rule_score * 0.78 + confidence * 0.22)
    return int(round(rule_score)), int(round(ai_rule_score)), round(divergence, 2)


def suggested_shadow_track(category: str, risk: str, divergence: float, volume: float, liquidity: float) -> str:
    if risk == "high":
        return "poly_observation_only"
    if volume >= 50000 and liquidity >= 3000 and divergence >= 12:
        return "poly_high_liquidity_divergence_shadow_v1"
    if category == "sports":
        return "poly_sports_market_radar_shadow_v1"
    if category in {"crypto", "macro_finance"}:
        return "poly_cross_asset_radar_shadow_v1"
    return "poly_market_radar_watch_shadow_v1"


def flatten_event(event: dict[str, Any], min_volume: float, min_liquidity: float) -> list[dict[str, Any]]:
    markets = event.get("markets")
    if not isinstance(markets, list) or not markets:
        markets = [event]
    rows: list[dict[str, Any]] = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("closed") is True or market.get("active") is False:
            continue
        probability = yes_probability(market)
        volume = first_number(
            market.get("volumeNum"),
            market.get("volumeClob"),
            market.get("volume"),
            event.get("volume"),
            default=0.0,
        )
        volume24h = first_number(
            market.get("volume24hr"),
            market.get("volume24h"),
            market.get("volume24hrClob"),
            event.get("volume24hr"),
            event.get("volume24h"),
            default=0.0,
        )
        liquidity = first_number(
            market.get("liquidityNum"),
            market.get("liquidityClob"),
            market.get("liquidity"),
            event.get("liquidityClob"),
            event.get("liquidity"),
            default=0.0,
        )
        end_date = parse_iso_datetime(market.get("endDate") or event.get("endDate"))
        category = infer_category(event, market)
        token_info = normalize_outcome_tokens(market)
        risk, flags = risk_and_flags(probability, volume, volume24h, liquidity, end_date, market, min_volume, min_liquidity)
        rule_score, ai_rule_score, divergence_abs = score_market(probability, volume, volume24h, liquidity, risk, flags)
        signed_divergence = None if probability is None else round(probability - 50.0, 2)
        track = suggested_shadow_track(category, risk, divergence_abs, volume, liquidity)
        rows.append(
            {
                "marketId": str(market.get("id") or event.get("id") or ""),
                "eventId": str(event.get("id") or ""),
                "question": str(market.get("question") or event.get("title") or event.get("slug") or ""),
                "eventTitle": str(event.get("title") or ""),
                "slug": str(market.get("slug") or event.get("slug") or ""),
                "polymarketUrl": market_url(event, market),
                "category": category,
                "probability": probability,
                "probabilitySource": "gamma_outcome_prices_or_market_quote",
                "volume": round(volume, 4),
                "volume24h": round(volume24h, 4),
                "liquidity": round(liquidity, 4),
                "divergence": signed_divergence,
                "absDivergence": divergence_abs,
                "ruleScore": rule_score,
                "aiRuleScore": ai_rule_score,
                "aiScoringMode": "RULE_PROXY_NO_LLM",
                "risk": risk,
                "riskFlags": flags,
                "suggestedShadowTrack": track,
                "recommendedAction": "SHADOW_REVIEW" if risk != "high" else "OBSERVE_ONLY",
                "endDate": format_iso(end_date),
                "acceptingOrders": market.get("acceptingOrders"),
                "spread": first_number(market.get("spread"), default=0.0),
                "outcomeTokens": token_info.get("outcomeTokens") or [],
                "yesTokenId": token_info.get("yesTokenId") or "",
                "noTokenId": token_info.get("noTokenId") or "",
                "yesPrice": token_info.get("yesPrice"),
                "noPrice": token_info.get("noPrice"),
                "clobStatus": "NOT_CHECKED",
                "clobBestBid": None,
                "clobBestAsk": None,
                "clobMidpoint": None,
                "clobSpread": None,
                "clobLiquidityUsd": None,
                "clobDepthScore": None,
                "source": "gamma_public_events",
            }
        )
    return rows


def enrich_clob_depth(rows: list[dict[str, Any]], limit: int, timeout: float, skip: bool) -> dict[str, int]:
    if skip or limit <= 0:
        for item in rows:
            item["clobStatus"] = "SKIPPED"
        return {"checked": 0, "ok": 0, "errors": 0, "skipped": len(rows)}
    checked = ok = errors = 0
    for item in rows[:limit]:
        token_id = str(item.get("yesTokenId") or "").strip()
        flags = item.get("riskFlags") if isinstance(item.get("riskFlags"), list) else []
        if not token_id:
            item["clobStatus"] = "NO_YES_TOKEN"
            if "clob_yes_token_missing" not in flags:
                flags.append("clob_yes_token_missing")
            item["riskFlags"] = flags
            errors += 1
            continue
        checked += 1
        book = fetch_order_book(token_id, timeout=timeout)
        depth = summarize_order_book(book)
        item.update(depth)
        if depth.get("clobStatus") == "OK":
            ok += 1
            clob_spread = safe_number(depth.get("clobSpread"), 0.0)
            depth_score = safe_number(depth.get("clobDepthScore"), 0.0)
            if depth_score <= 12.0 and "clob_depth_thin" not in flags:
                flags.append("clob_depth_thin")
            if clob_spread >= 0.08 and "clob_spread_wide" not in flags:
                flags.append("clob_spread_wide")
            if depth_score >= 55.0 and clob_spread <= 0.04:
                item["aiRuleScore"] = int(round(clamp(safe_number(item.get("aiRuleScore"), 0.0) + 4.0)))
            elif depth_score <= 12.0 or clob_spread >= 0.08:
                item["aiRuleScore"] = int(round(clamp(safe_number(item.get("aiRuleScore"), 0.0) - 6.0)))
        else:
            errors += 1
            if "clob_depth_unavailable" not in flags:
                flags.append("clob_depth_unavailable")
        item["riskFlags"] = flags
    for item in rows[limit:]:
        item["clobStatus"] = "NOT_CHECKED_LIMIT"
    return {
        "checked": checked,
        "ok": ok,
        "errors": errors,
        "skipped": max(0, len(rows) - max(0, limit)),
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = utc_now_iso()
    try:
        events = request_gamma_events(args.endpoint, args.limit, args.timeout)
        radar: list[dict[str, Any]] = []
        for event in events:
            radar.extend(flatten_event(event, args.min_volume, args.min_liquidity))
        radar.sort(
            key=lambda item: (
                safe_number(item.get("aiRuleScore")),
                safe_number(item.get("liquidity")),
                safe_number(item.get("volume24h")),
            ),
            reverse=True,
        )
        radar = radar[: max(1, args.top)]
        clob_summary = enrich_clob_depth(
            radar,
            max(0, args.clob_depth_limit),
            max(1.0, args.clob_timeout),
            bool(args.skip_clob_depth),
        )
        radar.sort(
            key=lambda item: (
                safe_number(item.get("aiRuleScore")),
                safe_number(item.get("clobDepthScore"), 0.0),
                safe_number(item.get("liquidity")),
                safe_number(item.get("volume24h")),
            ),
            reverse=True,
        )
        for idx, item in enumerate(radar, start=1):
            item["rank"] = idx
        low = sum(1 for item in radar if item.get("risk") == "low")
        medium = sum(1 for item in radar if item.get("risk") == "medium")
        high = sum(1 for item in radar if item.get("risk") == "high")
        top_item = radar[0] if radar else {}
        return {
            "mode": "POLYMARKET_OPPORTUNITY_RADAR_V1",
            "generatedAt": generated_at,
            "status": "OK",
            "decision": "SHADOW_ONLY_MARKET_RADAR_NO_BETTING",
            "source": {
                "endpoint": args.endpoint,
                "publicReadOnly": True,
                "loadsEnv": False,
                "callsClobPublicBook": not bool(args.skip_clob_depth),
                "walletWrite": False,
                "orderExecution": False,
                "mutatesMt5": False,
                "scanner": "Gamma API active events",
            },
            "scoring": {
                "aiScoringMode": "RULE_PROXY_PLUS_PUBLIC_CLOB_DEPTH",
                "note": "AI/rule score is deterministic. Public CLOB book depth is used only as read-only liquidity evidence.",
            },
            "summary": {
                "scannedEvents": len(events),
                "rankedMarkets": len(radar),
                "clobDepthChecked": clob_summary.get("checked", 0),
                "clobDepthOk": clob_summary.get("ok", 0),
                "clobDepthErrors": clob_summary.get("errors", 0),
                "lowRisk": low,
                "mediumRisk": medium,
                "highRisk": high,
                "topScore": top_item.get("aiRuleScore"),
                "topMarket": top_item.get("question", ""),
            },
            "radar": radar,
            "nextActions": [
                "Feed low/medium risk markets into shadow-only tracks; do not place bets from Radar output.",
                "Use riskFlags to decide which market families deserve retune/backtest style research.",
                "Execution support, if added later, must pass a separate wallet, sizing, SL/TP, and kill-switch gate.",
            ],
        }
    except Exception as exc:  # noqa: BLE001 - write a diagnostic snapshot instead of blocking the dashboard.
        return {
            "mode": "POLYMARKET_OPPORTUNITY_RADAR_V1",
            "generatedAt": generated_at,
            "status": "ERROR",
            "decision": "SHADOW_ONLY_MARKET_RADAR_NO_BETTING",
            "source": {
                "endpoint": args.endpoint,
                "publicReadOnly": True,
                "loadsEnv": False,
                "callsClobPublicBook": not bool(getattr(args, "skip_clob_depth", False)),
                "walletWrite": False,
                "orderExecution": False,
                "mutatesMt5": False,
            },
            "summary": {
                "scannedEvents": 0,
                "rankedMarkets": 0,
                "lowRisk": 0,
                "mediumRisk": 0,
                "highRisk": 0,
                "topScore": None,
                "topMarket": "",
            },
            "error": f"{type(exc).__name__}: {exc}",
            "radar": [],
            "nextActions": [
                "Gamma API snapshot failed; keep Polymarket execution disabled and retry later.",
            ],
        }


def radar_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "generated_at",
            "rank",
            "market_id",
            "question",
            "category",
            "probability",
            "probability_source",
            "divergence",
            "volume",
            "volume_24h",
            "liquidity",
            "spread",
            "yes_token_id",
            "no_token_id",
            "clob_status",
            "clob_best_bid",
            "clob_best_ask",
            "clob_spread",
            "clob_liquidity_usd",
            "clob_depth_score",
            "rule_score",
            "ai_rule_score",
            "risk",
            "suggested_shadow_track",
            "polymarket_url",
            "risk_flags",
        ],
    )
    writer.writeheader()
    generated_at = snapshot.get("generatedAt", "")
    for item in snapshot.get("radar") or []:
        writer.writerow(
            {
                "generated_at": generated_at,
                "rank": item.get("rank", ""),
                "market_id": item.get("marketId", ""),
                "question": item.get("question", ""),
                "category": item.get("category", ""),
                "probability": item.get("probability", ""),
                "probability_source": item.get("probabilitySource", ""),
                "divergence": item.get("divergence", ""),
                "volume": item.get("volume", ""),
                "volume_24h": item.get("volume24h", ""),
                "liquidity": item.get("liquidity", ""),
                "spread": item.get("spread", ""),
                "yes_token_id": item.get("yesTokenId", ""),
                "no_token_id": item.get("noTokenId", ""),
                "clob_status": item.get("clobStatus", ""),
                "clob_best_bid": item.get("clobBestBid", ""),
                "clob_best_ask": item.get("clobBestAsk", ""),
                "clob_spread": item.get("clobSpread", ""),
                "clob_liquidity_usd": item.get("clobLiquidityUsd", ""),
                "clob_depth_score": item.get("clobDepthScore", ""),
                "rule_score": item.get("ruleScore", ""),
                "ai_rule_score": item.get("aiRuleScore", ""),
                "risk": item.get("risk", ""),
                "suggested_shadow_track": item.get("suggestedShadowTrack", ""),
                "polymarket_url": item.get("polymarketUrl", ""),
                "risk_flags": " / ".join(item.get("riskFlags") or []),
            }
        )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    csv_text = radar_csv(snapshot)
    written: list[str] = []
    for base_dir in [runtime_dir, dashboard_dir]:
        if base_dir is None:
            continue
        json_path = base_dir / OUTPUT_NAME
        csv_path = base_dir / LEDGER_NAME
        atomic_write_text(json_path, json_text)
        atomic_write_text(csv_path, csv_text)
        written.extend([str(json_path), str(csv_path)])
    return written


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    snapshot = build_snapshot(args)
    written = write_outputs(snapshot, runtime_dir, dashboard_dir)
    summary = snapshot.get("summary", {})
    print(
        "Polymarket market radar "
        f"{snapshot.get('status')} | ranked={summary.get('rankedMarkets', 0)} "
        f"| top={summary.get('topMarket') or '--'} | outputs={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
