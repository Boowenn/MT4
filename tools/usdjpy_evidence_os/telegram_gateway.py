from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

from .io_utils import append_jsonl, append_jsonl_unique, read_jsonl_tail, utc_now_iso, write_json
from .schema import AGENT_VERSION, SAFETY_BOUNDARY, gateway_ledger_path, gateway_queue_path, gateway_status_path

MAX_EVENTS_PER_RUN = 8


def build_notification_event(source: str, topic: str, severity: str, text: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    digest = hashlib.sha256(f"{source}|{topic}|{severity}|{text[:1000]}".encode("utf-8")).hexdigest()
    return {
        "schema": "quantgod.notification.v1",
        "agentVersion": AGENT_VERSION,
        "eventId": digest[:24],
        "createdAt": utc_now_iso(),
        "source": source,
        "topic": topic,
        "severity": severity,
        "lang": "zh-CN",
        "text": text,
        "payload": payload or {},
        "safety": dict(SAFETY_BOUNDARY),
    }


def dispatch_text(
    runtime_dir: Path,
    source: str,
    topic: str,
    severity: str,
    text: str,
    payload: Dict[str, Any] | None = None,
    send: bool = False,
) -> Dict[str, Any]:
    event = build_notification_event(source, topic, severity, text, payload=payload)
    return dispatch_event(runtime_dir, event, send=send)


def dispatch_event(runtime_dir: Path, event: Dict[str, Any], send: bool = False) -> Dict[str, Any]:
    ledger = gateway_ledger_path(runtime_dir)
    recent_ids = {row.get("eventId") for row in read_jsonl_tail(ledger, 200)}
    duplicate = event.get("eventId") in recent_ids
    rate_limited = _rate_limited(ledger)
    delivery = {"ok": False, "skipped": True, "reason": "send_disabled"}
    if send and not duplicate and not rate_limited:
        delivery = _send_telegram(event.get("text", ""))
    elif rate_limited:
        delivery = {"ok": False, "skipped": True, "reason": "rate_limited"}
    row = {
        **event,
        "duplicateSuppressed": duplicate,
        "rateLimited": rate_limited,
        "delivery": delivery,
    }
    append_jsonl(ledger, [row])
    status = {
        "ok": True,
        "schema": "quantgod.telegram_gateway_status.v1",
        "agentVersion": AGENT_VERSION,
        "lastEventId": event.get("eventId"),
        "duplicateSuppressed": duplicate,
        "rateLimited": rate_limited,
        "sendRequested": bool(send),
        "delivery": delivery,
        "reasonZh": "独立 Telegram Gateway 统一做中文模板、去重、限频、投递账本；不接收 Telegram 交易命令。",
        "safety": dict(SAFETY_BOUNDARY),
    }
    write_json(gateway_status_path(runtime_dir), status)
    return status


def enqueue_event(runtime_dir: Path, event: Dict[str, Any]) -> Dict[str, Any]:
    queued = append_jsonl_unique(gateway_queue_path(runtime_dir), [event], "eventId")
    status = gateway_status(runtime_dir)
    status.update(
        {
            "queued": queued,
            "lastQueuedEventId": event.get("eventId"),
            "reasonZh": "NotificationEvent 已进入独立 Telegram Gateway 队列，等待统一投递。",
        }
    )
    write_json(gateway_status_path(runtime_dir), status)
    return status


def dispatch_pending(runtime_dir: Path, send: bool = False, limit: int = MAX_EVENTS_PER_RUN) -> Dict[str, Any]:
    queue = read_jsonl_tail(gateway_queue_path(runtime_dir), 1000)
    ledger_ids = {row.get("eventId") for row in read_jsonl_tail(gateway_ledger_path(runtime_dir), 2000)}
    pending = [row for row in queue if row.get("eventId") not in ledger_ids]
    dispatched = []
    for event in pending[: max(1, min(int(limit), MAX_EVENTS_PER_RUN))]:
        dispatched.append(dispatch_event(runtime_dir, event, send=send))
    status = gateway_status(runtime_dir)
    status.update(
        {
            "pendingCount": max(0, len(pending) - len(dispatched)),
            "dispatchedCount": len(dispatched),
            "sendRequested": bool(send),
            "dispatchResults": dispatched[-5:],
            "reasonZh": "独立 Telegram Gateway 已处理队列；只 push 中文通知，不接收交易命令。",
        }
    )
    write_json(gateway_status_path(runtime_dir), status)
    return status


def gateway_status(runtime_dir: Path) -> Dict[str, Any]:
    queue = read_jsonl_tail(gateway_queue_path(runtime_dir), 1000)
    ledger = read_jsonl_tail(gateway_ledger_path(runtime_dir), 1000)
    delivered_ids = {row.get("eventId") for row in ledger}
    pending = [row for row in queue if row.get("eventId") not in delivered_ids]
    last = ledger[-1] if ledger else {}
    return {
        "ok": True,
        "schema": "quantgod.telegram_gateway_status.v1",
        "agentVersion": AGENT_VERSION,
        "queuedCount": len(queue),
        "deliveredCount": len(ledger),
        "pendingCount": len(pending),
        "lastEventId": last.get("eventId"),
        "lastTopic": last.get("topic"),
        "lastDelivery": last.get("delivery"),
        "pushAllowed": os.environ.get("QG_TELEGRAM_PUSH_ALLOWED", "0").strip() == "1",
        "commandsAllowed": os.environ.get("QG_TELEGRAM_COMMANDS_ALLOWED", "0").strip() == "1",
        "reasonZh": "独立 Telegram Gateway 当前可审计；负责去重、限频、投递 ledger，不接收命令。",
        "safety": dict(SAFETY_BOUNDARY),
    }


def _send_telegram(text: str) -> Dict[str, Any]:
    if os.environ.get("QG_TELEGRAM_PUSH_ALLOWED", "0").strip() != "1":
        return {"ok": False, "skipped": True, "reason": "QG_TELEGRAM_PUSH_ALLOWED is not 1"}
    if os.environ.get("QG_TELEGRAM_COMMANDS_ALLOWED", "0").strip() == "1":
        return {"ok": False, "skipped": True, "reason": "Telegram command execution must stay disabled"}
    token = os.environ.get("QG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("QG_TELEGRAM_CHAT_ID", "").strip()
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


def _rate_limited(ledger: Path) -> bool:
    current_hour = utc_now_iso()[:13]
    recent = read_jsonl_tail(ledger, 200)
    sent = [
        row
        for row in recent
        if (row.get("delivery") or {}).get("ok") and str(row.get("createdAt") or "").startswith(current_hour)
    ]
    return len(sent) >= MAX_EVENTS_PER_RUN
