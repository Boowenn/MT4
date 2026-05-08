from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from tools.strategy_json.normalizer import normalize_strategy_json
    from tools.strategy_json.validator import validate_strategy_json
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.normalizer import normalize_strategy_json
    from strategy_json.validator import validate_strategy_json

from .cost_model import BacktestCostModel, cost_model_from_strategy
from .indicators import bollinger_bands, ema_values, macd_values, rsi_values
from .metrics import summarize_trades
from .sqlite_store import Bar


SUPPORTED_BACKTEST_FAMILIES = {
    "RSI_Reversal",
    "MA_Cross",
    "BB_Triple",
    "MACD_Divergence",
    "SR_Breakout",
    "USDJPY_TOKYO_RANGE_BREAKOUT",
    "USDJPY_NIGHT_REVERSION_SAFE",
    "USDJPY_H4_TREND_PULLBACK",
}


def run_strategy(seed: Dict[str, Any], bars: List[Bar] | Dict[str, List[Bar]]) -> Dict[str, Any]:
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
    bars_by_timeframe = _normalize_bars_input(bars)
    primary_timeframe = _primary_timeframe(strategy, bars_by_timeframe)
    primary_bars = bars_by_timeframe.get(primary_timeframe, [])
    if len(primary_bars) < 40:
        return {
            "ok": False,
            "validation": validation,
            "strategyJson": strategy,
            "trades": [],
            "equityCurve": [],
            "metrics": {},
            "reasonZh": "USDJPY H1 K线样本不足，无法生成高保真回测",
        }
    family = str(strategy.get("strategyFamily") or "")
    if family not in SUPPORTED_BACKTEST_FAMILIES:
        return _research_only_result(strategy, validation)

    cost_model = cost_model_from_strategy(strategy)
    signals = _entry_signals(strategy, primary_bars, bars_by_timeframe)
    trades = _run_entries(strategy, primary_bars, signals, cost_model)
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
        "reasonZh": "Strategy JSON 已按 USDJPY 多策略因果规则完成回测",
        "engine": {
            "schema": "quantgod.strategy_backtest_engine.v2",
            "coverage": "ALL_SUPPORTED_USDJPY_SHADOW_FAMILIES",
            "primaryTimeframe": primary_timeframe,
            "supportedFamilies": sorted(SUPPORTED_BACKTEST_FAMILIES),
            "signalCount": len(signals),
            "costModel": cost_model.to_payload(),
            "parityVector": _parity_vector(strategy, primary_bars, signals),
        },
    }


def _research_only_result(strategy: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "validation": validation,
        "strategyJson": strategy,
        "trades": [],
        "equityCurve": [],
        "metrics": summarize_trades([], []),
        "reasonZh": "该策略族暂未接入高保真 runner；保留为 shadow research",
    }


def _normalize_bars_input(bars: List[Bar] | Dict[str, List[Bar]]) -> Dict[str, List[Bar]]:
    if isinstance(bars, dict):
        return {str(key).upper(): value for key, value in bars.items() if isinstance(value, list)}
    return {"H1": bars}


def _primary_timeframe(strategy: Dict[str, Any], bars_by_timeframe: Dict[str, List[Bar]]) -> str:
    rsi_cfg = ((strategy.get("indicators") or {}).get("rsi") or {})
    preferred = str(rsi_cfg.get("timeframe") or "H1").upper()
    if len(bars_by_timeframe.get(preferred, [])) >= 40:
        return preferred
    for candidate in ("H1", "M15", "M5", "M1", "H4", "D1"):
        if len(bars_by_timeframe.get(candidate, [])) >= 40:
            return candidate
    return preferred


def _entry_signals(strategy: Dict[str, Any], bars: List[Bar], bars_by_timeframe: Dict[str, List[Bar]]) -> List[Dict[str, Any]]:
    family = str(strategy.get("strategyFamily") or "")
    if family == "RSI_Reversal":
        return _rsi_signals(strategy, bars)
    if family == "MA_Cross":
        return _ma_cross_signals(strategy, bars)
    if family == "BB_Triple":
        return _bb_triple_signals(strategy, bars)
    if family == "MACD_Divergence":
        return _macd_signals(strategy, bars)
    if family == "SR_Breakout":
        return _sr_breakout_signals(strategy, bars)
    if family == "USDJPY_TOKYO_RANGE_BREAKOUT":
        return _tokyo_breakout_signals(strategy, bars)
    if family == "USDJPY_NIGHT_REVERSION_SAFE":
        return _night_reversion_signals(strategy, bars)
    if family == "USDJPY_H4_TREND_PULLBACK":
        return _h4_pullback_signals(strategy, bars, bars_by_timeframe)
    return []


