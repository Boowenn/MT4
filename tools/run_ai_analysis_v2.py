#!/usr/bin/env python3
"""CLI for QuantGod AI Analysis V2."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
for candidate in (str(REPO_ROOT), str(TOOLS_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from ai_analysis.analysis_service_v2 import AnalysisServiceV2, phase3_ai_safety


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod AI Analysis V2 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframes", default="M15,H1,H4,D1")
    sub.add_parser("latest").add_argument("--allow-empty", action="store_true")
    p = sub.add_parser("history")
    p.add_argument("--symbol", default=None)
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("history-item")
    p.add_argument("--id", required=True)
    sub.add_parser("config")
    args = parser.parse_args(argv)
    service = AnalysisServiceV2()
    if args.cmd == "run":
        tfs = [item.strip().upper() for item in args.timeframes.split(",") if item.strip()]
        emit(await service.run_analysis(args.symbol, tfs))
    elif args.cmd == "latest":
        emit(service.latest(allow_empty=args.allow_empty))
    elif args.cmd == "history":
        emit(service.history(args.symbol, args.limit))
    elif args.cmd == "history-item":
        emit(service.history_item(args.id))
    elif args.cmd == "config":
        emit(service.config())
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "safety": phase3_ai_safety()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
