from __future__ import annotations

from typing import Any, Mapping

FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "bearer",
    "private_key",
    "wallet_private_key",
    "order_request",
    "live_preset",
}

EXECUTION_FLAGS = {
    "orderSendAllowed",
    "closeAllowed",
    "cancelAllowed",
    "modifyAllowed",
    "orderModifyAllowed",
    "brokerExecutionAllowed",
    "credentialStorageAllowed",
    "livePresetMutationAllowed",
    "telegramCommandExecutionAllowed",
    "webhookReceiverAllowed",
    "canOverrideKillSwitch",
    "writesMt5OrderRequest",
    "writesMt5Preset",
}


def safety_payload() -> dict[str, bool]:
    return {
        "localOnly": True,
        "readOnlyDataPlane": True,
        "advisoryOnly": True,
        "shadowTradingOnly": True,
        "dynamicSltpCalibrationOnly": True,
        "telegramPushOnly": True,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "modifyAllowed": False,
        "orderModifyAllowed": False,
        "brokerExecutionAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "telegramCommandExecutionAllowed": False,
        "webhookReceiverAllowed": False,
        "canOverrideKillSwitch": False,
        "writesMt5OrderRequest": False,
        "writesMt5Preset": False,
    }


def _walk(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lower = str(key).replace("-", "_").lower()
            if lower in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden secret-like field at {path}.{key}")
            if key in EXECUTION_FLAGS and item is True:
                raise ValueError(f"execution flag must be false at {path}.{key}")
            _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]")


def assert_safe_payload(payload: Mapping[str, Any]) -> None:
    _walk(payload)
    safety = payload.get("safety") if isinstance(payload, Mapping) else None
    if isinstance(safety, Mapping):
        for flag in EXECUTION_FLAGS:
            if safety.get(flag) is True:
                raise ValueError(f"unsafe safety flag: {flag}")