def _rsi_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    rsi_cfg = ((strategy.get("indicators") or {}).get("rsi") or {})
    exit_cfg = strategy.get("exit") if isinstance(strategy.get("exit"), dict) else {}
    period = int(float(rsi_cfg.get("period", 14)))
    buy_band = float(rsi_cfg.get("buyBand", 34))
    sell_band = float(rsi_cfg.get("sellBand", max(55.0, 100.0 - buy_band)))
    crossback_threshold = float(rsi_cfg.get("crossbackThreshold", 0.8))

    closes = [item.close for item in bars]
    rsi_series = rsi_values(closes, period)
    signals: List[Dict[str, Any]] = []
    index = period + 1
    while index < len(bars) - 2:
        previous_rsi = rsi_series[index - 1]
        current_rsi = rsi_series[index]
        if previous_rsi is None or current_rsi is None:
            index += 1
            continue
        long_cross = previous_rsi <= buy_band and current_rsi >= buy_band + crossback_threshold
        short_cross = previous_rsi >= sell_band and current_rsi <= sell_band - crossback_threshold
        direction = str(strategy.get("direction") or "LONG").upper()
        if (direction == "LONG" and long_cross) or (direction == "SHORT" and short_cross):
            signals.append(_signal(index + 1, direction, "RSI_CROSSBACK", {"rsi": round(current_rsi, 4)}))
            index += 3
        else:
            index += 1
    return signals


def _ma_cross_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    closes = [item.close for item in bars]
    fast = ema_values(closes, 9)
    slow = ema_values(closes, 21)
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(22, len(bars) - 2):
        if None in (fast[index - 1], slow[index - 1], fast[index], slow[index]):
            continue
        long_cross = fast[index - 1] <= slow[index - 1] and fast[index] > slow[index]
        short_cross = fast[index - 1] >= slow[index - 1] and fast[index] < slow[index]
        if (direction == "LONG" and long_cross) or (direction == "SHORT" and short_cross):
            signals.append(_signal(index + 1, direction, "EMA_9_21_CROSS", {"fastEma": fast[index], "slowEma": slow[index]}))
    return signals


def _bb_triple_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    closes = [item.close for item in bars]
    bands = bollinger_bands(closes, 20, 2.0)
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(21, len(bars) - 2):
        lower, mid, upper = bands[index]
        if lower is None or mid is None or upper is None:
            continue
        previous_close = closes[index - 1]
        current_close = closes[index]
        long_reclaim = previous_close < lower and current_close > lower
        short_reclaim = previous_close > upper and current_close < upper
        if (direction == "LONG" and long_reclaim) or (direction == "SHORT" and short_reclaim):
            signals.append(_signal(index + 1, direction, "BOLLINGER_RECLAIM", {"lower": lower, "mid": mid, "upper": upper}))
    return signals


def _macd_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    closes = [item.close for item in bars]
    macd = macd_values(closes)
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(35, len(bars) - 2):
        previous_hist = macd[index - 1][2]
        current_hist = macd[index][2]
        if previous_hist is None or current_hist is None:
            continue
        long_cross = previous_hist <= 0 < current_hist
        short_cross = previous_hist >= 0 > current_hist
        if (direction == "LONG" and long_cross) or (direction == "SHORT" and short_cross):
            signals.append(_signal(index + 1, direction, "MACD_HISTOGRAM_CROSS", {"histogram": current_hist}))
    return signals


def _sr_breakout_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    direction = str(strategy.get("direction") or "LONG").upper()
    lookback = 24
    signals: List[Dict[str, Any]] = []
    for index in range(lookback, len(bars) - 2):
        window = bars[index - lookback : index]
        resistance = max(item.high for item in window)
        support = min(item.low for item in window)
        long_break = bars[index].close > resistance
        short_break = bars[index].close < support
        if (direction == "LONG" and long_break) or (direction == "SHORT" and short_break):
            signals.append(_signal(index + 1, direction, "SR_BREAKOUT", {"support": support, "resistance": resistance}))
    return signals


def _tokyo_breakout_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(12, len(bars) - 2):
        hour = _hour_utc(bars[index].timestamp)
        if hour not in {3, 4, 5, 6}:
            continue
        asian_window = [item for item in bars[max(0, index - 8) : index] if _hour_utc(item.timestamp) in {0, 1, 2}]
        if len(asian_window) < 2:
            continue
        high = max(item.high for item in asian_window)
        low = min(item.low for item in asian_window)
        if direction == "LONG" and bars[index].close > high:
            signals.append(_signal(index + 1, direction, "TOKYO_RANGE_BREAKOUT", {"rangeHigh": high, "rangeLow": low}))
        if direction == "SHORT" and bars[index].close < low:
            signals.append(_signal(index + 1, direction, "TOKYO_RANGE_BREAKOUT", {"rangeHigh": high, "rangeLow": low}))
    return signals


