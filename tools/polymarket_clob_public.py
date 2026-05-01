#!/usr/bin/env python3
"""Public read-only Polymarket CLOB helpers.

These helpers only call public order-book endpoints and normalize Gamma market
token metadata. They never read wallet credentials, build orders, or write to a
Polymarket account.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any


CLOB_HOST = "https://clob.polymarket.com"

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


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
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


def normalize_outcome_tokens(market: dict[str, Any]) -> dict[str, Any]:
    outcomes = [str(item).strip() for item in parse_json_list(market.get("outcomes"))]
    prices = parse_json_list(market.get("outcomePrices"))
    token_ids = parse_json_list(market.get("clobTokenIds"))
    tokens: list[dict[str, Any]] = []
    for index, name in enumerate(outcomes):
        token_id = str(token_ids[index]).strip() if index < len(token_ids) else ""
        price = safe_number(prices[index], default=-1.0) if index < len(prices) else None
        if price is not None and 0.0 <= price <= 1.0:
            normalized_price = round(price * 100.0, 4)
        elif price is not None and 0.0 <= price <= 100.0:
            normalized_price = round(price, 4)
        else:
            normalized_price = None
        tokens.append(
            {
                "index": index,
                "outcome": name,
                "tokenId": token_id,
                "pricePct": normalized_price,
            }
        )
    yes = next((item for item in tokens if str(item.get("outcome", "")).lower() == "yes"), None)
    no = next((item for item in tokens if str(item.get("outcome", "")).lower() == "no"), None)
    if yes is None and tokens:
        yes = tokens[0]
    if no is None and len(tokens) > 1:
        no = tokens[1]
    return {
        "outcomeTokens": tokens,
        "yesTokenId": str((yes or {}).get("tokenId") or ""),
        "noTokenId": str((no or {}).get("tokenId") or ""),
        "yesPrice": (yes or {}).get("pricePct"),
        "noPrice": (no or {}).get("pricePct"),
    }


def request_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "QuantGod-Polymarket-CLOB-Public/1.0",
        },
        method="GET",
    )
    with public_urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_order_book(token_id: str, timeout: float = 4.0, host: str = CLOB_HOST) -> dict[str, Any]:
    token = str(token_id or "").strip()
    if not token:
        return {"status": "NO_TOKEN", "bids": [], "asks": []}
    url = f"{host.rstrip('/')}/book?token_id={urllib.parse.quote(token)}"
    try:
        payload = request_json(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - dashboard needs a compact non-secret diagnostic.
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}", "bids": [], "asks": []}
    if not isinstance(payload, dict):
        return {"status": "MALFORMED", "bids": [], "asks": []}
    bids = payload.get("bids") if isinstance(payload.get("bids"), list) else []
    asks = payload.get("asks") if isinstance(payload.get("asks"), list) else []
    return {"status": "OK", "bids": bids, "asks": asks, "raw": payload}


def _book_side_depth(rows: list[Any], side: str, limit: int = 8) -> tuple[float | None, float]:
    parsed: list[tuple[float, float]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        price = safe_number(item.get("price"), default=-1.0)
        size = safe_number(item.get("size"), default=0.0)
        if price < 0 or size <= 0:
            continue
        parsed.append((price, size))
    if not parsed:
        return None, 0.0
    parsed.sort(key=lambda row: row[0], reverse=(side == "bid"))
    best_price = parsed[0][0]
    notional = sum(price * size for price, size in parsed[: max(1, limit)])
    return best_price, round(notional, 4)


def summarize_order_book(book: dict[str, Any], depth_levels: int = 8) -> dict[str, Any]:
    if book.get("status") != "OK":
        return {
            "clobStatus": book.get("status") or "UNKNOWN",
            "clobBestBid": None,
            "clobBestAsk": None,
            "clobMidpoint": None,
            "clobSpread": None,
            "clobBidDepthUsd": 0.0,
            "clobAskDepthUsd": 0.0,
            "clobLiquidityUsd": 0.0,
            "clobDepthScore": 0.0,
        }
    best_bid, bid_depth = _book_side_depth(book.get("bids") or [], "bid", depth_levels)
    best_ask, ask_depth = _book_side_depth(book.get("asks") or [], "ask", depth_levels)
    midpoint = None
    spread = None
    if best_bid is not None and best_ask is not None:
        midpoint = round((best_bid + best_ask) / 2.0, 6)
        spread = round(abs(best_ask - best_bid), 6)
    liquidity = round(bid_depth + ask_depth, 4)
    depth_score = min(100.0, liquidity ** 0.5 * 2.8)
    if spread is not None:
        depth_score -= min(35.0, spread * 250.0)
    return {
        "clobStatus": "OK",
        "clobBestBid": best_bid,
        "clobBestAsk": best_ask,
        "clobMidpoint": midpoint,
        "clobSpread": spread,
        "clobBidDepthUsd": bid_depth,
        "clobAskDepthUsd": ask_depth,
        "clobLiquidityUsd": liquidity,
        "clobDepthScore": round(max(0.0, min(100.0, depth_score)), 2),
    }
