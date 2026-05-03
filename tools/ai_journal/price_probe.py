"""Read reference/current prices from QuantGod runtime reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def mid_price(price: dict[str, Any]) -> float | None:
    last = _num(price.get("last") or price.get("price"))
    if last is not None:
        return last
    bid = _num(price.get("bid"))
    ask = _num(price.get("ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return bid if bid is not None else ask


def spread_value(price: dict[str, Any]) -> float | None:
    spread = _num(price.get("spread") or price.get("spread_points") or price.get("spreadPoints"))
    if spread is not None:
        return abs(spread)
    bid = _num(price.get("bid"))
    ask = _num(price.get("ask"))
    if bid is not None and ask is not None:
        return abs(ask - bid)
    return None


def current_price_from_report(report: dict[str, Any]) -> dict[str, Any]:
    snapshot = _as_dict(report.get("snapshot"))
    price = _as_dict(snapshot.get("current_price"))
    return {
        "bid": _num(price.get("bid")),
        "ask": _num(price.get("ask")),
        "last": _num(price.get("last") or price.get("price")),
        "spread": spread_value(price),
        "mid": mid_price(price),
        "source": snapshot.get("source") or "unknown",
        "timeIso": price.get("timeIso") or price.get("time") or report.get("generatedAt"),
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def find_runtime_snapshot(runtime_dir: str | Path, symbol: str) -> dict[str, Any]:
    root = Path(runtime_dir).expanduser().resolve()
    candidates = [
        root / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json",
        root / f"QuantGod_BrokerRuntimeSnapshot_mt5-runtime_{symbol}.json",
        root / "QuantGod_Dashboard.json",
        root / "QuantGod_RuntimeSnapshot.json",
    ]
    for path in candidates:
        payload = _load_json(path)
        if not payload:
            continue
        if path.name.startswith("QuantGod_Dashboard"):
            current = payload.get("current_price") or payload.get("price") or payload.get("quote")
            if isinstance(current, dict):
                return {
                    "symbol": symbol,
                    "source": payload.get("source") or "dashboard_runtime",
                    "generatedAt": payload.get("generatedAt") or payload.get("timestamp"),
                    "current_price": current,
                }
        else:
            return payload
    return {}


def current_price_from_runtime(runtime_dir: str | Path, symbol: str) -> dict[str, Any]:
    snapshot = find_runtime_snapshot(runtime_dir, symbol)
    if not snapshot:
        return {"symbol": symbol, "mid": None, "source": "runtime_missing"}
    report = {"snapshot": snapshot, "generatedAt": snapshot.get("generatedAt")}
    price = current_price_from_report(report)
    price["symbol"] = symbol
    return price
