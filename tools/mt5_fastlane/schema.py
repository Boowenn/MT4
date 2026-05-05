from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "token",
    "apikey",
    "api_key",
    "secret",
    "authorization",
    "bearer",
    "privatekey",
    "private_key",
}

EXECUTION_FLAGS = {
    "orderSendAllowed",
    "closeAllowed",
    "cancelAllowed",
    "modifyAllowed",
    "brokerExecutionAllowed",
    "livePresetMutationAllowed",
    "credentialStorageAllowed",
    "telegramCommandExecutionAllowed",
    "telegramWebhookReceiverAllowed",
    "webhookReceiverAllowed",
    "canOverrideKillSwitch",
}

SAFETY_PAYLOAD = {
    "localOnly": True,
    "readOnlyDataPlane": True,
    "advisoryOnly": True,
    "runtimeEvidenceOnly": True,
    "mt5FastLaneExporterOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "modifyAllowed": False,
    "brokerExecutionAllowed": False,
    "livePresetMutationAllowed": False,
    "credentialStorageAllowed": False,
    "telegramCommandExecutionAllowed": False,
    "telegramWebhookReceiverAllowed": False,
    "webhookReceiverAllowed": False,
    "canOverrideKillSwitch": False,
}

@dataclass(frozen=True)
class FastLaneThresholds:
    max_heartbeat_age_seconds: int = 5
    max_tick_age_seconds: int = 3
    max_indicator_age_seconds: int = 15
    min_tick_rows: int = 3
    max_spread_points: float = 80.0
    stale_warn_seconds: int = 10


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def _walk(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_norm = str(key).replace("-", "_").replace(" ", "_").lower()
            if key_norm in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: 禁止出现凭据/密钥字段")
            if key in EXECUTION_FLAGS and _truthy(item):
                errors.append(f"{path}.{key}: 执行类安全开关必须为 false")
            errors.extend(_walk(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            errors.extend(_walk(item, f"{path}[{idx}]"))
    return errors


def assert_safe_payload(payload: Any) -> None:
    errors = _walk(payload)
    if errors:
        raise ValueError("MT5 fast lane payload failed safety validation: " + "; ".join(errors[:5]))


def safety_payload() -> dict[str, bool]:
    return dict(SAFETY_PAYLOAD)


def runtime_dir(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()
