from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "quantgod.usdjpy_strategy_policy_lab.v1"
FOCUS_SYMBOL = "USDJPYc"
FOCUS_SYMBOL_ALIASES = {"USDJPY", "USDJPYc", "USDJPYm", "USDJPYpro", "USDJPY."}
DEFAULT_STRATEGIES = [
    "RSI_Reversal",
    "MA_Cross",
    "BB_Triple",
    "MACD_Divergence",
    "SR_Breakout",
]
DIRECTIONS = ("LONG", "SHORT")

STATUS_RUNNABLE = "RUNNABLE"
STATUS_WATCH_ONLY = "WATCH_ONLY"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_PAUSED = "PAUSED"

ENTRY_STANDARD = "STANDARD_ENTRY"
ENTRY_OPPORTUNITY = "OPPORTUNITY_ENTRY"
ENTRY_BLOCKED = "BLOCKED"

READ_ONLY_SAFETY = {
    "localOnly": True,
    "focusOnly": True,
    "focusSymbol": FOCUS_SYMBOL,
    "readOnlyDataPlane": True,
    "advisoryOnly": True,
    "dryRunOnly": True,
    "shadowTradingOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "modifyAllowed": False,
    "livePresetMutationAllowed": False,
    "writesMt5Preset": False,
    "writesMt5OrderRequest": False,
    "telegramCommandExecutionAllowed": False,
    "webhookReceiverAllowed": False,
    "credentialStorageAllowed": False,
}

SECRET_KEYS = {
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "bearer",
    "private_key",
    "mnemonic",
}
EXECUTION_KEYS = {
    "orderSendAllowed",
    "closeAllowed",
    "cancelAllowed",
    "modifyAllowed",
    "livePresetMutationAllowed",
    "writesMt5Preset",
    "writesMt5OrderRequest",
    "telegramCommandExecutionAllowed",
    "webhookReceiverAllowed",
    "brokerExecutionAllowed",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip()
    if text in FOCUS_SYMBOL_ALIASES or text.upper().startswith("USDJPY"):
        return FOCUS_SYMBOL
    return text


def is_focus_symbol(symbol: Any) -> bool:
    return normalize_symbol(symbol) == FOCUS_SYMBOL


def direction_cn(direction: Any) -> str:
    value = str(direction or "").strip().upper()
    if value in {"LONG", "BUY", "多", "买", "买入"}:
        return "买入观察"
    if value in {"SHORT", "SELL", "空", "卖", "卖出"}:
        return "卖出观察"
    return "方向待确认"


def status_cn(status: Any) -> str:
    mapping = {
        STATUS_RUNNABLE: "允许运行",
        STATUS_WATCH_ONLY: "仅影子观察",
        STATUS_INSUFFICIENT_DATA: "样本不足",
        STATUS_PAUSED: "暂停",
        ENTRY_STANDARD: "标准入场候选",
        ENTRY_OPPORTUNITY: "机会入场候选",
        ENTRY_BLOCKED: "阻断",
    }
    return mapping.get(str(status or ""), str(status or "未知"))


def assert_no_secret_or_execution_flags(payload: Any, path: str = "root") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lower = str(key).lower()
            if lower in SECRET_KEYS or any(secret in lower for secret in SECRET_KEYS):
                raise ValueError(f"secret-like field is forbidden at {path}.{key}")
            if key in EXECUTION_KEYS and bool(value):
                raise ValueError(f"truthy execution flag is forbidden at {path}.{key}")
            assert_no_secret_or_execution_flags(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            assert_no_secret_or_execution_flags(item, f"{path}[{idx}]")


@dataclass
class RouteScore:
    symbol: str
    strategy: str
    direction: str
    regime: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    sampleCount: int = 0
    winRate: float = 0.0
    avgR: float = 0.0
    avgPips: float = 0.0
    profitFactor: float = 0.0
    mfeP50: float = 0.0
    mfeP70: float = 0.0
    maeP70: float = 0.0
    mfeCaptureRate: float = 0.0
    lossStreak: int = 0
    status: str = STATUS_INSUFFICIENT_DATA
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyItem:
    symbol: str
    strategy: str
    direction: str
    regime: str
    entryMode: str
    allowed: bool
    recommendedLot: float
    maxLot: float
    score: float
    entryStrictness: str
    exitMode: str
    breakevenDelayR: float
    trailStartR: float
    timeStopBars: int
    reasons: List[str] = field(default_factory=list)
    safety: Dict[str, Any] = field(default_factory=lambda: dict(READ_ONLY_SAFETY))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
