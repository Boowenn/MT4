from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .schema import FOCUS_SYMBOL, NEW_USDJPY_STRATEGIES, READ_ONLY_SAFETY, STRATEGY_DISPLAY_NAMES, assert_no_secret_or_execution_flags, utc_now_iso


def build_backtest_plan(runtime_dir: Path | None = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for key in NEW_USDJPY_STRATEGIES:
        if key == "USDJPY_TOKYO_RANGE_BREAKOUT":
            window = "2018-01-01 至今，重点覆盖 BOJ/FOMC/CPI/NFP 周期"
            timeframe = "M5/M15"
            acceptance = "PF>=1.15、样本>=80、最大回撤可控、新闻/干预窗口不过拟合"
        elif key == "USDJPY_NIGHT_REVERSION_SAFE":
            window = "2018-01-01 至今，拆分低波动夜盘与政策波动日"
            timeframe = "M5/M15"
            acceptance = "PF>=1.10、样本>=100、政策大 K 当日不恶化"
        else:
            window = "2015-01-01 至今，walk-forward 按年份滚动"
            timeframe = "H4+M15"
            acceptance = "PF>=1.15、样本>=60、趋势年和震荡年均不过度失效"
        rows.append({
            "strategy": key,
            "strategyName": STRATEGY_DISPLAY_NAMES.get(key, key),
            "symbol": FOCUS_SYMBOL,
            "timeframe": timeframe,
            "suggestedWindow": window,
            "acceptance": acceptance,
            "dryRunOnly": True,
        })
    payload = {
        "schema": "quantgod.usdjpy_strategy_backtest_plan.v1",
        "generatedAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "plans": rows,
        "runtimeDir": str(runtime_dir) if runtime_dir else "",
        "safety": dict(READ_ONLY_SAFETY),
    }
    assert_no_secret_or_execution_flags(payload)
    return payload
