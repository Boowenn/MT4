#!/usr/bin/env python3
"""CLI for QuantGod Phase 3 Vibe Coding."""

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

from vibe_coding.vibe_coding_service import VibeCodingService


def _load_payload(args) -> dict:
    if getattr(args, "payload_file", None):
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8-sig"))
    return {}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod Vibe Coding CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config")

    p = sub.add_parser("generate")
    p.add_argument("--description", default="")
    p.add_argument("--symbol", default=None)
    p.add_argument("--timeframe", "--tf", dest="timeframe", default=None)
    p.add_argument("--payload-file", default=None)

    p = sub.add_parser("iterate")
    p.add_argument("--strategy-id", default="")
    p.add_argument("--feedback", default="")
    p.add_argument("--payload-file", default=None)

    p = sub.add_parser("backtest")
    p.add_argument("--strategy-id", default="")
    p.add_argument("--symbol", default="EURUSDc")
    p.add_argument("--timeframe", "--tf", dest="timeframe", default="H1")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--version", default=None)
    p.add_argument("--payload-file", default=None)

    p = sub.add_parser("analyze")
    p.add_argument("--strategy-id", default="")
    p.add_argument("--payload-file", required=True)

    sub.add_parser("list")

    p = sub.add_parser("get")
    p.add_argument("--strategy-id", required=True)
    p.add_argument("--version", default=None)

    args = parser.parse_args(argv)
    service = VibeCodingService()
    payload = _load_payload(args)

    if args.cmd == "config":
        emit(service.config_payload())
    elif args.cmd == "generate":
        emit(await service.generate_strategy(payload.get("description") or args.description, payload.get("symbol") or args.symbol, payload.get("timeframe") or payload.get("tf") or args.timeframe))
    elif args.cmd == "iterate":
        emit(await service.iterate_strategy(payload.get("strategy_id") or payload.get("strategyId") or args.strategy_id, payload.get("feedback") or args.feedback, payload.get("backtest_result") or payload.get("backtestResult")))
    elif args.cmd == "backtest":
        emit(await service.run_backtest(payload.get("strategy_id") or payload.get("strategyId") or args.strategy_id, payload.get("symbol") or args.symbol, payload.get("timeframe") or payload.get("tf") or args.timeframe, int(payload.get("days") or args.days), payload.get("version") or args.version))
    elif args.cmd == "analyze":
        sid = payload.get("strategy_id") or payload.get("strategyId") or args.strategy_id
        emit(await service.analyze_backtest(sid, payload.get("backtest_result") or payload.get("backtestResult") or payload))
    elif args.cmd == "list":
        emit(service.list_strategies())
    elif args.cmd == "get":
        emit(service.get_strategy(args.strategy_id, args.version))
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
