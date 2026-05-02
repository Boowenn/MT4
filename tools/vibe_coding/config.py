"""Configuration helpers for QuantGod Phase 3 Vibe Coding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class VibeCodingConfig:
    """Runtime configuration for strategy generation and backtesting.

    All paths are local. The service writes research artifacts only; it never
    writes MT5 live presets, account credentials, or order-intent files.
    """

    repo_root: Path
    runtime_dir: Path
    strategy_dir: Path
    history_dir: Path
    max_code_bytes: int = 64 * 1024
    max_backtest_bars: int = 5000
    allowed_imports: tuple[str, ...] = (
        "math",
        "statistics",
        "datetime",
        "pandas",
        "numpy",
        "talib",
        "ta",
        "pandas_ta",
        "tools.vibe_coding.strategy_template",
        "vibe_coding.strategy_template",
    )
    llm_model: str = "anthropic/claude-sonnet-4-20250514"

    def to_public_dict(self) -> dict:
        payload = asdict(self)
        for key in ("repo_root", "runtime_dir", "strategy_dir", "history_dir"):
            payload[key] = str(payload[key])
        payload["safety"] = phase3_vibe_safety()
        return payload


def _resolve_path(value: str | None, fallback: Path) -> Path:
    if not value:
        return fallback.resolve()
    p = Path(value)
    return p.resolve() if not p.is_absolute() else p


def load_config(repo_root: str | Path | None = None) -> VibeCodingConfig:
    root = Path(repo_root or os.environ.get("QG_REPO_ROOT") or Path.cwd()).resolve()
    runtime = _resolve_path(
        os.environ.get("QG_RUNTIME_DIR")
        or os.environ.get("QG_MT5_FILES_DIR")
        or os.environ.get("QG_HFM_FILES"),
        root / "runtime" / "phase3_vibe",
    )
    strategy_dir = _resolve_path(os.environ.get("QG_VIBE_STRATEGY_DIR"), runtime / "vibe_strategies")
    history_dir = _resolve_path(os.environ.get("QG_VIBE_HISTORY_DIR"), runtime / "vibe_history")
    return VibeCodingConfig(
        repo_root=root,
        runtime_dir=runtime,
        strategy_dir=strategy_dir,
        history_dir=history_dir,
        max_code_bytes=int(os.environ.get("QG_VIBE_MAX_CODE_BYTES", str(64 * 1024))),
        max_backtest_bars=int(os.environ.get("QG_VIBE_MAX_BACKTEST_BARS", "5000")),
        llm_model=os.environ.get("AI_MODEL_VIBE_CODING", "anthropic/claude-sonnet-4-20250514"),
    )


def phase3_vibe_safety() -> dict:
    return {
        "mode": "QUANTGOD_PHASE3_VIBE_CODING_V1",
        "localOnly": True,
        "researchOnly": True,
        "backtestOnly": True,
        "generatedCodeCanTradeLive": False,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "canOverrideKillSwitch": False,
        "canMutateGovernanceDecision": False,
        "canPromoteOrDemoteRoute": False,
        "requiresPathToLive": [
            "backtest",
            "ParamLab",
            "Governance Advisor",
            "Version Promotion Gate",
            "manual authorization lock",
        ],
        "allowedImports": ["pandas", "numpy", "talib", "ta", "pandas_ta", "math", "statistics", "datetime"],
    }
