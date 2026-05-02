#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from notify.config import NotifyConfig
from notify.notify_service import (
    load_history,
    run_async,
    scan_once,
    send_ai_analysis_summary,
    send_daily_digest,
    send_event,
)


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_json_arg(value: str) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("JSON payload must be an object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod Telegram notification CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config", help="print redacted notification configuration")

    hist = sub.add_parser("history", help="print notification history")
    hist.add_argument("--limit", type=int, default=50)

    test = sub.add_parser("test", help="send a Telegram test message")
    test.add_argument("--message", default="QuantGod Telegram notification test")
    test.add_argument("--event-type", default="TEST")
    test.add_argument("--dry-run", action="store_true")

    send = sub.add_parser("send-event", help="send a formatted event")
    send.add_argument("--event-type", required=True)
    send.add_argument("--data-json", type=parse_json_arg, default={})
    send.add_argument("--dry-run", action="store_true")

    ai = sub.add_parser("ai-summary", help="send AI analysis summary from a report JSON")
    ai.add_argument("--report-file", required=True)
    ai.add_argument("--dry-run", action="store_true")

    digest = sub.add_parser("daily-digest", help="send a daily digest from runtime ledgers")
    digest.add_argument("--dry-run", action="store_true")

    scan = sub.add_parser("scan-once", help="best-effort one-shot runtime scan")
    scan.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    config = NotifyConfig.from_env()

    if args.cmd == "config":
        emit(config.public_dict())
        return 0
    if args.cmd == "history":
        emit(load_history(config, limit=args.limit))
        return 0
    if args.cmd == "test":
        emit(run_async(send_event(args.event_type, {"message": args.message}, config=config, dry_run=args.dry_run)))
        return 0
    if args.cmd == "send-event":
        emit(run_async(send_event(args.event_type, args.data_json, config=config, dry_run=args.dry_run)))
        return 0
    if args.cmd == "ai-summary":
        try:
            report = json.loads(Path(args.report_file).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            emit({"ok": False, "error": f"report_read_failed: {exc}"})
            return 2
        emit(run_async(send_ai_analysis_summary(report, config=config, dry_run=args.dry_run)))
        return 0
    if args.cmd == "daily-digest":
        emit(run_async(send_daily_digest(config=config, dry_run=args.dry_run)))
        return 0
    if args.cmd == "scan-once":
        emit(run_async(scan_once(config=config, dry_run=args.dry_run)))
        return 0
    emit({"ok": False, "error": "unknown_command"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
