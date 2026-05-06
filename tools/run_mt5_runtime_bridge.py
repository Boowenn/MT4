#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from mt5_runtime_bridge.reader import RuntimeBridgeReader  # noqa: E402
from mt5_runtime_bridge.schema import ALLOWED_TIMEFRAMES, bridge_safety_payload  # noqa: E402

DEFAULT_RUNTIME_DIR = r"C:\Program Files\HFM Metatrader 5\MQL5\Files"
DEFAULT_SYMBOLS = "USDJPYc"


def runtime_dir_from_args(args: argparse.Namespace) -> Path:
    value = args.runtime_dir or os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR") or DEFAULT_RUNTIME_DIR
    return Path(value).expanduser().resolve()


def parse_csv(value: str | None, fallback: str) -> list[str]:
    raw = value if value not in (None, "") else fallback
    out: list[str] = []
    for part in str(raw).split(","):
        item = part.strip()
        if item and item not in out:
            out.append(item)
    return out


def reader_from_args(args: argparse.Namespace) -> RuntimeBridgeReader:
    return RuntimeBridgeReader(
        runtime_dir_from_args(args),
        max_age_seconds=max(0, int(args.max_age_seconds)),
        allow_stale=bool(args.allow_stale),
    )


def cmd_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "QUANTGOD_MT5_RUNTIME_EVIDENCE_BRIDGE_CONFIG_V1",
        "defaultRuntimeDir": DEFAULT_RUNTIME_DIR,
        "defaultSymbols": DEFAULT_SYMBOLS,
        "allowedTimeframes": list(ALLOWED_TIMEFRAMES),
        "safety": bridge_safety_payload(),
    }


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    symbols = parse_csv(args.symbols, DEFAULT_SYMBOLS)
    return reader_from_args(args).status(symbols)


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    return reader_from_args(args).validate_symbol(args.symbol)


def cmd_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    timeframes = parse_csv(args.timeframes, ",".join(ALLOWED_TIMEFRAMES))
    payload = reader_from_args(args).collect_for_ai_snapshot(args.symbol, timeframes)
    return {"ok": not payload.get("fallback", True), "symbol": args.symbol, "snapshot": payload, "safety": bridge_safety_payload()}


def cmd_sample(args: argparse.Namespace) -> dict[str, Any]:
    symbols = parse_csv(args.symbols, DEFAULT_SYMBOLS)
    reader = RuntimeBridgeReader(runtime_dir_from_args(args), max_age_seconds=max(0, int(args.max_age_seconds)), allow_stale=True)
    result = reader.write_sample_files(symbols, overwrite=bool(args.overwrite))
    result["status"] = reader.status(symbols)
    return result


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-dir", default="", help="MT5/HFM EA runtime files directory. Defaults to QG_RUNTIME_DIR/QG_MT5_FILES_DIR.")
    parser.add_argument("--max-age-seconds", type=int, default=int(os.environ.get("QG_MT5_RUNTIME_MAX_AGE_SECONDS", "1800") or "1800"), help="Freshness threshold. Use 0 to disable freshness checks.")
    parser.add_argument("--allow-stale", action="store_true", help="Allow stale runtime snapshots for diagnostics only.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod MT5 runtime evidence bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="Show bridge defaults and safety flags")
    config.set_defaults(func=cmd_config)

    status = sub.add_parser("status", help="Check runtime directory and symbol freshness")
    add_common_args(status)
    status.add_argument("--symbols", default=DEFAULT_SYMBOLS, help=f"Comma-separated symbols. Default: {DEFAULT_SYMBOLS}")
    status.set_defaults(func=cmd_status)

    validate = sub.add_parser("validate", help="Validate one symbol runtime snapshot")
    add_common_args(validate)
    validate.add_argument("--symbol", required=True, help="Broker symbol, e.g. USDJPYc")
    validate.set_defaults(func=cmd_validate)

    snapshot = sub.add_parser("snapshot", help="Emit normalized AI snapshot payload for one symbol")
    add_common_args(snapshot)
    snapshot.add_argument("--symbol", required=True, help="Broker symbol, e.g. USDJPYc")
    snapshot.add_argument("--timeframes", default=",".join(ALLOWED_TIMEFRAMES), help="Comma-separated timeframes")
    snapshot.set_defaults(func=cmd_snapshot)

    sample = sub.add_parser("sample", help="Write sample read-only runtime snapshots for CI/local smoke tests")
    add_common_args(sample)
    sample.add_argument("--symbols", default=DEFAULT_SYMBOLS, help=f"Comma-separated symbols. Default: {DEFAULT_SYMBOLS}")
    sample.add_argument("--overwrite", action="store_true", help="Overwrite existing sample files")
    sample.set_defaults(func=cmd_sample)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        emit(args.func(args))
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "safety": bridge_safety_payload()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
