#!/usr/bin/env python3
"""Run a read-only MT5 + DeepSeek advisory fusion pass.

This CLI is intentionally single-user and local-only.  It exists to smoke-test
and inspect the same fusion layer that the Telegram MT5 monitor uses after this
overlay patches it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
for candidate in (str(REPO_ROOT), str(TOOLS_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from ai_analysis.advisory_fusion import compact_fusion_payload, fuse_advisory_report, fusion_summary_for_message  # noqa: E402
from ai_analysis.analysis_service_v2 import AnalysisServiceV2, phase3_ai_safety  # noqa: E402
from ai_analysis.deepseek_mt5_advisor import DeepSeekAdvisorError, DeepSeekMt5Advisor, load_deepseek_config  # noqa: E402

MODE = "QUANTGOD_AI_ADVISORY_FUSION_V1"
DEFAULT_SYMBOLS = "USDJPYc,EURUSDc,XAUUSDc"
DEFAULT_TIMEFRAMES = "M15,H1,H4,D1"


def safety_payload() -> dict[str, Any]:
    payload = {
        "mode": MODE,
        "localOnly": True,
        "readOnlyDataPlane": True,
        "advisoryOnly": True,
        "telegramPushOnlyCompatible": True,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "canOverrideKillSwitch": False,
        "telegramCommandExecutionAllowed": False,
        "telegramWebhookReceiverAllowed": False,
        "webhookReceiverAllowed": False,
        "emailDeliveryAllowed": False,
        "multiUserAllowed": False,
        "billingAllowed": False,
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


def runtime_dir_from_args(args: argparse.Namespace) -> Path:
    value = args.runtime_dir or os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR")
    return Path(value or (REPO_ROOT / "runtime")).expanduser().resolve()


def latest_path(args: argparse.Namespace) -> Path:
    if args.latest_file:
        return Path(args.latest_file).expanduser().resolve()
    return runtime_dir_from_args(args) / "QuantGod_AIAdvisoryFusionLatest.json"


def attach_deepseek(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(report)
    if args.no_deepseek:
        enriched["deepseek_advice"] = {"ok": False, "status": "disabled_by_cli", "provider": "deepseek"}
        return fuse_advisory_report(enriched)
    try:
        config = load_deepseek_config(repo_root=REPO_ROOT, env_file=args.deepseek_env_file)
        advice = DeepSeekMt5Advisor(config).analyze(enriched)
    except (DeepSeekAdvisorError, ValueError, OSError) as error:
        advice = {"ok": False, "status": "error", "provider": "deepseek", "error": str(error)[:240]}
    enriched["deepseek_advice"] = advice
    return fuse_advisory_report(enriched)


def build_compact_message(report: dict[str, Any]) -> str:
    compact = compact_fusion_payload(report)
    quality = compact.get("evidenceQuality") if isinstance(compact.get("evidenceQuality"), dict) else {}
    return "\n".join(
        [
            "[QuantGod][AI Advisory Fusion]",
            f"symbol: {compact.get('symbol')}",
            f"finalAction: {compact.get('finalAction')}",
            f"severity: {compact.get('notifySeverity')}",
            f"validator: {compact.get('validatorStatus')} / {compact.get('validatorReasons')}",
            f"agreement: {compact.get('agreement')}",
            f"source: {quality.get('source')} | fallback={quality.get('fallback')} | runtimeFresh={quality.get('runtimeFresh')}",
            f"headline: {compact.get('headline')}",
            f"verdict: {compact.get('verdict')}",
            f"planStatus: {compact.get('planStatus')}",
            f"entryZone: {compact.get('entryZone')}",
            f"targets: {compact.get('targets')}",
            "boundary: advisory-only; Telegram push-only compatible; no order/close/cancel/live preset mutation.",
        ]
    )


def maybe_send(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    if not args.send:
        return {"ok": True, "status": "dry_run", "messagePreview": build_compact_message(report)[:200]}

    from telegram_notifier.client import TelegramClient, validate_message_text  # noqa: WPS433
    from telegram_notifier.config import load_config  # noqa: WPS433
    from telegram_notifier.records import record_notification  # noqa: WPS433
    from telegram_notifier.safety import (  # noqa: WPS433
        assert_telegram_safety,
        require_chat_id,
        require_push_enabled,
        require_token,
        safety_payload as telegram_safety_payload,
    )

    config = load_config(repo_root=args.repo_root, env_file=args.env_file)
    assert_telegram_safety(config)
    require_token(config)
    require_chat_id(config)
    require_push_enabled(config)
    message = validate_message_text(build_compact_message(report))
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
            event_type="AI_ADVISORY_FUSION",
            status="sent",
            payload={"telegramMessageId": result.get("message_id"), "messagePreview": message[:160]},
        )
    return {
        "ok": True,
        "status": "sent",
        "telegramMessageId": result.get("message_id"),
        "record": record,
        "safety": telegram_safety_payload(config),
    }


async def scan_once(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = runtime_dir_from_args(args)
    symbols = parse_csv_list(args.symbols or os.environ.get("QG_MT5_AI_MONITOR_SYMBOLS"), DEFAULT_SYMBOLS)
    timeframes = parse_csv_list(args.timeframes, DEFAULT_TIMEFRAMES)
    service = AnalysisServiceV2(runtime_dir=runtime_dir)
    items: list[dict[str, Any]] = []
    for symbol in symbols:
        report = await service.run_analysis(symbol, timeframes)
        fused = attach_deepseek(args, report)
        delivery = maybe_send(args, fused) if args.send or args.delivery_preview else {"ok": True, "status": "not_requested"}
        items.append(
            {
                "symbol": symbol,
                "fusion": compact_fusion_payload(fused),
                "summary": fusion_summary_for_message(fused),
                "delivery": delivery,
            }
        )
    payload = {
        "ok": True,
        "mode": MODE,
        "runtimeDir": str(runtime_dir),
        "symbols": symbols,
        "timeframes": timeframes,
        "items": items,
        "safety": safety_payload(),
    }
    target = latest_path(args)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    payload["latestPath"] = str(target)
    return payload


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantGod DeepSeek Telegram advisory fusion")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="Show fusion safety/config")
    config.set_defaults(func=lambda args: {"ok": True, "mode": MODE, "defaultSymbols": DEFAULT_SYMBOLS, "safety": safety_payload()})

    once = sub.add_parser("scan-once", help="Run one MT5 + DeepSeek fusion pass")
    once.add_argument("--symbols", default="", help=f"Comma-separated symbols. Default: {DEFAULT_SYMBOLS}")
    once.add_argument("--timeframes", default=DEFAULT_TIMEFRAMES, help=f"Comma-separated timeframes. Default: {DEFAULT_TIMEFRAMES}")
    once.add_argument("--runtime-dir", type=Path, default=None, help="MT5 runtime directory")
    once.add_argument("--latest-file", type=Path, default=None, help="Where to write latest fusion JSON")
    once.add_argument("--deepseek-env-file", type=Path, default=None, help="Local .env.deepseek.local path")
    once.add_argument("--no-deepseek", action="store_true", help="Skip DeepSeek and run validator downgrade/fallback path")
    once.add_argument("--delivery-preview", action="store_true", help="Build dry-run Telegram preview in output")
    once.add_argument("--send", action="store_true", help="Send compact Telegram fusion message")
    once.add_argument("--disable-notification", action="store_true", help="Send Telegram silently when --send is used")
    once.add_argument("--no-record", action="store_true", help="Do not write notification evidence when --send is used")
    once.add_argument("--repo-root", type=Path, default=None, help="Backend repo root for Telegram config")
    once.add_argument("--env-file", type=Path, default=None, help="Local .env.telegram.local path")
    once.set_defaults(func=scan_once)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        emit(result)
        return 0
    except Exception as exc:  # pragma: no cover - CLI boundary
        emit({"ok": False, "mode": MODE, "error": str(exc), "safety": safety_payload()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
