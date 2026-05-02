from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _default_runtime_dir() -> Path:
    raw = os.getenv("QG_RUNTIME_DIR") or os.getenv("QG_MT5_FILES_DIR") or os.getenv("QG_HFM_FILES")
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "runtime" / "notify"


@dataclass(frozen=True)
class NotifyConfig:
    bot_token: str
    chat_id: str
    enabled: bool
    runtime_dir: Path
    history_path: Path
    request_timeout: float
    max_retries: int
    notify_trade_signal: bool
    notify_risk_alert: bool
    notify_ai_summary: bool
    notify_daily_digest: bool
    notify_governance: bool

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        runtime_dir = _default_runtime_dir()
        history_path = Path(os.getenv("QG_NOTIFY_HISTORY_PATH", str(runtime_dir / "QuantGod_NotifyHistory.json"))).expanduser()
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            enabled=_bool_env("QG_NOTIFY_ENABLED", True),
            runtime_dir=runtime_dir,
            history_path=history_path,
            request_timeout=float(os.getenv("QG_NOTIFY_TIMEOUT", "10") or 10),
            max_retries=max(0, int(os.getenv("QG_NOTIFY_MAX_RETRIES", "2") or 2)),
            notify_trade_signal=_bool_env("NOTIFY_TRADE_SIGNAL", True),
            notify_risk_alert=_bool_env("NOTIFY_RISK_ALERT", True),
            notify_ai_summary=_bool_env("NOTIFY_AI_SUMMARY", True),
            notify_daily_digest=_bool_env("NOTIFY_DAILY_DIGEST", True),
            notify_governance=_bool_env("NOTIFY_GOVERNANCE", False),
        )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def event_enabled(self, event_type: str) -> bool:
        event = str(event_type or "").upper()
        if event in {"TEST"}:
            return True
        if event in {"TRADE_OPEN", "TRADE_CLOSE"}:
            return self.notify_trade_signal
        if event in {"KILL_SWITCH", "NEWS_BLOCK", "CONSECUTIVE_LOSS"}:
            return self.notify_risk_alert
        if event == "AI_ANALYSIS":
            return self.notify_ai_summary
        if event == "DAILY_DIGEST":
            return self.notify_daily_digest
        if event == "GOVERNANCE":
            return self.notify_governance
        return True

    def public_dict(self) -> dict:
        return {
            "ok": True,
            "mode": "QUANTGOD_NOTIFY_CONFIG_V1",
            "enabled": self.enabled,
            "telegramConfigured": self.telegram_configured,
            "tokenConfigured": bool(self.bot_token),
            "chatConfigured": bool(self.chat_id),
            "runtimeDir": str(self.runtime_dir),
            "historyPath": str(self.history_path),
            "requestTimeout": self.request_timeout,
            "maxRetries": self.max_retries,
            "events": {
                "tradeSignal": self.notify_trade_signal,
                "riskAlert": self.notify_risk_alert,
                "aiSummary": self.notify_ai_summary,
                "dailyDigest": self.notify_daily_digest,
                "governance": self.notify_governance,
            },
            "safety": {
                "pushOnly": True,
                "telegramCommandsAccepted": False,
                "orderSendAllowed": False,
                "closeAllowed": False,
                "cancelAllowed": False,
                "livePresetMutationAllowed": False,
            },
        }
