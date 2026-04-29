#!/usr/bin/env python3
"""QuantDinger-style Polymarket research primitives for QuantGod.

This module is deliberately research-only. It reads public Gamma API market
data and produces local evidence objects. It must not load wallet secrets,
write orders, start executors, or mutate MT5.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from build_polymarket_market_radar import (
    DEFAULT_ENDPOINT,
    flatten_event,
    request_gamma_events,
    safe_number,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: Any, length: int = 20) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]


def compact_text(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return text[: limit - 1] + "..." if len(text) > limit else text


def normalize_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


@dataclass(frozen=True)
class AssetRule:
    symbol: str
    market: str
    family: str
    keywords: tuple[str, ...]
    bias: str
    rationale: str


ASSET_RULES: tuple[AssetRule, ...] = (
    AssetRule("BTC", "crypto", "crypto", ("bitcoin", "btc"), "crypto_beta", "Bitcoin event can alter broad crypto beta."),
    AssetRule("ETH", "crypto", "crypto", ("ethereum", "eth"), "crypto_beta", "Ethereum event can alter crypto beta and smart-contract risk."),
    AssetRule("SOL", "crypto", "crypto", ("solana", "sol"), "crypto_beta", "Solana event can alter high beta crypto appetite."),
    AssetRule("USDJPY", "mt5_research", "fx_macro", ("yen", "jpy", "bank of japan", "boj", "dollar", "usd", "fed", "rate", "interest"), "macro_fx", "Rates, central-bank and dollar events can affect USDJPY risk."),
    AssetRule("XAUUSD", "mt5_research", "macro_safe_haven", ("gold", "war", "conflict", "inflation", "cpi", "geopolitical", "iran", "russia", "ukraine", "israel", "taiwan"), "safe_haven", "Inflation and geopolitical events can affect gold safe-haven demand."),
    AssetRule("US_RATE", "macro_research", "rates", ("fed", "fomc", "rate cut", "rate hike", "inflation", "cpi", "jobs", "payroll"), "rates", "US rate expectations can reprice macro risk."),
    AssetRule("US_EQUITY", "equity_research", "equity_index", ("nasdaq", "s&p", "sp500", "stock market", "recession", "earnings"), "risk_assets", "Broad equity events can affect risk appetite."),
    AssetRule("NVDA", "equity_research", "single_stock", ("nvidia", "nvda", "gpu", "ai chip"), "tech_equity", "AI-chip events can affect NVDA-linked risk."),
    AssetRule("TSLA", "equity_research", "single_stock", ("tesla", "tsla", "elon"), "tech_equity", "Tesla events can affect TSLA-linked risk."),
    AssetRule("AAPL", "equity_research", "single_stock", ("apple", "aapl", "iphone"), "tech_equity", "Apple events can affect AAPL-linked risk."),
    AssetRule("MSFT", "equity_research", "single_stock", ("microsoft", "msft", "openai"), "tech_equity", "Microsoft/OpenAI events can affect MSFT-linked risk."),
)


def infer_related_assets(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("question", "eventTitle", "slug", "category", "polymarketUrl")
    ).lower()
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in ASSET_RULES:
        hits = [keyword for keyword in rule.keywords if keyword in text]
        if not hits or rule.symbol in seen:
            continue
        seen.add(rule.symbol)
        probability = safe_number(row.get("probability"), 50.0)
        divergence = safe_number(row.get("divergence"), 0.0)
        risk = str(row.get("risk") or "")
        confidence = max(5.0, min(95.0, safe_number(row.get("aiRuleScore"), 0.0) * (0.85 if risk == "high" else 1.0)))
        directional_hint = "watch"
        if probability >= 65 or divergence >= 15:
            directional_hint = "risk_event_yes"
        elif probability <= 35 or divergence <= -15:
            directional_hint = "risk_event_no"
        matched.append(
            {
                "symbol": rule.symbol,
                "market": rule.market,
                "family": rule.family,
                "bias": rule.bias,
                "directionalHint": directional_hint,
                "confidence": round(confidence, 2),
                "matchedKeywords": hits[:8],
                "rationale": rule.rationale,
            }
        )
    return matched


def market_catalog_key(row: dict[str, Any]) -> str:
    for key in ("marketId", "polymarketUrl", "slug", "question"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return value
    return stable_id(json.dumps(row, sort_keys=True, ensure_ascii=False))


def build_market_catalog(
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    limit: int = 240,
    top: int = 120,
    min_volume: float = 0.0,
    min_liquidity: float = 0.0,
    timeout: float = 15.0,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    try:
        events = request_gamma_events(endpoint, limit, timeout)
        best_by_key: dict[str, dict[str, Any]] = {}
        for event in events:
            for row in flatten_event(event, min_volume=min_volume, min_liquidity=min_liquidity):
                key = market_catalog_key(row)
                related_assets = infer_related_assets(row)
                enriched = {
                    **row,
                    "catalogId": stable_id("catalog", key),
                    "catalogKey": key,
                    "eventSlug": normalize_slug(row.get("eventTitle") or row.get("slug")),
                    "relatedAssets": related_assets,
                    "relatedAssetCount": len(related_assets),
                    "quantdingerParity": {
                        "marketCatalog": True,
                        "relatedAssetInference": True,
                        "walletExecution": False,
                    },
                }
                current = best_by_key.get(key)
                if current is None or safe_number(enriched.get("aiRuleScore")) > safe_number(current.get("aiRuleScore")):
                    best_by_key[key] = enriched
        catalog = list(best_by_key.values())
        catalog.sort(
            key=lambda item: (
                safe_number(item.get("aiRuleScore")),
                safe_number(item.get("volume24h")),
                safe_number(item.get("liquidity")),
                safe_number(item.get("volume")),
            ),
            reverse=True,
        )
        catalog = catalog[: max(1, top)]
        for idx, row in enumerate(catalog, start=1):
            row["catalogRank"] = idx
        return {
            "mode": "POLYMARKET_MARKET_CATALOG_V1_QUANTDINGER_PARITY",
            "generatedAt": generated_at,
            "status": "OK",
            "decision": "READ_ONLY_MARKET_CATALOG_NO_WALLET_WRITE",
            "source": {
                "endpoint": endpoint,
                "scanner": "Gamma API active events",
                "publicReadOnly": True,
                "loadsEnv": False,
                "walletWrite": False,
                "orderExecution": False,
                "mutatesMt5": False,
            },
            "summary": summarize_catalog(catalog, len(events)),
            "markets": catalog,
            "marketCatalog": catalog,
            "safety": safety_contract(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "mode": "POLYMARKET_MARKET_CATALOG_V1_QUANTDINGER_PARITY",
            "generatedAt": generated_at,
            "status": "ERROR",
            "decision": "READ_ONLY_MARKET_CATALOG_NO_WALLET_WRITE",
            "source": {
                "endpoint": endpoint,
                "publicReadOnly": True,
                "walletWrite": False,
                "orderExecution": False,
                "mutatesMt5": False,
            },
            "summary": summarize_catalog([], 0),
            "error": f"{type(exc).__name__}: {exc}",
            "markets": [],
            "marketCatalog": [],
            "safety": safety_contract(),
        }


def summarize_catalog(rows: list[dict[str, Any]], scanned_events: int) -> dict[str, Any]:
    categories: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    related = 0
    for row in rows:
        categories[str(row.get("category") or "unknown")] = categories.get(str(row.get("category") or "unknown"), 0) + 1
        risk_counts[str(row.get("risk") or "unknown")] = risk_counts.get(str(row.get("risk") or "unknown"), 0) + 1
        related += int(row.get("relatedAssetCount") or 0)
    top = rows[0] if rows else {}
    return {
        "scannedEvents": scanned_events,
        "catalogMarkets": len(rows),
        "relatedAssetLinks": related,
        "categories": categories,
        "risk": risk_counts,
        "topMarket": top.get("question", ""),
        "topScore": top.get("aiRuleScore"),
    }


def build_related_asset_opportunities(catalog: dict[str, Any]) -> dict[str, Any]:
    generated_at = str(catalog.get("generatedAt") or utc_now_iso())
    rows: list[dict[str, Any]] = []
    for market in catalog.get("markets") or catalog.get("marketCatalog") or []:
        if not isinstance(market, dict):
            continue
        for asset in market.get("relatedAssets") or []:
            if not isinstance(asset, dict):
                continue
            confidence = safe_number(asset.get("confidence"), 0.0)
            risk = str(market.get("risk") or "")
            suggested_action = "SHADOW_TRACK"
            if risk == "high" or confidence < 25:
                suggested_action = "OBSERVE_ONLY"
            elif confidence >= 55 and risk in {"low", "medium"}:
                suggested_action = "SHADOW_REVIEW"
            opportunity_id = stable_id(
                "related_asset",
                market.get("marketId"),
                market.get("question"),
                asset.get("symbol"),
                asset.get("directionalHint"),
            )
            rows.append(
                {
                    "opportunityId": opportunity_id,
                    "generatedAt": generated_at,
                    "marketId": market.get("marketId", ""),
                    "eventId": market.get("eventId", ""),
                    "question": compact_text(market.get("question"), 260),
                    "eventTitle": compact_text(market.get("eventTitle"), 180),
                    "polymarketUrl": market.get("polymarketUrl", ""),
                    "category": market.get("category", ""),
                    "probability": market.get("probability"),
                    "marketScore": market.get("aiRuleScore"),
                    "marketRisk": risk,
                    "assetSymbol": asset.get("symbol", ""),
                    "assetMarket": asset.get("market", ""),
                    "assetFamily": asset.get("family", ""),
                    "bias": asset.get("bias", ""),
                    "directionalHint": asset.get("directionalHint", ""),
                    "confidence": round(confidence, 2),
                    "suggestedAction": suggested_action,
                    "suggestedShadowTrack": market.get("suggestedShadowTrack", ""),
                    "matchedKeywords": asset.get("matchedKeywords", []),
                    "rationale": asset.get("rationale", ""),
                    "walletWriteAllowed": False,
                    "orderSendAllowed": False,
                    "mt5ExecutionAllowed": False,
                    "source": "polymarket_market_catalog_v1",
                }
            )
    rows.sort(
        key=lambda row: (
            safe_number(row.get("confidence")),
            safe_number(row.get("marketScore")),
            safe_number(row.get("probability")),
        ),
        reverse=True,
    )
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    return {
        "mode": "POLYMARKET_RELATED_ASSET_OPPORTUNITIES_V1_QUANTDINGER_PARITY",
        "generatedAt": generated_at,
        "status": str(catalog.get("status") or "OK"),
        "decision": "READ_ONLY_RELATED_ASSET_OPPORTUNITIES_NO_WALLET_WRITE_NO_MT5_EXECUTION",
        "summary": {
            "opportunities": len(rows),
            "uniqueMarkets": len({row.get("marketId") or row.get("question") for row in rows}),
            "uniqueAssets": len({row.get("assetSymbol") for row in rows}),
            "shadowReview": sum(1 for row in rows if row.get("suggestedAction") == "SHADOW_REVIEW"),
            "observeOnly": sum(1 for row in rows if row.get("suggestedAction") == "OBSERVE_ONLY"),
        },
        "relatedAssetOpportunities": rows,
        "assetOpportunities": rows,
        "safety": safety_contract(),
    }


def safety_contract() -> dict[str, bool]:
    return {
        "readsPrivateKey": False,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "startsExecutor": False,
        "mutatesMt5": False,
        "mt5ExecutionAllowed": False,
        "publicReadOnly": True,
    }


def polymarket_url_from_slug(slug: str) -> str:
    slug = str(slug or "").strip("/")
    if not slug:
        return "https://polymarket.com"
    return "https://polymarket.com/event/" + urllib.parse.quote(slug)
