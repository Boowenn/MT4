#!/usr/bin/env python3
"""Create a short-lived AUTO_TESTER_WINDOW authorization lock.

This helper only writes the tester-only lock file. It never launches MT5,
never mutates live presets, and never sends orders. The guarded runner still
revalidates the lock, window, queue, live snapshot, and isolated tester root
before any Strategy Tester launch.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auto_tester_window_guard import LOCK_NAME, LOCK_PURPOSE


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = DEFAULT_REPO_ROOT / "runtime" / "mac_import" / "mt5_files_snapshot"
DEFAULT_TESTER_ROOT = DEFAULT_REPO_ROOT / "runtime" / "ParamLab_Tester_Sandbox" / "isolated_tester"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a guarded ParamLab Strategy Tester lock.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--hfm-root", default=str(DEFAULT_TESTER_ROOT), help="Pinned isolated tester root expected by the guard.")
    parser.add_argument("--output", default="")
    parser.add_argument("--ttl-minutes", type=int, default=90)
    parser.add_argument("--max-tasks", type=int, default=8)
    parser.add_argument("--source", default="cli")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    hfm_root = Path(args.hfm_root)
    output = Path(args.output) if args.output else runtime_dir / LOCK_NAME
    ttl_minutes = max(15, min(int(args.ttl_minutes or 90), 180))
    max_tasks = max(1, min(int(args.max_tasks or 8), 12))
    now = datetime.now(timezone.utc)
    lock = {
        "schemaVersion": 1,
        "purpose": LOCK_PURPOSE,
        "authorized": True,
        "testerOnly": True,
        "allowRunTerminal": True,
        "livePresetMutation": False,
        "allowOutsideWindow": False,
        "createdAtIso": now.isoformat(),
        "expiresAtIso": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "runtimeDir": str(runtime_dir),
        "hfmRoot": str(hfm_root),
        "maxTasks": max_tasks,
        "source": str(args.source or "cli"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "lockPath": str(output), "expiresAtIso": lock["expiresAtIso"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
