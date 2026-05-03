from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .base import AIProviderConfig, AIProviderError, assert_ai_provider_safety, read_env_file, truthy
from .deepseek_provider import DeepSeekProvider
from .mock_provider import MockProvider
from .openrouter_provider import OpenRouterProvider

SUPPORTED_MODELS = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "openrouter": ["anthropic/claude-sonnet-4-20250514", "deepseek/deepseek-v4-flash"],
    "mock": ["mock-local"],
}

DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "mock": "mock://local",
}


def _first(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_ai_provider_config(
    *,
    repo_root: str | Path | None = None,
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AIProviderConfig:
    env = dict(os.environ if environ is None else environ)
    root = Path(repo_root or Path.cwd()).resolve()

    ai_env_path = Path(env_file or env.get("QG_AI_ENV_FILE") or root / ".env.ai.local").expanduser()
    deepseek_env_path = Path(env.get("QG_MT5_AI_DEEPSEEK_ENV_FILE") or root / ".env.deepseek.local").expanduser()

    merged = {}
    merged.update(read_env_file(deepseek_env_path))
    merged.update(read_env_file(ai_env_path))
    merged.update(env)

    assert_ai_provider_safety(merged)

    provider = _first(merged.get("QG_AI_PROVIDER"), fallback="deepseek").lower()
    if provider not in SUPPORTED_MODELS:
        raise AIProviderError(f"unsupported AI provider: {provider}")

    api_key = _first(
        merged.get("QG_AI_API_KEY"),
        merged.get("DEEPSEEK_API_KEY"),
        merged.get("QG_DEEPSEEK_API_KEY"),
        merged.get("QG_MT5_AI_DEEPSEEK_API_KEY"),
        merged.get("OPENROUTER_API_KEY"),
        merged.get("QG_OPENROUTER_API_KEY"),
        fallback="",
    )
    enabled_default = bool(api_key.strip()) or provider == "mock"
    enabled = truthy(merged.get("QG_AI_ENABLED", merged.get("QG_MT5_AI_DEEPSEEK_ENABLED")), enabled_default)

    default_model = SUPPORTED_MODELS[provider][0]
    model = _first(
        merged.get("QG_AI_MODEL"),
        merged.get("QG_MT5_AI_DEEPSEEK_MODEL"),
        merged.get("DEEPSEEK_MODEL"),
        merged.get("OPENROUTER_MODEL"),
        fallback=default_model,
    )
    base_url = _first(
        merged.get("QG_AI_BASE_URL"),
        merged.get("QG_DEEPSEEK_BASE_URL"),
        merged.get("DEEPSEEK_BASE_URL"),
        merged.get("OPENROUTER_BASE_URL"),
        fallback=DEFAULT_BASE_URLS[provider],
    )

    return AIProviderConfig(
        enabled=enabled,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=_int(merged.get("QG_AI_TIMEOUT_SECONDS") or merged.get("QG_MT5_AI_DEEPSEEK_TIMEOUT_SECONDS"), 45),
        max_tokens=_int(merged.get("QG_AI_MAX_TOKENS") or merged.get("QG_MT5_AI_DEEPSEEK_MAX_TOKENS"), 1800),
        temperature=_float(merged.get("QG_AI_TEMPERATURE") or merged.get("QG_MT5_AI_DEEPSEEK_TEMPERATURE"), 0.25),
        require_json=truthy(merged.get("QG_AI_REQUIRE_JSON"), True),
        daily_call_limit=_int(merged.get("QG_AI_DAILY_CALL_LIMIT"), 50),
        daily_budget_usd=_float(merged.get("QG_AI_DAILY_BUDGET_USD"), 2.0),
        env_file=str(ai_env_path),
    )


def load_ai_provider(config: AIProviderConfig | None = None, **kwargs: Any):  # type: ignore[no-untyped-def]
    cfg = config or load_ai_provider_config(**kwargs)
    if cfg.provider == "mock":
        return MockProvider(cfg)
    if cfg.provider == "openrouter":
        return OpenRouterProvider(cfg)
    if cfg.provider == "deepseek":
        return DeepSeekProvider(cfg)
    raise AIProviderError(f"unsupported AI provider: {cfg.provider}")


def supported_models_payload() -> dict[str, Any]:
    return {
        "schema": "quantgod.ai_provider.models.v1",
        "supportedProviders": sorted(SUPPORTED_MODELS.keys()),
        "models": SUPPORTED_MODELS,
        "defaultBaseUrls": DEFAULT_BASE_URLS,
        "safety": {
            "advisoryOnly": True,
            "researchOnly": True,
            "orderSendAllowed": False,
            "credentialStorageAllowed": False,
        },
    }
