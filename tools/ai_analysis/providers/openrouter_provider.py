from __future__ import annotations

from .base import AIProviderConfig
from .deepseek_provider import DeepSeekProvider


class OpenRouterProvider(DeepSeekProvider):
    """OpenRouter provider using the same OpenAI-compatible chat JSON path."""

    def __init__(self, config: AIProviderConfig, opener=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(config, opener=opener)
