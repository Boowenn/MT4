#!/usr/bin/env python3
"""Configure the local Polymarket private-key env without echoing secrets."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from polymarket_governance_utils import atomic_write_text


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ENV = REPO_ROOT / ".env.local"
DEFAULT_LAUNCHD_ENV = Path.home() / ".quantgod" / "launchd.env"

SWITCHES = {
    "QG_POLYMARKET_REAL_EXECUTION": "true",
    "QG_POLYMARKET_CANARY_ACK": "REAL_MONEY_CANARY_OK",
    "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
    "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
    "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
    "QG_POLYMARKET_CHAIN_ID": "137",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-env", default=str(DEFAULT_REPO_ENV))
    parser.add_argument("--launchd-env", default=str(DEFAULT_LAUNCHD_ENV))
    parser.add_argument("--allow-single-entry", action="store_true", help="Do not require retyping the private key.")
    return parser.parse_args()


def normalize_private_key(value: str) -> str:
    cleaned = value.strip().strip("\"'")
    if cleaned.startswith("0X"):
        cleaned = "0x" + cleaned[2:]
    if cleaned and not cleaned.startswith("0x"):
        cleaned = "0x" + cleaned
    return cleaned


def looks_like_private_key(value: str) -> bool:
    raw = value[2:] if value.startswith("0x") else value
    return len(raw) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in raw)


def looks_like_address(value: str) -> bool:
    raw = value[2:] if value.startswith("0x") else value
    return len(raw) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in raw)


def parse_env(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def update_env(path: Path, values: dict[str, str]) -> None:
    lines = parse_env(path)
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
    try:
        path.chmod(0o600)
    except OSError:
        pass


def main() -> int:
    args = parse_args()
    private_key = normalize_private_key(getpass.getpass("Paste Polymarket private key (hidden input): "))
    if not args.allow_single_entry:
        confirm = normalize_private_key(getpass.getpass("Paste it again to confirm (hidden input): "))
        if private_key != confirm:
            print("POLYMARKET_PRIVATE_KEY_CONFIG | status=FAILED | reason=confirmation_mismatch")
            return 2
    if not looks_like_private_key(private_key):
        print("POLYMARKET_PRIVATE_KEY_CONFIG | status=FAILED | reason=invalid_private_key_format")
        return 2
    funder = input("Optional Polymarket funder/proxy wallet address (press Enter to skip): ").strip().strip("\"'")
    if funder and not looks_like_address(funder):
        print("POLYMARKET_PRIVATE_KEY_CONFIG | status=FAILED | reason=invalid_funder_address")
        return 2
    values = {**SWITCHES, "QG_POLYMARKET_PRIVATE_KEY": private_key}
    if funder:
        values["QG_POLYMARKET_FUNDER"] = funder
    targets = [Path(args.repo_env).expanduser(), Path(args.launchd_env).expanduser()]
    for target in targets:
        update_env(target, values)
    print(
        "POLYMARKET_PRIVATE_KEY_CONFIG | status=CONFIGURED "
        f"| private_key_configured=true | funder_configured={str(bool(funder)).lower()} | files={len(targets)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
