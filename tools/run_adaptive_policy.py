#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from adaptive_policy.policy_engine import build_adaptive_policy, load_policy_file
from adaptive_policy.telegram_text import build_policy_telegram_text

def _json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))

def _symbols(text: str | None) -> list[str] | None:
    if not text:
        return None
    return [part.strip() for part in text.split(",") if part.strip()]

def _send_telegram(text: str) -> dict[str, object]:
    push_allowed = os.environ.get("QG_TELEGRAM_PUSH_ALLOWED", "0").strip().lower() in {"1", "true", "yes", "y"}
    commands_allowed = os.environ.get("QG_TELEGRAM_COMMANDS_ALLOWED", "0").strip().lower() in {"1", "true", "yes", "y"}
    if not push_allowed:
        return {"sent": False, "reason": "QG_TELEGRAM_PUSH_ALLOWED 未开启"}
    if commands_allowed:
        return {"sent": False, "reason": "Telegram 命令执行必须关闭"}
    token = os.environ.get("QG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("QG_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"sent": False, "reason": "缺少 Telegram token 或 chat_id"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    return {"sent": bool(data.get("ok")), "telegramResponse": data}

def cmd_status(args: argparse.Namespace) -> int:
    policy = load_policy_file(args.runtime_dir)
    if not policy:
        _json({"ok": True, "policyFound": False, "message": "尚未生成自适应策略，请先运行 build。"})
        return 0
    _json({
        "ok": True,
        "policyFound": True,
        "generatedAt": policy.get("generatedAt"),
        "dataQuality": policy.get("dataQuality", {}),
        "routeCount": len(policy.get("routes", [])),
        "gateCount": len(policy.get("entryGates", [])),
        "planCount": len(policy.get("dynamicSltpPlans", [])),
        "safety": policy.get("safety", {}),
    })
    return 0

def cmd_build(args: argparse.Namespace) -> int:
    policy = build_adaptive_policy(args.runtime_dir, symbols=_symbols(args.symbols), write=not args.no_write)
    _json(policy if args.verbose else {
        "ok": True,
        "generatedAt": policy.get("generatedAt"),
        "dataQuality": policy.get("dataQuality", {}),
        "routeCount": len(policy.get("routes", [])),
        "gateCount": len(policy.get("entryGates", [])),
        "planCount": len(policy.get("dynamicSltpPlans", [])),
        "outputDir": str(Path(args.runtime_dir).expanduser() / "adaptive"),
    })
    return 0

def cmd_score(args: argparse.Namespace) -> int:
    policy = build_adaptive_policy(args.runtime_dir, symbols=_symbols(args.symbols), write=False)
    routes = policy.get("routes", [])
    if args.symbol:
        routes = [r for r in routes if str(r.get("symbol", "")).upper() == args.symbol.upper()]
    _json({"ok": True, "routes": routes})
    return 0

def cmd_gate(args: argparse.Namespace) -> int:
    policy = build_adaptive_policy(args.runtime_dir, symbols=_symbols(args.symbols), write=False)
    gates = policy.get("entryGates", [])
    if args.symbol:
        gates = [g for g in gates if str(g.get("symbol", "")).upper() == args.symbol.upper()]
    _json({"ok": True, "entryGates": gates})
    return 0

def cmd_sltp(args: argparse.Namespace) -> int:
    policy = build_adaptive_policy(args.runtime_dir, symbols=_symbols(args.symbols), write=False)
    plans = policy.get("dynamicSltpPlans", [])
    if args.symbol:
        plans = [p for p in plans if str(p.get("symbol", "")).upper() == args.symbol.upper()]
    _json({"ok": True, "dynamicSltpPlans": plans})
    return 0

def cmd_telegram_text(args: argparse.Namespace) -> int:
    policy = build_adaptive_policy(args.runtime_dir, symbols=_symbols(args.symbols), write=not args.no_write)
    text = build_policy_telegram_text(policy, symbol=args.symbol)
    print(text)
    if args.send:
        result = _send_telegram(text)
        _json(result)
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod P3-6 adaptive policy engine")
    parser.add_argument("--runtime-dir", default="runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    build = sub.add_parser("build")
    build.add_argument("--symbols", default=None, help="逗号分隔品种，例如 USDJPYc,XAUUSDc")
    build.add_argument("--no-write", action="store_true")
    build.add_argument("--verbose", action="store_true")
    build.set_defaults(func=cmd_build)

    score = sub.add_parser("score")
    score.add_argument("--symbols", default=None)
    score.add_argument("--symbol", default=None)
    score.set_defaults(func=cmd_score)

    gate = sub.add_parser("gate")
    gate.add_argument("--symbols", default=None)
    gate.add_argument("--symbol", default=None)
    gate.set_defaults(func=cmd_gate)

    sltp = sub.add_parser("sltp")
    sltp.add_argument("--symbols", default=None)
    sltp.add_argument("--symbol", default=None)
    sltp.set_defaults(func=cmd_sltp)

    text = sub.add_parser("telegram-text")
    text.add_argument("--symbols", default=None)
    text.add_argument("--symbol", default=None)
    text.add_argument("--no-write", action="store_true")
    text.add_argument("--send", action="store_true")
    text.set_defaults(func=cmd_telegram_text)

    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))

if __name__ == "__main__":
    raise SystemExit(main())
