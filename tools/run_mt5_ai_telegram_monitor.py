#!/usr/bin/env python3
"""Read-only MT5 AI monitor with Telegram push-only advisory delivery.

The monitor follows the Web3-style loop of source monitoring -> AI summary ->
push notification, but keeps QuantGod trading safety intact: no orders, no
position changes, no preset mutation, no Telegram commands, and no kill-switch
override.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
for candidate in (str(REPO_ROOT), str(TOOLS_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from ai_analysis.analysis_service_v2 import AnalysisServiceV2, phase3_ai_safety  # noqa: E402
from telegram_notifier.client import TelegramClient, validate_message_text  # noqa: E402
from telegram_notifier.config import load_config  # noqa: E402
from telegram_notifier.records import record_notification  # noqa: E402
from telegram_notifier.safety import (  # noqa: E402
    assert_telegram_safety,
    require_chat_id,
    require_push_enabled,
    require_token,
    safety_payload as telegram_safety_payload,
)

MODE = "QUANTGOD_MT5_AI_TELEGRAM_MONITOR_V1"
DEFAULT_SYMBOLS = "USDJPYc,EURUSDc,XAUUSDc"
DEFAULT_TIMEFRAMES = "M15,H1,H4,D1"
DEFAULT_MIN_INTERVAL_SECONDS = 15 * 60


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def monitor_safety() -> dict[str, Any]:
    payload = {
        "mode": MODE,
        "localOnly": True,
        "readOnlyDataPlane": True,
        "advisoryOnly": True,
        "notificationPushOnly": True,
        "telegramCommandExecutionAllowed": False,
        "telegramWebhookReceiverAllowed": False,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "canOverrideKillSwitch": False,
        "canMutateGovernanceDecision": False,
        "canPromoteOrDemoteRoute": False,
        "automatedTradingAllowed": False,
    }
    payload["ai"] = phase3_ai_safety()
    return payload


def parse_csv_list(value: str | None, fallback: str) -> list[str]:
    raw = value if value not in (None, "") else fallback
    items: list[str] = []
    for part in str(raw).split(","):
        item = part.strip()
        if item and item not in items:
            items.append(item)
    return items


def read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def runtime_dir_from_args(args: argparse.Namespace) -> Path:
    value = args.runtime_dir or os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR")
    return Path(value or (REPO_ROOT / "runtime")).expanduser().resolve()


def monitor_state_path(args: argparse.Namespace) -> Path:
    if args.state_file:
        return Path(args.state_file).expanduser().resolve()
    return runtime_dir_from_args(args) / "QuantGod_MT5AiTelegramMonitorState.json"


def latest_report_path(args: argparse.Namespace) -> Path:
    return runtime_dir_from_args(args) / "QuantGod_MT5AiTelegramMonitorLatest.json"


def summarize_source(report: dict[str, Any]) -> dict[str, Any]:
    snapshot = report.get("snapshot") if isinstance(report.get("snapshot"), dict) else {}
    current_price = snapshot.get("current_price") if isinstance(snapshot.get("current_price"), dict) else {}
    positions = snapshot.get("open_positions") if isinstance(snapshot.get("open_positions"), list) else []
    risk = report.get("risk") if isinstance(report.get("risk"), dict) else {}
    technical = report.get("technical") if isinstance(report.get("technical"), dict) else {}
    return {
        "snapshotSource": snapshot.get("source", ""),
        "fallback": bool(snapshot.get("fallback", False)),
        "price": current_price,
        "openPositions": len(positions),
        "riskLevel": risk.get("risk_level", "unknown"),
        "killSwitchActive": bool(risk.get("kill_switch_active", False)),
        "technicalDirection": technical.get("direction") or ((technical.get("trend") or {}).get("consensus") if isinstance(technical.get("trend"), dict) else ""),
    }


def decision_summary(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    return {
        "action": str(decision.get("action") or "HOLD"),
        "confidence": decision.get("confidence"),
        "reasoning": str(decision.get("reasoning") or ""),
        "keyFactors": decision.get("key_factors") if isinstance(decision.get("key_factors"), list) else [],
    }


def event_signature(report: dict[str, Any]) -> str:
    seed = {
        "symbol": report.get("symbol"),
        "decision": decision_summary(report),
        "source": summarize_source(report),
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def parse_iso_seconds(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def should_notify(state: dict[str, Any], *, symbol: str, signature: str, now_epoch: float, min_interval_seconds: int, force: bool) -> tuple[bool, str]:
    if force:
        return True, "force"
    symbols = state.get("symbols") if isinstance(state.get("symbols"), dict) else {}
    previous = symbols.get(symbol) if isinstance(symbols.get(symbol), dict) else {}
    if previous.get("signature") != signature:
        return True, "changed"
    last_epoch = parse_iso_seconds(previous.get("lastNotifiedAt"))
    if last_epoch is None:
        return True, "first_seen"
    remaining = min_interval_seconds - int(now_epoch - last_epoch)
    if remaining <= 0:
        return True, "interval_elapsed"
    return False, f"dedup_wait_{remaining}s"


def update_state(state: dict[str, Any], *, symbol: str, signature: str, status: str, reason: str, report: dict[str, Any], now_iso: str) -> dict[str, Any]:
    out = dict(state)
    out["mode"] = MODE
    out["updatedAt"] = now_iso
    symbols = dict(out.get("symbols") or {})
    previous = dict(symbols.get(symbol) or {})
    previous.update(
        {
            "symbol": symbol,
            "signature": signature,
            "status": status,
            "reason": reason,
            "lastDecision": decision_summary(report),
            "lastSource": summarize_source(report),
            "lastAnalyzedAt": report.get("generatedAt") or now_iso,
        }
    )
    if status in {"sent", "dry_run"}:
        previous["lastNotifiedAt"] = now_iso
    symbols[symbol] = previous
    out["symbols"] = symbols
    out["safety"] = monitor_safety()
    return out


def build_advisory_message(report: dict[str, Any], *, reason: str) -> str:
    symbol = str(report.get("symbol") or "UNKNOWN")
    decision = decision_summary(report)
    source = summarize_source(report)
    factors = decision.get("keyFactors") or []
    factor_text = "；".join(str(item) for item in factors[:4]) or "暂无关键因子"
    price = source.get("price") if isinstance(source.get("price"), dict) else {}
    bid = price.get("bid", "--")
    ask = price.get("ask", "--")
    return validate_message_text(
        "\n".join(
            [
                f"[QuantGod][MT5 AI 监听][{decision['action']}] {symbol}",
                f"置信度: {decision.get('confidence', '--')} | 触发: {reason}",
                f"价格: bid {bid} / ask {ask} | 来源: {source.get('snapshotSource') or 'unknown'}",
                f"风险: {source.get('riskLevel')} | KillSwitch: {source.get('killSwitchActive')} | 持仓: {source.get('openPositions')}",
                f"技术方向: {source.get('technicalDirection') or 'unknown'}",
                f"AI 建议: {decision.get('reasoning') or 'advisory-only analysis generated'}",
                f"因子: {factor_text}",
                "边界: 只读监听 + AI advisory-only + Telegram push-only；不会下单、平仓、撤单或修改 live preset。",
            ]
        )
    )


def send_or_record(args: argparse.Namespace, *, message: str, event_type: str, dry_run: bool) -> dict[str, Any]:
    config = load_config(repo_root=args.repo_root, env_file=args.env_file)
    assert_telegram_safety(config)
    require_token(config)
    require_chat_id(config)
    if dry_run:
        record = {"ok": True, "recorded": False}
        if not args.no_record:
            record = record_notification(config, event_type=event_type, status="dry_run", payload={"messagePreview": message[:160]})
        return {"ok": True, "status": "dry_run", "record": record, "safety": telegram_safety_payload(config)}
    require_push_enabled(config)
    payload = TelegramClient(token=config.bot_token, api_base_url=config.api_base_url, timeout_seconds=config.timeout_seconds).send_message(
        chat_id=config.chat_id,
        text=message,
        disable_notification=args.disable_notification,
    )
    result = payload.get("result") or {}
    record = {"ok": True, "recorded": False}
    if not args.no_record:
        record = record_notification(
            config,
            event_type=event_type,
            status="sent",
            payload={"telegramMessageId": result.get("message_id"), "messagePreview": message[:160]},
        )
    return {"ok": True, "status": "sent", "telegramMessageId": result.get("message_id"), "record": record, "safety": telegram_safety_payload(config)}


async def scan_once(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    symbols = parse_csv_list(args.symbols or os.environ.get("QG_MT5_AI_MONITOR_SYMBOLS"), DEFAULT_SYMBOLS)
    timeframes = parse_csv_list(args.timeframes, DEFAULT_TIMEFRAMES)
    state_path = monitor_state_path(args)
    state = read_json(state_path)
    now_epoch = time.time()
    now_iso = utc_now_iso()
    service = AnalysisServiceV2(runtime_dir=runtime_dir)
    items: list[dict[str, Any]] = []
    notifications = 0

    for symbol in symbols:
        report = await service.run_analysis(symbol, timeframes)
        signature = event_signature(report)
        should_send, reason = should_notify(
            state,
            symbol=symbol,
            signature=signature,
            now_epoch=now_epoch,
            min_interval_seconds=max(0, int(args.min_interval_seconds)),
            force=bool(args.force),
        )
        delivery: dict[str, Any] = {"ok": True, "status": "skipped", "reason": reason}
        status = "skipped"
        if should_send:
            message = build_advisory_message(report, reason=reason)
            delivery = send_or_record(args, message=message, event_type="MT5_AI_ADVISORY", dry_run=not args.send)
            status = str(delivery.get("status") or "sent")
            notifications += 1
        state = update_state(state, symbol=symbol, signature=signature, status=status, reason=reason, report=report, now_iso=now_iso)
        items.append(
            {
                "symbol": symbol,
                "signature": signature,
                "shouldNotify": should_send,
                "reason": reason,
                "delivery": delivery,
                "decision": decision_summary(report),
                "source": summarize_source(report),
            }
        )

    payload = {
        "ok": True,
        "mode": MODE,
        "generatedAt": now_iso,
        "runtimeDir": str(runtime_dir),
        "dryRun": not args.send,
        "items": items,
        "summary": {"symbols": len(symbols), "notifications": notifications},
        "statePath": str(state_path),
        "latestPath": str(latest_report_path(args)),
        "safety": monitor_safety(),
    }
    write_json(state_path, state)
    write_json(latest_report_path(args), payload)
    return payload


async def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    cycles = max(1, int(args.cycles))
    interval = max(1, int(args.interval_seconds))
    runs: list[dict[str, Any]] = []
    for index in range(cycles):
        runs.append(await scan_once(args))
        if index < cycles - 1:
            await asyncio.sleep(interval)
    return {"ok": True, "mode": MODE, "cycles": cycles, "runs": runs, "safety": monitor_safety()}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def add_common_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbols", default="", help=f"Comma-separated symbols. Default: {DEFAULT_SYMBOLS}")
    parser.add_argument("--timeframes", default=DEFAULT_TIMEFRAMES, help=f"Comma-separated timeframes. Default: {DEFAULT_TIMEFRAMES}")
    parser.add_argument("--runtime-dir", default="", help="MT5/QuantGod runtime evidence directory")
    parser.add_argument("--state-file", default="", help="Optional monitor state JSON path")
    parser.add_argument("--min-interval-seconds", type=int, default=DEFAULT_MIN_INTERVAL_SECONDS, help="Minimum interval before repeating unchanged advisory")
    parser.add_argument("--force", action="store_true", help="Bypass dedupe for this run")
    parser.add_argument("--send", action="store_true", help="Actually send Telegram push. Default records dry-run evidence only.")
    parser.add_argument("--disable-notification", action="store_true", help="Send silently when --send is used")
    parser.add_argument("--no-record", action="store_true", help="Do not write notification evidence to SQLite")
    parser.add_argument("--repo-root", type=Path, default=None, help="Backend repo root for Telegram config")
    parser.add_argument("--env-file", type=Path, default=None, help="Local .env.telegram.local path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod read-only MT5 AI Telegram monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("config", help="Show monitor safety/config defaults")
    config.set_defaults(func=lambda args: {"ok": True, "mode": MODE, "defaultSymbols": DEFAULT_SYMBOLS, "defaultTimeframes": DEFAULT_TIMEFRAMES, "safety": monitor_safety()})
    once = sub.add_parser("scan-once", help="Run one read-only AI analysis and Telegram advisory pass")
    add_common_scan_args(once)
    once.set_defaults(func=scan_once)
    loop = sub.add_parser("loop", help="Run a bounded polling loop")
    add_common_scan_args(loop)
    loop.add_argument("--cycles", type=int, default=3, help="Number of cycles to run")
    loop.add_argument("--interval-seconds", type=int, default=60, help="Delay between cycles")
    loop.set_defaults(func=run_loop)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        emit(result)
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "safety": monitor_safety()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
