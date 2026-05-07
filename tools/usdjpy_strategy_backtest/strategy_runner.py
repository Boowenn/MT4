from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from tools.strategy_json.normalizer import normalize_strategy_json
    from tools.strategy_json.validator import validate_strategy_json
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.normalizer import normalize_strategy_json
    from strategy_json.validator import validate_strategy_json

from .indicators import rsi_values
from .metrics import summarize_trades
from .sqlite_store import Bar


def run_strategy(seed: Dict[str, Any], bars: List[Bar]) -> Dict[str, Any]:
    validation = validate_strategy_json(seed)
    if not validation.get("valid"):
        return {
            "ok": False,
            "validation": validation,
            "trades": [],
            "equityCurve": [],
            "metrics": {},
            "reasonZh": "Strategy JSON 未通过安全校验，不能回测",
        }
    strategy = normalize_strategy_json(seed)
    if len(bars) < 40:
        return {
            "ok": False,
            "validation": validation,
            "strategyJson": strategy,
            "trades": [],
            "equityCurve": [],
            "metrics": {},
            "reasonZh": "USDJPY H1 K线样本不足，无法生成高保真回测",
        }
    if strategy.get("strategyFamily") != "RSI_Reversal":
        return _research_only_result(strategy, validation)
    if strategy.get("direction") != "LONG":
        return _research_only_result(strategy, validation)

    trades = _run_rsi_long(strategy, bars)
    equity_curve: List[float] = []
    running = 0.0
    for trade in trades:
        running += float(trade["profitR"])
        equity_curve.append(round(running, 4))
    return {
        "ok": True,
        "validation": validation,
        "strategyJson": strategy,
        "trades": trades,
        "equityCurve": equity_curve,
        "metrics": summarize_trades(trades, equity_curve),
        "reasonZh": "Strategy JSON 已按 USDJPY H1 RSI 因果规则完成回测",
    }


def _research_only_result(strategy: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "validation": validation,
        "strategyJson": strategy,
        "trades": [],
        "equityCurve": [],
        "metrics": summarize_trades([], []),
        "reasonZh": "当前高保真回测 v1 只执行 USDJPY RSI_Reversal LONG；其他策略保留为 shadow research",
    }


def _run_rsi_long(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    rsi_cfg = ((strategy.get("indicators") or {}).get("rsi") or {})
    exit_cfg = strategy.get("exit") if isinstance(strategy.get("exit"), dict) else {}
    period = int(float(rsi_cfg.get("period", 14)))
    buy_band = float(rsi_cfg.get("buyBand", 34))
    crossback_threshold = float(rsi_cfg.get("crossbackThreshold", 0.8))
    hold_bars = int(((exit_cfg.get("timeStopBars") or {}).get("H1") or 4))
    giveback_pct = float(exit_cfg.get("mfeGivebackPct", 0.6))
    trail_start_r = float(exit_cfg.get("trailStartR", 1.5))
    risk_pips = 10.0

    closes = [item.close for item in bars]
    rsi_series = rsi_values(closes, period)
    trades: List[Dict[str, Any]] = []
    index = period + 1
    while index < len(bars) - 2:
        previous_rsi = rsi_series[index - 1]
        current_rsi = rsi_series[index]
        if previous_rsi is None or current_rsi is None:
            index += 1
            continue
        threshold = buy_band + crossback_threshold
        crossed = previous_rsi <= buy_band and current_rsi >= threshold
        if not crossed:
            index += 1
            continue

        trade, exit_index = _simulate_long_exit(
            bars,
            entry_index=index + 1,
            hold_bars=hold_bars,
            risk_pips=risk_pips,
            trail_start_r=trail_start_r,
            giveback_pct=giveback_pct,
            trade_no=len(trades) + 1,
        )
        trades.append(trade)
        index = max(exit_index + 1, index + 2)
    return trades


def _simulate_long_exit(
    bars: List[Bar],
    entry_index: int,
    hold_bars: int,
    risk_pips: float,
    trail_start_r: float,
    giveback_pct: float,
    trade_no: int,
) -> Tuple[Dict[str, Any], int]:
    entry = bars[entry_index]
    entry_price = entry.open
    pip_size = 0.01
    risk_price = risk_pips * pip_size
    stop_price = entry_price - risk_price
    max_profit_pips = 0.0
    max_loss_pips = 0.0
    exit_bar = entry
    exit_price = entry.close
    exit_reason = "TIME_STOP"
    last_index = min(len(bars) - 1, entry_index + max(1, hold_bars))
    for index in range(entry_index, last_index + 1):
        bar = bars[index]
        high_profit = (bar.high - entry_price) / pip_size
        low_profit = (bar.low - entry_price) / pip_size
        max_profit_pips = max(max_profit_pips, high_profit)
        max_loss_pips = min(max_loss_pips, low_profit)
        if bar.low <= stop_price:
            exit_bar = bar
            exit_price = stop_price
            exit_reason = "STOP_LOSS"
            last_index = index
            break
        if max_profit_pips / risk_pips >= trail_start_r:
            giveback_stop = entry_price + (max_profit_pips * (1.0 - giveback_pct) * pip_size)
            if bar.low <= giveback_stop:
                exit_bar = bar
                exit_price = giveback_stop
                exit_reason = "MFE_GIVEBACK"
                last_index = index
                break
        exit_bar = bar
        exit_price = bar.close
    profit_pips = (exit_price - entry_price) / pip_size
    profit_r = profit_pips / risk_pips
    return {
        "tradeId": f"BT-{trade_no:04d}",
        "symbol": "USDJPYc",
        "direction": "LONG",
        "entryTime": entry.timestamp,
        "exitTime": exit_bar.timestamp,
        "entryPrice": round(entry_price, 5),
        "exitPrice": round(exit_price, 5),
        "exitReason": exit_reason,
        "riskPips": round(risk_pips, 3),
        "profitPips": round(profit_pips, 3),
        "profitR": round(profit_r, 4),
        "mfeR": round(max_profit_pips / risk_pips, 4),
        "maeR": round(max_loss_pips / risk_pips, 4),
    }, last_index