def _night_reversion_signals(strategy: Dict[str, Any], bars: List[Bar]) -> List[Dict[str, Any]]:
    closes = [item.close for item in bars]
    bands = bollinger_bands(closes, 20, 1.8)
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(21, len(bars) - 2):
        hour = _hour_utc(bars[index].timestamp)
        if hour not in {20, 21, 22, 23, 0, 1, 2}:
            continue
        lower, _, upper = bands[index]
        if lower is None or upper is None:
            continue
        if direction == "LONG" and closes[index] <= lower:
            signals.append(_signal(index + 1, direction, "NIGHT_REVERSION_LOWER_BAND", {"lower": lower}))
        if direction == "SHORT" and closes[index] >= upper:
            signals.append(_signal(index + 1, direction, "NIGHT_REVERSION_UPPER_BAND", {"upper": upper}))
    return signals


def _h4_pullback_signals(strategy: Dict[str, Any], bars: List[Bar], bars_by_timeframe: Dict[str, List[Bar]]) -> List[Dict[str, Any]]:
    closes = [item.close for item in bars]
    ema20 = ema_values(closes, 20)
    ema50 = ema_values(closes, 50)
    direction = str(strategy.get("direction") or "LONG").upper()
    signals: List[Dict[str, Any]] = []
    for index in range(55, len(bars) - 2):
        if ema20[index] is None or ema50[index] is None:
            continue
        trend_long = ema20[index] > ema50[index]
        trend_short = ema20[index] < ema50[index]
        pullback_long = bars[index].low <= ema20[index] <= bars[index].close
        pullback_short = bars[index].high >= ema20[index] >= bars[index].close
        if direction == "LONG" and trend_long and pullback_long:
            signals.append(_signal(index + 1, direction, "H4_TREND_PULLBACK", {"ema20": ema20[index], "ema50": ema50[index]}))
        if direction == "SHORT" and trend_short and pullback_short:
            signals.append(_signal(index + 1, direction, "H4_TREND_PULLBACK", {"ema20": ema20[index], "ema50": ema50[index]}))
    return signals


def _signal(index: int, direction: str, reason: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "entryIndex": index,
        "direction": direction,
        "reason": reason,
        "evidence": {key: round(value, 5) if isinstance(value, float) else value for key, value in evidence.items()},
    }


def _run_entries(
    strategy: Dict[str, Any],
    bars: List[Bar],
    signals: List[Dict[str, Any]],
    cost_model: BacktestCostModel,
) -> List[Dict[str, Any]]:
    exit_cfg = strategy.get("exit") if isinstance(strategy.get("exit"), dict) else {}
    hold_bars = int(((exit_cfg.get("timeStopBars") or {}).get("H1") or 4))
    giveback_pct = float(exit_cfg.get("mfeGivebackPct", 0.6))
    trail_start_r = float(exit_cfg.get("trailStartR", 1.5))
    risk_pips = float(((strategy.get("risk") or {}).get("riskPips") or 10.0))
    trades: List[Dict[str, Any]] = []
    next_available_index = 0
    for signal in signals:
        entry_index = int(signal["entryIndex"])
        if entry_index < next_available_index or entry_index >= len(bars) - 1:
            continue
        trade, exit_index = _simulate_exit(
            strategy,
            bars,
            entry_index=entry_index,
            direction=signal["direction"],
            hold_bars=hold_bars,
            risk_pips=risk_pips,
            trail_start_r=trail_start_r,
            giveback_pct=giveback_pct,
            trade_no=len(trades) + 1,
            signal=signal,
            cost_model=cost_model,
        )
        trades.append(trade)
        next_available_index = exit_index + 1
    return trades


