#!/usr/bin/env python3
"""Sync local MT5 account context into the isolated Strategy Tester root.

This copies the minimum local terminal account context needed for MT5's
Strategy Tester to recognize an account in portable isolated mode. It writes
only under the tester root, never launches MT5, and never edits live presets.
The target runtime directory is gitignored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5"
DEFAULT_TESTER_ROOT = DEFAULT_REPO_ROOT / "runtime" / "HFM_MT5_Tester_Isolated"
DEFAULT_LOGIN = "186054398"
DEFAULT_SERVER = "HFMarketsGlobal-Live12"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync HFM MT5 account context into isolated tester root.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--tester-root", default=str(DEFAULT_TESTER_ROOT))
    parser.add_argument("--login", default=DEFAULT_LOGIN)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--status", default="")
    parser.add_argument(
        "--allow-sensitive-account-context",
        action="store_true",
        help="Required: confirms copying local account context into gitignored isolated tester runtime.",
    )
    return parser.parse_args()


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def copy_file(src: Path, dst: Path, *, required: bool = False) -> dict[str, Any] | None:
    if not src.exists():
        if required:
            raise FileNotFoundError(src)
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "path": str(dst),
        "bytes": dst.stat().st_size,
        "sha256Prefix": sha256_prefix(dst),
    }


def copy_tree(src: Path, dst: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    if not src.exists():
        return copied
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        copied_file = copy_file(item, dst / rel)
        if copied_file:
            copied_file["relativePath"] = str(rel).replace("\\", "/")
            copied.append(copied_file)
    return copied


def path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    source_root = Path(args.source_root)
    tester_root = Path(args.tester_root)
    status_path = Path(args.status) if args.status else repo_root / "runtime" / "QuantGod_IsolatedTesterAccountContextStatus.json"
    login = str(args.login).strip()
    server = str(args.server).strip()

    if not args.allow_sensitive_account_context:
        raise SystemExit("Refusing to copy account context without --allow-sensitive-account-context")
    if not path_under(tester_root, repo_root / "runtime"):
        raise SystemExit(f"tester root must stay under repo runtime/: {tester_root}")
    if not (source_root / "terminal64.exe").exists():
        raise FileNotFoundError(f"source MT5 terminal missing: {source_root / 'terminal64.exe'}")
    if not (tester_root / "terminal64.exe").exists():
        raise FileNotFoundError(f"isolated tester terminal missing: {tester_root / 'terminal64.exe'}")

    copied_files: list[dict[str, Any]] = []
    copied_trees: list[dict[str, Any]] = []

    for name in ("accounts.dat", "servers.dat", "dnsperf.dat"):
        copied = copy_file(source_root / "Config" / name, tester_root / "Config" / name, required=(name == "accounts.dat"))
        if copied:
            copied["relativePath"] = f"Config/{name}"
            copied_files.append(copied)

    terminal_license = copy_file(source_root / "Config" / "terminal.lic", tester_root / "Config" / "terminal.lic")
    if terminal_license:
        terminal_license["relativePath"] = "Config/terminal.lic"
        copied_files.append(terminal_license)

    for rel in (
        Path("Bases") / "dns.dat",
        Path("Bases") / "symbols.raw",
    ):
        copied = copy_file(source_root / rel, tester_root / rel)
        if copied:
            copied["relativePath"] = str(rel).replace("\\", "/")
            copied_files.append(copied)

    server_tree = copy_tree(source_root / "Bases" / server, tester_root / "Bases" / server)
    if server_tree:
        copied_trees.append({
            "relativeRoot": f"Bases/{server}",
            "fileCount": len(server_tree),
            "sample": [
                {
                    "relativePath": item["relativePath"],
                    "bytes": item["bytes"],
                    "sha256Prefix": item["sha256Prefix"],
                }
                for item in server_tree[:12]
            ],
        })

    account_trade_root = tester_root / "Bases" / server / "trades" / login
    selected_symbols = tester_root / "Bases" / server / "symbols" / f"selected-{login}.dat"
    ready = (
        (tester_root / "Config" / "accounts.dat").exists()
        and (tester_root / "Config" / "servers.dat").exists()
        and (tester_root / "Bases" / server).exists()
        and (account_trade_root.exists() or selected_symbols.exists())
    )
    status = {
        "schemaVersion": 1,
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "mode": "LOCAL_ONLY_SYNC_TO_ISOLATED_TESTER",
        "sourceRoot": str(source_root),
        "testerRoot": str(tester_root),
        "login": login,
        "server": server,
        "ready": ready,
        "copiedFileCount": len(copied_files),
        "copiedTreeCount": len(copied_trees),
        "copiedFiles": [
            {
                "relativePath": item["relativePath"],
                "bytes": item["bytes"],
                "sha256Prefix": item["sha256Prefix"],
            }
            for item in copied_files
        ],
        "copiedTrees": copied_trees,
        "hardGuards": [
            "Local filesystem copy only; no network transfer.",
            "Writes only under repo runtime/HFM_MT5_Tester_Isolated.",
            "Does not launch terminal64.exe or Strategy Tester.",
            "Does not mutate live HFM presets or live-pilot Files.",
            "Generated ParamLab tester configs still set AllowLiveTrading=0.",
        ],
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Synced isolated tester account context: ready={ready}")
    print(f"Wrote {status_path}")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
