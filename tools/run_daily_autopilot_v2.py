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

from daily_autopilot_v2.report import build_daily_autopilot_v2
from daily_autopilot_v2.telegram_text import daily_autopilot_v2_to_chinese_text


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


def todo_text(payload: Dict[str, object]) -> str:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    lines = [
        "【QuantGod Agent 今日待办】",
        "",
        f"状态：{payload.get('status', 'COMPLETED_BY_AGENT')}",
        f"Agent 版本：{payload.get('agentVersion', 'v2.4')}",
        "无需人工回灌；每项由 Agent 自动检查、完成、晋级或回滚。",
        "",
    ]
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('laneZh') or item.get('lane')}｜{item.get('status')}｜"
            f"{item.get('summaryZh', '')}"
        )
    return "\n".join(lines)


def review_text(payload: Dict[str, object]) -> str:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    live = payload.get("liveLane") if isinstance(payload.get("liveLane"), dict) else {}
    mt5 = payload.get("mt5ShadowLane") if isinstance(payload.get("mt5ShadowLane"), dict) else {}
    poly = payload.get("polymarketShadowLane") if isinstance(payload.get("polymarketShadowLane"), dict) else {}
    lines = [
        "【QuantGod Agent 每日复盘】",
        "",
        f"阶段：{live.get('stageZh') or live.get('stage') or payload.get('promotionDecision', 'SHADOW')}",
        f"回滚：{'是' if payload.get('rollbackTriggered') else '否'}",
        f"净 R：{metrics.get('netR', 0)}｜最大不利 R：{metrics.get('maxAdverseR', '—')}｜利润捕获：{metrics.get('profitCaptureRatio', '—')}",
        f"错失机会：{metrics.get('missedOpportunity', 0)}｜早出场改善：{metrics.get('earlyExit', 0)}",
        f"MT5 模拟路线：{(mt5.get('summary') or {}).get('routeCount', 0)}｜Polymarket：{poly.get('stageZh') or poly.get('stage', '模拟观察')}",
        "",
        "复盘已由 Agent 自动完成；不等待人工确认，不修改 live preset，不连接 Polymarket 钱包。",
    ]
    return "\n".join(lines)


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
    parser = argparse.ArgumentParser(description="QuantGod Daily Autopilot 2.0 for USDJPY cent-account autonomous agent")
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR", str(root / "runtime")))
    parser.add_argument("--repo-root", default=str(root))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    build = sub.add_parser("build")
    build.add_argument("--write", action="store_true")
    todo = sub.add_parser("daily-todo")
    todo.add_argument("--write", action="store_true")
    review = sub.add_parser("daily-review")
    review.add_argument("--write", action="store_true")
    text = sub.add_parser("telegram-text")
    text.add_argument("--refresh", action="store_true")
    text.add_argument("--write", action="store_true")
    text.add_argument("--send", action="store_true")
    todo_text_parser = sub.add_parser("daily-todo-telegram-text")
    todo_text_parser.add_argument("--refresh", action="store_true")
    todo_text_parser.add_argument("--write", action="store_true")
    todo_text_parser.add_argument("--send", action="store_true")
    review_text_parser = sub.add_parser("daily-review-telegram-text")
    review_text_parser.add_argument("--refresh", action="store_true")
    review_text_parser.add_argument("--write", action="store_true")
    review_text_parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    repo_root = Path(args.repo_root)
    if args.command == "status":
        return emit(build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=False))
    if args.command == "build":
        return emit(build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write))
    if args.command == "daily-todo":
        payload = build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write)
        return emit(payload.get("dailyTodo") or {"ok": False, "error": "daily_todo_missing"})
    if args.command == "daily-review":
        payload = build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write)
        return emit(payload.get("dailyReview") or {"ok": False, "error": "daily_review_missing"})
    if args.command == "telegram-text":
        payload = build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write or args.refresh)
        content = daily_autopilot_v2_to_chinese_text(payload)
        result = {"ok": True, "text": content, "dailyAutopilotV2": payload}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    if args.command == "daily-todo-telegram-text":
        payload = build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write or args.refresh)
        daily_todo = payload.get("dailyTodo") if isinstance(payload.get("dailyTodo"), dict) else {}
        content = todo_text(daily_todo)
        result = {"ok": True, "text": content, "dailyTodo": daily_todo}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    if args.command == "daily-review-telegram-text":
        payload = build_daily_autopilot_v2(runtime_dir, repo_root=repo_root, write=args.write or args.refresh)
        daily_review = payload.get("dailyReview") if isinstance(payload.get("dailyReview"), dict) else {}
        content = review_text(daily_review)
        result = {"ok": True, "text": content, "dailyReview": daily_review}
        if args.send:
            result["telegram"] = send_telegram(content)
        return emit(result)
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
