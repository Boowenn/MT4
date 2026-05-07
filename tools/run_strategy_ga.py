#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from strategy_ga.generation_runner import build_ga_status, read_candidates, read_generations, run_generation
from strategy_ga.schema import BLOCKER_FILE, EVOLUTION_PATH_FILE, ga_dir
from strategy_ga.telegram_text import ga_to_chinese_text


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


def _load_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def send_telegram(text: str) -> dict:
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
    parser = argparse.ArgumentParser(description="QuantGod Strategy JSON GA Evolution Trace")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--write", action="store_true")
    run = sub.add_parser("run-generation")
    run.add_argument("--write", action="store_true")
    sub.add_parser("generations")
    sub.add_parser("candidates")
    candidate = sub.add_parser("candidate")
    candidate.add_argument("--seed-id", required=True)
    sub.add_parser("evolution-path")
    sub.add_parser("blockers")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)

    if args.command == "status":
        if args.write and not (ga_dir(runtime_dir) / "QuantGod_GAStatus.json").exists():
            return emit(run_generation(runtime_dir, write=True))
        return emit(build_ga_status(runtime_dir))
    if args.command == "run-generation":
        return emit(run_generation(runtime_dir, write=True if args.write else True))
    if args.command == "generations":
        return emit(read_generations(runtime_dir))
    if args.command == "candidates":
        return emit(read_candidates(runtime_dir))
    if args.command == "candidate":
        rows = read_candidates(runtime_dir).get("candidates", [])
        match = next((row for row in rows if row.get("seedId") == args.seed_id), None)
        return emit({"ok": bool(match), "candidate": match})
    if args.command == "evolution-path":
        return emit(_load_json(ga_dir(runtime_dir) / EVOLUTION_PATH_FILE))
    if args.command == "blockers":
        return emit(_load_json(ga_dir(runtime_dir) / BLOCKER_FILE))
    if args.command == "telegram-text":
        payload = run_generation(runtime_dir, write=True) if args.refresh else build_ga_status(runtime_dir)
        content = ga_to_chinese_text(payload)
        result = {"ok": True, "text": content, "ga": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

