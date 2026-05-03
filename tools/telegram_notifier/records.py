"""Optional SQLite evidence recording for Telegram push-only notifications."""
from __future__ import annotations
import hashlib
from typing import Any
from .config import TelegramConfig


def stable_event_id(prefix: str, payload: dict[str, Any]) -> str:
    seed = repr(sorted(payload.items())).encode("utf-8", errors="replace")
    return f"{prefix}:{hashlib.sha256(seed).hexdigest()[:16]}"


def record_notification(config: TelegramConfig, *, event_type: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = dict(payload)
    safe_payload.pop("bot_token", None)
    safe_payload.pop("token", None)
    safe_payload.setdefault("chatIdRedacted", config.chat_id_redacted)
    event_id = stable_event_id(event_type.lower(), {"status": status, **safe_payload})
    try:
        from state_store.config import build_config as build_state_config
        from state_store.db import StateStore, utc_now_iso
        state_config = build_state_config(repo_root=config.repo_root)
        store = StateStore(state_config)
        store.init()
        store.upsert_notification_event({
            "event_id": event_id,
            "event_type": event_type,
            "channel": "telegram",
            "status": status,
            "push_only": True,
            "generated_at": utc_now_iso(),
            "source_path": "tools/run_telegram_notifier.py",
            "payload": safe_payload,
        })
        return {"ok": True, "recorded": True, "eventId": event_id, "dbPath": str(state_config.db_path)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "recorded": False, "eventId": event_id, "error": str(exc)}
