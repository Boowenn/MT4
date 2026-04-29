#!/usr/bin/env python3
"""Build QuantDinger-style Polymarket market catalog evidence for QuantGod.

Outputs are local research artifacts only. This script never reads wallet
credentials, never sends orders, and never mutates MT5.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from build_polymarket_market_radar import DEFAULT_DASHBOARD_DIR, DEFAULT_ENDPOINT, DEFAULT_RUNTIME_DIR, atomic_write_text
from polymarket_quantdinger_core import build_market_catalog, build_related_asset_opportunities


MARKET_CATALOG_NAME = "QuantGod_PolymarketMarketCatalog.json"
MARKET_CATALOG_CSV = "QuantGod_PolymarketMarketCatalog.csv"
ASSET_OPPORTUNITY_NAME = "QuantGod_PolymarketAssetOpportunities.json"
ASSET_OPPORTUNITY_CSV = "QuantGod_PolymarketAssetOpportunities.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--limit", type=int, default=240)
    parser.add_argument("--top", type=int, default=120)
    parser.add_argument("--min-volume", type=float, default=0.0)
    parser.add_argument("--min-liquidity", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalized = dict(row)
        for key, value in list(normalized.items()):
            if isinstance(value, (list, dict)):
                normalized[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        writer.writerow(normalized)
    return output.getvalue()


def write_pair(payload: dict[str, Any], json_name: str, csv_name: str, rows_key: str, dirs: list[Path | None]) -> list[str]:
    written: list[str] = []
    json_blob = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    rows = payload.get(rows_key) if isinstance(payload.get(rows_key), list) else []
    if rows_key == "marketCatalog":
        fields = [
            "generatedAt",
            "catalogRank",
            "catalogId",
            "marketId",
            "eventId",
            "question",
            "eventTitle",
            "category",
            "probability",
            "volume",
            "volume24h",
            "liquidity",
            "divergence",
            "aiRuleScore",
            "risk",
            "relatedAssetCount",
            "suggestedShadowTrack",
            "polymarketUrl",
        ]
        generated_at = payload.get("generatedAt", "")
        csv_rows = [{**row, "generatedAt": generated_at} for row in rows]
    else:
        fields = [
            "generatedAt",
            "rank",
            "opportunityId",
            "marketId",
            "question",
            "assetSymbol",
            "assetMarket",
            "assetFamily",
            "directionalHint",
            "confidence",
            "suggestedAction",
            "marketRisk",
            "marketScore",
            "suggestedShadowTrack",
            "polymarketUrl",
        ]
        csv_rows = rows
    csv_blob = csv_text(csv_rows, fields)
    for base_dir in dirs:
        if base_dir is None:
            continue
        atomic_write_text(base_dir / json_name, json_blob)
        atomic_write_text(base_dir / csv_name, csv_blob)
        written.extend([str(base_dir / json_name), str(base_dir / csv_name)])
    return written


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir) if args.runtime_dir else None
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    catalog = build_market_catalog(
        endpoint=args.endpoint,
        limit=args.limit,
        top=args.top,
        min_volume=args.min_volume,
        min_liquidity=args.min_liquidity,
        timeout=args.timeout,
    )
    related = build_related_asset_opportunities(catalog)
    dirs = [runtime_dir, dashboard_dir]
    written = []
    written.extend(write_pair(catalog, MARKET_CATALOG_NAME, MARKET_CATALOG_CSV, "marketCatalog", dirs))
    written.extend(write_pair(related, ASSET_OPPORTUNITY_NAME, ASSET_OPPORTUNITY_CSV, "relatedAssetOpportunities", dirs))
    summary = catalog.get("summary") or {}
    related_summary = related.get("summary") or {}
    print(
        "Polymarket QuantDinger parity "
        f"{catalog.get('status')} | markets={summary.get('catalogMarkets', 0)} "
        f"| related={related_summary.get('opportunities', 0)} | wrote={len(written)}"
    )
    return 0 if catalog.get("status") != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
