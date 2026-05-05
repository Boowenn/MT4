#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict

from usdjpy_strategy_lab.data_loader import sample_runtime
from usdjpy_strategy_lab.dry_run_bridge import build_dry_run_decision
from usdjpy_strategy_lab.policy_builder import build_usdjpy_policy
from usdjpy_strategy_lab.schema import FOCUS_SYMBOL, READ_ONLY_SAFETY
from usdjpy_strategy_lab.strategy_scoreboard import build_strategy_scoreboard
from usdjpy_strategy_lab.telegram_text import dry_run_to_chinese_text, policy_to_chinese_text


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def emit(payload) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def send_telegram(text: str) -> Dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.telegram.local")
    token = os.environ.get("QG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("QG_TELEGRAM_CHAT_ID", "").strip()
    push_allowed = os.environ.get("QG_TELEGRAM_PUSH_ALLOWED", "0").strip() == "1"
    commands_allowed = os.environ.get("QG_TELEGRAM_COMMANDS_ALLOWED", "0").strip() == "1"
    if not push_allowed:
        return {"ok": False, "skipped": True, "reason": "QG_TELEGRAM_PUSH_ALLOWED is not 1"}
    if commands_allowed:
        return {"ok": False, "skipped": True, "reason": "Telegram command execution must stay disabled"}
    if not token or not chat_id:
        return {"ok": False, "skipped": True, "reason": "Telegram token/chat_id missing"}
    token_path = urllib.parse.quote(token, safe=":")
    url = f"https://api.telegram.org/bot{token_path}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3900]}).encode("utf-8")
    try:
        with urllib.request.urlopen(url, data=body, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": bool(payload.get("ok")), "telegram": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.usdjpy.local")
    load_env(root / ".env.auto.local")
    parser = argparse.ArgumentParser(description="QuantGod USDJPY strategy policy lab")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--symbol", default=FOCUS_SYMBOL)
    parser.add_argument("--min-samples", type=int, default=int(os.environ.get("QG_USDJPY_MIN_SAMPLES", "5")))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config")
    sub.add_parser("status")
    sample = sub.add_parser("sample")
    sample.add_argument("--overwrite", action="store_true")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    sub.add_parser("scoreboard")
    policy = sub.add_parser("policy")
    policy.add_argument("--write", action="store_true")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--write", action="store_true")
    text.add_argument("--send", action="store_true")
    loop = sub.add_parser("loop")
    loop.add_argument("--interval-seconds", type=int, default=300)
    loop.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    if args.symbol.upper() not in {"USDJPY", "USDJPYC"}:
        return emit({"ok": False, "error": "P3-14 只允许 USDJPY/USDJPYc", "symbol": args.symbol})
    if args.command == "config":
        return emit({
            "ok": True,
            "focusSymbol": FOCUS_SYMBOL,
            "runtimeDir": str(runtime_dir),
            "maxLot": float(os.environ.get("QG_AUTO_MAX_LOT", "2.0")),
            "dryRunOnly": True,
            "safety": READ_ONLY_SAFETY,
        })
    if args.command == "sample":
        return emit(sample_runtime(runtime_dir, overwrite=args.overwrite))
    if args.command == "scoreboard":
        return emit(build_strategy_scoreboard(runtime_dir, min_samples=args.min_samples))
    if args.command in {"policy", "build", "status"}:
        payload = build_usdjpy_policy(runtime_dir, write=getattr(args, "write", False), min_samples=args.min_samples)
        return emit(payload)
    if args.command == "dry-run":
        return emit(build_dry_run_decision(runtime_dir, write=args.write))
    if args.command == "telegram-text":
        payload = build_usdjpy_policy(runtime_dir, write=args.write or args.refresh, min_samples=args.min_samples)
        content = policy_to_chinese_text(payload)
        result = {"ok": True, "text": content, "policy": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    if args.command == "loop":
        while True:
            payload = build_usdjpy_policy(runtime_dir, write=True, min_samples=args.min_samples)
            content = policy_to_chinese_text(payload)
            result = {"ok": True, "generatedAt": payload.get("generatedAt"), "textPreview": content[:500]}
            if args.send:
                result["telegram"] = send_telegram(content)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(max(30, args.interval_seconds))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
