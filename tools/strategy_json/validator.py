from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .normalizer import normalize_strategy_json
from .safety import find_forbidden_tokens
from .schema import (
    ALLOWED_DIRECTIONS,
    ALLOWED_LANES,
    ALLOWED_STRATEGY_FAMILIES,
    ALLOWED_TIMEFRAMES,
    FOCUS_SYMBOL,
    LIVE_FORBIDDEN_STAGES,
    SCHEMA_VERSION,
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _check_range(name: str, value: Any, low: float, high: float) -> Tuple[bool, str]:
    numeric = _num(value, low - 1)
    if numeric < low or numeric > high:
        return False, f"{name} 超出允许范围"
    return True, ""


def _reject(seed: Dict[str, Any], code: str, reason: str, details: List[str] | None = None) -> Dict[str, Any]:
    return {
        "seedId": seed.get("seedId", "UNKNOWN"),
        "valid": False,
        "blockerCode": code,
        "reasonZh": reason,
        "details": details or [],
    }


def validate_strategy_json(seed: Dict[str, Any]) -> Dict[str, Any]:
    if seed.get("symbol") not in (None, FOCUS_SYMBOL):
        return _reject(seed, "NON_USDJPY_REJECTED", "GA 只允许 USDJPYc 策略种子")
    data = normalize_strategy_json(seed)
    if data.get("schema") != SCHEMA_VERSION:
        return _reject(data, "SCHEMA_INVALID", "Strategy JSON schema 不匹配")
    if data.get("symbol") != FOCUS_SYMBOL:
        return _reject(data, "NON_USDJPY_REJECTED", "GA 只允许 USDJPYc 策略种子")
    if data.get("lane") not in ALLOWED_LANES:
        return _reject(data, "LANE_INVALID", "策略种子只能进入 MT5 Shadow / Tester / Paper-live-sim")
    if data.get("strategyFamily") not in ALLOWED_STRATEGY_FAMILIES:
        return _reject(data, "STRATEGY_FAMILY_INVALID", "策略族不在允许的 USDJPY 模拟池内")
    if data.get("direction") not in ALLOWED_DIRECTIONS:
        return _reject(data, "DIRECTION_INVALID", "方向字段不合法")

    stage = str((data.get("risk") or {}).get("stage") or "SHADOW").upper()
    if stage in LIVE_FORBIDDEN_STAGES:
        return _reject(data, "LIVE_STAGE_REJECTED", "GA 种子不能直接进入 MICRO_LIVE 或 LIVE_LIMITED")
    if _num((data.get("risk") or {}).get("maxLot"), 0) > 2.0:
        return _reject(data, "MAX_LOT_TOO_HIGH", "最大仓位超过 2.0 上限")

    bad_tokens = find_forbidden_tokens(data)
    if bad_tokens:
        return _reject(data, "SAFETY_REJECTED", "Strategy JSON 含有代码、密钥或交易执行原语", bad_tokens[:6])

    timeframes = data.get("timeframes") if isinstance(data.get("timeframes"), list) else []
    if not timeframes or any(item not in ALLOWED_TIMEFRAMES for item in timeframes):
        return _reject(data, "TIMEFRAME_INVALID", "周期字段不合法")

    rsi = ((data.get("indicators") or {}).get("rsi") or {})
    checks = [
        _check_range("RSI period", rsi.get("period"), 2, 50),
        _check_range("RSI buyBand", rsi.get("buyBand"), 20, 45),
        _check_range("RSI crossbackThreshold", rsi.get("crossbackThreshold"), 0, 3),
        _check_range("breakevenDelayR", (data.get("exit") or {}).get("breakevenDelayR"), 0, 3),
        _check_range("trailStartR", (data.get("exit") or {}).get("trailStartR"), 0, 5),
        _check_range("mfeGivebackPct", (data.get("exit") or {}).get("mfeGivebackPct"), 0.1, 0.9),
    ]
    for ok, reason in checks:
        if not ok:
            return _reject(data, "PARAM_RANGE_INVALID", reason)

    return {
        "seedId": data.get("seedId"),
        "valid": True,
        "blockerCode": None,
        "reasonZh": "Strategy JSON 合法；可进入 GA replay / walk-forward 评分",
        "normalized": data,
    }
