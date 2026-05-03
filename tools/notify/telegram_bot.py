from __future__ import annotations

import asyncio
import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .event_formatter import format_event


@dataclass
class TelegramSendResult:
    ok: bool
    error: str = ""
    status_code: int | None = None


class TelegramBot:
    def __init__(self, token: str, chat_id: str, timeout: float = 10, max_retries: int = 2):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_error = ""

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> bool:
        result = await self.send_message_result(text, parse_mode=parse_mode, disable_notification=disable_notification)
        return result.ok

    async def send_message_result(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> TelegramSendResult:
        if not self.token or not self.chat_id:
            self.last_error = "telegram_not_configured"
            return TelegramSendResult(ok=False, error=self.last_error)
        payload = {
            "chat_id": self.chat_id,
            "text": str(text)[:4096],
            "parse_mode": parse_mode,
            "disable_notification": bool(disable_notification),
            "disable_web_page_preview": True,
        }
        return await asyncio.to_thread(self._post_with_retries, payload)

    async def send_alert(self, event_type: str, data: dict[str, Any]) -> bool:
        return await self.send_message(format_event(event_type, data))

    def _post_with_retries(self, payload: dict[str, Any]) -> TelegramSendResult:
        last = TelegramSendResult(ok=False, error="not_attempted")
        for attempt in range(self.max_retries + 1):
            last = self._post_once(payload)
            if last.ok:
                self.last_error = ""
                return last
            if attempt >= self.max_retries:
                break
            time.sleep(min(2.0, 0.4 * (2**attempt)))
        self.last_error = last.error
        return last

    def _post_once(self, payload: dict[str, Any]) -> TelegramSendResult:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            try:
                import certifi  # type: ignore

                context = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                context = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=context) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body or "{}")
                ok = bool(parsed.get("ok"))
                return TelegramSendResult(ok=ok, error="" if ok else "telegram_api_rejected", status_code=response.status)
        except urllib.error.HTTPError as error:
            safe_message = f"telegram_http_{error.code}"
            return TelegramSendResult(ok=False, error=safe_message, status_code=error.code)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            return TelegramSendResult(ok=False, error=type(error).__name__)
