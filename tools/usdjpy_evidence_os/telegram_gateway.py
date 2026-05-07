from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

from .io_utils import append_jsonl, read_jsonl_tail, utc_now_iso, write_json
from .schema import AGENT_VERSION, SAFETY_BOUNDARY, gateway_ledger_path, gateway_status_path


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


def dispatch_event(runtime_dir: Path, event: Dict[str, Any], send: bool = False) -> Dict[str, Any]:
    ledger = gateway_ledger_path(runtime_dir)
    recent_ids = {row.get("eventId") for row in read_jsonl_tail(ledger, 200)}
    duplicate = event.get("eventId") in recent_ids
    delivery = {"ok": False, "skipped": True, "reason": "send_disabled"}
    if send and not duplicate:
        delivery = _send_telegram(event.get("text", ""))
    row = {
        **event,
        "duplicateSuppressed": duplicate,
        "delivery": delivery,
    }
    append_jsonl(ledger, [row])
    status = {
        "ok": True,
        "schema": "quantgod.telegram_gateway_status.v1",
        "agentVersion": AGENT_VERSION,
        "lastEventId": event.get("eventId"),
        "duplicateSuppressed": duplicate,
        "sendRequested": bool(send),
        "delivery": delivery,
        "reasonZh": "Telegram Gateway 统一做中文模板、去重、投递账本；不接收 Telegram 交易命令。",
        "safety": dict(SAFETY_BOUNDARY),
    }
    write_json(gateway_status_path(runtime_dir), status)
    return status


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

