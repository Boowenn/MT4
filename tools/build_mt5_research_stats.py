#!/usr/bin/env python3
"""Build read-only MT5 research statistics from local runtime CSVs.

This turns the Dashboard-only MT5 research aggregation into a reusable file
artifact for Governance Advisor and future adaptive controls. It reads local
CSV exports only, normalizes broker symbols through the MT5 symbol registry
normalizer, and never connects to MT5 or sends orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mt5_symbol_registry  # noqa: E402


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_MT5ResearchStats.json"
LEDGER_NAME = "QuantGod_MT5ResearchStatsLedger.csv"

TRADE_JOURNAL_NAME = "QuantGod_TradeJournal.csv"
CLOSE_HISTORY_NAME = "QuantGod_CloseHistory.csv"
OUTCOME_LABELS_NAME = "QuantGod_TradeOutcomeLabels.csv"
EVENT_LINKS_NAME = "QuantGod_TradeEventLinks.csv"

SAFETY = {
    "readOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "symbolSelectAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "mutatesMt5": False,
}

LEDGER_FIELDS = [
    "GeneratedAtIso",
    "Route",
    "CanonicalSymbol",
    "SourceSymbols",
    "BrokerSymbols",
    "AssetClass",
    "EntryRegime",
    "RegimeTimeframe",
    "JournalEvents",
    "EntryEvents",
    "ExitEvents",
    "ClosedTrades",
    "Wins",
    "Losses",
    "Flats",
    "WinRate",
    "ProfitFactor",
    "NetProfit",
    "GrossProfit",
    "GrossLoss",
    "AvgNet",
    "AvgDurationMinutes",
    "OutcomeLabels",
    "PositiveOutcomes",
    "NegativeOutcomes",
    "FlatOutcomes",
    "EventLinks",
    "ClosedLinks",
    "OpenLinks",
    "LinkCoverage",
    "SampleState",
    "LatestTime",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only MT5 research stats.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = read_text(path)
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def clean(value: Any) -> str:
    return str(value or "").strip()


def field(row: dict[str, Any], *names: str, default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return clean(value)
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(str(value).strip())
        if math.isfinite(parsed):
            return parsed
    except Exception:
        pass
    return default


def sorted_join(values: set[str]) -> str:
    return "/".join(sorted(value for value in values if value))


def latest_text(current: str, *values: Any) -> str:
    candidates = [clean(current), *(clean(value) for value in values)]
    candidates = [value for value in candidates if value]
    return sorted(candidates).pop() if candidates else ""


def symbol_mapping(symbol: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw = clean(symbol)
    if not raw:
        return {}
    key = mt5_symbol_registry.compact_symbol(raw)
    if key not in cache:
        cache[key] = mt5_symbol_registry.normalize_symbol_row({"name": raw})
    return cache[key]


def make_bucket(route: str, canonical: str, regime: str, timeframe: str, mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": route,
        "strategy": route,
        "canonicalSymbol": canonical,
        "symbol": canonical,
        "sourceSymbols": set(),
        "brokerSymbols": set(),
        "assetClass": mapping.get("assetClass", ""),
        "marketCategory": mapping.get("marketCategory", ""),
        "baseCurrency": mapping.get("baseCurrency", ""),
        "quoteCurrency": mapping.get("quoteCurrency", ""),
        "entryRegime": regime,
        "regime": regime,
        "regimeTimeframe": timeframe,
        "timeframe": timeframe,
        "sources": set(),
        "journalEvents": 0,
        "entryEvents": 0,
        "exitEvents": 0,
        "closedTrades": 0,
        "wins": 0,
        "losses": 0,
        "flats": 0,
        "netProfit": 0.0,
        "grossProfit": 0.0,
        "grossLoss": 0.0,
        "durationSum": 0.0,
        "durationCount": 0,
        "outcomeLabels": 0,
        "positiveOutcomes": 0,
        "negativeOutcomes": 0,
        "flatOutcomes": 0,
        "eventLinks": 0,
        "closedLinks": 0,
        "openLinks": 0,
        "latestEventTime": "",
        "latestCloseTime": "",
        "latestOutcomeTime": "",
        "latestLinkTime": "",
        "latestTime": "",
    }


def bucket_for(
    buckets: dict[tuple[str, str, str, str], dict[str, Any]],
    row: dict[str, Any],
    mapping_cache: dict[str, dict[str, Any]],
    *,
    regime_default: str = "UNKNOWN",
) -> dict[str, Any] | None:
    source_symbol = field(row, "Symbol", "symbol")
    mapping = symbol_mapping(source_symbol, mapping_cache)
    canonical = clean(mapping.get("canonicalSymbol")) or source_symbol
    if not canonical:
        return None
    route = field(row, "Strategy", "strategy", "Route", "route", default="QuantGod/Other")
    regime = field(row, "EntryRegime", "entryRegime", "Regime", "regime", "ExitRegime", "exitRegime", default=regime_default)
    timeframe = field(row, "RegimeTimeframe", "regimeTimeframe", "Timeframe", "timeframe")
    key = (route, canonical, regime or "UNKNOWN", timeframe)
    if key not in buckets:
        buckets[key] = make_bucket(route, canonical, regime or "UNKNOWN", timeframe, mapping)
    bucket = buckets[key]
    bucket["sourceSymbols"].add(source_symbol)
    broker_symbol = clean(mapping.get("brokerSymbol")) or source_symbol
    if broker_symbol and broker_symbol != canonical:
        bucket["brokerSymbols"].add(broker_symbol)
    source = field(row, "Source", "source")
    if source:
        bucket["sources"].add(source)
    return bucket


def sample_state(row: dict[str, Any]) -> str:
    closed = int(row.get("closedTrades") or 0)
    coverage = as_float(row.get("linkCoverage"))
    labels = int(row.get("outcomeLabels") or 0)
    if closed >= 10 and coverage >= 70 and labels >= min(10, closed):
        return "READY"
    if closed >= 5 and coverage >= 50:
        return "CANDIDATE"
    if closed >= 2 or int(row.get("journalEvents") or 0) > 0 or int(row.get("eventLinks") or 0) > 0:
        return "CAUTION"
    return "WARMUP"


def finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    closed = int(bucket["closedTrades"])
    win_rate = (bucket["wins"] / closed * 100.0) if closed else None
    if bucket["grossLoss"] > 0:
        profit_factor = bucket["grossProfit"] / bucket["grossLoss"]
    elif bucket["grossProfit"] > 0:
        profit_factor = 999.0
    else:
        profit_factor = None
    avg_net = bucket["netProfit"] / closed if closed else 0.0
    avg_duration = bucket["durationSum"] / bucket["durationCount"] if bucket["durationCount"] else None
    link_coverage = min(100.0, bucket["closedLinks"] / closed * 100.0) if closed else (100.0 if bucket["closedLinks"] else 0.0)

    row = {
        **{key: value for key, value in bucket.items() if not isinstance(value, set)},
        "sourceSymbols": sorted(bucket["sourceSymbols"]),
        "brokerSymbols": sorted(bucket["brokerSymbols"]),
        "sources": sorted(bucket["sources"]),
        "closedTrades": closed,
        "winRate": win_rate,
        "profitFactor": profit_factor,
        "avgNet": avg_net,
        "avgDurationMinutes": avg_duration,
        "linkCoverage": link_coverage,
    }
    row["sampleState"] = sample_state(row)
    return row


def summarize_by_symbol(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical = clean(row.get("canonicalSymbol"))
        if not canonical:
            continue
        if canonical not in grouped:
            grouped[canonical] = {
                "canonicalSymbol": canonical,
                "sourceSymbols": set(),
                "brokerSymbols": set(),
                "sliceCount": 0,
                "closedTrades": 0,
                "journalEvents": 0,
                "outcomeLabels": 0,
                "eventLinks": 0,
                "netProfit": 0.0,
                "latestTime": "",
            }
        item = grouped[canonical]
        item["sourceSymbols"].update(row.get("sourceSymbols") or [])
        item["brokerSymbols"].update(row.get("brokerSymbols") or [])
        item["sliceCount"] += 1
        item["closedTrades"] += int(row.get("closedTrades") or 0)
        item["journalEvents"] += int(row.get("journalEvents") or 0)
        item["outcomeLabels"] += int(row.get("outcomeLabels") or 0)
        item["eventLinks"] += int(row.get("eventLinks") or 0)
        item["netProfit"] += as_float(row.get("netProfit"))
        item["latestTime"] = latest_text(item["latestTime"], row.get("latestTime"))
    return [
        {
            **{key: value for key, value in item.items() if not isinstance(value, set)},
            "sourceSymbols": sorted(item["sourceSymbols"]),
            "brokerSymbols": sorted(item["brokerSymbols"]),
        }
        for item in sorted(grouped.values(), key=lambda row: (-int(row["closedTrades"]), row["canonicalSymbol"]))
    ]


def build_stats(runtime_dir: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    journal_rows = read_csv(runtime_dir / TRADE_JOURNAL_NAME)
    close_rows = read_csv(runtime_dir / CLOSE_HISTORY_NAME)
    outcome_rows = read_csv(runtime_dir / OUTCOME_LABELS_NAME)
    link_rows = read_csv(runtime_dir / EVENT_LINKS_NAME)

    mapping_cache: dict[str, dict[str, Any]] = {}
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in journal_rows:
        bucket = bucket_for(buckets, row, mapping_cache, regime_default="UNKNOWN")
        if not bucket:
            continue
        event_type = field(row, "EventType", "eventType").upper()
        bucket["journalEvents"] += 1
        if event_type == "ENTRY":
            bucket["entryEvents"] += 1
        elif event_type == "EXIT":
            bucket["exitEvents"] += 1
        bucket["latestEventTime"] = latest_text(bucket["latestEventTime"], field(row, "EventTime", "eventTime"))
        bucket["latestTime"] = latest_text(bucket["latestTime"], bucket["latestEventTime"])

    for row in close_rows:
        bucket = bucket_for(buckets, row, mapping_cache, regime_default="UNKNOWN")
        if not bucket:
            continue
        net = as_float(field(row, "NetProfit", "netProfit"))
        duration = as_float(field(row, "DurationMinutes", "durationMinutes"))
        bucket["closedTrades"] += 1
        bucket["netProfit"] += net
        if net > 0:
            bucket["wins"] += 1
            bucket["grossProfit"] += net
        elif net < 0:
            bucket["losses"] += 1
            bucket["grossLoss"] += abs(net)
        else:
            bucket["flats"] += 1
        if duration > 0:
            bucket["durationSum"] += duration
            bucket["durationCount"] += 1
        bucket["latestCloseTime"] = latest_text(bucket["latestCloseTime"], field(row, "CloseTime", "closeTime"), field(row, "OpenTime", "openTime"))
        bucket["latestTime"] = latest_text(bucket["latestTime"], bucket["latestCloseTime"])

    for row in outcome_rows:
        bucket = bucket_for(buckets, row, mapping_cache, regime_default="UNKNOWN")
        if not bucket:
            continue
        label = field(row, "OutcomeLabel", "outcomeLabel").upper()
        bucket["outcomeLabels"] += 1
        if any(token in label for token in ("WIN", "TP", "POSITIVE")):
            bucket["positiveOutcomes"] += 1
        elif any(token in label for token in ("LOSS", "SL", "NEGATIVE")):
            bucket["negativeOutcomes"] += 1
        else:
            bucket["flatOutcomes"] += 1
        bucket["latestOutcomeTime"] = latest_text(bucket["latestOutcomeTime"], field(row, "LabelTimeServer", "labelTimeServer"), field(row, "LabelTimeLocal", "labelTimeLocal"), field(row, "CloseTime", "closeTime"))
        bucket["latestTime"] = latest_text(bucket["latestTime"], bucket["latestOutcomeTime"])

    for row in link_rows:
        bucket = bucket_for(buckets, row, mapping_cache, regime_default="UNKNOWN")
        if not bucket:
            continue
        status = field(row, "Status", "status").upper()
        exit_deal = field(row, "ExitDeal", "exitDeal")
        is_closed = status == "CLOSED" or bool(exit_deal and exit_deal != "0")
        bucket["eventLinks"] += 1
        if is_closed:
            bucket["closedLinks"] += 1
        else:
            bucket["openLinks"] += 1
        bucket["latestLinkTime"] = latest_text(bucket["latestLinkTime"], field(row, "CloseTime", "closeTime"), field(row, "OpenTime", "openTime"))
        bucket["latestTime"] = latest_text(bucket["latestTime"], bucket["latestLinkTime"])

    rows = [finalize_bucket(bucket) for bucket in buckets.values()]
    rows.sort(key=lambda row: (-int(row.get("closedTrades") or 0), -abs(as_float(row.get("netProfit"))), row.get("route", ""), row.get("canonicalSymbol", ""), row.get("entryRegime", "")))
    canonical_summary = summarize_by_symbol(rows)
    source_symbols = sorted({symbol for row in rows for symbol in row.get("sourceSymbols", [])})
    broker_symbols = sorted({symbol for row in rows for symbol in row.get("brokerSymbols", [])})

    return {
        "ok": True,
        "schemaVersion": 1,
        "mode": "MT5_RESEARCH_STATS_V1",
        "generatedAtIso": generated_at,
        "runtimeDir": str(runtime_dir),
        "source": "local_runtime_csv_symbol_registry_normalizer",
        "safety": SAFETY,
        "inputs": {
            "tradeJournal": {"file": TRADE_JOURNAL_NAME, "rows": len(journal_rows)},
            "closeHistory": {"file": CLOSE_HISTORY_NAME, "rows": len(close_rows)},
            "outcomeLabels": {"file": OUTCOME_LABELS_NAME, "rows": len(outcome_rows)},
            "eventLinks": {"file": EVENT_LINKS_NAME, "rows": len(link_rows)},
        },
        "summary": {
            "sliceCount": len(rows),
            "canonicalSymbolCount": len(canonical_summary),
            "sourceSymbolCount": len(source_symbols),
            "brokerSymbolCount": len(broker_symbols),
            "journalEvents": len(journal_rows),
            "closedTrades": len(close_rows),
            "outcomeLabels": len(outcome_rows),
            "eventLinks": len(link_rows),
            "readySlices": sum(1 for row in rows if row.get("sampleState") == "READY"),
            "candidateSlices": sum(1 for row in rows if row.get("sampleState") == "CANDIDATE"),
            "sourceSymbols": source_symbols,
            "brokerSymbols": broker_symbols,
        },
        "canonicalSymbolSummary": canonical_summary,
        "rows": rows,
    }


def ledger_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    generated_at = clean(payload.get("generatedAtIso"))
    rows = []
    for row in payload.get("rows", []):
        rows.append(
            {
                "GeneratedAtIso": generated_at,
                "Route": row.get("route", ""),
                "CanonicalSymbol": row.get("canonicalSymbol", ""),
                "SourceSymbols": sorted_join(set(row.get("sourceSymbols") or [])),
                "BrokerSymbols": sorted_join(set(row.get("brokerSymbols") or [])),
                "AssetClass": row.get("assetClass", ""),
                "EntryRegime": row.get("entryRegime", ""),
                "RegimeTimeframe": row.get("regimeTimeframe", ""),
                "JournalEvents": row.get("journalEvents", 0),
                "EntryEvents": row.get("entryEvents", 0),
                "ExitEvents": row.get("exitEvents", 0),
                "ClosedTrades": row.get("closedTrades", 0),
                "Wins": row.get("wins", 0),
                "Losses": row.get("losses", 0),
                "Flats": row.get("flats", 0),
                "WinRate": "" if row.get("winRate") is None else round(as_float(row.get("winRate")), 4),
                "ProfitFactor": "" if row.get("profitFactor") is None else round(as_float(row.get("profitFactor")), 6),
                "NetProfit": round(as_float(row.get("netProfit")), 6),
                "GrossProfit": round(as_float(row.get("grossProfit")), 6),
                "GrossLoss": round(as_float(row.get("grossLoss")), 6),
                "AvgNet": round(as_float(row.get("avgNet")), 6),
                "AvgDurationMinutes": "" if row.get("avgDurationMinutes") is None else round(as_float(row.get("avgDurationMinutes")), 4),
                "OutcomeLabels": row.get("outcomeLabels", 0),
                "PositiveOutcomes": row.get("positiveOutcomes", 0),
                "NegativeOutcomes": row.get("negativeOutcomes", 0),
                "FlatOutcomes": row.get("flatOutcomes", 0),
                "EventLinks": row.get("eventLinks", 0),
                "ClosedLinks": row.get("closedLinks", 0),
                "OpenLinks": row.get("openLinks", 0),
                "LinkCoverage": round(as_float(row.get("linkCoverage")), 4),
                "SampleState": row.get("sampleState", ""),
                "LatestTime": row.get("latestTime", ""),
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    payload = build_stats(runtime_dir)
    write_json(output, payload)
    write_csv(ledger, ledger_rows(payload), LEDGER_FIELDS)
    if args.print_summary:
        print(json.dumps({"output": str(output), "ledger": str(ledger), "summary": payload["summary"], "canonicalSymbolSummary": payload["canonicalSymbolSummary"]}, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {output}")
        print(f"Wrote {ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
