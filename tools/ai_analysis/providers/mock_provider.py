from __future__ import annotations

from typing import Any

from .base import AIProviderConfig, AIProviderResponse


class MockProvider:
    """Deterministic local provider for CI and offline smoke tests."""

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config

    def chat_json(self, *, system_prompt: str, user_payload: dict[str, Any], purpose: str = "advisory") -> AIProviderResponse:
        parsed = {
            "ok": True,
            "provider": "mock",
            "purpose": purpose,
            "verdict": "观望，不开新仓",
            "summary": "Mock provider returned a deterministic advisory-only JSON response.",
            "receivedKeys": sorted(str(key) for key in user_payload.keys()),
            "advisoryOnly": True,
            "orderSendAllowed": False,
        }
        return AIProviderResponse(True, "mock", self.config.model or "mock-local", "ok", parsed=parsed, content="")
