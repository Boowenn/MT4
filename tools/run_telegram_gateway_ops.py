#!/usr/bin/env python3
from __future__ import annotations
"""CLI entrypoint for Telegram Gateway observability helpers."""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from tools.telegram_gateway_ops.status import (
        build_gateway_ops_status,
        collect_gateway_ops,
    )
    from tools.telegram_gateway_ops.telegram_text import gateway_ops_to_chinese_text
except ModuleNotFoundError:  # pragma: no cover
    from telegram_gateway_ops.status import (
        build_gateway_ops_status,
        collect_gateway_ops,
    )
    from telegram_gateway_ops.telegram_text import gateway_ops_to_chinese_text


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="QuantGod P4-5 Telegram Gateway Ops")
    parser.add_argument(
        "--runtime-dir",
        default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")),
    )
    parser.add_argument("--repo-root", default=str(root))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    collect = sub.add_parser("collect")
    collect.add_argument("--no-refresh", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    repo_root = Path(args.repo_root)

    if args.command == "status":
        return emit(build_gateway_ops_status(runtime_dir))
    if args.command == "collect":
        return emit(
            collect_gateway_ops(
                runtime_dir,
                repo_root=repo_root,
                refresh=not args.no_refresh,
            )
        )
    if args.command == "telegram-text":
        status = (
            collect_gateway_ops(runtime_dir, repo_root=repo_root, refresh=True)
            if args.refresh
            else build_gateway_ops_status(runtime_dir)
        )
        return emit({"ok": True, "text": gateway_ops_to_chinese_text(status), "status": status})
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
