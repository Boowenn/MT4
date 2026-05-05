from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

SAFETY_DEFAULTS: Dict[str, bool] = {
    "localOnly": True,
    "readOnlyDataPlane": True,
    "advisoryOnly": True,
    "entryTriggerLabOnly": True,
    "shadowTradingOnly": True,
    "telegramPushOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "orderModifyAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "canOverrideKillSwitch": False,
    "telegramCommandExecutionAllowed": False,
    "telegramWebhookReceiverAllowed": False,
    "webhookReceiverAllowed": False,
    "brokerExecutionAllowed": False,
    "writesMt5OrderRequest": False,
    "writesMt5Preset": False,
}
SECRETLIKE_KEYS = {"password","passwd","token","apikey","api_key","secret","authorization","bearer","private_key","privatekey"}
EXECUTION_FLAGS = {"orderSendAllowed","closeAllowed","cancelAllowed","orderModifyAllowed","brokerExecutionAllowed","livePresetMutationAllowed","canOverrideKillSwitch","telegramCommandExecutionAllowed","telegramWebhookReceiverAllowed","webhookReceiverAllowed","writesMt5OrderRequest","writesMt5Preset"}

@dataclass
class TriggerDecision:
    symbol: str
    direction: str
    timeframe: str
    state: str
    score: float
    reasons: List[str]
    confirmations: Dict[str, bool]
    suggested_wait: str
    generated_at: str
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def assert_safe_payload(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).replace("-", "_").lower()
            if lower in SECRETLIKE_KEYS:
                raise ValueError(f"secret-like key is forbidden at {path}.{key}")
            if key in EXECUTION_FLAGS and child is True:
                raise ValueError(f"execution flag must not be true at {path}.{key}")
            assert_safe_payload(child, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            assert_safe_payload(child, f"{path}[{idx}]")
