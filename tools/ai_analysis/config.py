from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_RUNTIME_DIR = r"C:\Program Files\HFM Metatrader 5\MQL5\Files"
DEFAULT_HISTORY_SUBDIR = "ai_analysis"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _path_from_env(name: str, default: str | Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser() if raw else Path(default).expanduser()


def default_runtime_dir() -> Path:
    return _path_from_env(
        "QG_RUNTIME_DIR",
        os.getenv("QG_MT5_FILES_DIR", DEFAULT_RUNTIME_DIR),
    )


@dataclass(frozen=True)
class AIAnalysisConfig:
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    model_technical: str = DEFAULT_MODEL
    model_risk: str = DEFAULT_MODEL
    model_decision: str = DEFAULT_MODEL
    request_timeout: float = 60.0
    max_retries: int = 2
    runtime_dir: Path = Path(DEFAULT_RUNTIME_DIR)
    history_dir: Path = Path(DEFAULT_RUNTIME_DIR) / DEFAULT_HISTORY_SUBDIR
    mock_mode: bool = False
    dry_run_advisory_only: bool = True

    @property
    def safe_runtime_dir(self) -> Path:
        return Path(self.runtime_dir).expanduser()

    @property
    def safe_history_dir(self) -> Path:
        return Path(self.history_dir).expanduser()


def load_config() -> AIAnalysisConfig:
    runtime_dir = default_runtime_dir()
    history_dir = _path_from_env(
        "AI_ANALYSIS_HISTORY_DIR",
        runtime_dir / DEFAULT_HISTORY_SUBDIR,
    )
    return AIAnalysisConfig(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_base_url=os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1/chat/completions",
        ).strip(),
        model_technical=os.getenv("AI_MODEL_TECHNICAL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        model_risk=os.getenv("AI_MODEL_RISK", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        model_decision=os.getenv("AI_MODEL_DECISION", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        request_timeout=_env_float("AI_REQUEST_TIMEOUT", 60.0),
        max_retries=_env_int("AI_MAX_RETRIES", 2),
        runtime_dir=runtime_dir,
        history_dir=history_dir,
        mock_mode=_env_bool("AI_ANALYSIS_MOCK_MODE", False),
        dry_run_advisory_only=True,
    )
