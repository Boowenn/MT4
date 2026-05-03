"""Safety defaults for the QuantGod P2-3 SQLite state layer.

The state layer is deliberately non-execution infrastructure. It stores and
serves local evidence snapshots only; it cannot send orders, mutate live presets,
override governance, store credentials, or receive Telegram trading commands.
"""

from __future__ import annotations

from typing import Dict, Any

STATE_STORE_SAFETY: Dict[str, Any] = {
    "mode": "QUANTGOD_P2_3_SQLITE_STATE_LAYER_V1",
    "phase": "P2-3",
    "localOnly": True,
    "statePersistenceOnly": True,
    "researchOnly": True,
    "advisoryOnly": True,
    "readOnlyDataPlane": True,
    "notificationPushOnly": True,
    "canExecuteTrade": False,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "canOverrideKillSwitch": False,
    "canMutateGovernanceDecision": False,
    "canPromoteOrDemoteRoute": False,
    "telegramCommandExecutionAllowed": False,
    "fundTransferAllowed": False,
    "withdrawalAllowed": False,
}

_FORBIDDEN_TRUE_KEYS = (
    "canExecuteTrade",
    "orderSendAllowed",
    "closeAllowed",
    "cancelAllowed",
    "credentialStorageAllowed",
    "livePresetMutationAllowed",
    "canOverrideKillSwitch",
    "canMutateGovernanceDecision",
    "canPromoteOrDemoteRoute",
    "telegramCommandExecutionAllowed",
    "fundTransferAllowed",
    "withdrawalAllowed",
)


def safety_payload() -> Dict[str, Any]:
    """Return a defensive copy of the immutable safety defaults."""

    return dict(STATE_STORE_SAFETY)


def assert_state_store_safety() -> None:
    """Fail fast if a future edit accidentally flips a dangerous flag."""

    missing = [key for key in _FORBIDDEN_TRUE_KEYS if key not in STATE_STORE_SAFETY]
    if missing:
        raise AssertionError(f"Missing safety keys: {', '.join(missing)}")
    unsafe = [key for key in _FORBIDDEN_TRUE_KEYS if STATE_STORE_SAFETY.get(key) is not False]
    if unsafe:
        raise AssertionError(f"SQLite state layer safety violation: {', '.join(unsafe)}")
    if STATE_STORE_SAFETY.get("localOnly") is not True:
        raise AssertionError("SQLite state layer must remain localOnly=true")
    if STATE_STORE_SAFETY.get("readOnlyDataPlane") is not True:
        raise AssertionError("SQLite state layer must remain readOnlyDataPlane=true")
