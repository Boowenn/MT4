from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ai_analysis.market_data_collector import READ_ONLY_SAFETY, _mock_kline  # noqa: E402
from tools.ai_analysis.agents.base_agent import utc_now_iso  # noqa: E402
from tools.ai_analysis.config import default_runtime_dir  # noqa: E402

DEFAULT_BARS = 200
SUPPORTED_TF = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


def build_kline_payload(symbol: str, tf: str = "H1", bars: int = DEFAULT_BARS) -> dict[str, Any]:
    clean_symbol = _clean_symbol(symbol)
    timeframe = _clean_tf(tf)
    count = max(1, min(int(bars), 2000))
    mt5_payload = _mt5_kline(clean_symbol, timeframe, count)
    payload = {
        "ok": True,
        "mode": "QUANTGOD_MT5_CHART_READONLY_V1",
        "endpoint": "kline",
        "generatedAtIso": utc_now_iso(),
        "symbol": clean_symbol,
        "timeframe": timeframe,
        "safety": READ_ONLY_SAFETY,
        "source": mt5_payload.get("source", "mock_fallback"),
        "bars": mt5_payload.get("bars") or _mock_kline(clean_symbol, timeframe if timeframe in {"M15", "H1", "H4", "D1"} else "H1", count),
    }
    if mt5_payload.get("error"):
        payload["warning"] = mt5_payload["error"]
    return payload


def build_trades_payload(symbol: str, days: int = 30, runtime_dir: Path | None = None) -> dict[str, Any]:
    clean_symbol = _clean_symbol(symbol)
    root = Path(runtime_dir) if runtime_dir else default_runtime_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    files = [
        ("QuantGod_TradeJournal.csv", "trade_journal"),
        ("QuantGod_CloseHistory.csv", "close_history"),
    ]
    items: list[dict[str, Any]] = []
    for file_name, source_name in files:
        items.extend(_read_trade_file(root / file_name, source_name, clean_symbol, cutoff))
    items.sort(key=lambda row: str(row.get("timeIso") or row.get("timestamp") or ""))
    return {
        "ok": True,
        "mode": "QUANTGOD_MT5_CHART_READONLY_V1",
        "endpoint": "trades",
        "generatedAtIso": utc_now_iso(),
        "symbol": clean_symbol,
        "days": days,
        "count": len(items),
        "items": items,
        "safety": READ_ONLY_SAFETY,
        "source": "runtime_csv",
    }


def build_shadow_signals_payload(symbol: str, days: int = 7, runtime_dir: Path | None = None) -> dict[str, Any]:
    clean_symbol = _clean_symbol(symbol)
    root = Path(runtime_dir) if runtime_dir else default_runtime_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    files = [
        ("QuantGod_ShadowSignalLedger.csv", "shadow_signal"),
        ("QuantGod_ShadowCandidateLedger.csv", "shadow_candidate"),
        ("QuantGod_ShadowOutcomeLedger.csv", "shadow_outcome"),
        ("QuantGod_ShadowCandidateOutcomeLedger.csv", "shadow_candidate_outcome"),
    ]
    items: list[dict[str, Any]] = []
    for file_name, source_name in files:
        items.extend(_read_signal_file(root / file_name, source_name, clean_symbol, cutoff))
    items.sort(key=lambda row: str(row.get("timeIso") or row.get("timestamp") or ""))
    return {
        "ok": True,
        "mode": "QUANTGOD_MT5_CHART_READONLY_V1",
        "endpoint": "shadow-signals",
        "generatedAtIso": utc_now_iso(),
        "symbol": clean_symbol,
        "days": days,
        "count": len(items),
        "items": items[-1000:],
        "safety": READ_ONLY_SAFETY,
        "source": "runtime_csv",
    }


def _mt5_kline(symbol: str, tf: str, bars: int) -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except Exception:
        return {"source": "mock_fallback", "error": "MetaTrader5 package is unavailable"}

    initialized = False
    try:
        terminal_path = os.getenv("QG_MT5_TERMINAL_PATH", "").strip()
        initialized = bool(mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize())
        if not initialized:
            return {"source": "mock_fallback", "error": f"mt5 initialize failed: {mt5.last_error()}"}
        mt5_tf = {
            "M1": getattr(mt5, "TIMEFRAME_M1", None),
            "M5": getattr(mt5, "TIMEFRAME_M5", None),
            "M15": getattr(mt5, "TIMEFRAME_M15", None),
            "M30": getattr(mt5, "TIMEFRAME_M30", None),
            "H1": getattr(mt5, "TIMEFRAME_H1", None),
            "H4": getattr(mt5, "TIMEFRAME_H4", None),
            "D1": getattr(mt5, "TIMEFRAME_D1", None),
        }.get(tf)
        if mt5_tf is None:
            return {"source": "mock_fallback", "error": f"unsupported mt5 timeframe: {tf}"}
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, bars)
        if rates is None:
            return {"source": "mock_fallback", "error": f"copy_rates_from_pos failed: {mt5.last_error()}"}
        return {"source": "live_mt5_readonly", "bars": [_rate_to_bar(row) for row in list(rates)]}
    except Exception as error:
        return {"source": "mock_fallback", "error": str(error)}
    finally:
        if initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass


