#!/usr/bin/env python3
"""QuantGod MT5 backend backtest loop.

This is a QuantDinger-style Python backtest executor adapted to QuantGod's
file-based MT5 research system. It reads tester-only ParamLab candidates, loads
historical MT5 rates, simulates route logic in Python, and writes reusable JSON
and CSV artifacts. It does not launch Strategy Tester, does not send orders,
does not close or cancel orders, and does not mutate live presets.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import mt5_symbol_registry
except ImportError:  # pragma: no cover - defensive path for unusual launchers
    sys.path.append(str(Path(__file__).resolve().parent))
    import mt5_symbol_registry  # type: ignore


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_NAME = "QuantGod_MT5BackendBacktest.json"
LEDGER_NAME = "QuantGod_MT5BackendBacktestLedger.csv"
TRADE_LEDGER_NAME = "QuantGod_MT5BackendBacktestTrades.csv"
SCHEDULER_NAME = "QuantGod_ParamLabAutoScheduler.json"
OPTIMIZER_NAME = "QuantGod_OptimizerV2Plan.json"

SAFETY = {
    "readOnly": True,
    "pythonBacktestOnly": True,
    "usesMt5StrategyTester": False,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "symbolSelectAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "mutatesMt5": False,
}

ROUTE_DEFAULTS: dict[str, dict[str, Any]] = {
    "MA_Cross": {"symbol": "EURUSDc", "timeframe": "M15"},
    "RSI_Reversal": {"symbol": "USDJPYc", "timeframe": "H1"},
    "BB_Triple": {"symbol": "EURUSDc", "timeframe": "H1"},
    "MACD_Divergence": {"symbol": "EURUSDc", "timeframe": "H1"},
    "SR_Breakout": {"symbol": "EURUSDc", "timeframe": "M15"},
}

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(read_text(path))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_timeframe(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30", "1H": "H1", "4H": "H4", "1D": "D1"}
    text = aliases.get(text, text)
    return text if text in TIMEFRAME_MINUTES else "M15"


def timeframe_to_mt5_constant(mt5: Any, timeframe: str) -> Any:
    name = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
        "D1": "TIMEFRAME_D1",
    }.get(normalize_timeframe(timeframe), "TIMEFRAME_M15")
    return getattr(mt5, name)


def parse_date(value: str, fallback: datetime) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y-%m-%dT%H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return fallback


def iso_from_epoch(seconds: Any) -> str:
    try:
        value = int(float(seconds))
    except Exception:
        return ""
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def pip_size(symbol: str) -> float:
    upper = str(symbol or "").upper()
    canonical = mt5_symbol_registry.normalize_symbol_row({"name": upper}).get("canonicalSymbol", upper)
    if "JPY" in canonical:
        return 0.01
    if canonical.startswith("XAU"):
        return 0.1
    if canonical.startswith("XAG"):
        return 0.01
    return 0.0001


def canonical_row(symbol: str) -> dict[str, Any]:
    return mt5_symbol_registry.normalize_symbol_row({"name": symbol})


def task_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    route_key = str(candidate.get("routeKey") or candidate.get("strategy") or "MA_Cross")
    defaults = ROUTE_DEFAULTS.get(route_key, ROUTE_DEFAULTS["MA_Cross"])
    symbol = str(candidate.get("symbol") or defaults["symbol"]).strip()
    timeframe = normalize_timeframe(candidate.get("timeframe") or defaults["timeframe"])
    candidate_id = str(candidate.get("candidateId") or candidate.get("proposalId") or f"{route_key}_{symbol}_{timeframe}")
    overrides = safe_dict(candidate.get("presetOverrides") or candidate.get("parameterOverrides"))
    return {
        "candidateId": candidate_id,
        "candidateVersionId": str(candidate.get("candidateVersionId") or ""),
        "parentVersionId": str(candidate.get("parentVersionId") or ""),
        "routeKey": route_key,
        "strategy": str(candidate.get("strategy") or route_key),
        "symbol": symbol,
        "timeframe": timeframe,
        "variant": str(candidate.get("variant") or candidate.get("template") or ""),
        "parameterSummary": str(candidate.get("parameterSummary") or ""),
        "presetOverrides": overrides,
        "score": as_float(candidate.get("score") or candidate.get("rankScore"), 0.0),
        "testerOnly": as_bool(candidate.get("testerOnly", True), True),
        "livePresetMutation": as_bool(candidate.get("livePresetMutation", False), False),
        "sourceDecision": str(candidate.get("sourceDecision") or candidate.get("objective") or ""),
    }


def load_scheduler_tasks(path: Path, max_tasks: int = 20, route_filter: set[str] | None = None) -> list[dict[str, Any]]:
    doc = read_json(path)
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for route_plan in safe_list(doc.get("routePlans")):
        route_plan = safe_dict(route_plan)
        for candidate in safe_list(route_plan.get("candidates")):
            task = task_from_candidate(safe_dict(candidate))
            if route_filter and task["routeKey"] not in route_filter:
                continue
            if task["candidateId"] in seen:
                continue
            seen.add(task["candidateId"])
            tasks.append(task)
            if len(tasks) >= max_tasks:
                return tasks
    return tasks


def load_optimizer_tasks(path: Path, max_tasks: int = 20, route_filter: set[str] | None = None) -> list[dict[str, Any]]:
    doc = read_json(path)
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in safe_list(doc.get("rankedProposals")):
        task = task_from_candidate(safe_dict(proposal))
        if route_filter and task["routeKey"] not in route_filter:
            continue
        if task["candidateId"] in seen:
            continue
        seen.add(task["candidateId"])
        tasks.append(task)
        if len(tasks) >= max_tasks:
            return tasks
    for route_plan in safe_list(doc.get("routePlans")):
        for proposal in safe_list(safe_dict(route_plan).get("proposals")):
            task = task_from_candidate(safe_dict(proposal))
            if route_filter and task["routeKey"] not in route_filter:
                continue
            if task["candidateId"] in seen:
                continue
            seen.add(task["candidateId"])
            tasks.append(task)
            if len(tasks) >= max_tasks:
                return tasks
    return tasks


def fallback_tasks(route_filter: set[str] | None = None) -> list[dict[str, Any]]:
    rows = []
    for route_key, defaults in ROUTE_DEFAULTS.items():
        if route_filter and route_key not in route_filter:
            continue
        rows.append(
            task_from_candidate(
                {
                    "candidateId": f"{route_key}_{defaults['symbol']}_backend_default",
                    "routeKey": route_key,
                    "strategy": route_key,
                    "symbol": defaults["symbol"],
                    "timeframe": defaults["timeframe"],
                    "variant": "backend_default",
                    "parameterSummary": "Backend default route parameters",
                    "presetOverrides": {},
                    "testerOnly": True,
                    "livePresetMutation": False,
                }
            )
        )
    return rows


def load_tasks(runtime_dir: Path, plan_path: Path | None, max_tasks: int, routes: list[str]) -> tuple[list[dict[str, Any]], str]:
    route_filter = {route for route in routes if route} or None
    scheduler_path = plan_path or runtime_dir / SCHEDULER_NAME
    tasks = load_scheduler_tasks(scheduler_path, max_tasks=max_tasks, route_filter=route_filter)
    source = str(scheduler_path)
    if not tasks:
        optimizer_path = runtime_dir / OPTIMIZER_NAME
        tasks = load_optimizer_tasks(optimizer_path, max_tasks=max_tasks, route_filter=route_filter)
        source = str(optimizer_path)
    if not tasks:
        tasks = fallback_tasks(route_filter=route_filter)[:max_tasks]
        source = "backend_default_tasks"
    return tasks[:max_tasks], source


def bar_from_mapping(row: dict[str, Any]) -> dict[str, Any]:
    time_value = row.get("time") or row.get("Time") or row.get("timestamp") or row.get("Timestamp")
    if isinstance(time_value, str) and not time_value.isdigit():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                time_value = int(datetime.strptime(time_value[:19], fmt).replace(tzinfo=timezone.utc).timestamp())
                break
            except ValueError:
                continue
    return {
        "time": int(float(time_value or 0)),
        "timeIso": row.get("timeIso") or iso_from_epoch(time_value),
        "open": as_float(row.get("open") or row.get("Open")),
        "high": as_float(row.get("high") or row.get("High")),
        "low": as_float(row.get("low") or row.get("Low")),
        "close": as_float(row.get("close") or row.get("Close")),
        "tickVolume": as_float(row.get("tick_volume") or row.get("tickVolume") or row.get("Volume")),
        "spread": as_float(row.get("spread") or row.get("Spread")),
    }


def bar_from_mt5_rate(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return bar_from_mapping(row)
    if hasattr(row, "_asdict"):
        return bar_from_mapping(dict(row._asdict()))
    data: dict[str, Any] = {}
    for key in ("time", "open", "high", "low", "close", "tick_volume", "spread"):
        try:
            data[key] = row[key]
        except Exception:
            data[key] = getattr(row, key, 0)
    return bar_from_mapping(data)


def read_bars_file(path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not path or not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        doc = read_json(path)
        output: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for key, value in doc.items():
            if key in {"schemaVersion", "mode", "generatedAtIso", "source", "summary", "safety"}:
                continue
            if "|" in key:
                symbol, timeframe = key.split("|", 1)
            else:
                if key != "bars":
                    continue
                symbol = str(doc.get("symbol") or "EURUSDc")
                timeframe = str(doc.get("timeframe") or "M15")
            rows = value if isinstance(value, list) else safe_list(doc.get("bars"))
            output[(symbol, normalize_timeframe(timeframe))] = [bar_from_mapping(safe_dict(row)) for row in rows]
        return output
    rows: list[dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append(bar_from_mapping(row))
    symbol = "EURUSDc"
    timeframe = "M15"
    if rows:
        first = rows[0]
        symbol = str(first.get("symbol") or first.get("Symbol") or symbol)
        timeframe = normalize_timeframe(first.get("timeframe") or first.get("Timeframe") or timeframe)
    return {(symbol, timeframe): rows}


def load_mt5_rates(
    *,
    mt5: Any,
    symbol: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    rates = mt5.copy_rates_range(symbol, timeframe_to_mt5_constant(mt5, timeframe), from_dt, to_dt)
    if rates is None:
        return []
    rows = [bar_from_mt5_rate(row) for row in list(rates)]
    rows = [row for row in rows if row["open"] and row["high"] and row["low"] and row["close"]]
    rows.sort(key=lambda row: row["time"])
    if limit > 0:
        rows = rows[-limit:]
    return rows


def maybe_load_mt5(terminal_path: str = "") -> tuple[Any | None, dict[str, Any]]:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        return None, {"ok": False, "error": "MetaTrader5 package unavailable", "detail": str(exc)}
    try:
        ok = bool(mt5.initialize(path=terminal_path)) if terminal_path else bool(mt5.initialize())
    except Exception as exc:
        return None, {"ok": False, "error": "MT5 initialize failed", "detail": str(exc)}
    if not ok:
        try:
            detail = mt5.last_error()
        except Exception:
            detail = ""
        return None, {"ok": False, "error": "MT5 initialize failed", "detail": detail}
    return mt5, {"ok": True}


def sma(values: list[float], index: int, period: int) -> float | None:
    period = max(1, int(period))
    if index + 1 < period:
        return None
    window = values[index + 1 - period:index + 1]
    return sum(window) / period


def ema_series(values: list[float], period: int) -> list[float | None]:
    period = max(1, int(period))
    out: list[float | None] = [None] * len(values)
    if not values:
        return out
    alpha = 2.0 / (period + 1.0)
    ema = values[0]
    for i, value in enumerate(values):
        ema = value if i == 0 else (value * alpha + ema * (1 - alpha))
        if i + 1 >= period:
            out[i] = ema
    return out


def stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def rsi_series(closes: list[float], period: int) -> list[float | None]:
    period = max(1, int(period))
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0.0, change))
        losses.append(max(0.0, -change))
    for i in range(period, len(closes)):
        avg_gain = sum(gains[i + 1 - period:i + 1]) / period
        avg_loss = sum(losses[i + 1 - period:i + 1]) / period
        if avg_loss == 0:
            out[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def atr_series(bars: list[dict[str, Any]], period: int) -> list[float | None]:
    period = max(1, int(period))
    out: list[float | None] = [None] * len(bars)
    trs: list[float] = []
    for i, bar in enumerate(bars):
        high = as_float(bar.get("high"))
        low = as_float(bar.get("low"))
        prev_close = as_float(bars[i - 1].get("close")) if i > 0 else as_float(bar.get("close"))
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        if i + 1 >= period:
            out[i] = sum(trs[i + 1 - period:i + 1]) / period
    return out


def macd_histogram(closes: list[float], fast: int, slow: int, signal: int) -> list[float | None]:
    fast_ema = ema_series(closes, fast)
    slow_ema = ema_series(closes, slow)
    macd: list[float] = []
    valid_index: list[int] = []
    for i, (fast_value, slow_value) in enumerate(zip(fast_ema, slow_ema)):
        if fast_value is None or slow_value is None:
            continue
        macd.append(fast_value - slow_value)
        valid_index.append(i)
    signal_values = ema_series(macd, signal)
    out: list[float | None] = [None] * len(closes)
    for local_i, original_i in enumerate(valid_index):
        sig = signal_values[local_i]
        if sig is not None:
            out[original_i] = macd[local_i] - sig
    return out


def signal_for_task(task: dict[str, Any], bars: list[dict[str, Any]], index: int, cache: dict[str, Any]) -> int:
    route = task["routeKey"]
    params = safe_dict(task.get("presetOverrides"))
    closes = cache["closes"]

    if route == "MA_Cross":
        fast = as_int(params.get("PilotFastMAPeriod"), 9)
        slow = as_int(params.get("PilotSlowMAPeriod"), 21)
        trend = as_int(params.get("PilotTrendMAPeriod"), 200)
        if index <= 0:
            return 0
        prev_fast = sma(closes, index - 1, fast)
        prev_slow = sma(closes, index - 1, slow)
        cur_fast = sma(closes, index, fast)
        cur_slow = sma(closes, index, slow)
        trend_ma = sma(closes, index, trend)
        if None in (prev_fast, prev_slow, cur_fast, cur_slow):
            return 0
        if prev_fast <= prev_slow and cur_fast > cur_slow and (trend_ma is None or closes[index] >= trend_ma):
            return 1
        if prev_fast >= prev_slow and cur_fast < cur_slow and (trend_ma is None or closes[index] <= trend_ma):
            return -1
        return 0

    if route == "RSI_Reversal":
        period = as_int(params.get("PilotRsiPeriod"), 2)
        oversold = as_float(params.get("PilotRsiOversold"), 20.0)
        overbought = as_float(params.get("PilotRsiOverbought"), 80.0)
        rsi = cache.setdefault(f"rsi_{period}", rsi_series(closes, period))
        if index <= 0 or rsi[index] is None or rsi[index - 1] is None:
            return 0
        if rsi[index - 1] < oversold <= rsi[index]:
            return 1
        if rsi[index - 1] > overbought >= rsi[index]:
            return -1
        return 0

    if route == "BB_Triple":
        period = as_int(params.get("PilotBBPeriod"), 20)
        deviation = as_float(params.get("PilotBBDeviation"), 2.0)
        rsi_period = as_int(params.get("PilotBBRsiPeriod"), 14)
        oversold = as_float(params.get("PilotBBRsiOversold"), 35.0)
        overbought = as_float(params.get("PilotBBRsiOverbought"), 65.0)
        rsi = cache.setdefault(f"rsi_{rsi_period}", rsi_series(closes, rsi_period))
        if index <= 0 or index + 1 < period or rsi[index] is None:
            return 0
        window = closes[index + 1 - period:index + 1]
        prev_window = closes[index - period:index] if index >= period else []
        mid = sum(window) / period
        band = stddev(window) * deviation
        lower = mid - band
        upper = mid + band
        if prev_window:
            prev_mid = sum(prev_window) / period
            prev_band = stddev(prev_window) * deviation
            prev_lower = prev_mid - prev_band
            prev_upper = prev_mid + prev_band
        else:
            prev_lower = lower
            prev_upper = upper
        if closes[index - 1] < prev_lower and closes[index] >= lower and rsi[index] <= oversold:
            return 1
        if closes[index - 1] > prev_upper and closes[index] <= upper and rsi[index] >= overbought:
            return -1
        return 0

    if route == "MACD_Divergence":
        fast = as_int(params.get("PilotMacdFast"), 12)
        slow = as_int(params.get("PilotMacdSlow"), 26)
        signal = as_int(params.get("PilotMacdSignal"), 9)
        hist = cache.setdefault(f"macd_{fast}_{slow}_{signal}", macd_histogram(closes, fast, slow, signal))
        if index <= 0 or hist[index] is None or hist[index - 1] is None:
            return 0
        if hist[index - 1] <= 0 < hist[index]:
            return 1
        if hist[index - 1] >= 0 > hist[index]:
            return -1
        return 0

    if route == "SR_Breakout":
        lookback = as_int(params.get("PilotSRLookback"), 24)
        break_pips = as_float(params.get("PilotSRBreakPips"), 2.0)
        if index < lookback:
            return 0
        buffer = break_pips * pip_size(task["symbol"])
        highs = [as_float(row.get("high")) for row in bars[index - lookback:index]]
        lows = [as_float(row.get("low")) for row in bars[index - lookback:index]]
        close = closes[index]
        if close > max(highs) + buffer:
            return 1
        if close < min(lows) - buffer:
            return -1
        return 0

    return 0


def route_sl_multiplier(task: dict[str, Any]) -> float:
    params = safe_dict(task.get("presetOverrides"))
    route = task["routeKey"]
    if route == "RSI_Reversal":
        return as_float(params.get("PilotRsiATRMultiplierSL"), 1.5)
    return as_float(params.get("PilotATRMulitplierSL"), 2.0)


def simulate_task(task: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    min_bars = 60
    if len(bars) < min_bars:
        return {
            "status": "insufficient_bars",
            "sampleState": "WARMUP",
            "closedTrades": 0,
            "blockers": [f"bars_lt_{min_bars}"],
        }, []

    closes = [as_float(row.get("close")) for row in bars]
    atr_period = as_int(safe_dict(task.get("presetOverrides")).get("PilotATRPeriod"), 14)
    atr_values = atr_series(bars, atr_period)
    cache: dict[str, Any] = {"closes": closes}
    point = pip_size(task["symbol"])
    reward_ratio = max(0.2, as_float(safe_dict(task.get("presetOverrides")).get("PilotRewardRatio"), 1.5))
    sl_multiplier = max(0.2, route_sl_multiplier(task))
    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for i in range(1, len(bars)):
        bar = bars[i]
        signal = signal_for_task(task, bars, i, cache)
        if position:
            direction = int(position["direction"])
            high = as_float(bar.get("high"))
            low = as_float(bar.get("low"))
            close = as_float(bar.get("close"))
            exit_price = 0.0
            exit_reason = ""
            if direction > 0:
                if low <= position["sl"]:
                    exit_price = position["sl"]
                    exit_reason = "stop_loss"
                elif high >= position["tp"]:
                    exit_price = position["tp"]
                    exit_reason = "take_profit"
            else:
                if high >= position["sl"]:
                    exit_price = position["sl"]
                    exit_reason = "stop_loss"
                elif low <= position["tp"]:
                    exit_price = position["tp"]
                    exit_reason = "take_profit"
            if not exit_reason and signal and signal != direction:
                exit_price = close
                exit_reason = "reverse_signal"
            if i == len(bars) - 1 and not exit_reason:
                exit_price = close
                exit_reason = "end_of_sample"
            if exit_reason:
                profit_pips = (exit_price - position["entryPrice"]) / point * direction
                equity += profit_pips
                peak = max(peak, equity)
                max_drawdown = max(max_drawdown, peak - equity)
                trades.append(
                    {
                        "candidateId": task["candidateId"],
                        "routeKey": task["routeKey"],
                        "strategy": task["strategy"],
                        "symbol": task["symbol"],
                        "timeframe": task["timeframe"],
                        "direction": "buy" if direction > 0 else "sell",
                        "entryTime": position["entryTime"],
                        "exitTime": bar.get("timeIso", ""),
                        "entryPrice": round(position["entryPrice"], 6),
                        "exitPrice": round(exit_price, 6),
                        "sl": round(position["sl"], 6),
                        "tp": round(position["tp"], 6),
                        "profitPips": round(profit_pips, 3),
                        "exitReason": exit_reason,
                        "backendEngine": "PYTHON_BACKTEST_NO_MT5_TESTER",
                    }
                )
                position = None
                continue

        if position is None and signal and i < len(bars) - 1:
            atr = atr_values[i] or (point * 10.0)
            sl_distance = max(point * 2.0, atr * sl_multiplier)
            entry_price = as_float(bar.get("close"))
            if signal > 0:
                sl = entry_price - sl_distance
                tp = entry_price + sl_distance * reward_ratio
            else:
                sl = entry_price + sl_distance
                tp = entry_price - sl_distance * reward_ratio
            position = {
                "direction": signal,
                "entryPrice": entry_price,
                "entryTime": bar.get("timeIso", ""),
                "sl": sl,
                "tp": tp,
            }

    profits = [as_float(row["profitPips"]) for row in trades]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    pf = (gross_profit / abs(gross_loss)) if gross_loss < 0 else (999.0 if gross_profit > 0 else 0.0)
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    net_pips = sum(profits)
    blockers = []
    if len(trades) < 20:
        blockers.append("backend_trades_lt_20")
    if pf < 1.15:
        blockers.append("backend_pf_lt_1_15")
    if net_pips <= 0:
        blockers.append("backend_net_pips_not_positive")
    if max_drawdown > max(25.0, abs(net_pips) * 1.25):
        blockers.append("backend_drawdown_high")
    sample_state = "BACKEND_READY" if not blockers else ("CAUTION" if len(trades) else "NO_TRADES")
    return {
        "status": "simulated",
        "sampleState": sample_state,
        "closedTrades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winRatePct": round(win_rate, 2),
        "netPips": round(net_pips, 3),
        "grossProfitPips": round(gross_profit, 3),
        "grossLossPips": round(gross_loss, 3),
        "profitFactor": round(pf, 4),
        "avgPips": round((net_pips / len(trades)) if trades else 0.0, 3),
        "maxDrawdownPips": round(max_drawdown, 3),
        "firstBarTime": bars[0].get("timeIso", ""),
        "lastBarTime": bars[-1].get("timeIso", ""),
        "barCount": len(bars),
        "blockers": blockers,
    }, trades


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = defaultdict(int)
    by_route = defaultdict(int)
    ready_count = 0
    best = None
    for row in rows:
        by_state[str(row.get("sampleState") or "")] += 1
        by_route[str(row.get("routeKey") or "")] += 1
        if row.get("sampleState") == "BACKEND_READY":
            ready_count += 1
        if best is None or as_float(row.get("rankScore")) > as_float(best.get("rankScore")):
            best = row
    return {
        "taskCount": len(rows),
        "readyCount": ready_count,
        "cautionCount": by_state.get("CAUTION", 0),
        "noTradeCount": by_state.get("NO_TRADES", 0),
        "routeCount": len([key for key in by_route if key]),
        "routeCounts": dict(by_route),
        "sampleStateCounts": dict(by_state),
        "topCandidateId": best.get("candidateId", "") if best else "",
        "topRouteKey": best.get("routeKey", "") if best else "",
        "topRankScore": best.get("rankScore", 0.0) if best else 0.0,
        "orderSendAllowed": False,
        "usesMt5StrategyTester": False,
        "livePresetMutation": False,
    }


def rank_score(metrics: dict[str, Any]) -> float:
    trades = as_float(metrics.get("closedTrades"))
    pf = min(5.0, as_float(metrics.get("profitFactor")))
    net = as_float(metrics.get("netPips"))
    dd = as_float(metrics.get("maxDrawdownPips"))
    win_rate = as_float(metrics.get("winRatePct"))
    return round((pf * 20.0) + (win_rate * 0.3) + (net * 0.05) + min(20.0, trades) - (dd * 0.1), 4)


def run_backend_loop(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    repo_root = Path(args.repo_root)
    from_dt = parse_date(args.from_date, datetime.now(timezone.utc) - timedelta(days=args.days))
    to_dt = parse_date(args.to_date, datetime.now(timezone.utc))
    if to_dt <= from_dt:
        to_dt = datetime.now(timezone.utc)
    tasks, task_source = load_tasks(
        runtime_dir,
        Path(args.plan) if args.plan else None,
        max_tasks=max(1, args.max_tasks),
        routes=args.route,
    )
    fixture_bars = read_bars_file(Path(args.input_bars)) if args.input_bars else {}
    mt5 = None
    mt5_status = {"ok": False, "skipped": bool(fixture_bars)}
    if not fixture_bars:
        mt5, mt5_status = maybe_load_mt5(args.terminal_path)

    rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    bars_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    try:
        for task in tasks:
            task["repoRoot"] = str(repo_root)
            if not task.get("testerOnly", True) or task.get("livePresetMutation"):
                metrics = {
                    "status": "blocked",
                    "sampleState": "BLOCKED",
                    "closedTrades": 0,
                    "blockers": ["task_not_tester_only_or_allows_live_preset_mutation"],
                }
                trades = []
            else:
                key = (task["symbol"], task["timeframe"])
                if key not in bars_cache:
                    bars = fixture_bars.get(key) or fixture_bars.get((task["symbol"], normalize_timeframe(task["timeframe"])))
                    if bars is None and mt5 is not None:
                        bars = load_mt5_rates(
                            mt5=mt5,
                            symbol=task["symbol"],
                            timeframe=task["timeframe"],
                            from_dt=from_dt,
                            to_dt=to_dt,
                            limit=args.max_bars,
                        )
                    bars_cache[key] = bars or []
                metrics, trades = simulate_task(task, bars_cache[key])
            c_row = canonical_row(task["symbol"])
            row = {
                **task,
                "canonicalSymbol": c_row.get("canonicalSymbol", task["symbol"]),
                "brokerSymbol": c_row.get("brokerSymbol", task["symbol"]),
                "assetClass": c_row.get("assetClass", ""),
                "marketCategory": c_row.get("marketCategory", ""),
                **metrics,
                "rankScore": rank_score(metrics),
                "backendDecision": "PROMOTION_REVIEW_CANDIDATE" if metrics.get("sampleState") == "BACKEND_READY" else "KEEP_RESEARCH",
                "backendOnly": True,
                "orderSendAllowed": False,
                "livePresetMutation": False,
            }
            rows.append(row)
            trade_rows.extend(trades)
    finally:
        if mt5 is not None:
            try:
                mt5.shutdown()
            except Exception:
                pass

    rows.sort(key=lambda row: (-as_float(row.get("rankScore")), str(row.get("candidateId"))))
    generated_at = utc_now()
    payload = {
        "schemaVersion": 1,
        "ok": True,
        "mode": "MT5_BACKEND_BACKTEST_LOOP_V1",
        "source": "QuantDinger-style Python backend backtest loop for QuantGod MT5",
        "generatedAtIso": generated_at,
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "taskSource": task_source,
        "range": {
            "from": from_dt.isoformat().replace("+00:00", "Z"),
            "to": to_dt.isoformat().replace("+00:00", "Z"),
            "days": round((to_dt - from_dt).total_seconds() / 86400.0, 3),
            "maxBars": args.max_bars,
        },
        "safety": SAFETY,
        "mt5Status": mt5_status,
        "summary": build_summary(rows),
        "rows": rows,
        "tradeSample": trade_rows[:200],
        "quantDingerAlignment": {
            "borrowedIdeas": [
                "server-side strategy/backtest engine",
                "batchable candidate execution",
                "persisted run/trade artifacts",
                "post-backtest advisory loop",
            ],
            "quantGodDifferences": [
                "no DB required in v1; JSON/CSV artifacts remain the source of truth",
                "no Python live execution adapter",
                "EA live trading, closing, SL, and TP stay untouched",
                "Strategy Tester remains available as a higher-fidelity validation layer",
            ],
        },
    }
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QuantGod MT5 backend backtest loop.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--trade-ledger", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--input-bars", default="", help="Optional JSON/CSV bars fixture for tests or offline runs.")
    parser.add_argument("--terminal-path", default=os.environ.get("QG_MT5_TERMINAL_PATH", ""))
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--from-date", default="")
    parser.add_argument("--to-date", default="")
    parser.add_argument("--max-bars", type=int, default=5000)
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--route", action="append", default=[])
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_backend_loop(args)
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    trade_ledger = Path(args.trade_ledger) if args.trade_ledger else runtime_dir / TRADE_LEDGER_NAME

    write_json(output, payload)
    ledger_fields = [
        "candidateId",
        "routeKey",
        "strategy",
        "symbol",
        "canonicalSymbol",
        "timeframe",
        "variant",
        "closedTrades",
        "wins",
        "losses",
        "winRatePct",
        "netPips",
        "profitFactor",
        "maxDrawdownPips",
        "sampleState",
        "backendDecision",
        "rankScore",
        "blockers",
    ]
    trade_fields = [
        "candidateId",
        "routeKey",
        "strategy",
        "symbol",
        "timeframe",
        "direction",
        "entryTime",
        "exitTime",
        "entryPrice",
        "exitPrice",
        "sl",
        "tp",
        "profitPips",
        "exitReason",
        "backendEngine",
    ]
    ledger_rows = []
    for row in payload["rows"]:
        ledger_row = dict(row)
        ledger_row["blockers"] = ";".join(str(item) for item in safe_list(row.get("blockers")))
        ledger_rows.append(ledger_row)
    write_csv(ledger, ledger_rows, ledger_fields)
    write_csv(trade_ledger, payload.get("tradeSample", []), trade_fields)
    if args.print_summary:
        print(json.dumps({"output": str(output), "ledger": str(ledger), "tradeLedger": str(trade_ledger), "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
