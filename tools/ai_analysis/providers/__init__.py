"""Shared AI provider router for QuantGod advisory features.

The provider package is intentionally execution-free: it can call LLM APIs for
JSON advisory/research output, but it exposes no trading, Telegram receiver, or
credential-storage capability.
"""

from .base import AIProviderConfig, AIProviderError, AIProviderResponse, provider_safety_payload
from .router import load_ai_provider, load_ai_provider_config

__all__ = [
    "AIProviderConfig",
    "AIProviderError",
    "AIProviderResponse",
    "provider_safety_payload",
    "load_ai_provider",
    "load_ai_provider_config",
]