def _simulate_exit(
    strategy: Dict[str, Any],
    bars: List[Bar],
    entry_index: int,
    direction: str,
    hold_bars: int,
    risk_pips: float,
    trail_start_r: float,
    giveback_pct: float,
    trade_no: int,
    signal: Dict[str, Any],
    cost_model: BacktestCostModel,
) -> Tuple[Dict[str, Any], int]:
    entry = bars[entry_index]
    entry_price = entry.open
    pip_size = 0.01
    risk_price = risk_pips * pip_size
    signed = 1.0 if direction == "LONG" else -1.0
    stop_price = entry_price - (signed * risk_price)
    max_profit_pips = 0.0
    max_loss_pips = 0.0
    exit_bar = entry
    exit_price = entry.close
    exit_reason = "TIME_STOP"
    last_index = min(len(bars) - 1, entry_index + max(1, hold_bars))
    for index in range(entry_index, last_index + 1):
        bar = bars[index]
        high_profit = signed * (bar.high - entry_price) / pip_size
        low_profit = signed * (bar.low - entry_price) / pip_size
        if direction == "SHORT":
            high_profit, low_profit = low_profit, high_profit
        max_profit_pips = max(max_profit_pips, high_profit)
        max_loss_pips = min(max_loss_pips, low_profit)
        stop_hit = bar.low <= stop_price if direction == "LONG" else bar.high >= stop_price
        if stop_hit:
            exit_bar = bar
            exit_price = stop_price
            exit_reason = "STOP_LOSS"
            last_index = index
            break
        if max_profit_pips / risk_pips >= trail_start_r:
            giveback_stop = entry_price + signed * (max_profit_pips * (1.0 - giveback_pct) * pip_size)
            giveback_hit = bar.low <= giveback_stop if direction == "LONG" else bar.high >= giveback_stop
            if giveback_hit:
                exit_bar = bar
                exit_price = giveback_stop
                exit_reason = "MFE_GIVEBACK"
                last_index = index
                break
        exit_bar = bar
        exit_price = bar.close
    gross_profit_pips = signed * (exit_price - entry_price) / pip_size
    cost_pips = cost_model.round_turn_pips
    profit_pips = gross_profit_pips - cost_pips
    profit_r = profit_pips / risk_pips
    return {
        "tradeId": f"BT-{trade_no:04d}",
        "symbol": "USDJPYc",
        "strategyFamily": strategy.get("strategyFamily"),
        "direction": direction,
        "signalReason": signal.get("reason"),
        "signalEvidence": signal.get("evidence", {}),
        "entryTime": entry.timestamp,
        "exitTime": exit_bar.timestamp,
        "entryPrice": round(entry_price, 5),
        "exitPrice": round(exit_price, 5),
        "exitReason": exit_reason,
        "riskPips": round(risk_pips, 3),
        "grossProfitPips": round(gross_profit_pips, 3),
        "costPips": round(cost_pips, 3),
        "profitPips": round(profit_pips, 3),
        "profitR": round(profit_r, 4),
        "mfeR": round(max_profit_pips / risk_pips, 4),
        "maeR": round(max_loss_pips / risk_pips, 4),
    }, last_index


def _parity_vector(strategy: Dict[str, Any], bars: List[Bar], signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    last_signal = signals[-1] if signals else {}
    last_signal_index = int(last_signal["entryIndex"]) if last_signal else -1
    rsi_cfg = ((strategy.get("indicators") or {}).get("rsi") or {})
    entry_cfg = strategy.get("entry") if isinstance(strategy.get("entry"), dict) else {}
    exit_cfg = strategy.get("exit") if isinstance(strategy.get("exit"), dict) else {}
    risk_cfg = strategy.get("risk") if isinstance(strategy.get("risk"), dict) else {}
    return {
        "schema": "quantgod.strategy_parity_vector.v1",
        "strategyFamily": strategy.get("strategyFamily"),
        "direction": strategy.get("direction"),
        "entryMode": entry_cfg.get("mode"),
        "entryConditions": entry_cfg.get("conditions") if isinstance(entry_cfg.get("conditions"), list) else [],
        "rsi": {
            "period": rsi_cfg.get("period"),
            "timeframe": rsi_cfg.get("timeframe"),
            "buyBand": rsi_cfg.get("buyBand"),
            "sellBand": rsi_cfg.get("sellBand"),
            "crossbackThreshold": rsi_cfg.get("crossbackThreshold"),
        },
        "exit": {
            "breakevenDelayR": exit_cfg.get("breakevenDelayR"),
            "trailStartR": exit_cfg.get("trailStartR"),
            "mfeGivebackPct": exit_cfg.get("mfeGivebackPct"),
            "timeStopBars": exit_cfg.get("timeStopBars") if isinstance(exit_cfg.get("timeStopBars"), dict) else {},
        },
        "risk": {
            "maxLot": risk_cfg.get("maxLot"),
            "stage": risk_cfg.get("stage"),
            "opportunityLotMultiplier": risk_cfg.get("opportunityLotMultiplier"),
        },
        "barCount": len(bars),
        "lastSignalTime": bars[last_signal_index].timestamp if 0 <= last_signal_index < len(bars) else None,
        "lastSignalReason": last_signal.get("reason"),
        "lastSignalDirection": last_signal.get("direction"),
        "signalCount": len(signals),
    }


def _hour_utc(timestamp: str) -> int:
    try:
        return int(timestamp.split("T", 1)[1].split(":", 1)[0])
    except Exception:
        return -1
