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

from usdjpy_runtime_dataset.builder import build_runtime_dataset
from usdjpy_runtime_dataset.config_proposal import build_live_config_proposal
from usdjpy_runtime_dataset.param_tuner import build_param_tuning_report
from usdjpy_runtime_dataset.replay import build_replay_report
from usdjpy_runtime_dataset.schema import FOCUS_SYMBOL, READ_ONLY_SAFETY
from usdjpy_runtime_dataset.telegram_text import evolution_to_chinese_text


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


def emit(payload) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def send_telegram(text: str) -> Dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.telegram.local")
    token = os.environ.get("QG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("QG_TELEGRAM_CHAT_ID", "").strip()
    if os.environ.get("QG_TELEGRAM_PUSH_ALLOWED", "0").strip() != "1":
        return {"ok": False, "skipped": True, "reason": "QG_TELEGRAM_PUSH_ALLOWED is not 1"}
    if os.environ.get("QG_TELEGRAM_COMMANDS_ALLOWED", "0").strip() == "1":
        return {"ok": False, "skipped": True, "reason": "Telegram command execution must stay disabled"}
    if not token or not chat_id:
        return {"ok": False, "skipped": True, "reason": "Telegram token/chat_id missing"}
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3900]}).encode("utf-8")
    try:
        with urllib.request.urlopen(url, data=body, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": bool(payload.get("ok")), "telegram": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_all(runtime_dir: Path, write: bool = False) -> Dict[str, object]:
    dataset = build_runtime_dataset(runtime_dir, write=write)
    replay = build_replay_report(runtime_dir, write=write)
    tuning = build_param_tuning_report(runtime_dir, write=write)
    proposal = build_live_config_proposal(runtime_dir, write=write)
    return {
        "ok": True,
        "mode": "USDJPY_EVOLUTION_CORE",
        "focusSymbol": FOCUS_SYMBOL,
        "runtimeDir": str(runtime_dir),
        "dataset": dataset,
        "replay": replay,
        "tuning": tuning,
        "proposal": proposal,
        "safety": READ_ONLY_SAFETY,
    }


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.usdjpy.local")
    parser = argparse.ArgumentParser(description="QuantGod USDJPY runtime dataset and replay evolution core")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--symbol", default=FOCUS_SYMBOL)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config")
    status = sub.add_parser("status")
    status.add_argument("--write", action="store_true")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("--write", action="store_true")
    tune = sub.add_parser("tune")
    tune.add_argument("--write", action="store_true")
    proposal = sub.add_parser("proposal")
    proposal.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--write", action="store_true")
    text.add_argument("--send", action="store_true")
    loop = sub.add_parser("loop")
    loop.add_argument("--interval-seconds", type=int, default=900)
    loop.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    if str(args.symbol).upper() not in {"USDJPY", "USDJPYC"}:
        return emit({"ok": False, "error": "USDJPY evolution core 只允许 USDJPY/USDJPYc", "symbol": args.symbol})
    runtime_dir = Path(args.runtime_dir)
    if args.command == "config":
        return emit({"ok": True, "focusSymbol": FOCUS_SYMBOL, "runtimeDir": str(runtime_dir), "safety": READ_ONLY_SAFETY})
    if args.command == "status":
        return emit(build_all(runtime_dir, write=args.write))
    if args.command == "build":
        return emit(build_runtime_dataset(runtime_dir, write=args.write))
    if args.command == "replay":
        return emit(build_replay_report(runtime_dir, write=args.write))
    if args.command == "tune":
        return emit(build_param_tuning_report(runtime_dir, write=args.write))
    if args.command == "proposal":
        return emit(build_live_config_proposal(runtime_dir, write=args.write))
    if args.command == "telegram-text":
        payload = build_all(runtime_dir, write=args.write or args.refresh)
        content = evolution_to_chinese_text(payload)
        result = {"ok": True, "text": content, "payload": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    if args.command == "loop":
        while True:
            payload = build_all(runtime_dir, write=True)
            content = evolution_to_chinese_text(payload)
            result = {"ok": True, "textPreview": content[:500], "generatedAtIso": payload["dataset"].get("generatedAtIso")}
            if args.send:
                result["telegram"] = send_telegram(content)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(max(60, args.interval_seconds))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
