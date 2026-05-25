#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from usdjpy_spread_gate_audit import (
    backfill_tokyo_h4_shadow_candidate_ledger,
    backfill_tokyo_h4_shadow_candidate_outcome_ledger,
    build_spread_gate_impact_audit,
    build_tokyo_h4_promotion_review,
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


def emit(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def parse_thresholds(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.usdjpy.local")
    parser = argparse.ArgumentParser(description="QuantGod USDJPY spread gate impact audit")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--start-date-jst", default=None)
    parser.add_argument("--end-date-jst", default=None)
    parser.add_argument("--thresholds", default="2.0,2.2,2.3,2.4,2.5")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--write", action="store_true")
    review = sub.add_parser("promotion-review")
    review.add_argument("--write", action="store_true")
    backfill = sub.add_parser("backfill-candidates")
    backfill.add_argument("--write", action="store_true")
    outcome_backfill = sub.add_parser("backfill-outcomes")
    outcome_backfill.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    thresholds = parse_thresholds(args.thresholds)
    if args.command == "audit":
        return emit(
            build_spread_gate_impact_audit(
                runtime_dir,
                start_date_jst=args.start_date_jst,
                end_date_jst=args.end_date_jst,
                thresholds=thresholds,
                write=args.write,
            )
        )
    if args.command == "promotion-review":
        return emit(
            build_tokyo_h4_promotion_review(
                runtime_dir,
                start_date_jst=args.start_date_jst,
                end_date_jst=args.end_date_jst,
                write=args.write,
            )
        )
    if args.command == "backfill-candidates":
        return emit(
            backfill_tokyo_h4_shadow_candidate_ledger(
                runtime_dir,
                start_date_jst=args.start_date_jst,
                end_date_jst=args.end_date_jst,
                write=args.write,
            )
        )
    if args.command == "backfill-outcomes":
        return emit(
            backfill_tokyo_h4_shadow_candidate_outcome_ledger(
                runtime_dir,
                start_date_jst=args.start_date_jst,
                end_date_jst=args.end_date_jst,
                write=args.write,
            )
        )
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
