#!/usr/bin/env python3
"""QuantGod P2-3 local SQLite state store CLI.

All commands are local-only. Only the CLI can initialize or ingest evidence;
Dashboard API routes call read/query commands only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Allow direct execution from tools/ without installing a package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.state_store import StateStore, assert_state_store_safety, build_config, safety_payload  # noqa: E402
from tools.state_store.ingest import SUPPORTED_SOURCES, ingest_sources  # noqa: E402


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return min(parsed, 500)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod P2-3 SQLite state store")
    parser.add_argument("--repo-root", default=None, help="Backend repository root. Defaults to tools/..")
    parser.add_argument("--db", default=None, help="SQLite database path. Defaults to runtime/quantgod_state.sqlite")
    parser.add_argument("--runtime-dir", default=None, help="Runtime evidence directory")
    parser.add_argument("--dashboard-dir", default=None, help="Dashboard directory")
    parser.add_argument("--json", action="store_true", help="Compatibility flag; output is JSON by default")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create or migrate the SQLite schema")
    sub.add_parser("status", help="Show schema, table counts, and safety flags")
    sub.add_parser("config", help="Show resolved local state store config")

    ingest = sub.add_parser("ingest", help="Ingest local evidence into SQLite")
    ingest.add_argument(
        "--sources",
        nargs="+",
        default=["all"],
        help="Evidence sources: all, " + ", ".join(SUPPORTED_SOURCES),
    )

    events = sub.add_parser("events", help="Query normalized state events")
    events.add_argument("--limit", default=50, type=positive_int)
    events.add_argument("--event-type", default="")
    events.add_argument("--source", default="")

    ai_runs = sub.add_parser("ai-runs", help="Query advisory-only AI analysis runs")
    ai_runs.add_argument("--limit", default=50, type=positive_int)
    ai_runs.add_argument("--symbol", default="")

    vibe = sub.add_parser("vibe-strategies", help="Query research-only Vibe strategies")
    vibe.add_argument("--limit", default=50, type=positive_int)

    notifications = sub.add_parser("notifications", help="Query push-only notification events")
    notifications.add_argument("--limit", default=50, type=positive_int)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = build_config(
        repo_root=args.repo_root,
        db_path=args.db,
        runtime_dir=args.runtime_dir,
        dashboard_dir=args.dashboard_dir,
    )
    assert_state_store_safety()
    store = StateStore(config)

    try:
        if args.command == "init":
            emit(store.init())
        elif args.command == "status":
            emit(store.status())
        elif args.command == "config":
            emit({"ok": True, **config.as_dict()})
        elif args.command == "ingest":
            emit(ingest_sources(config, args.sources))
        elif args.command == "events":
            store.init()
            emit({"ok": True, "items": store.query_events(limit=args.limit, event_type=args.event_type, source=args.source), "safety": safety_payload()})
        elif args.command == "ai-runs":
            store.init()
            emit({"ok": True, "items": store.query_ai_runs(limit=args.limit, symbol=args.symbol), "safety": safety_payload()})
        elif args.command == "vibe-strategies":
            store.init()
            emit({"ok": True, "items": store.query_vibe_strategies(limit=args.limit), "safety": safety_payload()})
        elif args.command == "notifications":
            store.init()
            emit({"ok": True, "items": store.query_notifications(limit=args.limit), "safety": safety_payload()})
        else:  # pragma: no cover - argparse prevents this path
            raise ValueError(f"Unknown command: {args.command}")
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "safety": safety_payload()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
