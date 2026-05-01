from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import urllib.error
import urllib.request
from typing import Any

LOGGER = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Raised when the OpenRouter client cannot return a usable response."""


class LLMClient:
    def __init__(
        self,
        api_key: str = "",
        default_model: str = "anthropic/claude-sonnet-4-20250514",
        timeout: float = 60.0,
        max_retries: int = 2,
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.default_model = default_model
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.base_url = base_url

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: str = "json",
    ) -> dict[str, Any] | str:
        """Call OpenRouter chat completions and return parsed JSON or text.

        The implementation uses only the Python standard library so QuantGod's
        current unittest-based CI can run without extra dependencies. HTTP work is
        delegated to a thread to keep the public method async.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        elif response_format != "text":
            raise ValueError("response_format must be 'json' or 'text'")

        data = await asyncio.to_thread(self._request_with_retries, payload)
        content = self._extract_content(data)
        if response_format == "text":
            return content
        return self.parse_json_content(content)

    def _request_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise LLMClientError("OPENROUTER_API_KEY is required unless using a mock LLM")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_once(payload)
            except urllib.error.HTTPError as error:
                last_error = error
                retryable = error.code in {408, 409, 425, 429, 500, 502, 503, 504}
                if not retryable or attempt >= self.max_retries:
                    detail = self._safe_error_body(error)
                    raise LLMClientError(f"OpenRouter HTTP {error.code}: {detail}") from error
                self._sleep_before_retry(attempt)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                if attempt >= self.max_retries:
                    raise LLMClientError(f"OpenRouter request failed: {error}") from error
                self._sleep_before_retry(attempt)

        raise LLMClientError(f"OpenRouter request failed: {last_error}")

    def _post_once(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Title": "QuantGod AI Analysis",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - operator-configured OpenRouter URL
            raw = response.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise LLMClientError("OpenRouter returned non-JSON response") from error

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMClientError("OpenRouter response missing choices[0].message.content") from error
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("OpenRouter response content is empty")
        return content.strip()

    @staticmethod
    def parse_json_content(content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            text = text[first : last + 1]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise LLMClientError("LLM response is not valid JSON") from error
        if not isinstance(parsed, dict):
            raise LLMClientError("LLM JSON response must be an object")
        return parsed

    @staticmethod
    def _safe_error_body(error: urllib.error.HTTPError) -> str:
        try:
            return error.read(2048).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive only
            return str(error)

    @staticmethod
    def _sleep_before_retry(attempt: int) -> None:
        delay = min(8.0, 0.75 * (2**attempt)) + random.uniform(0.0, 0.25)
        time.sleep(delay)

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate call cost in USD using conservative fallback pricing.

        Exact OpenRouter pricing can change, so this method is deliberately a rough
        local estimate. Unknown models return 0.0 rather than pretending precision.
        """

        price_per_million = {
            "anthropic/claude-sonnet-4-20250514": (3.0, 15.0),
            "anthropic/claude-3.7-sonnet": (3.0, 15.0),
            "openai/gpt-4.1": (2.0, 8.0),
            "openai/gpt-4.1-mini": (0.4, 1.6),
        }
        input_price, output_price = price_per_million.get(model, (0.0, 0.0))
        return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)
