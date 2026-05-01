from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..llm_client import LLMClient, LLMClientError

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


class BaseAgent(ABC):
    name = "base"
    required_fields: tuple[str, ...] = ("agent",)

    def __init__(
        self,
        llm: LLMClient,
        model: str | None = None,
        prompt_path: str | Path | None = None,
        use_fallback_on_error: bool = True,
    ) -> None:
        self.llm = llm
        self.model = model
        self.prompt_path = Path(prompt_path) if prompt_path else PROMPT_DIR / f"{self.name}.md"
        self.use_fallback_on_error = use_fallback_on_error

    @abstractmethod
    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        """Analyze context and return a structured dict."""

    def load_prompt(self, variables: dict[str, Any] | None = None) -> str:
        text = self.prompt_path.read_text(encoding="utf-8")
        for key, value in (variables or {}).items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    def validate_response(self, response: dict[str, Any]) -> bool:
        if not isinstance(response, dict):
            return False
        if response.get("agent") != self.name:
            return False
        return all(field in response for field in self.required_fields)

    async def _llm_json(self, context: dict[str, Any], max_tokens: int = 4096) -> dict[str, Any]:
        prompt = self.load_prompt({"agent_name": self.name})
        payload = json.dumps(context, ensure_ascii=False, default=_json_default)
        response = await self.llm.chat(
            system_prompt=prompt,
            user_message=payload,
            model=self.model,
            temperature=0.2,
            max_tokens=max_tokens,
            response_format="json",
        )
        if not isinstance(response, dict):
            raise LLMClientError(f"{self.name} agent expected JSON object")
        response.setdefault("agent", self.name)
        response.setdefault("model", self.model or self.llm.default_model)
        response.setdefault("timestamp", utc_now_iso())
        response.setdefault("cost_usd", 0.0)
        return response

    def _validate_or_raise(self, response: dict[str, Any]) -> dict[str, Any]:
        if not self.validate_response(response):
            missing = [field for field in self.required_fields if field not in response]
            raise LLMClientError(
                f"{self.name} agent returned invalid schema; missing={missing}, "
                f"agent={response.get('agent')!r}"
            )
        return response


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def last_close(snapshot: dict[str, Any]) -> float | None:
    for key in ("kline_m15", "kline_h1", "kline_h4", "kline_d1"):
        bars = snapshot.get(key)
        if isinstance(bars, list) and bars:
            value = bars[-1].get("close") if isinstance(bars[-1], dict) else None
            if value is not None:
                return as_float(value)
    current = snapshot.get("current_price") or {}
    if isinstance(current, dict):
        bid = as_float(current.get("bid"), 0.0)
        ask = as_float(current.get("ask"), 0.0)
        if bid and ask:
            return (bid + ask) / 2
        return bid or ask or None
    return None
