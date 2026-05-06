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

from usdjpy_autonomous_agent.agent_state import build_agent_state
from usdjpy_autonomous_agent.config_patch import build_config_patch
from usdjpy_autonomous_agent.promotion_gate import build_promotion_decision
from usdjpy_autonomous_agent.schema import FOCUS_SYMBOL, HARD_SAFETY
from usdjpy_autonomous_agent.telegram_text import autonomous_agent_to_chinese_text
from usdjpy_walk_forward.selector import sample_walk_forward_runtime


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


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[1]
    load_env(root / ".env.usdjpy.local")
    parser = argparse.ArgumentParser(description="QuantGod P3-20 USDJPY autonomous walk-forward promotion gate")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--symbol", default=FOCUS_SYMBOL)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config")
    sample = sub.add_parser("sample")
    sample.add_argument("--overwrite", action="store_true")
    decision = sub.add_parser("decision")
    decision.add_argument("--write", action="store_true")
    patch = sub.add_parser("patch")
    patch.add_argument("--write", action="store_true")
    state = sub.add_parser("state")
    state.add_argument("--write", action="store_true")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--write", action="store_true")
    text.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    if args.symbol.upper() not in {"USDJPY", "USDJPYC"}:
        return emit({"ok": False, "error": "P3-20 只允许 USDJPY/USDJPYc", "symbol": args.symbol})
    if args.command == "config":
        return emit({"ok": True, "focusSymbol": FOCUS_SYMBOL, "runtimeDir": str(runtime_dir), "safety": HARD_SAFETY})
    if args.command == "sample":
        return emit(sample_walk_forward_runtime(runtime_dir, overwrite=args.overwrite))
    if args.command == "decision":
        return emit(build_promotion_decision(runtime_dir, write=args.write))
    if args.command == "patch":
        return emit(build_config_patch(runtime_dir, write=args.write))
    if args.command in {"state", "build"}:
        return emit(build_agent_state(runtime_dir, write=args.write))
    if args.command == "telegram-text":
        payload = build_agent_state(runtime_dir, write=args.write or args.refresh)
        content = autonomous_agent_to_chinese_text(payload)
        result = {"ok": True, "text": content, "state": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

