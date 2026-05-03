#!/usr/bin/env python3
"""QuantGod AI advisory outcome journal CLI.

Records and scores Telegram advisory outputs as local shadow samples. This CLI
never places orders, closes positions, cancels orders, mutates live presets,
stores credentials, or receives Telegram commands.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
for candidate in (str(REPO_ROOT), str(TOOLS_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from ai_journal.kill_switch import evaluate_family, settings_from_env  # noqa: E402
from ai_journal.reader import journal_path, kill_switch_path, latest_outcomes, latest_records, outcome_path  # noqa: E402
from ai_journal.scorer import score_latest  # noqa: E402
from ai_journal.schema import safety_payload  # noqa: E402
from ai_journal.summary import chinese_summary_text, summarize  # noqa: E402
from ai_journal.telegram_text import ensure_chinese_telegram_text  # noqa: E402

MODE = "QUANTGOD_AI_ADVISORY_JOURNAL_CLI_V1"


def runtime_dir_from_args(args: argparse.Namespace) -> Path:
    value = args.runtime_dir or os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR")
    return Path(value or (REPO_ROOT / "runtime")).expanduser().resolve()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def add_runtime_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-dir", default="", help="MT5/QuantGod runtime directory. Default: runtime/")


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    records = latest_records(runtime_dir, limit=int(args.limit))
    outcomes = latest_outcomes(runtime_dir, limit=int(args.limit))
    return {
        "ok": True,
        "mode": MODE,
        "runtimeDir": str(runtime_dir),
        "journalPath": str(journal_path(runtime_dir)),
        "outcomePath": str(outcome_path(runtime_dir)),
        "killSwitchPath": str(kill_switch_path(runtime_dir)),
        "records": len(records),
        "outcomes": len(outcomes),
        "settings": settings_from_env(),
        "safety": safety_payload(),
    }


def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    return {
        "ok": True,
        "mode": MODE,
        "runtimeDir": str(runtime_dir),
        "records": latest_records(runtime_dir, limit=int(args.limit)),
        "safety": safety_payload(),
    }


def cmd_score(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    return score_latest(runtime_dir, limit=int(args.limit), horizon=str(args.horizon), write=not bool(args.no_write))


def cmd_summary(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    payload = summarize(runtime_dir, limit=int(args.limit))
    if args.text:
        payload["text"] = ensure_chinese_telegram_text(chinese_summary_text(payload))
    return payload


def cmd_kill_switch(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    evaluation = evaluate_family(runtime_dir, str(args.symbol), str(args.direction).upper())
    return {"ok": True, "mode": MODE, "runtimeDir": str(runtime_dir), "evaluation": evaluation, "safety": safety_payload()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod AI advisory outcome journal")
    parser.add_argument("--runtime-dir", default="", help="MT5/QuantGod runtime directory. Default: runtime/")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show journal paths, counts and safety settings")
    add_runtime_arg(status)
    status.add_argument("--limit", type=int, default=20)
    status.set_defaults(func=cmd_status)

    list_cmd = sub.add_parser("list", help="List latest journal records")
    add_runtime_arg(list_cmd)
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=cmd_list)

    score = sub.add_parser("score", help="Score latest shadow advisory records against current runtime price")
    add_runtime_arg(score)
    score.add_argument("--limit", type=int, default=50)
    score.add_argument("--horizon", default="4h", choices=["1h", "4h", "24h", "manual"])
    score.add_argument("--no-write", action="store_true", help="Do not append outcome records")
    score.set_defaults(func=cmd_score)

    summary = sub.add_parser("summary", help="Summarize journal outcome quality")
    add_runtime_arg(summary)
    summary.add_argument("--limit", type=int, default=100)
    summary.add_argument("--text", action="store_true", help="Include Chinese Telegram-ready text")
    summary.set_defaults(func=cmd_summary)

    ks = sub.add_parser("kill-switch", help="Evaluate signal pause status for one symbol/direction family")
    add_runtime_arg(ks)
    ks.add_argument("--symbol", required=True)
    ks.add_argument("--direction", required=True, choices=["LONG", "SHORT"])
    ks.set_defaults(func=cmd_kill_switch)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        emit(args.func(args))
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "safety": safety_payload()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
