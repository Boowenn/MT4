from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools.ga_multi_generation_stability.stability import build_report, read_report
    from tools.ga_multi_generation_stability.telegram_text import build_text
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from ga_multi_generation_stability.stability import build_report, read_report
    from ga_multi_generation_stability.telegram_text import build_text


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="QuantGod GA multi-generation stability evidence")
    parser.add_argument("--runtime-dir", default="runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    if args.command == "status":
        _print_json(read_report(runtime_dir))
        return 0
    if args.command == "build":
        _print_json(build_report(runtime_dir, write=bool(args.write)))
        return 0
    if args.command == "telegram-text":
        print(build_text(runtime_dir, refresh=bool(args.refresh)))
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
