#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from mt5_fastlane.quality import build_quality_report, build_telegram_text
    from mt5_fastlane.schema import safety_payload
except ModuleNotFoundError:  # unittest imports this file as tools.run_mt5_fastlane
    from tools.mt5_fastlane.quality import build_quality_report, build_telegram_text
    from tools.mt5_fastlane.schema import safety_payload


def _json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _symbols(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def cmd_status(args: argparse.Namespace) -> int:
    report = build_quality_report(args.runtime_dir, _symbols(args.symbols), write=False)
    _json({
        "ok": True,
        "runtimeDir": report.get("runtimeDir"),
        "heartbeatFound": report.get("heartbeatFound"),
        "heartbeatFresh": report.get("heartbeatFresh"),
        "symbolCount": len(report.get("symbols", [])),
        "safety": safety_payload(),
    })
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    report = build_quality_report(args.runtime_dir, _symbols(args.symbols), write=not args.no_write)
    _json(report)
    return 0


def cmd_telegram_text(args: argparse.Namespace) -> int:
    report = build_quality_report(args.runtime_dir, _symbols(args.symbols), write=not args.no_write)
    print(build_telegram_text(report))
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone
    import random
    root = Path(args.runtime_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    symbols = _symbols(args.symbols) or ["USDJPYc"]
    (root / "QuantGod_RuntimeHeartbeat.json").write_text(json.dumps({
        "schema": "quantgod.mt5.fast_lane.heartbeat.v1",
        "generatedAt": now,
        "source": "sample_fast_lane",
        "terminalConnected": True,
        "safety": safety_payload(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for symbol in symbols:
        tick_path = root / f"QuantGod_RuntimeTicks_{symbol}.jsonl"
        rows = []
        bid = 155.0 + random.random()
        for idx in range(5):
            rows.append(json.dumps({
                "schema": "quantgod.mt5.fast_lane.tick.v1",
                "generatedAt": now,
                "timeIso": now,
                "symbol": symbol,
                "bid": round(bid + idx * 0.001, 5),
                "ask": round(bid + idx * 0.001 + 0.002, 5),
                "point": 0.001,
                "spreadPoints": 2.0,
                "safety": safety_payload(),
            }, ensure_ascii=False))
        tick_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        (root / f"QuantGod_RuntimeIndicators_{symbol}.json").write_text(json.dumps({
            "schema": "quantgod.mt5.fast_lane.indicators.v1",
            "generatedAt": now,
            "symbol": symbol,
            "atr": 0.12,
            "adx": 22.5,
            "bbWidth": 0.18,
            "barProgressPct": 45.0,
            "safety": safety_payload(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    _json({"ok": True, "runtimeDir": str(root), "symbols": symbols})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod MT5 runtime fast lane quality CLI")
    parser.add_argument("--runtime-dir", default="runtime")
    parser.add_argument("--symbols", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--symbols", default=None)
    sample.set_defaults(func=cmd_sample)
    status = sub.add_parser("status")
    status.add_argument("--symbols", default=None)
    status.set_defaults(func=cmd_status)
    quality = sub.add_parser("quality")
    quality.add_argument("--symbols", default=None)
    quality.add_argument("--no-write", action="store_true")
    quality.set_defaults(func=cmd_quality)
    text = sub.add_parser("telegram-text")
    text.add_argument("--symbols", default=None)
    text.add_argument("--no-write", action="store_true")
    text.set_defaults(func=cmd_telegram_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
