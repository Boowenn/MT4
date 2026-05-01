"""QuantGod Phase 1 AI analysis package.

The package is intentionally advisory/read-only. It can write analysis artifacts for
Dashboard/Governance review, but it must never place, close, cancel, or modify live
orders or presets.
"""

from .analysis_service import AnalysisService
from .config import AIAnalysisConfig, load_config
from .llm_client import LLMClient, LLMClientError

__all__ = [
    "AIAnalysisConfig",
    "AnalysisService",
    "LLMClient",
    "LLMClientError",
    "load_config",
]
