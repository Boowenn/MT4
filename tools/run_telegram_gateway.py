#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from usdjpy_evidence_os.telegram_gateway import (
    build_notification_event,
    dispatch_pending,
    enqueue_event,
    gateway_status,
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.telegram.local")
    parser = argparse.ArgumentParser(description="QuantGod independent Telegram Gateway")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--source", default="manual_gateway_test")
    enqueue.add_argument("--topic", default="GATEWAY_TEST")
    enqueue.add_argument("--severity", default="INFO")
    enqueue.add_argument("--text", required=True)
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--send", action="store_true")
    dispatch.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    if args.command == "status":
        return emit(gateway_status(runtime_dir))
    if args.command == "enqueue":
        event = build_notification_event(args.source, args.topic, args.severity, args.text)
        return emit(enqueue_event(runtime_dir, event))
    if args.command == "dispatch":
        return emit(dispatch_pending(runtime_dir, send=args.send, limit=args.limit))
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
