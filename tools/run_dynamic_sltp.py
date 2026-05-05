from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dynamic_sltp.calibrator import build_calibration, select_plan, write_sample_runtime
from tools.dynamic_sltp.schema import safety_payload
from tools.dynamic_sltp.telegram_text import build_telegram_text


def _symbols(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantGod dynamic SL/TP calibration CLI")
    parser.add_argument("command", choices=["status", "sample", "build", "plan", "telegram-text", "safety"])
    parser.add_argument("--runtime-dir", default="runtime")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol", default="USDJPYc")
    parser.add_argument("--strategy", default="")
    parser.add_argument("--direction", choices=["", "LONG", "SHORT"], default="")
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    runtime = Path(args.runtime_dir)
    if args.command == "safety":
        print(json.dumps(safety_payload(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "sample":
        path = write_sample_runtime(runtime, overwrite=args.overwrite)
        print(f"sampleWritten={path}")
        return 0
    if args.command == "status":
        path = runtime / "adaptive" / "QuantGod_DynamicSLTPCalibration.json"
        print(f"runtimeDir={runtime}")
        print(f"calibrationExists={path.exists()}")
        return 0

    payload = build_calibration(runtime, symbols=_symbols(args.symbols), min_samples=args.min_samples, write=not args.no_write)
    if args.command == "build":
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"plans={len(payload.get('plans', []))}")
            print(f"shadowOutcomes={payload.get('sourceCounts', {}).get('shadowOutcomes', 0)}")
        return 0
    if args.command == "plan":
        plan = select_plan(payload, args.symbol, strategy=args.strategy or None, direction=args.direction or None)
        print(json.dumps(plan or {"error": "未找到匹配计划"}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "telegram-text":
        print(build_telegram_text(payload, symbol=args.symbol if args.symbol else None))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
