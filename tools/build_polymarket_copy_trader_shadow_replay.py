#!/usr/bin/env python3
"""Build shadow replay and walk-forward evidence for Polymarket copy signals.

This worker is read-only. It consumes the copy-trader discovery snapshot,
matches Telegram smart-money signals and self-discovered copy candidates to
public Gamma market snapshots when possible, writes shadow/outcome ledgers, and
produces the validation files used by the autonomous wallet gate. It never
loads wallet secrets or places orders.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
DEFAULT_DISCOVERY_NAME = "QuantGod_PolymarketCopyTraderDiscovery.json"
DEFAULT_GAMMA_ENDPOINT = "https://gamma-api.polymarket.com/events"
DEFAULT_GAMMA_MARKETS_ENDPOINT = "https://gamma-api.polymarket.com/markets"
SHADOW_REPLAY_NAME = "QuantGod_PolymarketCopyTraderShadowReplay.json"
SHADOW_REPLAY_LEDGER_NAME = "QuantGod_PolymarketCopyTraderShadowReplay.csv"
OUTCOME_LEDGER_NAME = "QuantGod_PolymarketCopyTraderOutcomeLedger.csv"
WALK_FORWARD_NAME = "QuantGod_PolymarketCopyTraderWalkForward.json"
WALK_FORWARD_LEDGER_NAME = "QuantGod_PolymarketCopyTraderWalkForward.csv"
SOURCE_BUCKETS_NAME = "QuantGod_PolymarketCopyTraderSourceBuckets.json"
SOURCE_BUCKETS_LEDGER_NAME = "QuantGod_PolymarketCopyTraderSourceBuckets.csv"
SELF_DISCOVERY_SOURCE = "copy_trader_discovery"
SELF_DISCOVERY_CHANNEL = "self_explore"

WORD_RE = re.compile(r"[a-z0-9]+")
RESOLVES_RE = re.compile(r"Resolves:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})", re.IGNORECASE)
SIGNAL_TITLE_RE = re.compile(r"(?:📌|📍)\s*(.*?)\s*(?:📅|🎯|🟢|🔴|├|$)")
TEXT_MARKERS_RE = re.compile(r"[📌📍📅🎯🟢🔴👤├└]")
MARKET_FAMILY_RULES = (
    ("crypto", re.compile(r"\b(bitcoin|btc|ethereum|eth|solana|sol\b|xrp|doge|crypto|token)\b", re.IGNORECASE)),
    (
        "sports",
        re.compile(
            r"\b(nba|nfl|nhl|mlb|ufc|fifa|soccer|football|tennis|serie|lazio|premier|champions|game|match)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "politics",
        re.compile(r"\b(trump|biden|election|senate|congress|president|mayor|governor|poll)\b", re.IGNORECASE),
    ),
    ("macro", re.compile(r"\b(fed|rate|inflation|cpi|gdp|unemployment|recession|tariff)\b", re.IGNORECASE)),
    (
        "geopolitics",
        re.compile(
            r"\b(israel|hezbollah|iran|russia|ukraine|china|gaza|war|ceasefire|peace|deal|nuclear)\b",
            re.IGNORECASE,
        ),
    ),
    ("culture", re.compile(r"\b(oscar|grammy|movie|album|song|tiktok|youtube|streamer)\b", re.IGNORECASE)),
    (
        "company",
        re.compile(r"\b(tesla|apple|nvidia|openai|xai|meta|google|microsoft|spacex|stock)\b", re.IGNORECASE),
    ),
)
ENTRY_PRICE_BANDS = (
    (0.04, "lt_0.04"),
    (0.20, "0.04_0.20"),
    (0.40, "0.20_0.40"),
    (0.60, "0.40_0.60"),
    (0.80, "0.60_0.80"),
    (0.90, "0.80_0.90"),
)

try:
    import certifi  # type: ignore
except Exception:  # pragma: no cover - optional local dependency.
    certifi = None

_SSL_CONTEXT: ssl.SSLContext | None = None


@dataclass(frozen=True)
class MarketQuote:
    event_title: str
    question: str
    slug: str
    event_slug: str
    url: str
    end_date: str
    active: bool
    closed: bool
    outcomes: list[str]
    prices: dict[str, float]
    raw_score_text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--discovery-path", default="")
    parser.add_argument("--gamma-endpoint", default=DEFAULT_GAMMA_ENDPOINT)
    parser.add_argument("--gamma-markets-endpoint", default=DEFAULT_GAMMA_MARKETS_ENDPOINT)
    parser.add_argument("--gamma-limit", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-signals", type=int, default=100)
    parser.add_argument("--max-discovery-candidates", type=int, default=150)
    parser.add_argument("--max-ledger-signals", type=int, default=600)
    parser.add_argument("--max-market-slug-lookups", type=int, default=120)
    parser.add_argument("--stake-usdc", type=float, default=1.0)
    parser.add_argument("--follow-slippage-cents", type=float, default=1.0)
    parser.add_argument("--take-profit-pct", type=float, default=35.0)
    parser.add_argument("--stop-loss-pct", type=float, default=18.0)
    parser.add_argument("--min-entry-price", type=float, default=0.04)
    parser.add_argument("--max-entry-price", type=float, default=0.90)
    parser.add_argument("--min-match-score", type=float, default=0.42)
    parser.add_argument("--min-shadow-replay-trades", type=int, default=30)
    parser.add_argument("--min-shadow-profit-factor", type=float, default=1.10)
    parser.add_argument("--min-shadow-net-pnl-usdc", type=float, default=0.01)
    parser.add_argument("--walk-forward-batches", type=int, default=3)
    parser.add_argument("--min-walk-forward-pass-rate-pct", type=float, default=60.0)
    parser.add_argument("--min-trader-bucket-samples", type=int, default=8)
    parser.add_argument("--min-source-bucket-samples", type=int, default=30)
    parser.add_argument("--min-source-trader-bucket-samples", type=int, default=8)
    parser.add_argument("--min-market-family-bucket-samples", type=int, default=12)
    parser.add_argument("--min-entry-price-band-bucket-samples", type=int, default=12)
    parser.add_argument("--min-trader-market-family-bucket-samples", type=int, default=8)
    parser.add_argument("--min-trader-entry-price-band-bucket-samples", type=int, default=8)
    parser.add_argument("--promotion-hold-hours", type=float, default=6.0)
    parser.add_argument("--promotion-hard-demote-profit-factor", type=float, default=0.35)
    parser.add_argument("--promotion-hard-demote-net-pnl-usdc", type=float, default=-2.0)
    parser.add_argument("--profit-lock-min-peak-usdc", type=float, default=0.25)
    parser.add_argument("--profit-lock-max-drawdown-usdc", type=float, default=0.25)
    parser.add_argument("--profit-lock-max-drawdown-pct", type=float, default=60.0)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def signal_identity_parts(signal: dict[str, Any]) -> list[str]:
    message_id = str(signal.get("messageId") or "").strip()
    source = str(signal.get("source") or "telegram").strip().lower()
    trader = str(signal.get("userName") or signal.get("trader") or "").strip().lower()
    market_slug = normalize_market_slug(signal.get("marketSlug") or "")
    side = str(signal.get("side") or "").strip().upper()
    outcome = normalize_key(signal.get("outcome") or "")
    price = safe_number(signal.get("priceCents"), -1.0)
    if price < 0:
        price = safe_number(signal.get("signalPrice"), -1.0) * 100.0
    if message_id:
        return ["message", message_id, source, trader, market_slug, side, outcome]
    preview = normalize_key(str(signal.get("textPreview") or "")[:180])
    return ["signal", source, trader, market_slug, side, outcome, f"{price:.4f}", preview]


def signal_identity(signal: dict[str, Any]) -> str:
    return hashlib.sha1("|".join(signal_identity_parts(signal)).encode("utf-8")).hexdigest()[:20]


def certifi_ssl_context() -> ssl.SSLContext | None:
    global _SSL_CONTEXT
    if certifi is None:
        return None
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    return _SSL_CONTEXT


def public_urlopen(request: urllib.request.Request, timeout: float):
    context = certifi_ssl_context()
    if context is not None:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    return urllib.request.urlopen(request, timeout=timeout)


def request_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "QuantGod-Polymarket-CopyReplay/1.0",
        },
        method="GET",
    )
    with public_urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_gamma_events(endpoint: str, limit: int, timeout: float, *, closed: bool) -> list[dict[str, Any]]:
    parsed = urllib.parse.urlparse(endpoint)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["limit"] = str(max(1, min(500, limit)))
    query["closed"] = "true" if closed else "false"
    query["active"] = "false" if closed else "true"
    url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    payload = request_json(url, timeout)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def fetch_gamma_markets_by_slug(endpoint: str, slugs: list[str], timeout: float, max_lookups: int) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    unique = sorted({normalize_market_slug(slug) for slug in slugs if normalize_market_slug(slug)})
    parsed = urllib.parse.urlparse(endpoint)
    for slug in unique[: max(0, int(max_lookups))]:
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        query["slug"] = slug
        url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
        try:
            payload = request_json(url, timeout)
        except Exception as exc:  # noqa: BLE001 - compact diagnostics for the ledger.
            errors.append(f"gamma_market_slug:{slug}:{type(exc).__name__}:{str(exc)[:120]}")
            continue
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            for key in ("markets", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows.extend(item for item in value if isinstance(item, dict))
                    break
            else:
                if payload.get("slug") or payload.get("question"):
                    rows.append(payload)
    return rows, errors


def normalize_price(value: Any) -> float | None:
    price = safe_number(value, default=-1.0)
    if 0.0 <= price <= 1.0:
        return round(price, 6)
    if 0.0 <= price <= 100.0:
        return round(price / 100.0, 6)
    return None


def market_url(event_slug: str, market_slug: str, market_id: str) -> str:
    slug = event_slug or market_slug
    if slug:
        return "https://polymarket.com/event/" + urllib.parse.quote(slug)
    if market_id:
        return "https://polymarket.com/market/" + urllib.parse.quote(market_id)
    return "https://polymarket.com"


def market_quote_from_payload(event: dict[str, Any], market: dict[str, Any]) -> MarketQuote | None:
    market_id = str(market.get("id") or market.get("conditionId") or market.get("marketId") or "")
    slug = normalize_market_slug(market.get("slug") or "")
    event_slug = normalize_market_slug(event.get("slug") or "")
    event_title = str(event.get("title") or event.get("question") or event_slug or "")
    question = str(market.get("question") or event_title or slug)
    outcomes = [str(item).strip() for item in parse_json_list(market.get("outcomes")) if str(item).strip()]
    outcome_prices = parse_json_list(market.get("outcomePrices"))
    prices: dict[str, float] = {}
    for index, outcome in enumerate(outcomes):
        if index >= len(outcome_prices):
            continue
        price = normalize_price(outcome_prices[index])
        if price is not None:
            prices[normalize_key(outcome)] = price
    if not prices:
        fallback = normalize_price(market.get("lastTradePrice") or market.get("price") or market.get("probability"))
        if fallback is not None and outcomes:
            prices[normalize_key(outcomes[0])] = fallback
            if len(outcomes) > 1:
                prices[normalize_key(outcomes[1])] = round(max(0.0, min(1.0, 1.0 - fallback)), 6)
    if not question and not slug and not market_id:
        return None
    return MarketQuote(
        event_title=event_title,
        question=question,
        slug=slug,
        event_slug=event_slug,
        url=market_url(event_slug, slug, market_id),
        end_date=str(market.get("endDate") or event.get("endDate") or ""),
        active=bool(market.get("active", event.get("active", True))),
        closed=bool(market.get("closed", event.get("closed", False))),
        outcomes=outcomes,
        prices=prices,
        raw_score_text=f"{event_title} {question} {slug} {event_slug}",
    )


def build_market_quotes(events: list[dict[str, Any]]) -> list[MarketQuote]:
    quotes: list[MarketQuote] = []
    seen: set[str] = set()
    for event in events:
        markets = event.get("markets") if isinstance(event.get("markets"), list) else []
        if not markets:
            markets = [event]
        event_title = str(event.get("title") or event.get("question") or event.get("slug") or "")
        event_slug = str(event.get("slug") or "")
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_id = str(market.get("id") or market.get("conditionId") or market.get("marketId") or "")
            slug = normalize_market_slug(market.get("slug") or "")
            key = market_id or slug or f"{event_slug}:{event_title}"
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            quote = market_quote_from_payload(event, market)
            if quote:
                quotes.append(quote)
    return quotes


def dedupe_quotes(quotes: list[MarketQuote]) -> list[MarketQuote]:
    deduped: list[MarketQuote] = []
    seen: set[str] = set()
    for quote in quotes:
        key = quote.slug or quote.event_slug or normalize_key(quote.question)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(quote)
    return deduped


def normalize_key(value: Any) -> str:
    return " ".join(WORD_RE.findall(str(value or "").lower()))


def normalize_market_slug(value: Any) -> str:
    slug = urllib.parse.unquote(str(value or "").strip()).strip("/")
    if slug.startswith("predictmon--"):
        slug = slug[len("predictmon--") :]
    return slug


def market_family(*parts: Any) -> str:
    text = " ".join(str(part or "") for part in parts if part is not None)
    for family, pattern in MARKET_FAMILY_RULES:
        if pattern.search(text):
            return family
    return "other"


def entry_price_band(value: Any) -> str:
    price = safe_number(value, -1.0)
    if price < 0:
        return "unknown"
    for limit, label in ENTRY_PRICE_BANDS:
        if price < limit:
            return label
    return "gt_0.90"


def token_set(value: Any) -> set[str]:
    tokens = set(WORD_RE.findall(str(value or "").lower()))
    return {token for token in tokens if token not in {"the", "will", "vs", "v", "by", "on", "to", "of", "a", "an"}}


def parse_signal_title(text: str) -> str:
    match = SIGNAL_TITLE_RE.search(text)
    if match:
        return " ".join(match.group(1).split())
    pieces = TEXT_MARKERS_RE.split(text)
    return " ".join((pieces[1] if len(pieces) > 1 else text).split())[:160]


def parse_resolves_date(text: str) -> str:
    match = RESOLVES_RE.search(text)
    if not match:
        return ""
    raw = match.group(1).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}$", raw):
        return raw
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def date_score(resolve_date: str, end_date: str) -> float:
    if not resolve_date or not end_date:
        return 0.0
    return 0.12 if end_date.startswith(resolve_date) else 0.0


def outcome_price(outcome: str, quote: MarketQuote) -> tuple[float | None, str]:
    wanted = normalize_key(outcome)
    if not wanted:
        return None, ""
    if wanted in quote.prices:
        return quote.prices[wanted], wanted
    for key, price in quote.prices.items():
        if wanted == key or wanted in key or key in wanted:
            return price, key
    if "yes" in quote.prices and "no" in quote.prices:
        if wanted in {"over", "under"}:
            quote_text = normalize_key(quote.raw_score_text)
            if wanted == "over" and ("over" in quote_text or " o u " in f" {quote_text} "):
                return quote.prices["yes"], "yes_inferred_over"
            if wanted == "under" and "under" in quote_text:
                return quote.prices["yes"], "yes_inferred_under"
            if wanted == "under" and "over" in quote_text:
                return quote.prices["no"], "no_inferred_under"
        wanted_tokens = token_set(wanted)
        quote_tokens = token_set(quote.raw_score_text)
        if wanted_tokens and wanted_tokens & quote_tokens:
            return quote.prices["yes"], "yes_inferred_" + wanted.replace(" ", "_")[:40]
    wanted_tokens = token_set(wanted)
    best_key = ""
    best_overlap = 0.0
    for key in quote.prices:
        key_tokens = token_set(key)
        if not wanted_tokens or not key_tokens:
            continue
        overlap = len(wanted_tokens & key_tokens) / max(1, len(wanted_tokens | key_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_key = key
    if best_overlap >= 0.5 and best_key:
        return quote.prices[best_key], best_key
    return None, ""


def match_market(
    signal_title: str,
    outcome: str,
    resolve_date: str,
    market_slug: str,
    quotes: list[MarketQuote],
    min_score: float,
) -> tuple[MarketQuote | None, float, float | None, str]:
    title_tokens = token_set(signal_title)
    best: tuple[MarketQuote | None, float, float | None, str] = (None, 0.0, None, "")
    normalized_slug = normalize_market_slug(market_slug)
    if normalized_slug:
        for quote in quotes:
            if normalized_slug in {normalize_market_slug(quote.slug), normalize_market_slug(quote.event_slug)}:
                price, matched_outcome = outcome_price(outcome, quote)
                return (quote, 1.0, price, matched_outcome)
    if not title_tokens:
        return best
    for quote in quotes:
        price, matched_outcome = outcome_price(outcome, quote)
        if price is None:
            continue
        quote_tokens = token_set(quote.raw_score_text)
        if not quote_tokens:
            continue
        overlap = len(title_tokens & quote_tokens) / max(1, len(title_tokens | quote_tokens))
        contains_bonus = 0.0
        normalized_title = normalize_key(signal_title)
        normalized_quote = normalize_key(quote.raw_score_text)
        if normalized_title and normalized_title in normalized_quote:
            contains_bonus = 0.22
        score = overlap + contains_bonus + date_score(resolve_date, quote.end_date)
        if score > best[1]:
            best = (quote, score, price, matched_outcome)
    if best[1] < min_score:
        return (None, best[1], None, "")
    return best


def signal_key(index: int, signal: dict[str, Any]) -> str:
    del index
    return signal_identity(signal)[:16]


def profit_factor(rows: list[dict[str, Any]]) -> float:
    gross_win = sum(max(0.0, safe_number(row.get("netPnlUSDC"))) for row in rows)
    gross_loss = abs(sum(min(0.0, safe_number(row.get("netPnlUSDC"))) for row in rows))
    if gross_loss <= 0:
        return 999.0 if gross_win > 0 else 0.0
    return gross_win / gross_loss


def row_chronological_key(row: dict[str, Any]) -> tuple[float, int]:
    parsed = parse_iso_datetime(row.get("messageDate") or row.get("generatedAtIso"))
    timestamp = parsed.timestamp() if parsed is not None else 0.0
    return (timestamp, safe_int(row.get("sequence")))


def profit_lock_metrics(validated: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    ordered = sorted(validated, key=row_chronological_key)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    peak_sequence = 0
    max_drawdown_sequence = 0
    for row in ordered:
        equity += safe_number(row.get("netPnlUSDC"))
        if equity > peak:
            peak = equity
            peak_sequence = safe_int(row.get("sequence"))
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_sequence = safe_int(row.get("sequence"))

    loss_wave_rows = 0
    loss_wave_pnl = 0.0
    for row in reversed(ordered):
        pnl = safe_number(row.get("netPnlUSDC"))
        if pnl >= 0:
            break
        loss_wave_rows += 1
        loss_wave_pnl += pnl

    min_peak = max(0.0, safe_number(getattr(args, "profit_lock_min_peak_usdc", 0.25), 0.25))
    drawdown_floor = max(0.0, safe_number(getattr(args, "profit_lock_max_drawdown_usdc", 0.25), 0.25))
    drawdown_pct = max(0.0, safe_number(getattr(args, "profit_lock_max_drawdown_pct", 60.0), 60.0))
    drawdown_limit = max(drawdown_floor, peak * drawdown_pct / 100.0)
    latest_drawdown = peak - equity
    active = bool(peak >= min_peak and latest_drawdown >= drawdown_limit)
    reason = ""
    if active:
        reason = "profit_peak_drawdown_exceeded"
    return {
        "active": active,
        "reason": reason,
        "samples": len(ordered),
        "currentNetPnlUSDC": round(equity, 6),
        "peakNetPnlUSDC": round(peak, 6),
        "peakSequence": peak_sequence,
        "latestDrawdownFromPeakUSDC": round(latest_drawdown, 6),
        "maxDrawdownUSDC": round(max_drawdown, 6),
        "maxDrawdownSequence": max_drawdown_sequence,
        "drawdownLimitUSDC": round(drawdown_limit, 6),
        "drawdownLimitPct": round(drawdown_pct, 4),
        "minPeakUSDC": round(min_peak, 6),
        "recentLossWaveRows": loss_wave_rows,
        "recentLossWavePnlUSDC": round(loss_wave_pnl, 6),
    }


def replay_signal(index: int, signal: dict[str, Any], quotes: list[MarketQuote], args: argparse.Namespace) -> dict[str, Any]:
    text = str(signal.get("textPreview") or "")
    title = str(signal.get("marketTitle") or "").strip() or parse_signal_title(text)
    resolve_date = parse_resolves_date(text)
    market_slug = normalize_market_slug(signal.get("marketSlug") or "")
    source = signal.get("source") or "telegram"
    channel_name = str(signal.get("channelName") or "").strip()
    source_bucket = f"{source}:{channel_name}" if channel_name else str(source)
    side = str(signal.get("side") or "").upper()
    outcome = str(signal.get("outcome") or "").strip()
    signal_price = safe_number(signal.get("priceCents")) / 100.0
    entry_price = round(min(0.99, max(0.01, signal_price + safe_number(args.follow_slippage_cents) / 100.0)), 6)
    take_profit = round(min(0.99, entry_price * (1.0 + safe_number(args.take_profit_pct) / 100.0)), 6)
    stop_loss = round(max(0.01, entry_price * (1.0 - safe_number(args.stop_loss_pct) / 100.0)), 6)
    quote, match_score, current_price, matched_outcome = match_market(
        title,
        outcome,
        resolve_date,
        market_slug,
        quotes,
        safe_number(args.min_match_score),
    )
    family = market_family(
        title,
        market_slug,
        quote.question if quote else "",
        quote.event_title if quote else "",
        quote.slug if quote else "",
    )
    price_band = entry_price_band(entry_price)
    blockers: list[str] = []
    if side != "BUY":
        blockers.append("non_buy_signal_not_copyable")
    if entry_price < safe_number(args.min_entry_price) or entry_price > safe_number(args.max_entry_price):
        blockers.append("entry_price_outside_policy_band")
    if quote is None or current_price is None:
        blockers.append("market_match_missing")

    exit_price: float | None = None
    exit_reason = "OPEN_MARK_TO_MARKET"
    validated_exit = False
    if current_price is not None:
        current_price = round(current_price, 6)
        if quote and quote.closed:
            exit_price = current_price
            exit_reason = "RESOLVED_WIN" if current_price >= 0.99 else "RESOLVED_LOSS" if current_price <= 0.01 else "CLOSED_MARK"
            validated_exit = True
        elif current_price >= take_profit:
            exit_price = take_profit
            exit_reason = "TAKE_PROFIT"
            validated_exit = True
        elif current_price <= stop_loss:
            exit_price = stop_loss
            exit_reason = "STOP_LOSS"
            validated_exit = True
        else:
            exit_price = current_price
    if blockers:
        validated_exit = False
        if exit_reason == "OPEN_MARK_TO_MARKET":
            exit_reason = "BLOCKED_OR_UNMATCHED"

    net_pnl = 0.0
    return_pct = 0.0
    if exit_price is not None and entry_price > 0:
        stake = safe_number(args.stake_usdc, 1.0)
        net_pnl = stake * ((exit_price - entry_price) / entry_price)
        return_pct = (exit_price - entry_price) / entry_price * 100.0

    return {
        "signalId": signal_key(index, signal),
        "sequence": index + 1,
        "source": source,
        "channelName": channel_name,
        "sourceBucket": source_bucket,
        "trader": signal.get("userName") or "",
        "rank": safe_int(signal.get("rank")),
        "wallet": signal.get("wallet") or "",
        "walletPreview": signal.get("walletPreview") or "",
        "messageId": signal.get("messageId"),
        "messageDate": signal.get("messageDate") or "",
        "marketSlug": market_slug,
        "kreoTradeUrl": signal.get("kreoTradeUrl") or "",
        "polymarketMarketUrl": signal.get("polymarketMarketUrl") or "",
        "side": side,
        "outcome": outcome,
        "marketTitle": title,
        "marketFamily": family,
        "entryPriceBand": price_band,
        "resolveDate": resolve_date,
        "telegramAmountUSDC": safe_number(signal.get("amountUSDC")),
        "smartScore": signal.get("smartScore"),
        "backtestPnlUSDC": signal.get("backtestPnlUSDC"),
        "winRatePct": signal.get("winRatePct"),
        "signalPrice": round(signal_price, 6),
        "entryPrice": entry_price,
        "currentPrice": current_price if current_price is not None else None,
        "exitPrice": round(exit_price, 6) if exit_price is not None else None,
        "takeProfitPrice": take_profit,
        "stopLossPrice": stop_loss,
        "stakeUSDC": round(safe_number(args.stake_usdc, 1.0), 4),
        "netPnlUSDC": round(net_pnl, 6),
        "returnPct": round(return_pct, 4),
        "exitReason": exit_reason,
        "validatedExit": validated_exit,
        "matchScore": round(match_score, 4),
        "matchedOutcome": matched_outcome,
        "matchedQuestion": quote.question if quote else "",
        "matchedEventTitle": quote.event_title if quote else "",
        "matchedSlug": quote.slug if quote else "",
        "matchedUrl": quote.url if quote else "",
        "marketClosed": bool(quote.closed) if quote else False,
        "marketActive": bool(quote.active) if quote else False,
        "blockers": blockers,
        "textPreview": text[:360],
    }


def build_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    matched = [row for row in rows if row.get("currentPrice") is not None and "market_match_missing" not in row.get("blockers", [])]
    validated = [row for row in rows if row.get("validatedExit")]
    wins = [row for row in validated if safe_number(row.get("netPnlUSDC")) > 0]
    losses = [row for row in validated if safe_number(row.get("netPnlUSDC")) < 0]
    mtm_net = sum(safe_number(row.get("netPnlUSDC")) for row in matched)
    validated_net = sum(safe_number(row.get("netPnlUSDC")) for row in validated)
    pf = profit_factor(validated)
    profit_lock = profit_lock_metrics(validated, args)
    blockers: list[str] = []
    warnings: list[str] = []
    if len(validated) < int(args.min_shadow_replay_trades):
        blockers.append("shadow_replay_samples_lt_min")
    if validated_net < safe_number(args.min_shadow_net_pnl_usdc):
        blockers.append("shadow_replay_net_pnl_not_positive")
    if pf < safe_number(args.min_shadow_profit_factor):
        blockers.append("shadow_replay_pf_lt_min")
    if profit_lock["active"]:
        blockers.append("shadow_replay_profit_lock_drawdown")
    unresolved = len(matched) - len(validated)
    if unresolved > 0:
        warnings.append("open_or_unresolved_signals_present")
    passed = not blockers
    return {
        "signals": len(rows),
        "rows": len(rows),
        "matchedSignals": len(matched),
        "unmatchedSignals": len(rows) - len(matched),
        "validatedCandidates": len(validated),
        "samples": len(validated),
        "outcomeSamples": len(validated),
        "wins": len(wins),
        "losses": len(losses),
        "openOrUnresolved": unresolved,
        "netPnlUSDC": round(validated_net, 6),
        "markToMarketNetPnlUSDC": round(mtm_net, 6),
        "profitFactor": round(pf, 6),
        "winRatePct": round(len(wins) / len(validated) * 100.0, 4) if validated else 0.0,
        "profitLock": profit_lock,
        "passed": passed,
        "status": "PASSED" if passed else "BLOCKED_PENDING_MORE_OUTCOMES",
        "blockers": blockers,
        "warnings": warnings,
    }


def bucket_status(validated: list[dict[str, Any]], args: argparse.Namespace, min_samples: int) -> tuple[str, str]:
    if len(validated) < min_samples:
        return "COLLECTING", "collect_more_settled_samples"
    net = sum(safe_number(row.get("netPnlUSDC")) for row in validated)
    pf = profit_factor(validated)
    if net >= safe_number(args.min_shadow_net_pnl_usdc) and pf >= safe_number(args.min_shadow_profit_factor):
        return "PROMOTABLE", "allow_shadow_candidates"
    return "QUARANTINE", "exclude_from_shadow_candidates"


def summarize_bucket(bucket_type: str, bucket_key: str, rows: list[dict[str, Any]], args: argparse.Namespace, min_samples: int) -> dict[str, Any]:
    matched = [row for row in rows if row.get("currentPrice") is not None and "market_match_missing" not in row.get("blockers", [])]
    validated = [row for row in rows if row.get("validatedExit")]
    wins = [row for row in validated if safe_number(row.get("netPnlUSDC")) > 0]
    losses = [row for row in validated if safe_number(row.get("netPnlUSDC")) < 0]
    net = sum(safe_number(row.get("netPnlUSDC")) for row in validated)
    mtm_net = sum(safe_number(row.get("netPnlUSDC")) for row in matched)
    pf = profit_factor(validated)
    status, action = bucket_status(validated, args, min_samples)
    return {
        "bucketType": bucket_type,
        "bucketKey": bucket_key or "unknown",
        "status": status,
        "action": action,
        "rows": len(rows),
        "matched": len(matched),
        "samples": len(validated),
        "outcomeSamples": len(validated),
        "wins": len(wins),
        "losses": len(losses),
        "openOrUnresolved": len(matched) - len(validated),
        "netPnlUSDC": round(net, 6),
        "markToMarketNetPnlUSDC": round(mtm_net, 6),
        "profitFactor": round(pf, 6),
        "winRatePct": round(len(wins) / len(validated) * 100.0, 4) if validated else 0.0,
        "minSamples": min_samples,
    }


def promoted_status(row: dict[str, Any]) -> bool:
    return "PROMOTABLE" in str(row.get("status") or "").upper()


def quarantine_status(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").upper()
    return "QUARANTINE" in status and not promoted_status(row)


def build_bucket_group(
    rows: list[dict[str, Any]],
    bucket_type: str,
    min_samples: int,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        source = str(row.get("source") or "unknown").strip().lower()
        channel = str(row.get("channelName") or "").strip().lower()
        source_bucket = str(row.get("sourceBucket") or (f"{source}:{channel}" if channel else source)).strip().lower()
        trader = str(row.get("trader") or "unknown").strip()
        family = str(row.get("marketFamily") or market_family(row.get("marketTitle"), row.get("marketSlug"))).strip().lower()
        band = str(row.get("entryPriceBand") or entry_price_band(row.get("entryPrice"))).strip()
        if bucket_type == "source":
            key = source_bucket
        elif bucket_type == "trader":
            key = trader
        elif bucket_type == "marketFamily":
            key = family
        elif bucket_type == "entryPriceBand":
            key = band
        elif bucket_type == "traderMarketFamily":
            key = f"{trader}:{family}"
        elif bucket_type == "traderEntryPriceBand":
            key = f"{trader}:{band}"
        else:
            key = f"{source_bucket}:{trader}"
        buckets.setdefault(key or "unknown", []).append(row)
    summaries = [summarize_bucket(bucket_type, key, bucket_rows, args, min_samples) for key, bucket_rows in buckets.items()]
    summaries.sort(
        key=lambda row: (
            0 if row.get("status") == "QUARANTINE" else 1 if row.get("status") == "COLLECTING" else 2,
            -safe_int(row.get("samples")),
            safe_number(row.get("netPnlUSDC")),
        )
    )
    return summaries


def refresh_quality_bucket_indexes(quality_buckets: dict[str, Any]) -> dict[str, Any]:
    by_source = [row for row in quality_buckets.get("bySource") or [] if isinstance(row, dict)]
    by_trader = [row for row in quality_buckets.get("byTrader") or [] if isinstance(row, dict)]
    by_source_trader = [row for row in quality_buckets.get("bySourceTrader") or [] if isinstance(row, dict)]
    by_market_family = [row for row in quality_buckets.get("byMarketFamily") or [] if isinstance(row, dict)]
    by_entry_price_band = [row for row in quality_buckets.get("byEntryPriceBand") or [] if isinstance(row, dict)]
    by_trader_market_family = [
        row for row in quality_buckets.get("byTraderMarketFamily") or [] if isinstance(row, dict)
    ]
    by_trader_entry_price_band = [
        row for row in quality_buckets.get("byTraderEntryPriceBand") or [] if isinstance(row, dict)
    ]
    quarantined_sources = [row["bucketKey"] for row in by_source if quarantine_status(row)]
    quarantined_traders = [row["bucketKey"] for row in by_trader if quarantine_status(row)]
    quarantined_source_traders = [row["bucketKey"] for row in by_source_trader if quarantine_status(row)]
    quarantined_market_families = [row["bucketKey"] for row in by_market_family if quarantine_status(row)]
    quarantined_entry_price_bands = [row["bucketKey"] for row in by_entry_price_band if quarantine_status(row)]
    quarantined_trader_market_families = [
        row["bucketKey"] for row in by_trader_market_family if quarantine_status(row)
    ]
    quarantined_trader_entry_price_bands = [
        row["bucketKey"] for row in by_trader_entry_price_band if quarantine_status(row)
    ]
    promotable = {
        "sources": [row["bucketKey"] for row in by_source if promoted_status(row)],
        "traders": [row["bucketKey"] for row in by_trader if promoted_status(row)],
        "sourceTraders": [row["bucketKey"] for row in by_source_trader if promoted_status(row)],
        "marketFamilies": [row["bucketKey"] for row in by_market_family if promoted_status(row)],
        "entryPriceBands": [row["bucketKey"] for row in by_entry_price_band if promoted_status(row)],
        "traderMarketFamilies": [row["bucketKey"] for row in by_trader_market_family if promoted_status(row)],
        "traderEntryPriceBands": [row["bucketKey"] for row in by_trader_entry_price_band if promoted_status(row)],
    }
    weak_bucket_count = (
        len(quarantined_sources)
        + len(quarantined_traders)
        + len(quarantined_source_traders)
        + len(quarantined_market_families)
        + len(quarantined_entry_price_bands)
        + len(quarantined_trader_market_families)
        + len(quarantined_trader_entry_price_bands)
    )
    quality_buckets["quarantine"] = {
        "sources": quarantined_sources,
        "traders": quarantined_traders,
        "sourceTraders": quarantined_source_traders,
        "marketFamilies": quarantined_market_families,
        "entryPriceBands": quarantined_entry_price_bands,
        "traderMarketFamilies": quarantined_trader_market_families,
        "traderEntryPriceBands": quarantined_trader_entry_price_bands,
        "weakBucketCount": weak_bucket_count,
    }
    quality_buckets["promotions"] = promotable
    quality_buckets["microScalpPolicy"] = {
        "realWalletRequiresPromotedCompositeBucket": True,
        "compositeBucketTypes": ["traderMarketFamily", "traderEntryPriceBand"],
        "promotedCompositeBucketCount": len(promotable["traderMarketFamilies"])
        + len(promotable["traderEntryPriceBands"]),
    }
    return quality_buckets


def build_quality_buckets(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    by_source = build_bucket_group(rows, "source", max(1, int(args.min_source_bucket_samples)), args)
    by_trader = build_bucket_group(rows, "trader", max(1, int(args.min_trader_bucket_samples)), args)
    by_source_trader = build_bucket_group(
        rows,
        "sourceTrader",
        max(1, int(args.min_source_trader_bucket_samples)),
        args,
    )
    by_market_family = build_bucket_group(rows, "marketFamily", max(1, int(args.min_market_family_bucket_samples)), args)
    by_entry_price_band = build_bucket_group(
        rows,
        "entryPriceBand",
        max(1, int(args.min_entry_price_band_bucket_samples)),
        args,
    )
    by_trader_market_family = build_bucket_group(
        rows,
        "traderMarketFamily",
        max(1, int(args.min_trader_market_family_bucket_samples)),
        args,
    )
    by_trader_entry_price_band = build_bucket_group(
        rows,
        "traderEntryPriceBand",
        max(1, int(args.min_trader_entry_price_band_bucket_samples)),
        args,
    )
    return refresh_quality_bucket_indexes({
        "schema": "quantgod.polymarket_copy_trader_source_buckets.v2",
        "generatedAtIso": utc_now_iso(),
        "thresholds": {
            "minTraderBucketSamples": max(1, int(args.min_trader_bucket_samples)),
            "minSourceBucketSamples": max(1, int(args.min_source_bucket_samples)),
            "minSourceTraderBucketSamples": max(1, int(args.min_source_trader_bucket_samples)),
            "minMarketFamilyBucketSamples": max(1, int(args.min_market_family_bucket_samples)),
            "minEntryPriceBandBucketSamples": max(1, int(args.min_entry_price_band_bucket_samples)),
            "minTraderMarketFamilyBucketSamples": max(1, int(args.min_trader_market_family_bucket_samples)),
            "minTraderEntryPriceBandBucketSamples": max(1, int(args.min_trader_entry_price_band_bucket_samples)),
            "minProfitFactor": safe_number(args.min_shadow_profit_factor),
            "minNetPnlUSDC": safe_number(args.min_shadow_net_pnl_usdc),
        },
        "bySource": by_source,
        "byTrader": by_trader,
        "bySourceTrader": by_source_trader,
        "byMarketFamily": by_market_family,
        "byEntryPriceBand": by_entry_price_band,
        "byTraderMarketFamily": by_trader_market_family,
        "byTraderEntryPriceBand": by_trader_entry_price_band,
    })


def split_batches(rows: list[dict[str, Any]], batches: int) -> list[list[dict[str, Any]]]:
    count = max(1, batches)
    if not rows:
        return []
    size = max(1, math.ceil(len(rows) / count))
    return [rows[index : index + size] for index in range(0, len(rows), size)][:count]


def build_walk_forward(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    validated = [row for row in rows if row.get("validatedExit")]
    batches = []
    for index, batch in enumerate(split_batches(validated, int(args.walk_forward_batches)), start=1):
        net = sum(safe_number(row.get("netPnlUSDC")) for row in batch)
        pf = profit_factor(batch)
        passed = bool(batch) and net > 0 and pf >= safe_number(args.min_shadow_profit_factor)
        batches.append(
            {
                "batch": index,
                "samples": len(batch),
                "netPnlUSDC": round(net, 6),
                "profitFactor": round(pf, 6),
                "passed": passed,
            }
        )
    pass_rate = sum(1 for row in batches if row.get("passed")) / len(batches) * 100.0 if batches else 0.0
    total_net = sum(safe_number(row.get("netPnlUSDC")) for row in batches)
    blockers: list[str] = []
    if len(batches) < int(args.walk_forward_batches):
        blockers.append("walk_forward_batches_lt_min")
    if pass_rate < safe_number(args.min_walk_forward_pass_rate_pct):
        blockers.append("walk_forward_pass_rate_lt_min")
    if total_net < 0:
        blockers.append("walk_forward_net_pnl_negative")
    passed = not blockers
    return {
        "generatedAtIso": utc_now_iso(),
        "schema": "quantgod.polymarket_copy_trader_walk_forward.v1",
        "status": "PASSED" if passed else "BLOCKED_PENDING_MORE_OUTCOMES",
        "passed": passed,
        "batches": len(batches),
        "windows": len(batches),
        "passRatePct": round(pass_rate, 4),
        "netPnlUSDC": round(total_net, 6),
        "rows": batches,
        "blockers": blockers,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def flatten_bucket_rows(quality_buckets: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "bySource",
        "byTrader",
        "bySourceTrader",
        "byMarketFamily",
        "byEntryPriceBand",
        "byTraderMarketFamily",
        "byTraderEntryPriceBand",
    ):
        rows.extend(row for row in quality_buckets.get(key) or [] if isinstance(row, dict))
    return rows


def write_outputs(
    payload: dict[str, Any],
    walk_forward: dict[str, Any],
    quality_buckets: dict[str, Any],
    rows: list[dict[str, Any]],
    runtime_dir: Path,
    dashboard_dir: Path | None,
) -> None:
    targets = [runtime_dir]
    if dashboard_dir:
        targets.append(dashboard_dir)
    replay_text = json.dumps(payload, ensure_ascii=False, indent=2)
    walk_text = json.dumps(walk_forward, ensure_ascii=False, indent=2)
    buckets_text = json.dumps(quality_buckets, ensure_ascii=False, indent=2)
    replay_fields = [
        "signalId",
        "sequence",
        "source",
        "channelName",
        "sourceBucket",
        "trader",
        "rank",
        "wallet",
        "walletPreview",
        "messageId",
        "messageDate",
        "marketSlug",
        "kreoTradeUrl",
        "polymarketMarketUrl",
        "side",
        "outcome",
        "marketTitle",
        "marketFamily",
        "entryPriceBand",
        "resolveDate",
        "telegramAmountUSDC",
        "smartScore",
        "backtestPnlUSDC",
        "winRatePct",
        "signalPrice",
        "entryPrice",
        "currentPrice",
        "exitPrice",
        "netPnlUSDC",
        "returnPct",
        "exitReason",
        "validatedExit",
        "matchScore",
        "matchedQuestion",
        "matchedUrl",
        "blockers",
    ]
    csv_rows = [{**row, "blockers": "|".join(row.get("blockers") or [])} for row in rows]
    bucket_fields = [
        "bucketType",
        "bucketKey",
        "status",
        "action",
        "rows",
        "matched",
        "samples",
        "wins",
        "losses",
        "openOrUnresolved",
        "netPnlUSDC",
        "markToMarketNetPnlUSDC",
        "profitFactor",
        "winRatePct",
        "minSamples",
        "rawStatus",
        "retainedPromotion",
        "promotionHoldUntilIso",
        "promotionHoldReason",
    ]
    for target in targets:
        atomic_write_text(target / SHADOW_REPLAY_NAME, replay_text)
        atomic_write_text(target / WALK_FORWARD_NAME, walk_text)
        atomic_write_text(target / SOURCE_BUCKETS_NAME, buckets_text)
        write_csv(target / SHADOW_REPLAY_LEDGER_NAME, csv_rows, replay_fields)
        write_csv(target / OUTCOME_LEDGER_NAME, csv_rows, replay_fields)
        write_csv(target / SOURCE_BUCKETS_LEDGER_NAME, flatten_bucket_rows(quality_buckets), bucket_fields)
        write_csv(
            target / WALK_FORWARD_LEDGER_NAME,
            walk_forward.get("rows") if isinstance(walk_forward.get("rows"), list) else [],
            ["batch", "samples", "netPnlUSDC", "profitFactor", "passed"],
        )


def prior_quality_buckets(runtime_dir: Path, dashboard_dir: Path | None) -> dict[str, Any]:
    paths = []
    if dashboard_dir:
        paths.append(dashboard_dir / SOURCE_BUCKETS_NAME)
    paths.append(runtime_dir / SOURCE_BUCKETS_NAME)
    for path in paths:
        payload = read_json(path)
        if payload:
            return payload
    return {}


def default_discovery_path(runtime_dir: Path, dashboard_dir: Path | None, explicit: str) -> Path:
    if explicit.strip():
        return Path(explicit).expanduser()
    if dashboard_dir and (dashboard_dir / DEFAULT_DISCOVERY_NAME).exists():
        return dashboard_dir / DEFAULT_DISCOVERY_NAME
    return runtime_dir / DEFAULT_DISCOVERY_NAME


def prior_replay_rows(runtime_dir: Path, dashboard_dir: Path | None) -> list[dict[str, Any]]:
    paths = []
    if dashboard_dir:
        paths.append(dashboard_dir / SHADOW_REPLAY_NAME)
    paths.append(runtime_dir / SHADOW_REPLAY_NAME)
    for path in paths:
        payload = read_json(path)
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        if rows:
            return [row for row in rows if isinstance(row, dict)]
    return []


def bucket_rows_by_group(quality_buckets: dict[str, Any], group: str) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("bucketKey") or ""): row
        for row in quality_buckets.get(group) or []
        if isinstance(row, dict) and str(row.get("bucketKey") or "")
    }


def hard_demote_bucket(row: dict[str, Any], args: argparse.Namespace) -> bool:
    samples = safe_int(row.get("samples") or row.get("outcomeSamples"))
    min_samples = safe_int(row.get("minSamples"))
    if min_samples and samples < min_samples:
        return False
    pf = safe_number(row.get("profitFactor"))
    net = safe_number(row.get("netPnlUSDC"))
    return pf <= safe_number(getattr(args, "promotion_hard_demote_profit_factor", 0.35)) or net <= safe_number(
        getattr(args, "promotion_hard_demote_net_pnl_usdc", -2.0)
    )


def retain_previous_promotions(
    quality_buckets: dict[str, Any],
    previous_buckets: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    hold_hours = max(0.0, safe_number(getattr(args, "promotion_hold_hours", 6.0)))
    if not hold_hours or not previous_buckets:
        return quality_buckets
    now = utc_now()
    default_until = now + timedelta(hours=hold_hours)
    retained_groups = ("bySource", "bySourceTrader", "byTraderMarketFamily", "byTraderEntryPriceBand")
    for group in retained_groups:
        previous = bucket_rows_by_group(previous_buckets, group)
        for row in quality_buckets.get(group) or []:
            if not isinstance(row, dict):
                continue
            if promoted_status(row):
                row.setdefault("promotionHoldUntilIso", default_until.isoformat())
                row.setdefault("retainedPromotion", False)
                continue
            key = str(row.get("bucketKey") or "")
            previous_row = previous.get(key)
            if not previous_row or not promoted_status(previous_row):
                continue
            hold_until = parse_iso_datetime(previous_row.get("promotionHoldUntilIso")) or default_until
            if hold_until < now or hard_demote_bucket(row, args):
                continue
            row["rawStatus"] = row.get("status")
            row["rawAction"] = row.get("action")
            row["status"] = "PROMOTABLE_PROBATION"
            row["action"] = "retain_micro_live_during_promotion_hold"
            row["retainedPromotion"] = True
            row["promotionHoldUntilIso"] = hold_until.isoformat()
            row["promotionHoldReason"] = "prior_promotable_bucket_hold"
    return refresh_quality_bucket_indexes(quality_buckets)


def infer_channel_name(row: dict[str, Any]) -> str:
    channel = str(row.get("channelName") or "").strip()
    if channel:
        return channel
    text = str(row.get("textPreview") or row.get("marketTitle") or row.get("matchedQuestion") or "")
    if "聪明钱包实时异动" in text:
        return "AI 1000x Polymarket"
    if "Smart Money" in text:
        return "预测市场内幕钱包监控"
    return ""


def signal_from_replay_row(row: dict[str, Any]) -> dict[str, Any]:
    signal_price = safe_number(row.get("signalPrice"), -1.0)
    source = row.get("source") or "telegram_replay_history"
    channel_name = infer_channel_name(row)
    source_bucket = row.get("sourceBucket") or (f"{source}:{channel_name}" if channel_name else "")
    return {
        "source": source,
        "channelName": channel_name,
        "sourceBucket": source_bucket,
        "userName": row.get("trader") or "",
        "rank": row.get("rank"),
        "wallet": row.get("wallet") or "",
        "walletPreview": row.get("walletPreview") or "",
        "side": row.get("side") or "",
        "outcome": row.get("outcome") or "",
        "amountUSDC": row.get("telegramAmountUSDC"),
        "priceCents": signal_price * 100.0 if signal_price >= 0 else None,
        "messageId": row.get("messageId"),
        "messageDate": row.get("messageDate") or "",
        "marketSlug": row.get("marketSlug") or row.get("matchedSlug") or "",
        "kreoTradeUrl": row.get("kreoTradeUrl") or "",
        "polymarketMarketUrl": row.get("polymarketMarketUrl") or "",
        "smartScore": row.get("smartScore"),
        "backtestPnlUSDC": row.get("backtestPnlUSDC"),
        "winRatePct": row.get("winRatePct"),
        "textPreview": row.get("textPreview") or row.get("marketTitle") or row.get("matchedQuestion") or "",
    }


def signal_from_shadow_candidate(index: int, row: dict[str, Any]) -> dict[str, Any]:
    price = safe_number(row.get("curPrice"), -1.0)
    generated = str(row.get("generatedAtIso") or "").strip()
    title = str(row.get("marketTitle") or "").strip()
    slug = str(row.get("marketSlug") or row.get("matchedSlug") or "").strip()
    outcome = str(row.get("outcome") or "").strip()
    trader = str(row.get("trader") or row.get("proxyWallet") or "").strip()
    return {
        "source": SELF_DISCOVERY_SOURCE,
        "channelName": SELF_DISCOVERY_CHANNEL,
        "sourceBucket": f"{SELF_DISCOVERY_SOURCE}:{SELF_DISCOVERY_CHANNEL}",
        "userName": trader,
        "wallet": row.get("proxyWallet") or "",
        "side": "BUY",
        "outcome": outcome,
        "priceCents": price * 100.0 if price > 0 else None,
        "messageId": f"self-{index}-{signal_identity(row)}",
        "messageDate": generated,
        "marketSlug": slug,
        "polymarketMarketUrl": row.get("url") or "",
        "textPreview": f"Self-discovered copy candidate: {title} | {outcome} | {trader}",
        "marketTitle": title,
    }


def current_discovery_candidate_signals(discovery: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    candidates = discovery.get("shadowCandidates") if isinstance(discovery.get("shadowCandidates"), list) else []
    signals: list[dict[str, Any]] = []
    for index, row in enumerate(candidates[: max(1, int(limit))]):
        if not isinstance(row, dict):
            continue
        if safe_number(row.get("curPrice"), -1.0) <= 0:
            continue
        if not (row.get("marketSlug") or row.get("marketTitle")):
            continue
        signals.append(signal_from_shadow_candidate(index, row))
    return signals


def signal_sort_timestamp(signal: dict[str, Any]) -> float:
    for field in ("messageDate", "generatedAtIso", "createdAt", "timestamp"):
        parsed = parse_iso_datetime(signal.get(field))
        if parsed is not None:
            return parsed.timestamp()
    return 0.0


def signal_sort_key(signal: dict[str, Any]) -> tuple[float, float, str]:
    return (
        signal_sort_timestamp(signal),
        safe_number(signal.get("messageId"), 0.0),
        str(signal.get("marketSlug") or ""),
    )


def merge_signals(current: list[dict[str, Any]], previous_rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    current_keys: set[str] = set()
    for row in previous_rows:
        signal = signal_from_replay_row(row)
        merged[signal_identity(signal)] = signal
    for signal in current:
        identity = signal_identity(signal)
        merged[identity] = signal
        current_keys.add(identity)
    current_rows = [signal for identity, signal in merged.items() if identity in current_keys]
    prior_rows = [signal for identity, signal in merged.items() if identity not in current_keys]
    current_rows.sort(key=signal_sort_key, reverse=True)
    prior_rows.sort(key=signal_sort_key, reverse=True)
    limit = max(1, int(max_rows))
    if len(current_rows) >= limit:
        rows = current_rows[:limit]
    else:
        rows = [*current_rows, *prior_rows[: limit - len(current_rows)]]
    rows.sort(key=signal_sort_key, reverse=True)
    return rows


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser()
    dashboard_dir = Path(args.dashboard_dir).expanduser() if args.dashboard_dir else None
    discovery_path = default_discovery_path(runtime_dir, dashboard_dir, args.discovery_path)
    discovery = read_json(discovery_path)
    telegram_channel = (discovery.get("sourceStatus") or {}).get("telegramChannel")
    telegram_sources = telegram_channel.get("sources") if isinstance(telegram_channel, dict) else {}
    telegram = telegram_sources.get("telethon") if isinstance(telegram_sources, dict) else {}
    signals = telegram.get("signals") if isinstance(telegram, dict) and isinstance(telegram.get("signals"), list) else []
    current_signals = [row for row in signals if isinstance(row, dict)][: max(1, int(args.max_signals))]
    current_discovery_signals = current_discovery_candidate_signals(discovery, args.max_discovery_candidates)
    previous_rows = prior_replay_rows(runtime_dir, dashboard_dir)
    previous_buckets = prior_quality_buckets(runtime_dir, dashboard_dir)
    signals = merge_signals(
        [*current_signals, *current_discovery_signals],
        previous_rows,
        max(1, int(args.max_ledger_signals)),
    )
    signal_slugs: list[str] = []
    for signal in signals:
        signal_slugs.append(normalize_market_slug(signal.get("marketSlug") or ""))
        if isinstance(signal.get("marketSlugs"), list):
            signal_slugs.extend(normalize_market_slug(item) for item in signal.get("marketSlugs") or [])
    signal_slugs = [slug for slug in signal_slugs if slug]
    events: list[dict[str, Any]] = []
    slug_markets: list[dict[str, Any]] = []
    fetch_errors: list[str] = []
    for closed in (False, True):
        try:
            events.extend(fetch_gamma_events(args.gamma_endpoint, args.gamma_limit, args.timeout, closed=closed))
        except Exception as exc:  # noqa: BLE001 - output needs compact diagnostics.
            fetch_errors.append(f"gamma_closed_{closed}:{type(exc).__name__}:{str(exc)[:160]}")
    if signal_slugs:
        slug_markets, slug_errors = fetch_gamma_markets_by_slug(
            args.gamma_markets_endpoint,
            signal_slugs,
            args.timeout,
            args.max_market_slug_lookups,
        )
        fetch_errors.extend(slug_errors)
    quotes = dedupe_quotes(build_market_quotes(events) + build_market_quotes(slug_markets))
    rows = [replay_signal(index, signal, quotes, args) for index, signal in enumerate(signals)]
    summary = build_summary(rows, args)
    quality_buckets = retain_previous_promotions(build_quality_buckets(rows, args), previous_buckets, args)
    payload = {
        "generatedAtIso": utc_now_iso(),
        "schema": "quantgod.polymarket_copy_trader_shadow_replay.v1",
        "status": summary["status"],
        "passed": summary["passed"],
        "validated": summary["passed"],
        "sourceDiscoveryPath": str(discovery_path),
        "readOnly": True,
        "placesOrders": False,
        "loadsWallet": False,
        "config": {
            "maxSignals": args.max_signals,
            "maxDiscoveryCandidates": args.max_discovery_candidates,
            "maxLedgerSignals": args.max_ledger_signals,
            "stakeUSDC": args.stake_usdc,
            "followSlippageCents": args.follow_slippage_cents,
            "takeProfitPct": args.take_profit_pct,
            "stopLossPct": args.stop_loss_pct,
            "minEntryPrice": args.min_entry_price,
            "maxEntryPrice": args.max_entry_price,
            "minMatchScore": args.min_match_score,
            "profitLockMinPeakUSDC": args.profit_lock_min_peak_usdc,
            "profitLockMaxDrawdownUSDC": args.profit_lock_max_drawdown_usdc,
            "profitLockMaxDrawdownPct": args.profit_lock_max_drawdown_pct,
        },
        "summary": summary,
        "metrics": summary,
        "collection": {
            "currentSignals": len(current_signals),
            "currentDiscoveryCandidates": len(current_discovery_signals),
            "priorReplayRows": len(previous_rows),
            "mergedSignals": len(signals),
        },
        "qualityBuckets": quality_buckets,
        "gamma": {
            "endpoint": args.gamma_endpoint,
            "marketsEndpoint": args.gamma_markets_endpoint,
            "eventsRead": len(events),
            "slugMarketsRead": len(slug_markets),
            "signalSlugs": len(set(signal_slugs)),
            "marketQuotes": len(quotes),
            "errors": fetch_errors,
        },
        "rows": rows,
        "nextAction": (
            "Replay produced validation files. If samples/pass-rate are still blocked, keep collecting "
            "Telegram and self-discovered copy outcomes until closed or bracket-exit evidence reaches the auto-unlock gate."
        ),
    }
    walk_forward = build_walk_forward(rows, args)
    write_outputs(payload, walk_forward, quality_buckets, rows, runtime_dir, dashboard_dir)
    print(
        f"{SHADOW_REPLAY_NAME}: {summary['status']} | "
        f"signals={summary['signals']} | matched={summary['matchedSignals']} | "
        f"validated={summary['validatedCandidates']} | pf={summary['profitFactor']} | "
        f"net={summary['netPnlUSDC']}"
    )
    print(
        f"{WALK_FORWARD_NAME}: {walk_forward['status']} | "
        f"batches={walk_forward['batches']} | passRate={walk_forward['passRatePct']} | "
        f"net={walk_forward['netPnlUSDC']}"
    )
    print(
        f"{SOURCE_BUCKETS_NAME}: weakBuckets={quality_buckets['quarantine']['weakBucketCount']} | "
        f"quarantinedTraders={len(quality_buckets['quarantine']['traders'])} | "
        f"promotedMicroBuckets={quality_buckets['microScalpPolicy']['promotedCompositeBucketCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