def _read_trade_file(path: Path, source_name: str, symbol: str, cutoff: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                row_symbol = _first(raw, "Symbol", "symbol", "BrokerSymbol", "brokerSymbol")
                if row_symbol and row_symbol.upper() != symbol.upper():
                    continue
                event_time = _parse_time(_first(raw, "OpenTimeIso", "OpenTime", "CloseTimeIso", "CloseTime", "TimeIso", "Time"))
                if event_time and event_time < cutoff:
                    continue
                price = _float_or_none(_first(raw, "OpenPrice", "EntryPrice", "PriceOpen", "ClosePrice", "PriceClose", "Price"))
                side = _normalize_side(_first(raw, "Type", "Side", "OrderType", "Direction"))
                rows.append(
                    {
                        "source": source_name,
                        "symbol": row_symbol or symbol,
                        "route": _first(raw, "Strategy", "Route", "route") or "UNKNOWN",
                        "side": side,
                        "event": "close" if "close" in source_name else "open",
                        "price": price,
                        "timeIso": event_time.isoformat().replace("+00:00", "Z") if event_time else None,
                        "profit": _float_or_none(_first(raw, "NetProfit", "Profit", "RealizedProfit", "Pnl")),
                        "ticket": _first(raw, "Ticket", "OrderTicket", "PositionTicket", "ticket"),
                        "raw": _compact_raw(raw),
                    }
                )
    except Exception:
        return rows
    return rows


def _read_signal_file(path: Path, source_name: str, symbol: str, cutoff: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                row_symbol = _first(raw, "Symbol", "symbol", "BrokerSymbol", "brokerSymbol")
                if row_symbol and row_symbol.upper() != symbol.upper():
                    continue
                event_time = _parse_time(_first(raw, "EventTimeIso", "TimeIso", "Timestamp", "Time"))
                if event_time and event_time < cutoff:
                    continue
                rows.append(
                    {
                        "source": source_name,
                        "symbol": row_symbol or symbol,
                        "route": _first(raw, "Strategy", "Route", "CandidateRoute", "route") or "UNKNOWN",
                        "side": _normalize_side(_first(raw, "Side", "SignalSide", "Direction", "Type")),
                        "signal": _first(raw, "Signal", "Decision", "Status", "Action") or "UNKNOWN",
                        "price": _float_or_none(_first(raw, "Price", "EntryPrice", "Close", "Bid", "Ask")),
                        "timeIso": event_time.isoformat().replace("+00:00", "Z") if event_time else None,
                        "blockedReason": _first(raw, "BlockedReason", "BlockReason", "Reason"),
                        "raw": _compact_raw(raw),
                    }
                )
    except Exception:
        return rows
    return rows


def _rate_to_bar(row: Any) -> dict[str, Any]:
    get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    timestamp = get("time")
    time_iso = None
    if timestamp is not None:
        time_iso = datetime.fromtimestamp(float(timestamp), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "timestamp": int(float(timestamp) * 1000) if timestamp is not None else None,
        "timeIso": time_iso,
        "open": float(get("open", 0.0)),
        "high": float(get("high", 0.0)),
        "low": float(get("low", 0.0)),
        "close": float(get("close", 0.0)),
        "volume": int(get("tick_volume", get("real_volume", 0)) or 0),
    }


def _clean_symbol(symbol: str) -> str:
    clean = str(symbol or "").strip()
    if not clean:
        raise ValueError("symbol is required")
    return clean[:64]


def _clean_tf(tf: str) -> str:
    value = str(tf or "H1").strip().upper()
    if value not in SUPPORTED_TF:
        raise ValueError(f"unsupported timeframe: {tf}")
    return value


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00"), text.replace(".", "-", 2)]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_side(value: str) -> str:
    upper = str(value or "").upper()
    if "BUY" in upper or upper in {"0", "LONG"}:
        return "BUY"
    if "SELL" in upper or upper in {"1", "SHORT"}:
        return "SELL"
    return upper or "UNKNOWN"


def _compact_raw(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in row.items() if value not in (None, "")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod MT5 chart read-only endpoints")
    sub = parser.add_subparsers(dest="endpoint", required=True)

    kline = sub.add_parser("kline")
    kline.add_argument("--symbol", required=True)
    kline.add_argument("--tf", default="H1")
    kline.add_argument("--bars", type=int, default=DEFAULT_BARS)

    trades = sub.add_parser("trades")
    trades.add_argument("--symbol", required=True)
    trades.add_argument("--days", type=int, default=30)
    trades.add_argument("--runtime-dir", default="")

    shadow = sub.add_parser("shadow-signals")
    shadow.add_argument("--symbol", required=True)
    shadow.add_argument("--days", type=int, default=7)
    shadow.add_argument("--runtime-dir", default="")

    args = parser.parse_args(argv)
    if args.endpoint == "kline":
        payload = build_kline_payload(args.symbol, args.tf, args.bars)
    elif args.endpoint == "trades":
        payload = build_trades_payload(args.symbol, args.days, Path(args.runtime_dir) if args.runtime_dir else None)
    else:
        payload = build_shadow_signals_payload(args.symbol, args.days, Path(args.runtime_dir) if args.runtime_dir else None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
