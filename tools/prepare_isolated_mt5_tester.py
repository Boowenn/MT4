#!/usr/bin/env python3
"""Prepare an isolated HFM MT5 Strategy Tester root for ParamLab.

The isolated root is a local terminal/profile sandbox used by
AUTO_TESTER_WINDOW when --tester-root is set. This script copies only the
terminal binaries, public server/config hints, QuantGod expert files, presets,
and tester profile inputs. It deliberately does not copy account/password
stores such as Config/accounts.dat or terminal license files.

Run sync_isolated_mt5_account_context.py afterwards, with explicit approval, if
the isolated Strategy Tester must inherit the local account context.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(r"C:\Program Files\HFM Metatrader 5")
DEFAULT_TESTER_ROOT = DEFAULT_REPO_ROOT / "runtime" / "HFM_MT5_Tester_Isolated"
SENSITIVE_CONFIG_NAMES = {
    "accounts.dat",
    "terminal.lic",
}
SAFE_CONFIG_NAMES = {
    "common.ini",
    "dnsperf.dat",
    "hotkeys.ini",
    "jupyter.ini",
    "metaeditor.ini",
    "servers.dat",
    "settings.ini",
    "terminal.ini",
}
TOP_LEVEL_FILES = (
    "terminal64.exe",
    "metatester64.exe",
    "MetaEditor64.exe",
    "Terminal.ico",
)
STRUCTURE_DIRS = (
    "Bases",
    "Config",
    "logs",
    "MQL5",
    "MQL5\\Experts",
    "MQL5\\Files",
    "MQL5\\Images",
    "MQL5\\Include",
    "MQL5\\Indicators",
    "MQL5\\Libraries",
    "MQL5\\logs",
    "MQL5\\Presets",
    "MQL5\\Profiles",
    "MQL5\\Profiles\\Tester",
    "MQL5\\Scripts",
    "MQL5\\Services",
    "Profiles",
    "Profiles\\Charts",
    "Profiles\\SymbolSets",
    "Profiles\\Templates",
    "Sounds",
    "Tester",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare QuantGod isolated HFM MT5 tester root.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--tester-root", default=str(DEFAULT_TESTER_ROOT))
    parser.add_argument("--status", default="")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing files in the isolated tester root.")
    return parser.parse_args()


def copy_file(src: Path, dst: Path, *, required: bool = False) -> bool:
    if not src.exists():
        if required:
            raise FileNotFoundError(src)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree_light(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    copied = 0
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        copy_file(item, dst / rel)
        copied += 1
    return copied


def join_rel(root: Path, rel: str) -> Path:
    parts = [part for part in str(rel).replace("\\", "/").split("/") if part]
    return root.joinpath(*parts)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    source_root = Path(args.source_root)
    tester_root = Path(args.tester_root)
    status_path = Path(args.status) if args.status else repo_root / "runtime" / "QuantGod_IsolatedTesterStatus.json"

    if not (source_root / "terminal64.exe").exists():
        raise FileNotFoundError(f"HFM source terminal missing: {source_root / 'terminal64.exe'}")

    for rel in STRUCTURE_DIRS:
        join_rel(tester_root, rel).mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    skipped_sensitive: list[str] = []

    for name in TOP_LEVEL_FILES:
        if copy_file(source_root / name, tester_root / name, required=(name == "terminal64.exe")):
            copied_files.append(name)

    config_root = source_root / "Config"
    for name in SAFE_CONFIG_NAMES:
        if copy_file(config_root / name, tester_root / "Config" / name):
            copied_files.append(f"Config/{name}")
    for name in SENSITIVE_CONFIG_NAMES:
        if (config_root / name).exists():
            skipped_sensitive.append(f"Config/{name}")

    certificates = config_root / "certificates"
    if certificates.exists():
        copied = copy_tree_light(certificates, tester_root / "Config" / "certificates")
        if copied:
            copied_files.append(f"Config/certificates ({copied})")

    for rel in ("MQL5\\Include", "MQL5\\Images", "MQL5\\Indicators", "MQL5\\Libraries", "MQL5\\Scripts", "MQL5\\Services", "MQL5\\Shared Projects"):
        copied = copy_tree_light(join_rel(source_root, rel), join_rel(tester_root, rel))
        if copied:
            copied_files.append(f"{rel.replace(chr(92), '/')} ({copied})")

    for rel in ("Profiles\\SymbolSets", "Profiles\\Templates", "Sounds"):
        copied = copy_tree_light(join_rel(source_root, rel), join_rel(tester_root, rel))
        if copied:
            copied_files.append(f"{rel.replace(chr(92), '/')} ({copied})")

    for name in ("QuantGod_MultiStrategy.mq5", "QuantGod_MultiStrategy.ex5"):
        if copy_file(repo_root / "MQL5" / "Experts" / name, tester_root / "MQL5" / "Experts" / name):
            copied_files.append(f"MQL5/Experts/{name}")

    preset_sources = [
        repo_root / "MQL5" / "Presets",
        source_root / "MQL5" / "Presets",
        source_root / "MQL5" / "Profiles" / "Tester",
    ]
    for preset_dir in preset_sources:
        if not preset_dir.exists():
            continue
        for preset in preset_dir.glob("QuantGod*.set"):
            if "LivePilot" in preset.name:
                continue
            target_dir = join_rel(tester_root / "MQL5", "Profiles\\Tester" if "Profiles" in str(preset_dir) else "Presets")
            if copy_file(preset, target_dir / preset.name):
                copied_files.append(str((target_dir / preset.name).relative_to(tester_root)).replace("\\", "/"))

    readme = tester_root / "QuantGod_IsolatedTester.README.txt"
    readme.write_text(
        "\n".join(
            [
                "QuantGod isolated HFM MT5 Strategy Tester root.",
                "Purpose: tester-only ParamLab runs through AUTO_TESTER_WINDOW.",
                "Do not attach live pilot charts or EA live trading here.",
                "Sensitive account/password stores are intentionally not copied by prepare_isolated_mt5_tester.py.",
                "AUTO_TESTER_WINDOW should use --tester-root pointing to this directory and --require-isolated-tester.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    status = {
        "schemaVersion": 1,
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "testerRoot": str(tester_root),
        "terminalPath": str(tester_root / "terminal64.exe"),
        "profileRoot": str(join_rel(tester_root, "MQL5\\Profiles\\Tester")),
        "expertPath": str(join_rel(tester_root, "MQL5\\Experts") / "QuantGod_MultiStrategy.ex5"),
        "sensitiveConfigSkipped": skipped_sensitive,
        "copiedCount": len(copied_files),
        "copiedSample": copied_files[:40],
        "ready": (tester_root / "terminal64.exe").exists() and join_rel(tester_root, "MQL5\\Profiles\\Tester").exists(),
        "hardGuards": [
            "Local copy only; no network transfer.",
            "Does not copy Config/accounts.dat or terminal.lic.",
            "Does not launch terminal64.exe or Strategy Tester.",
            "Does not mutate live HFM presets or live-pilot Files.",
        ],
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared isolated tester root: {tester_root}")
    print(f"Wrote {status_path}")
    print(f"ready={status['ready']} copied={status['copiedCount']} skippedSensitive={len(skipped_sensitive)}")
    return 0 if status["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
