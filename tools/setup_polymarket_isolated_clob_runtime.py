#!/usr/bin/env python3
"""Prepare the isolated Polymarket CLOB runtime without enabling real orders.

This tool creates a local isolated runtime root, audit ledgers, and a public
preflight manifest that downstream wallet policy can inspect. It never reads or
prints private-key values, never signs orders, and never sends CLOB orders.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
from typing import Any

from polymarket_governance_utils import atomic_write_text, stable_id, utc_now_iso


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = REPO_ROOT / "Dashboard"
DEFAULT_ISOLATED_ROOT = REPO_ROOT / "runtime" / "Polymarket_Canary_Isolated"
OUTPUT_NAME = "QuantGod_PolymarketIsolatedClobRuntime.json"
PREFLIGHT_LEDGER = "QuantGod_PolymarketIsolatedClobPreflightLedger.csv"
ORDER_INTENT_LEDGER = "QuantGod_PolymarketIsolatedClobOrderIntentLedger.csv"
POSITION_LEDGER = "QuantGod_PolymarketIsolatedClobPositionLedger.csv"
EXIT_LEDGER = "QuantGod_PolymarketIsolatedClobExitLedger.csv"
SCHEMA_VERSION = "quantgod.polymarket_isolated_clob_runtime.v1"

PREFLIGHT_FIELDS = [
    "generated_at",
    "status",
    "runtime_prepared",
    "adapter",
    "clob_host_configured",
    "py_clob_client_available",
    "real_execution_switch",
    "kill_switch_off",
    "private_key_configured",
    "wallet_write_allowed",
    "order_send_allowed",
    "blockers",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--isolated-root", default=os.environ.get("QG_POLYMARKET_ISOLATED_CLOB_ROOT", str(DEFAULT_ISOLATED_ROOT)))
    parser.add_argument("--adapter", default=os.environ.get("QG_POLYMARKET_WALLET_ADAPTER", "isolated_clob"))
    parser.add_argument("--clob-host", default=os.environ.get("QG_POLYMARKET_CLOB_HOST", "https://clob.polymarket.com"))
    parser.add_argument("--chain-id", type=int, default=int(os.environ.get("QG_POLYMARKET_CHAIN_ID", "137") or 137))
    parser.add_argument("--max-position-usdc", type=float, default=float(os.environ.get("QG_POLYMARKET_REAL_WALLET_MAX_POSITION_USDC", "1") or 1))
    parser.add_argument("--max-daily-loss-usdc", type=float, default=float(os.environ.get("QG_POLYMARKET_REAL_WALLET_MAX_DAILY_LOSS_USDC", "2") or 2))
    parser.add_argument("--max-open-positions", type=int, default=int(os.environ.get("QG_POLYMARKET_REAL_WALLET_MAX_OPEN_POSITIONS", "3") or 3))
    return parser.parse_args()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def py_clob_client_available() -> bool:
    return importlib.util.find_spec("py_clob_client") is not None


def ensure_runtime_tree(root: Path) -> dict[str, str]:
    dirs = {
        "root": root,
        "audit": root / "audit",
        "orders": root / "orders",
        "positions": root / "positions",
        "exits": root / "exits",
        "state": root / "state",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        root / ".gitignore",
        "*\n!.gitignore\n!README.md\n",
    )
    atomic_write_text(
        root / "README.md",
        (
            "# Polymarket Canary Isolated Runtime\n\n"
            "Local audit/runtime directory for the guarded CLOB adapter. "
            "Do not store private keys in this directory. Real orders remain "
            "blocked unless the external wallet policy and kill switch both pass.\n"
        ),
    )
    return {key: str(path) for key, path in dirs.items()}


def write_empty_csv(path: Path, fieldnames: list[str]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    atomic_write_text(path, output.getvalue())


def write_runtime_ledgers(root: Path) -> dict[str, str]:
    audit = root / "audit"
    write_empty_csv(audit / ORDER_INTENT_LEDGER, ["generated_at", "intent_id", "market_id", "side", "price", "size", "decision", "blockers"])
    write_empty_csv(audit / POSITION_LEDGER, ["generated_at", "position_id", "market_id", "state", "size", "entry_price", "notes"])
    write_empty_csv(audit / EXIT_LEDGER, ["generated_at", "position_id", "market_id", "exit_state", "reason", "notes"])
    return {
        "orderIntent": str(audit / ORDER_INTENT_LEDGER),
        "positions": str(audit / POSITION_LEDGER),
        "exits": str(audit / EXIT_LEDGER),
    }


def preflight_blockers(checks: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not checks["adapterIsolatedClob"]:
        blockers.append("wallet_adapter_not_isolated_clob")
    if not checks["clobHostConfigured"]:
        blockers.append("clob_host_missing")
    if not checks["pyClobClientAvailable"]:
        blockers.append("py_clob_client_missing")
    if not checks["realExecutionSwitch"]:
        blockers.append("real_execution_switch_false")
    if not checks["killSwitchOff"]:
        blockers.append("wallet_kill_switch_on_or_unset")
    if not checks["privateKeyConfigured"]:
        blockers.append("private_key_env_missing")
    return blockers


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    generated = utc_now_iso()
    isolated_root = Path(args.isolated_root).expanduser().resolve()
    dirs = ensure_runtime_tree(isolated_root)
    ledgers = write_runtime_ledgers(isolated_root)
    adapter = str(args.adapter or "").strip()
    host = str(args.clob_host or "").strip()
    checks = {
        "adapterIsolatedClob": adapter == "isolated_clob",
        "clobHostConfigured": bool(host),
        "pyClobClientAvailable": py_clob_client_available(),
        "realExecutionSwitch": env_bool("QG_POLYMARKET_REAL_EXECUTION"),
        "killSwitchOff": str(os.environ.get("QG_POLYMARKET_CANARY_KILL_SWITCH", "true")).strip().lower() == "false",
        "privateKeyConfigured": bool(os.environ.get("QG_POLYMARKET_PRIVATE_KEY")),
    }
    runtime_prepared = bool(dirs.get("root")) and checks["adapterIsolatedClob"] and checks["clobHostConfigured"] and checks["pyClobClientAvailable"]
    blockers = preflight_blockers(checks)
    status = "PREPARED_REAL_WALLET_BLOCKED" if runtime_prepared else "CONFIG_REQUIRED"
    snapshot = {
        "schema": SCHEMA_VERSION,
        "generatedAtIso": generated,
        "status": status,
        "mode": "POLYMARKET_ISOLATED_CLOB_RUNTIME_PREPARE_ONLY",
        "runtimePrepared": runtime_prepared,
        "isolatedRoot": str(isolated_root),
        "directories": dirs,
        "ledgers": ledgers,
        "adapter": {
            "name": adapter,
            "configured": checks["adapterIsolatedClob"],
            "pyClobClientAvailable": checks["pyClobClientAvailable"],
            "sharedPolymarketExecutorAllowed": False,
            "sharedMt5RuntimeAllowed": False,
        },
        "clob": {
            "hostConfigured": checks["clobHostConfigured"],
            "host": host if checks["clobHostConfigured"] else "",
            "chainId": int(args.chain_id),
        },
        "wallet": {
            "privateKeyConfigured": checks["privateKeyConfigured"],
            "funderConfigured": bool(os.environ.get("QG_POLYMARKET_FUNDER")),
            "neverEchoesSecretValues": True,
        },
        "runtimeSwitches": {
            "realExecutionSwitch": checks["realExecutionSwitch"],
            "killSwitchOff": checks["killSwitchOff"],
            "killSwitchRawState": "off" if checks["killSwitchOff"] else "on_or_unset",
        },
        "riskLimits": {
            "maxPositionUSDC": round(float(args.max_position_usdc), 4),
            "maxDailyLossUSDC": round(float(args.max_daily_loss_usdc), 4),
            "maxOpenPositions": max(1, int(args.max_open_positions)),
        },
        "safety": {
            "prepareOnly": True,
            "readsPrivateKeyValue": False,
            "logsPrivateKey": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutorLoop": False,
            "callsClobOrderApi": False,
            "mutatesMt5": False,
        },
        "preflight": {
            **checks,
            "passedForRealOrders": False,
            "blockers": blockers,
        },
        "runtimeId": "ISO-CLOB-" + stable_id(str(isolated_root), adapter, host, generated),
        "nextActions": [
            "Keep QG_POLYMARKET_REAL_EXECUTION=false and the kill switch on to prevent real orders.",
            "Only an external walletRiskPolicy, private-key env, kill switch, daily-loss check, and audited order candidate can allow isolated micro-live later.",
            "This tool only prepares the isolated runtime and audit files; it does not start an executor.",
        ],
    }
    return snapshot


def preflight_csv(snapshot: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PREFLIGHT_FIELDS, lineterminator="\n")
    writer.writeheader()
    preflight = snapshot["preflight"]
    writer.writerow(
        {
            "generated_at": snapshot["generatedAtIso"],
            "status": snapshot["status"],
            "runtime_prepared": snapshot["runtimePrepared"],
            "adapter": snapshot["adapter"]["name"],
            "clob_host_configured": snapshot["clob"]["hostConfigured"],
            "py_clob_client_available": snapshot["adapter"]["pyClobClientAvailable"],
            "real_execution_switch": snapshot["runtimeSwitches"]["realExecutionSwitch"],
            "kill_switch_off": snapshot["runtimeSwitches"]["killSwitchOff"],
            "private_key_configured": snapshot["wallet"]["privateKeyConfigured"],
            "wallet_write_allowed": snapshot["safety"]["walletWriteAllowed"],
            "order_send_allowed": snapshot["safety"]["orderSendAllowed"],
            "blockers": " / ".join(preflight["blockers"]),
        }
    )
    return output.getvalue()


def write_outputs(snapshot: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    csv_text = preflight_csv(snapshot)
    written: list[str] = []
    targets = [Path(snapshot["isolatedRoot"]), runtime_dir]
    if dashboard_dir is not None:
        targets.append(dashboard_dir)
    for base in targets:
        atomic_write_text(base / OUTPUT_NAME, text)
        atomic_write_text(base / PREFLIGHT_LEDGER, csv_text)
        written.extend([str(base / OUTPUT_NAME), str(base / PREFLIGHT_LEDGER)])
    return written


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args)
    written = write_outputs(
        snapshot,
        Path(args.runtime_dir),
        Path(args.dashboard_dir) if args.dashboard_dir else None,
    )
    print(
        f"{snapshot['mode']} | status={snapshot['status']} | prepared={str(snapshot['runtimePrepared']).lower()} "
        f"| order_send=false | wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
