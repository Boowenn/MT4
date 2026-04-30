"""Read-only MetaTrader 5 bridge for the local QuantGod dashboard.

The bridge intentionally exposes status, account, positions, orders, symbols,
and quote data only. It never sends orders, closes positions, cancels orders,
stores credentials, writes MT5 files, or changes the live preset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


SAFETY = {
    "readOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "mutatesMt5": False,
}

ENDPOINTS = {"status", "account", "positions", "orders", "symbols", "quote", "snapshot"}
DEFAULT_SYMBOL_LIMIT = 120
MAX_SYMBOL_LIMIT = 2000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_from_timestamp(value: Any) -> str:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return ""


def public_error(message: str, *, detail: Any = None) -> dict[str, Any]:
    payload = {
        "ok": False,
        "status": "UNAVAILABLE",
        "generatedAtIso": utc_now(),
        "error": str(message),
        "safety": SAFETY,
    }
    if detail not in (None, ""):
        payload["detail"] = detail
    return payload


def base_payload(endpoint: str) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "MT5_READONLY_BRIDGE_V1",
        "endpoint": endpoint,
        "generatedAtIso": utc_now(),
        "safety": SAFETY,
    }


def load_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        return None, public_error(
            "MetaTrader5 Python package is unavailable in this Python environment. On macOS, use the EA dashboard snapshot; the Python bridge is Windows-only/optional.",
            detail=str(exc),
        )
    return mt5, None


def maybe_asdict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if isinstance(value, dict):
        return dict(value)
    return {}


def safe_last_error(mt5: Any) -> Any:
    try:
        return mt5.last_error()
    except Exception:
        return None


def initialize_mt5(mt5: Any, terminal_path: str = "") -> tuple[bool, Any]:
    try:
        if terminal_path:
            return bool(mt5.initialize(path=terminal_path)), safe_last_error(mt5)
        return bool(mt5.initialize()), safe_last_error(mt5)
    except Exception as exc:
        return False, str(exc)


def terminal_payload(mt5: Any) -> dict[str, Any]:
    info = maybe_asdict(mt5.terminal_info())
    if not info:
        return {"connected": False}
    return {
        "connected": bool(info.get("connected")),
        "tradeAllowed": bool(info.get("trade_allowed")),
        "dllsAllowed": bool(info.get("dlls_allowed")),
        "name": info.get("name", ""),
        "company": info.get("company", ""),
        "path": info.get("path", ""),
        "dataPath": info.get("data_path", ""),
        "commonDataPath": info.get("commondata_path", ""),
        "codepage": info.get("codepage", 0),
        "maxBars": info.get("maxbars", 0),
    }


def account_payload(mt5: Any) -> dict[str, Any] | None:
    info = maybe_asdict(mt5.account_info())
    if not info:
        return None
    return {
        "login": info.get("login", 0),
        "server": info.get("server", ""),
        "name": info.get("name", ""),
        "currency": info.get("currency", ""),
        "company": info.get("company", ""),
        "balance": info.get("balance", 0.0),
        "equity": info.get("equity", 0.0),
        "profit": info.get("profit", 0.0),
        "margin": info.get("margin", 0.0),
        "marginFree": info.get("margin_free", 0.0),
        "marginLevel": info.get("margin_level", 0.0),
        "leverage": info.get("leverage", 0),
        "tradeAllowed": bool(info.get("trade_allowed")),
        "tradeExpert": bool(info.get("trade_expert")),
    }


def status_payload(mt5: Any, endpoint: str = "status") -> dict[str, Any]:
    payload = base_payload(endpoint)
    account = account_payload(mt5)
    terminal = terminal_payload(mt5)
    payload.update(
        {
            "status": "CONNECTED" if terminal.get("connected") and account else "INITIALIZED",
            "terminal": terminal,
            "account": account,
            "lastError": safe_last_error(mt5),
        }
    )
    return payload


def position_type_label(mt5: Any, value: Any) -> str:
    if value == getattr(mt5, "POSITION_TYPE_BUY", 0):
        return "buy"
    if value == getattr(mt5, "POSITION_TYPE_SELL", 1):
        return "sell"
    return str(value)


def order_type_label(mt5: Any, value: Any) -> str:
    mapping = {
        getattr(mt5, "ORDER_TYPE_BUY", -100): "buy",
        getattr(mt5, "ORDER_TYPE_SELL", -101): "sell",
        getattr(mt5, "ORDER_TYPE_BUY_LIMIT", -102): "buy_limit",
        getattr(mt5, "ORDER_TYPE_SELL_LIMIT", -103): "sell_limit",
        getattr(mt5, "ORDER_TYPE_BUY_STOP", -104): "buy_stop",
        getattr(mt5, "ORDER_TYPE_SELL_STOP", -105): "sell_stop",
        getattr(mt5, "ORDER_TYPE_BUY_STOP_LIMIT", -106): "buy_stop_limit",
        getattr(mt5, "ORDER_TYPE_SELL_STOP_LIMIT", -107): "sell_stop_limit",
    }
    return mapping.get(value, str(value))


def normalize_symbol_filter(symbol: str) -> str:
    return str(symbol or "").strip()


def get_positions(mt5: Any, symbol: str = "") -> dict[str, Any]:
    symbol = normalize_symbol_filter(symbol)
    raw_items = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if raw_items is None:
        raw_items = []
    items = []
    for item in raw_items:
        row = maybe_asdict(item)
        items.append(
            {
                "ticket": row.get("ticket", 0),
                "identifier": row.get("identifier", 0),
                "symbol": row.get("symbol", ""),
                "type": position_type_label(mt5, row.get("type")),
                "volume": row.get("volume", 0.0),
                "priceOpen": row.get("price_open", 0.0),
                "priceCurrent": row.get("price_current", 0.0),
                "sl": row.get("sl", 0.0),
                "tp": row.get("tp", 0.0),
                "profit": row.get("profit", 0.0),
                "swap": row.get("swap", 0.0),
                "magic": row.get("magic", 0),
                "comment": row.get("comment", ""),
                "time": row.get("time", 0),
                "timeIso": iso_from_timestamp(row.get("time")),
            }
        )
    return {"count": len(items), "symbol": symbol, "items": items}


def get_orders(mt5: Any, symbol: str = "") -> dict[str, Any]:
    symbol = normalize_symbol_filter(symbol)
    raw_items = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
    if raw_items is None:
        raw_items = []
    items = []
    for item in raw_items:
        row = maybe_asdict(item)
        items.append(
            {
                "ticket": row.get("ticket", 0),
                "symbol": row.get("symbol", ""),
                "type": order_type_label(mt5, row.get("type")),
                "volumeInitial": row.get("volume_initial", 0.0),
                "volumeCurrent": row.get("volume_current", 0.0),
                "priceOpen": row.get("price_open", 0.0),
                "priceCurrent": row.get("price_current", 0.0),
                "sl": row.get("sl", 0.0),
                "tp": row.get("tp", 0.0),
                "magic": row.get("magic", 0),
                "comment": row.get("comment", ""),
                "timeSetup": row.get("time_setup", 0),
                "timeSetupIso": iso_from_timestamp(row.get("time_setup")),
            }
        )
    return {"count": len(items), "symbol": symbol, "items": items}


def get_symbols(mt5: Any, group: str = "*", query: str = "", limit: int = DEFAULT_SYMBOL_LIMIT) -> dict[str, Any]:
    group = str(group or "*").strip() or "*"
    query = str(query or "").strip().lower()
    limit = max(0, min(int(limit or DEFAULT_SYMBOL_LIMIT), MAX_SYMBOL_LIMIT))
    raw_items = mt5.symbols_get(group=group)
    if raw_items is None:
        raw_items = []
    items = []
    for item in raw_items:
        row = maybe_asdict(item)
        text = " ".join(str(row.get(key, "")) for key in ("name", "description", "path")).lower()
        if query and query not in text:
            continue
        items.append(
            {
                "name": row.get("name", ""),
                "description": row.get("description", ""),
                "path": row.get("path", ""),
                "visible": bool(row.get("visible")),
                "selected": bool(row.get("select")),
                "currencyBase": row.get("currency_base", ""),
                "currencyProfit": row.get("currency_profit", ""),
                "digits": row.get("digits", 0),
                "point": row.get("point", 0.0),
                "spread": row.get("spread", 0),
                "tradeMode": row.get("trade_mode", 0),
                "volumeMin": row.get("volume_min", 0.0),
                "volumeMax": row.get("volume_max", 0.0),
                "volumeStep": row.get("volume_step", 0.0),
            }
        )
    returned = items[:limit] if limit else []
    return {
        "group": group,
        "query": query,
        "count": len(items),
        "returned": len(returned),
        "truncated": bool(limit and len(items) > len(returned)),
        "items": returned,
    }


def get_quote(mt5: Any, symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol_filter(symbol)
    if not symbol:
        return {"ok": False, "error": "symbol is required", "symbol": ""}
    info = maybe_asdict(mt5.symbol_info(symbol))
    if not info:
        return {"ok": False, "error": f"symbol not found: {symbol}", "symbol": symbol}
    tick = maybe_asdict(mt5.symbol_info_tick(symbol))
    if not tick:
        return {
            "ok": False,
            "error": f"tick unavailable for {symbol}; add it to Market Watch in MT5 if needed",
            "symbol": symbol,
            "visible": bool(info.get("visible")),
        }
    point = float(info.get("point") or 0.0)
    bid = float(tick.get("bid") or 0.0)
    ask = float(tick.get("ask") or 0.0)
    spread_points = ((ask - bid) / point) if point and ask and bid else 0.0
    return {
        "ok": True,
        "symbol": symbol,
        "visible": bool(info.get("visible")),
        "digits": info.get("digits", 0),
        "point": point,
        "bid": bid,
        "ask": ask,
        "last": tick.get("last", 0.0),
        "volume": tick.get("volume", 0),
        "spreadPoints": round(spread_points, 2),
        "time": tick.get("time", 0),
        "timeIso": iso_from_timestamp(tick.get("time")),
    }


def build_endpoint_payload(mt5: Any, args: argparse.Namespace) -> dict[str, Any]:
    endpoint = args.endpoint
    payload = status_payload(mt5, endpoint=endpoint)

    if endpoint == "status":
        return payload
    if endpoint == "account":
        payload["account"] = account_payload(mt5)
        payload["status"] = "CONNECTED" if payload["account"] else "NO_ACCOUNT"
        return payload
    if endpoint == "positions":
        payload["positions"] = get_positions(mt5, args.symbol)
        return payload
    if endpoint == "orders":
        payload["orders"] = get_orders(mt5, args.symbol)
        return payload
    if endpoint == "symbols":
        payload["symbols"] = get_symbols(mt5, args.group, args.query, args.limit)
        return payload
    if endpoint == "quote":
        quote = get_quote(mt5, args.symbol)
        payload["quote"] = quote
        payload["ok"] = bool(quote.get("ok"))
        if not payload["ok"]:
            payload["error"] = quote.get("error", "quote unavailable")
        return payload
    if endpoint == "snapshot":
        payload["positions"] = get_positions(mt5, args.symbol)
        payload["orders"] = get_orders(mt5, args.symbol)
        payload["symbols"] = get_symbols(mt5, args.group, args.query, args.symbols_limit)
        payload["quote"] = get_quote(mt5, args.symbol) if args.symbol else None
        payload["status"] = "CONNECTED" if payload.get("account") else payload.get("status", "INITIALIZED")
        return payload
    raise ValueError(f"unsupported endpoint: {endpoint}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantGod read-only MT5 bridge")
    parser.add_argument("--endpoint", choices=sorted(ENDPOINTS), default="snapshot")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--group", default="*")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=DEFAULT_SYMBOL_LIMIT)
    parser.add_argument("--symbols-limit", type=int, default=DEFAULT_SYMBOL_LIMIT)
    parser.add_argument("--terminal-path", default=os.environ.get("QG_MT5_TERMINAL_PATH", ""))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    mt5, error = load_mt5()
    if error:
        error["endpoint"] = args.endpoint
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 0

    initialized, init_error = initialize_mt5(mt5, args.terminal_path)
    if not initialized:
        payload = public_error("MT5 initialize failed", detail=init_error)
        payload["endpoint"] = args.endpoint
        payload["terminalPath"] = args.terminal_path
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        payload = build_endpoint_payload(mt5, args)
    except Exception as exc:
        payload = public_error(f"MT5 read-only query failed: {exc}")
        payload["endpoint"] = args.endpoint
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
