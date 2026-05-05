from __future__ import annotations

from typing import Any, Dict, List

from .schema import (
    FOCUS_SYMBOL,
    NEW_USDJPY_STRATEGIES,
    READ_ONLY_SAFETY,
    STRATEGY_CATALOG_VERSION,
    STRATEGY_DISPLAY_NAMES,
    assert_no_secret_or_execution_flags,
    utc_now_iso,
)


def _strategy_item(key: str) -> Dict[str, Any]:
    if key == "USDJPY_TOKYO_RANGE_BREAKOUT":
        item = {
            "key": key,
            "name": STRATEGY_DISPLAY_NAMES[key],
            "stage": "SHADOW_RESEARCH",
            "timeframes": ["M5", "M15"],
            "coreIdea": "东京时间 09:00-12:00 建箱体，12:00-18:00 只记录突破或临界突破样本。",
            "entryLogic": "突破箱体高低点且 ADX 确认；临界突破也记入影子样本以加快学习。",
            "riskNotes": ["过滤点差", "箱体过窄/过宽不采样", "高影响 USD/JPY 新闻和疑似干预区只做观察"],
            "promotionPath": ["Shadow outcome", "Strategy Tester", "ParamLab", "Governance", "manual approval"],
        }
    elif key == "USDJPY_NIGHT_REVERSION_SAFE":
        item = {
            "key": key,
            "name": STRATEGY_DISPLAY_NAMES[key],
            "stage": "SHADOW_RESEARCH",
            "timeframes": ["M5", "M15"],
            "coreIdea": "低波动夜盘触碰布林带后记录均值回归机会，只允许机会级观察。",
            "entryLogic": "ADX<20、RANGE/RANGE_TIGHT、触碰布林带并配合 RSI 极值。",
            "riskNotes": ["政策大 K 禁用", "趋势行情禁用", "只做 opportunity 候选，不直接进实盘"],
            "promotionPath": ["Shadow outcome", "walk-forward backtest", "manual review"],
        }
    else:
        item = {
            "key": key,
            "name": STRATEGY_DISPLAY_NAMES[key],
            "stage": "SHADOW_RESEARCH",
            "timeframes": ["M15", "H1", "H4"],
            "coreIdea": "H4 EMA50/200 定方向，M15 回踩 EMA20/50 后记录顺势恢复样本。",
            "entryLogic": "H4 趋势通过，M15 回踩后重新收回趋势方向并配合 RSI 恢复。",
            "riskNotes": ["样本慢但更稳", "至少经过 Strategy Tester 和治理复核", "不绕过 RSI 现有实盘路线"],
            "promotionPath": ["Shadow outcome", "Strategy Tester", "ParamLab", "Governance", "manual approval"],
        }
    item["symbol"] = FOCUS_SYMBOL
    item["dryRunOnly"] = True
    item["shadowTradingOnly"] = True
    item["orderSendAllowed"] = False
    item["livePresetMutationAllowed"] = False
    return item


def build_strategy_catalog() -> Dict[str, Any]:
    payload = {
        "schema": STRATEGY_CATALOG_VERSION,
        "generatedAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "description": "USDJPY 策略工厂目录；新增策略默认只写影子证据，不进入实盘下单。",
        "catalog": [_strategy_item(key) for key in NEW_USDJPY_STRATEGIES],
        "safety": dict(READ_ONLY_SAFETY),
    }
    assert_no_secret_or_execution_flags(payload)
    return payload
