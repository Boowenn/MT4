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
    import mt5_trading_client
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parent))
    import mt5_trading_client  # type: ignore


MODE = "LIVE_TRADING_FACTORY_V1"
SUPPORTED_BROKERS = {"MT5", "HFM_MT5"}


class GuardedMt5Client:
    """Thin broker client wrapper around `mt5_trading_client`.

    The method names are intentionally similar to a generic broker client, but
    every call delegates to the guarded MT5 bridge.
    """

    broker = "MT5"

    def __init__(self, runtime_dir: Path | None = None, config_path: Path | None = None):
        self.runtime_dir = runtime_dir or mt5_trading_client.DEFAULT_RUNTIME_DIR
        self.config_path = config_path

    def status(self) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("status", {}, runtime_dir=self.runtime_dir, config_path=self.config_path)

    def profiles(self) -> dict[str, Any]:
        return mt5_trading_client.execute_endpoint("profiles", {}, runtime_dir=self.runtime_dir, config_path=self.config_path)

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


def create_client(
    broker: str,
    *,
    market_category: str = "",
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> GuardedMt5Client:
    normalized = str(broker or "").strip().upper()
    category = str(market_category or "").strip().lower()
    if normalized not in SUPPORTED_BROKERS:
        raise ValueError(f"unsupported broker: {broker}")
    if category and category not in {"forex", "fx", "multi_asset", "mt5"}:
        raise ValueError(f"unsupported MT5 market category: {market_category}")
    return GuardedMt5Client(
        runtime_dir=Path(runtime_dir) if runtime_dir else None,
        config_path=Path(config_path) if config_path else None,
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
                "guardedMutation": True,
                "defaultDryRun": True,
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
