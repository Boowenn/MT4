#!/usr/bin/env python3
"""Unified live-trading client factory for QuantGod.

The factory gives QuantGod the broker-abstraction shape that QuantDinger has,
while keeping MT5 live mutation behind the guarded trading bridge.  Creating an
MT5 client does not grant trading authority; the client still needs the MT5
config, environment switch, authorization lock, limits, and audit ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import mt5_readonly_bridge
    import mt5_platform_store
    import mt5_trading_client
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parent))
    import mt5_readonly_bridge  # type: ignore
    import mt5_platform_store  # type: ignore
    import mt5_trading_client  # type: ignore


MODE = "LIVE_TRADING_FACTORY_V1"
SUPPORTED_BROKERS = {"MT5", "HFM_MT5"}


def readonly_payload(endpoint: str, *, symbol: str = "", group: str = "*", query: str = "", limit: int = 120, terminal_path: str = "") -> dict[str, Any]:
    mt5, error = mt5_readonly_bridge.load_mt5()
    if error:
        return error
    initialized, init_error = mt5_readonly_bridge.initialize_mt5(mt5, terminal_path)
    if not initialized:
        return mt5_readonly_bridge.public_error("MT5 initialize failed", detail=init_error)
    try:
        return mt5_readonly_bridge.build_endpoint_payload(
            mt5,
            argparse.Namespace(endpoint=endpoint, symbol=symbol, group=group, query=query, limit=limit, symbols_limit=limit, focus_symbol=symbol),
        )
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


class GuardedMt5Client:
    """Thin broker client wrapper around `mt5_trading_client`.

    The method names are intentionally similar to a generic broker client, but
    every call delegates to the guarded MT5 bridge.
    """

    broker = "MT5"

    def __init__(self, runtime_dir: Path | None = None, config_path: Path | None = None, exchange_config: dict[str, Any] | None = None):
        self.runtime_dir = runtime_dir or mt5_trading_client.DEFAULT_RUNTIME_DIR
        self.config_path = config_path
        self.exchange_config = exchange_config or {}

    def status(self) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("status", {}, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def profiles(self) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("profiles", {}, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def get_account_info(self) -> dict[str, Any]:
        return readonly_payload("account", terminal_path=str(self.exchange_config.get("mt5_terminal_path") or self.exchange_config.get("terminalPath") or ""))

    def get_positions(self, symbol: str = "") -> dict[str, Any]:
        return readonly_payload("positions", symbol=symbol, terminal_path=str(self.exchange_config.get("mt5_terminal_path") or self.exchange_config.get("terminalPath") or ""))

    def get_orders(self, symbol: str = "") -> dict[str, Any]:
        return readonly_payload("orders", symbol=symbol, terminal_path=str(self.exchange_config.get("mt5_terminal_path") or self.exchange_config.get("terminalPath") or ""))

    def get_symbols(self, group: str = "*", query: str = "", limit: int = 2000) -> dict[str, Any]:
        return readonly_payload("symbols", group=group, query=query, limit=limit, terminal_path=str(self.exchange_config.get("mt5_terminal_path") or self.exchange_config.get("terminalPath") or ""))

    def get_quote(self, symbol: str) -> dict[str, Any]:
        return readonly_payload("quote", symbol=symbol, terminal_path=str(self.exchange_config.get("mt5_terminal_path") or self.exchange_config.get("terminalPath") or ""))

    def save_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("save-profile", payload, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def login(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("login", payload, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("order", payload, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def place_market_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        side = str(request.get("side") or request.get("orderType") or "").lower()
        request["orderType"] = "buy" if side == "buy" else "sell"
        return self.place_order(request)

    def place_limit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        side = str(request.get("side") or request.get("orderType") or "").lower()
        request["orderType"] = "sell_limit" if side == "sell" else "buy_limit"
        return self.place_order(request)

    def close_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("close", payload, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def cancel_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("cancel", payload, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def enqueue_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_platform_store.run(self.runtime_dir, endpoint="enqueue", payload={**dict(payload), "dryRun": True})

    def quick_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        return mt5_platform_store.run(self.runtime_dir, endpoint="quick-trade", payload={**dict(payload), "dryRun": True})


def create_client(
    broker: str | dict[str, Any],
    *,
    market_category: str = "",
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> GuardedMt5Client:
    exchange_config: dict[str, Any] = dict(broker) if isinstance(broker, dict) else {}
    normalized = str(exchange_config.get("exchange_id") or exchange_config.get("broker") or broker or "").strip().upper()
    category = str(market_category or exchange_config.get("market_category") or exchange_config.get("marketCategory") or "").strip().lower()
    if normalized not in SUPPORTED_BROKERS:
        raise ValueError(f"unsupported broker: {broker}")
    if category and category not in {"forex", "fx", "multi_asset", "mt5"}:
        raise ValueError(f"unsupported MT5 market category: {market_category}")
    runtime_dir = runtime_dir or exchange_config.get("runtime_dir") or exchange_config.get("runtimeDir")
    config_path = config_path or exchange_config.get("config_path") or exchange_config.get("configPath")
    return GuardedMt5Client(
        runtime_dir=Path(runtime_dir) if runtime_dir else None,
        config_path=Path(config_path) if config_path else None,
        exchange_config=exchange_config,
    )


def describe_factory() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": MODE,
        "supportedBrokers": sorted(SUPPORTED_BROKERS),
        "clients": [
            {
                "broker": "MT5",
                "marketCategories": ["Forex", "multi_asset"],
                "implementation": "tools/mt5_trading_client.py",
                "platformStore": "tools/mt5_platform_store.py",
                "guardedMutation": True,
                "defaultDryRun": True,
                "queueDryRunRequired": True,
                "authorizationLockRequired": True,
                "auditLedgerRequired": True,
                "livePresetMutationAllowed": False,
            }
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantGod live trading factory")
    parser.add_argument("--broker", default="MT5")
    parser.add_argument("--market-category", default="Forex")
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--config", default="")
    parser.add_argument("--describe", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.describe:
        payload = describe_factory()
    else:
        client = create_client(
            args.broker,
            market_category=args.market_category,
            runtime_dir=args.runtime_dir or None,
            config_path=args.config or None,
        )
        payload = client.status()
        payload["factory"] = describe_factory()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
