#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict

from usdjpy_bar_replay.dataset_loader import sample_runtime
from usdjpy_bar_replay.replay_engine import build_bar_replay_report, build_entry_comparison, build_exit_comparison
from usdjpy_bar_replay.schema import FOCUS_SYMBOL, READ_ONLY_SAFETY
from usdjpy_bar_replay.telegram_text import bar_replay_to_chinese_text


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
    parser = argparse.ArgumentParser(description="QuantGod P3-19 USDJPY causal bar replay simulator")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--symbol", default=FOCUS_SYMBOL)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config")
    sample = sub.add_parser("sample")
    sample.add_argument("--overwrite", action="store_true")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--write", action="store_true")
    entry = sub.add_parser("entry")
    entry.add_argument("--write", action="store_true")
    exit_cmd = sub.add_parser("exit")
    exit_cmd.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--write", action="store_true")
    text.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    if args.symbol.upper() not in {"USDJPY", "USDJPYC"}:
        return emit({"ok": False, "error": "P3-19 只允许 USDJPY/USDJPYc", "symbol": args.symbol})
    if args.command == "config":
        return emit({"ok": True, "focusSymbol": FOCUS_SYMBOL, "runtimeDir": str(runtime_dir), "safety": READ_ONLY_SAFETY})
    if args.command == "sample":
        return emit(sample_runtime(runtime_dir, overwrite=args.overwrite))
    if args.command in {"build", "status"}:
        return emit(build_bar_replay_report(runtime_dir, write=args.write))
    if args.command == "entry":
        return emit(build_entry_comparison(runtime_dir, write=args.write))
    if args.command == "exit":
        return emit(build_exit_comparison(runtime_dir, write=args.write))
    if args.command == "telegram-text":
        payload = build_bar_replay_report(runtime_dir, write=args.write or args.refresh)
        content = bar_replay_to_chinese_text(payload)
        result = {"ok": True, "text": content, "report": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
