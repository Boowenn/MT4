#!/usr/bin/env python3
"""Synchronize Polymarket micro-live software switches from validated evidence.

The tool only writes non-secret local runtime switches and the canary lock file.
It never prints, stores, or modifies private-key values. If the strategy gate
fails later, it re-locks the software switches.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from polymarket_governance_utils import atomic_write_text, utc_now_iso


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = REPO_ROOT / "Dashboard"
DEFAULT_REPO_ENV = REPO_ROOT / ".env.local"
DEFAULT_LAUNCHD_ENV = Path.home() / ".quantgod" / "launchd.env"
DEFAULT_LOCK_FILE = REPO_ROOT / "runtime" / "Polymarket_Canary_Isolated" / "REAL_MONEY_CANARY.lock"

COPY_DISCOVERY_NAME = "QuantGod_PolymarketCopyTraderDiscovery.json"
SHADOW_REPLAY_NAME = "QuantGod_PolymarketCopyTraderShadowReplay.json"
WALK_FORWARD_NAME = "QuantGod_PolymarketCopyTraderWalkForward.json"
ISOLATED_RUNTIME_NAME = "QuantGod_PolymarketIsolatedClobRuntime.json"
OUTPUT_NAME = "QuantGod_PolymarketMicroLiveUnlock.json"
LEDGER_NAME = "QuantGod_PolymarketMicroLiveUnlock.csv"
SCHEMA_VERSION = "quantgod.polymarket_micro_live_unlock.v1"

ENV_TARGETS_UNLOCKED = {
    "QG_POLYMARKET_REAL_EXECUTION": "true",
    "QG_POLYMARKET_CANARY_ACK": "REAL_MONEY_CANARY_OK",
    "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
    "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
    "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
    "QG_POLYMARKET_CHAIN_ID": "137",
}

ENV_TARGETS_LOCKED = {
    "QG_POLYMARKET_REAL_EXECUTION": "false",
    "QG_POLYMARKET_CANARY_ACK": "",
    "QG_POLYMARKET_CANARY_KILL_SWITCH": "true",
    "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
    "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
    "QG_POLYMARKET_CHAIN_ID": "137",
}

LEDGER_FIELDS = [
    "generated_at",
    "status",
    "strategy_gate_passed",
    "software_switches_unlocked",
    "private_key_configured",
    "real_execution",
    "kill_switch",
    "ack",
    "blockers",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--repo-env", default=str(DEFAULT_REPO_ENV))
    parser.add_argument("--launchd-env", default=str(DEFAULT_LAUNCHD_ENV))
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--min-shadow-samples", type=int, default=30)
    parser.add_argument("--min-walk-batches", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_json_candidate(name: str, runtime_dir: Path, dashboard_dir: Path) -> dict[str, Any]:
    for path in (dashboard_dir / name, runtime_dir / name):
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    return payload["data"]
                return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def passed(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").upper()
    return bool(payload.get("passed")) or status == "PASSED"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def env_file_has_value(path: Path, key: str) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    for raw in lines:
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or not line.startswith(f"{key}="):
            continue
        value = line.split("=", 1)[1].strip().strip("\"'")
        return bool(value)
    return False


def private_key_configured(paths: list[Path]) -> bool:
    if os.environ.get("QG_POLYMARKET_PRIVATE_KEY"):
        return True
    return any(env_file_has_value(path, "QG_POLYMARKET_PRIVATE_KEY") for path in paths)


def update_env_file(path: Path, values: dict[str, str]) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    seen: set[str] = set()
    updated: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        candidate = stripped[len("export "):] if stripped.startswith("export ") else stripped
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            updated.append(raw)
            continue
        key = candidate.split("=", 1)[0]
        if key in values:
            updated.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated.append(raw)
    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, "\n".join(updated).rstrip() + "\n")


def write_lock(path: Path, enabled: bool, generated_at: str, status: str) -> None:
    if enabled:
        payload = {
            "schema": SCHEMA_VERSION,
            "generatedAtIso": generated_at,
            "status": status,
            "ack": "REAL_MONEY_CANARY_OK",
            "source": "validated_copy_trader_shadow_replay_walk_forward",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, "REAL_MONEY_CANARY_OK\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


def strategy_gate(runtime_dir: Path, dashboard_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    discovery = read_json_candidate(COPY_DISCOVERY_NAME, runtime_dir, dashboard_dir)
    shadow = read_json_candidate(SHADOW_REPLAY_NAME, runtime_dir, dashboard_dir)
    walk = read_json_candidate(WALK_FORWARD_NAME, runtime_dir, dashboard_dir)
    isolated = read_json_candidate(ISOLATED_RUNTIME_NAME, runtime_dir, dashboard_dir)
    summary = discovery.get("summary") if isinstance(discovery.get("summary"), dict) else {}
    shadow_summary = shadow.get("summary") if isinstance(shadow.get("summary"), dict) else {}
    walk_summary = walk.get("summary") if isinstance(walk.get("summary"), dict) else {}
    source = discovery.get("sourceStatus") if isinstance(discovery.get("sourceStatus"), dict) else {}
    telegram = source.get("telegramChannel") if isinstance(source.get("telegramChannel"), dict) else {}
    shadow_samples = safe_int(
        shadow.get("samples")
        or shadow.get("outcomeSamples")
        or shadow.get("validatedCandidates")
        or shadow_summary.get("samples")
        or shadow_summary.get("outcomeSamples")
        or shadow_summary.get("validatedCandidates")
    )
    walk_batches = safe_int(walk.get("batches") or walk.get("windows") or walk_summary.get("batches") or walk_summary.get("windows"))
    telegram_active = safe_int(summary.get("telegramWallets")) > 0 or safe_int(summary.get("telegramSignals")) > 0 or bool(telegram.get("configured"))
    checks = {
        "shadowReplayPassed": passed(shadow),
        "shadowReplaySamplesOk": shadow_samples >= max(1, int(args.min_shadow_samples)),
        "walkForwardPassed": passed(walk),
        "walkForwardBatchesOk": walk_batches >= max(1, int(args.min_walk_batches)),
        "isolatedRuntimePrepared": bool(isolated.get("runtimePrepared")),
        "telegramSourceActive": telegram_active,
        "shadowCandidatesPresent": safe_int(summary.get("shadowCandidates")) > 0,
    }
    blockers = [key for key, value in checks.items() if not value]
    return {
        "passed": not blockers,
        "checks": checks,
        "blockers": blockers,
        "shadowReplay": {
            "status": shadow.get("status", "") or shadow_summary.get("status", ""),
            "samples": shadow_samples,
            "profitFactor": shadow.get("profitFactor", shadow_summary.get("profitFactor")),
            "netPnlUSDC": shadow.get("netPnlUSDC", shadow_summary.get("netPnlUSDC")),
        },
        "walkForward": {
            "status": walk.get("status", ""),
            "batches": walk_batches,
            "passRatePct": walk.get("passRatePct"),
            "netPnlUSDC": walk.get("netPnlUSDC"),
        },
        "summary": {
            "shadowCandidates": safe_int(summary.get("shadowCandidates")),
            "telegramWallets": safe_int(summary.get("telegramWallets")),
            "telegramSignals": safe_int(summary.get("telegramSignals")),
        },
    }


def snapshot(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir)
    repo_env = Path(args.repo_env).expanduser()
    launchd_env = Path(args.launchd_env).expanduser()
    lock_file = Path(args.lock_file).expanduser()
    generated = utc_now_iso()
    gate = strategy_gate(runtime_dir, dashboard_dir, args)
    software_unlocked = bool(gate["passed"])
    key_configured = private_key_configured([repo_env, launchd_env])
    env_targets = ENV_TARGETS_UNLOCKED if software_unlocked else ENV_TARGETS_LOCKED
    if not args.dry_run:
        update_env_file(repo_env, env_targets)
        update_env_file(launchd_env, env_targets)
        write_lock(lock_file, software_unlocked, generated, "MICRO_LIVE_SOFTWARE_UNLOCKED")
    if not software_unlocked:
        status = "MICRO_LIVE_LOCKED_BY_STRATEGY_GATE"
    elif key_configured:
        status = "MICRO_LIVE_READY"
    else:
        status = "MICRO_LIVE_SOFTWARE_UNLOCKED_PRIVATE_KEY_MISSING"
    return {
        "schema": SCHEMA_VERSION,
        "generatedAtIso": generated,
        "status": status,
        "strategyGatePassed": bool(gate["passed"]),
        "softwareSwitchesUnlocked": software_unlocked,
        "privateKeyConfigured": key_configured,
        "envTargets": {key: ("<set>" if key == "QG_POLYMARKET_CANARY_ACK" and value else value) for key, value in env_targets.items()},
        "repoEnvPath": str(repo_env),
        "launchdEnvPath": str(launchd_env),
        "lockFile": str(lock_file),
        "lockFileWritten": software_unlocked and not args.dry_run,
        "gate": gate,
        "safety": {
            "writesSecretValues": False,
            "logsPrivateKey": False,
            "orderSendAllowedByThisTool": False,
            "policyOrderSendAllowedAfterCredentialConfigured": software_unlocked and key_configured,
        },
        "nextAction": (
            "Software switches are open; configure QG_POLYMARKET_PRIVATE_KEY in the local env to allow the isolated executor preflight."
            if software_unlocked and not key_configured
            else "Micro-live software gate is ready; isolated executor still performs its own order-level preflight."
            if software_unlocked
            else "Strategy evidence gate failed; software switches were re-locked."
        ),
    }


def ledger_text(payload: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    env_targets = payload.get("envTargets") if isinstance(payload.get("envTargets"), dict) else {}
    writer.writerow(
        {
            "generated_at": payload["generatedAtIso"],
            "status": payload["status"],
            "strategy_gate_passed": payload["strategyGatePassed"],
            "software_switches_unlocked": payload["softwareSwitchesUnlocked"],
            "private_key_configured": payload["privateKeyConfigured"],
            "real_execution": env_targets.get("QG_POLYMARKET_REAL_EXECUTION", ""),
            "kill_switch": env_targets.get("QG_POLYMARKET_CANARY_KILL_SWITCH", ""),
            "ack": env_targets.get("QG_POLYMARKET_CANARY_ACK", ""),
            "blockers": " / ".join(payload.get("gate", {}).get("blockers") or []),
        }
    )
    return out.getvalue()


def write_outputs(payload: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    csv_text = ledger_text(payload)
    written: list[str] = []
    for base in (runtime_dir, dashboard_dir):
        if base is None:
            continue
        atomic_write_text(base / OUTPUT_NAME, text)
        atomic_write_text(base / LEDGER_NAME, csv_text)
        written.extend([str(base / OUTPUT_NAME), str(base / LEDGER_NAME)])
    return written


def main() -> int:
    args = parse_args()
    payload = snapshot(args)
    written = write_outputs(payload, Path(args.runtime_dir), Path(args.dashboard_dir) if args.dashboard_dir else None)
    print(
        f"POLYMARKET_MICRO_LIVE_UNLOCK | status={payload['status']} "
        f"| strategy_gate={str(payload['strategyGatePassed']).lower()} "
        f"| software_unlocked={str(payload['softwareSwitchesUnlocked']).lower()} "
        f"| private_key_configured={str(payload['privateKeyConfigured']).lower()} "
        f"| wrote={len(written)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
