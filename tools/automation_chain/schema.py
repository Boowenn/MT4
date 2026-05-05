from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

SCHEMA = "quantgod.automation_chain.v1"
LATEST_NAME = "QuantGod_AutomationChainLatest.json"
RUN_NAME = "QuantGod_AutomationChainRun.json"
LEDGER_NAME = "QuantGod_AutomationChainLedger.csv"

FORBIDDEN_KEYS = {
    "ordersendallowed",
    "closeallowed",
    "cancelallowed",
    "modifyallowed",
    "credentialstorageallowed",
    "livepresetmutationallowed",
    "telegramcommandexecutionallowed",
    "webhookreceiverallowed",
    "brokerexecutionallowed",
    "writesmt5orderrequest",
    "writesmt5preset",
}

SECRET_LIKE = ("password", "passwd", "token", "apikey", "api_key", "secret", "authorization", "bearer", "private_key")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def automation_dir(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / "automation"


def latest_path(runtime_dir: str | Path) -> Path:
    return automation_dir(runtime_dir) / LATEST_NAME


def run_path(runtime_dir: str | Path) -> Path:
    return automation_dir(runtime_dir) / RUN_NAME


def ledger_path(runtime_dir: str | Path) -> Path:
    return automation_dir(runtime_dir) / LEDGER_NAME


def default_safety() -> Dict[str, Any]:
    return {
        "localOnly": True,
        "automationChainOnly": True,
        "advisoryOnly": True,
        "telegramPushOnly": True,
        "doesNotPlaceOrders": True,
        "doesNotClosePositions": True,
        "doesNotCancelOrders": True,
        "doesNotModifyMt5SlTp": True,
        "doesNotModifyLivePreset": True,
        "doesNotWriteMt5OrderRequest": True,
        "telegramCommandsAllowed": False,
        "webhookReceiverAllowed": False,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "modifyAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "brokerExecutionAllowed": False,
        "walletIntegrationAllowed": False,
    }


def walk_payload(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for k, v in value.items():
            key_path = f"{path}.{k}" if path else str(k)
            yield key_path, v
            yield from walk_payload(v, key_path)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk_payload(item, f"{path}[{i}]")


def validate_safe_payload(payload: Dict[str, Any]) -> None:
    errors: List[str] = []
    for key_path, value in walk_payload(payload):
        normalized = key_path.split(".")[-1].lower().replace("_", "")
        if any(part in normalized for part in SECRET_LIKE) and value not in (None, "", False):
            errors.append(f"禁止在自动化链路输出中写入疑似密钥字段：{key_path}")
        if normalized in FORBIDDEN_KEYS and bool(value):
            errors.append(f"禁止打开执行能力字段：{key_path}={value}")
    if errors:
        raise ValueError("; ".join(errors))


def build_empty_status(runtime_dir: str | Path, symbols: list[str]) -> Dict[str, Any]:
    payload = {
        "schema": SCHEMA,
        "generatedAt": now_iso(),
        "runtimeDir": str(runtime_dir),
        "symbols": symbols,
        "state": "NOT_RUN",
        "stateZh": "尚未运行",
        "steps": [],
        "missingEvidence": [],
        "blockedReasons": ["尚未生成自动化链路运行报告"],
        "opportunityCount": 0,
        "standardCount": 0,
        "blockedCount": 0,
        "safety": default_safety(),
    }
    validate_safe_payload(payload)
    return payload
