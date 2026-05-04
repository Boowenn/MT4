from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import NotifyConfig
from .event_formatter import format_event
from .telegram_bot import TelegramBot


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_history(config: NotifyConfig | None = None, limit: int = 50) -> dict[str, Any]:
    cfg = config or NotifyConfig.from_env()
    payload = _read_json(cfg.history_path, {"mode": "QUANTGOD_NOTIFY_HISTORY_V1", "items": []})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return {"ok": True, "mode": "QUANTGOD_NOTIFY_HISTORY_V1", "items": list(items)[-max(1, limit):], "historyPath": str(cfg.history_path)}


def append_history(config: NotifyConfig, record: dict[str, Any]) -> None:
    payload = _read_json(config.history_path, {"mode": "QUANTGOD_NOTIFY_HISTORY_V1", "items": []})
    if not isinstance(payload, dict):
        payload = {"mode": "QUANTGOD_NOTIFY_HISTORY_V1", "items": []}
    items = payload.setdefault("items", [])
    items.append(record)
    payload["items"] = items[-500:]
    payload["updatedAt"] = utc_now()
    _write_json(config.history_path, payload)


def _event_payload_from_analysis(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("decision") or report.get("decision_report") or report.get("DecisionReport") or {}
    risk = report.get("risk") or report.get("risk_report") or report.get("RiskReport") or {}
    return {
        "symbol": report.get("symbol") or decision.get("symbol") or report.get("Symbol") or "--",
        "action": decision.get("action") or decision.get("decision") or "HOLD",
        "confidence": decision.get("confidence") or 0,
        "risk": risk.get("risk_level") or risk.get("riskLevel") or risk.get("level") or "unknown",
        "note": decision.get("suggested_wait_condition") or decision.get("reasoning") or report.get("summary") or "analysis complete",
    }


def _should_disable_notification(event_type: str) -> bool:
    return str(event_type or "").upper() in {"DAILY_DIGEST"}


async def send_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    config: NotifyConfig | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg = config or NotifyConfig.from_env()
    event = str(event_type or "TEST").upper()
    payload = data or {}
    text = format_event(event, payload)

    record = {
        "timestamp": utc_now(),
        "eventType": event,
        "dryRun": bool(dry_run),
        "text": text,
        "sent": False,
        "ok": False,
        "error": "",
    }

    # HOLD → skip push (renderer returned None, wrapper gave us "")
    if not text.strip():
        record.update({"ok": True, "skipped": True, "status": "skipped_hold", "error": "action=HOLD"})
        append_history(cfg, record)
        return {"ok": True, "sent": False, "skipped": True, "status": "skipped_hold", "reason": "action=HOLD", "record": record}

    if not cfg.enabled:
        record.update({"ok": True, "skipped": True, "error": "notify_disabled"})
        append_history(cfg, record)
        return {"ok": True, "sent": False, "skipped": True, "reason": "notify_disabled", "record": record}

    if not cfg.event_enabled(event):
        record.update({"ok": True, "skipped": True, "error": "event_disabled"})
        append_history(cfg, record)
        return {"ok": True, "sent": False, "skipped": True, "reason": "event_disabled", "record": record}

    if dry_run:
        record.update({"ok": True, "sent": False, "dryRun": True})
        append_history(cfg, record)
        return {"ok": True, "sent": False, "dryRun": True, "record": record}

    if not cfg.telegram_configured:
        record.update({"ok": False, "sent": False, "error": "telegram_not_configured"})
        append_history(cfg, record)
        return {"ok": False, "sent": False, "error": "telegram_not_configured", "record": record}

    if not cfg.telegram_push_allowed:
        record.update({"ok": False, "sent": False, "error": "telegram_push_disabled"})
        append_history(cfg, record)
        return {"ok": False, "sent": False, "error": "telegram_push_disabled", "record": record}

    bot = TelegramBot(cfg.bot_token, cfg.chat_id, timeout=cfg.request_timeout, max_retries=cfg.max_retries)
    result = await bot.send_message_result(text, disable_notification=_should_disable_notification(event))
    record.update({"ok": result.ok, "sent": result.ok, "error": result.error, "statusCode": result.status_code})
    append_history(cfg, record)
    return {"ok": result.ok, "sent": result.ok, "error": result.error, "record": record}


async def send_ai_analysis_summary(report: dict[str, Any], config: NotifyConfig | None = None, dry_run: bool = False) -> dict[str, Any]:
    return await send_event("AI_ANALYSIS", _event_payload_from_analysis(report), config=config, dry_run=dry_run)


def _read_csv_rows(path: Path, limit: int = 500) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    return rows[-limit:]


def build_daily_digest(config: NotifyConfig | None = None) -> dict[str, Any]:
    cfg = config or NotifyConfig.from_env()
    journal = _read_csv_rows(cfg.runtime_dir / "QuantGod_TradeJournal.csv")
    closes = _read_csv_rows(cfg.runtime_dir / "QuantGod_CloseHistory.csv")
    shadow = _read_csv_rows(cfg.runtime_dir / "QuantGod_ShadowSignalLedger.csv")
    pnl = 0.0
    wins = 0
    losses = 0
    for row in closes:
        raw = row.get("Profit") or row.get("profit") or row.get("PnL") or row.get("pnl") or "0"
        try:
            value = float(str(raw).replace("$", "").replace(",", ""))
        except ValueError:
            continue
        pnl += value
        if value > 0:
            wins += 1
        elif value < 0:
            losses += 1
    route_counts: dict[str, int] = {}
    for row in journal:
        route = row.get("Route") or row.get("route") or row.get("Strategy") or "unknown"
        route_counts[route] = route_counts.get(route, 0) + 1
    route_summary = " ".join(f"{route}: {count}" for route, count in sorted(route_counts.items())[:5]) or "routes: --"
    return {"pnl": pnl, "wins": wins, "losses": losses, "routes": route_summary, "shadowSignals": len(shadow)}


async def send_daily_digest(config: NotifyConfig | None = None, dry_run: bool = False) -> dict[str, Any]:
    cfg = config or NotifyConfig.from_env()
    return await send_event("DAILY_DIGEST", build_daily_digest(cfg), config=cfg, dry_run=dry_run)


def scan_runtime_events(config: NotifyConfig | None = None) -> list[dict[str, Any]]:
    """Best-effort one-shot scanner used by Task Scheduler or manual smoke tests."""
    cfg = config or NotifyConfig.from_env()
    events: list[dict[str, Any]] = []
    dashboard = _read_json(cfg.runtime_dir / "QuantGod_Dashboard.json", {})
    if isinstance(dashboard, dict):
        if dashboard.get("killSwitchActive") or dashboard.get("KillSwitchActive"):
            events.append({"eventType": "KILL_SWITCH", "data": {"reason": dashboard.get("killSwitchReason") or dashboard.get("KillSwitchReason") or "dashboard", "pnl": dashboard.get("dailyPnl") or dashboard.get("DailyPnl") or 0}})
        news = dashboard.get("news") or {}
        news_active = news.get("blocked") or news.get("active")
        if news_active:
            events.append({
                "eventType": "NEWS_BLOCK",
                "data": {
                    "label": news.get("eventLabel") or news.get("eventName") or "tracked USD event",
                    "eta": news.get("minutesToEvent") or "--",
                    "phase": news.get("phase"),
                    "actual": news.get("actual"),
                    "forecast": news.get("forecast"),
                    "previous": news.get("previous"),
                    "reason": news.get("reason"),
                },
            })
    ai_latest = _read_json(cfg.runtime_dir / "ai_analysis" / "latest.json", {})
    if isinstance(ai_latest, dict) and ai_latest:
        events.append({"eventType": "AI_ANALYSIS", "data": _event_payload_from_analysis(ai_latest)})
    return events


async def scan_once(config: NotifyConfig | None = None, dry_run: bool = False) -> dict[str, Any]:
    cfg = config or NotifyConfig.from_env()
    results = []
    for event in scan_runtime_events(cfg):
        results.append(await send_event(event["eventType"], event.get("data", {}), config=cfg, dry_run=dry_run))
    return {"ok": True, "count": len(results), "results": results}


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)
