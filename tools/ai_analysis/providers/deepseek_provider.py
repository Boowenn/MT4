from __future__ import annotations

import json
import ssl
from typing import Any, Callable
import urllib.error
import urllib.request

from .base import AIProviderConfig, AIProviderError, AIProviderResponse, parse_json_object

Opener = Callable[[urllib.request.Request, int], Any]


def default_urlopen(request: urllib.request.Request, timeout_seconds: int) -> Any:
    try:
        import certifi  # type: ignore

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    return urllib.request.urlopen(request, timeout=timeout_seconds, context=context)


def chat_completions_url(base_url: str) -> str:
    base = str(base_url or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def anthropic_messages_url(base_url: str) -> str:
    base = str(base_url or "https://api.deepseek.com/anthropic").rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    return f"{base}/v1/messages"


def uses_anthropic_gateway(base_url: str) -> bool:
    return "/anthropic" in str(base_url or "").lower()


class DeepSeekProvider:
    """OpenAI/Anthropic-compatible DeepSeek provider.

    This class is intentionally generic so MT5 advisory, Vibe research, journal
    summaries, and future read-only context features can share one safe client.
    """

    def __init__(self, config: AIProviderConfig, opener: Opener | None = None) -> None:
        self.config = config
        self.opener = opener or default_urlopen

    def chat_json(self, *, system_prompt: str, user_payload: dict[str, Any], purpose: str = "advisory") -> AIProviderResponse:
        if not self.config.enabled:
            return AIProviderResponse(False, self.config.provider, self.config.model, "disabled")
        if not self.config.configured:
            return AIProviderResponse(False, self.config.provider, self.config.model, "missing_api_key")
        payload = self._build_payload(system_prompt, user_payload)
        data = self._post(payload)
        content = self._extract_content(data)
        parsed = parse_json_object(content) if self.config.require_json else {"text": content}
        return AIProviderResponse(
            ok=True,
            provider=self.config.provider,
            model=self.config.model,
            status="ok",
            parsed=parsed,
            content=content,
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else {},
        )

    def _build_payload(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        user_content = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
        if uses_anthropic_gateway(self.config.base_url):
            return {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
            }
        payload: dict[str, Any] = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if self.config.require_json:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        is_anthropic = uses_anthropic_gateway(self.config.base_url)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        headers.update(self.config.extra_headers)
        if is_anthropic:
            headers["anthropic-version"] = "2023-06-01"
        request = urllib.request.Request(
            anthropic_messages_url(self.config.base_url) if is_anthropic else chat_completions_url(self.config.base_url),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self.opener(request, self.config.timeout_seconds) as response:  # type: ignore[misc]
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise AIProviderError(f"AI provider HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise AIProviderError(f"AI provider request failed: {error.reason}") from error
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AIProviderError("AI provider returned non-JSON response") from error
        if not isinstance(parsed, dict):
            raise AIProviderError("AI provider response must be a JSON object")
        return parsed

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        content_blocks = data.get("content")
        if isinstance(content_blocks, list):
            text_parts = [
                str(item.get("text") or "").strip()
                for item in content_blocks
                if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text") or "").strip()
            ]
            if text_parts:
                return "\n".join(text_parts).strip()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise AIProviderError("AI provider response missing text content") from error
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider response content is empty")
        return content.strip()
