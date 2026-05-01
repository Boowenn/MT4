from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .analysis_service import AnalysisService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod AI Analysis V1 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the 3-Agent analysis pipeline")
    run.add_argument("--symbol", required=True)
    run.add_argument("--timeframes", default="M15,H1,H4,D1")

    latest = sub.add_parser("latest", help="Return latest analysis report")
    latest.add_argument("--allow-empty", action="store_true")

    history = sub.add_parser("history", help="Return analysis history summary")
    history.add_argument("--symbol", default="")
    history.add_argument("--limit", type=int, default=20)

    item = sub.add_parser("history-item", help="Return a full history report")
    item.add_argument("--id", required=True)

    sub.add_parser("config", help="Return AI analysis config/status")

    args = parser.parse_args(argv)
    service = AnalysisService()
    if args.command == "run":
        timeframes = [item.strip() for item in args.timeframes.split(",") if item.strip()]
        payload = asyncio.run(service.run_analysis(args.symbol, timeframes))
    elif args.command == "latest":
        payload = service.latest()
        if payload is None and not args.allow_empty:
            payload = {"ok": False, "error": "latest analysis not found"}
    elif args.command == "history":
        payload = {"ok": True, "items": service.history(args.symbol or None, args.limit)}
    elif args.command == "history-item":
        payload = service.history_item(args.id) or {"ok": False, "error": "history item not found"}
    elif args.command == "config":
        payload = service.config_status()
    else:  # pragma: no cover - argparse prevents this
        parser.error("unsupported command")
        return 2

    _print_json(payload)
    return 0


def _print_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
