"""Research-only backtest connector for Vibe Coding strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import builtins
import json
import math
import random
from typing import Any

from .config import VibeCodingConfig, load_config, phase3_vibe_safety
from .safety import validate_strategy_code
from .strategy_registry import StrategyRegistry, utc_now
from .strategy_template import BaseStrategy, normalize_signal


@dataclass
class BacktestRequest:
    strategy_id: str
    symbol: str = "EURUSDc"
    timeframe: str = "H1"
    days: int = 30
    version: str | None = None


class SafeImportError(ImportError):
    pass


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed_roots = {"math", "statistics", "datetime", "pandas", "numpy", "talib", "ta", "pandas_ta", "tools"}
    root = str(name or "").split(".")[0]
    if root not in allowed_roots:
        raise SafeImportError(f"import blocked by QuantGod Vibe sandbox: {name}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _sandbox_builtins() -> dict[str, Any]:
    names = [
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max", "min",
        "object", "range", "round", "set", "str", "sum", "tuple", "zip", "isinstance", "Exception",
        "ValueError", "TypeError", "property", "staticmethod", "classmethod", "super", "__build_class__",
    ]
    payload = {name: getattr(builtins, name) for name in names}
    payload["__import__"] = _safe_import
    return payload


def load_strategy_class(code: str):
    validation = validate_strategy_code(code)
    if not validation.ok:
        raise ValueError(json.dumps(validation.to_dict(), ensure_ascii=False))
    namespace: dict[str, Any] = {
        "__builtins__": _sandbox_builtins(),
        "__name__": "quantgod_vibe_sandbox",
        "BaseStrategy": BaseStrategy,
    }
    exec(compile(code, "<quantgod_vibe_strategy>", "exec"), namespace, namespace)
    candidates = []
    for value in namespace.values():
        if not isinstance(value, type) or value is BaseStrategy or getattr(value, "__name__", "") == "BaseStrategy":
            continue
        try:
            if issubclass(value, BaseStrategy):
                candidates.append(value)
                continue
        except TypeError:
            pass
        base_names = [getattr(base, "__name__", "") for base in getattr(value, "__mro__", ())]
        if "BaseStrategy" in base_names and callable(getattr(value, "evaluate", None)):
            candidates.append(value)
    if not candidates:
        raise ValueError("No BaseStrategy subclass found after sandbox load")
    return candidates[0]


class _MiniIloc:
    def __init__(self, owner):
        self.owner = owner

    def __getitem__(self, index):
        return self.owner._iloc(index)


class MiniSeries:
    """Tiny pandas-like series surface for deterministic CI backtests."""

    def __init__(self, values: list[float]):
        self.values = [float(v) if v is not None else math.nan for v in values]
        self.iloc = _MiniIloc(self)

    def __len__(self) -> int:
        return len(self.values)

    def _iloc(self, index):
        return self.values[index]

    def rolling(self, window: int):
        return _MiniRolling(self.values, max(1, int(window)))

    def mean(self) -> float:
        values = [v for v in self.values if not math.isnan(v)]
        return sum(values) / len(values) if values else math.nan

    def diff(self):
        out = [math.nan]
        out.extend(self.values[i] - self.values[i - 1] for i in range(1, len(self.values)))
        return MiniSeries(out)

    def clip(self, lower=None, upper=None):
        out = []
        for value in self.values:
            if math.isnan(value):
                out.append(value)
                continue
            next_value = value
            if lower is not None:
                next_value = max(next_value, float(lower))
            if upper is not None:
                next_value = min(next_value, float(upper))
            out.append(next_value)
        return MiniSeries(out)

    def __neg__(self):
        return MiniSeries([-value if not math.isnan(value) else value for value in self.values])


class _MiniRolling:
    def __init__(self, values: list[float], window: int):
        self.values = values
        self.window = window

    def mean(self):
        out = []
        for index in range(len(self.values)):
            window_values = [
                value
                for value in self.values[max(0, index - self.window + 1): index + 1]
                if not math.isnan(value)
            ]
            out.append(sum(window_values) / len(window_values) if window_values else math.nan)
        return MiniSeries(out)


class MiniBars:
    """Small dataframe-like OHLCV container used when pandas is unavailable."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = list(rows)
        self.iloc = _MiniIloc(self)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, column: str):
        return MiniSeries([row.get(column) for row in self.rows])

    def _iloc(self, index):
        if isinstance(index, slice):
            return MiniBars(self.rows[index])
        return self.rows[index]

    def copy(self):
        return MiniBars([dict(row) for row in self.rows])


def _mock_bars(symbol: str, timeframe: str, days: int, max_bars: int = 1000):
    tf_minutes = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}.get(str(timeframe).upper(), 60)
    bars = min(max(220, int(days * 24 * 60 / tf_minutes)), max_bars)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    seed = sum(ord(c) for c in f"{symbol}:{timeframe}:{days}")
    rng = random.Random(seed)
    price = 1.08 if "JPY" not in symbol.upper() else 150.0
    rows = []
    for i in range(bars):
        t = now - timedelta(minutes=tf_minutes * (bars - i))
        drift = math.sin(i / 35.0) * 0.00025
        shock = rng.uniform(-0.0007, 0.0007)
        if "JPY" in symbol.upper():
            drift *= 100
            shock *= 100
        open_ = price
        close = max(0.0001, price + drift + shock)
        high = max(open_, close) + abs(shock) * 0.7
        low = min(open_, close) - abs(shock) * 0.7
        rows.append({"timestamp": int(t.timestamp() * 1000), "open": open_, "high": high, "low": low, "close": close, "volume": rng.randint(50, 500)})
        price = close
    return MiniBars(rows)


def _pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


class BacktestConnector:
    """Connects generated strategies to a local Python research backtest.

    This intentionally does not launch MT5 Strategy Tester or call trading APIs.
    It produces a research artifact that can later be reviewed by ParamLab and
    Governance before any manual live authorization.
    """

    def __init__(self, config: VibeCodingConfig | None = None, registry: StrategyRegistry | None = None):
        self.config = config or load_config()
        self.registry = registry or StrategyRegistry(self.config)
        self.config.history_dir.mkdir(parents=True, exist_ok=True)

    def run_backtest(self, request: BacktestRequest) -> dict[str, Any]:
        loaded = self.registry.get_strategy(request.strategy_id, request.version, include_code=True)
        if not loaded.get("ok"):
            return {"ok": False, "error": loaded.get("error"), "request": request.__dict__, "safety": phase3_vibe_safety()}
        strategy_meta = loaded["strategy"]
        code = loaded.get("code", "")
        validation = validate_strategy_code(code)
        if not validation.ok:
            return {"ok": False, "error": "strategy_failed_safety_validation", "validation": validation.to_dict(), "safety": phase3_vibe_safety()}
        strategy_cls = load_strategy_class(code)
        strategy = strategy_cls()
        bars = _mock_bars(request.symbol, request.timeframe, request.days, self.config.max_backtest_bars)
        pip = _pip_size(request.symbol)
        trades: list[dict[str, Any]] = []
        equity = 0.0
        curve = []
        horizon = 12 if request.timeframe.upper().startswith("M") else 6
        warmup = min(200, max(50, len(bars) // 4))
        i = warmup
        while i < len(bars) - horizon:
            window = bars.iloc[max(0, i - 200): i + 1].copy()
            signal = normalize_signal(strategy.evaluate(window))
            action = signal["signal"]
            confidence = signal["confidence"]
            if action and confidence >= 0.35:
                entry = float(bars.iloc[i]["close"])
                sl_pips = max(float(signal["sl_pips"] or 12.0), 1.0)
                tp_pips = max(float(signal["tp_pips"] or sl_pips * 1.5), 1.0)
                exit_price = float(bars.iloc[i + horizon]["close"])
                pnl_pips = (exit_price - entry) / pip if action == "BUY" else (entry - exit_price) / pip
                pnl_pips = max(-sl_pips, min(tp_pips, pnl_pips))
                equity += pnl_pips
                trades.append({
                    "index": int(i),
                    "time": datetime.fromtimestamp(int(bars.iloc[i]["timestamp"]) / 1000, tz=timezone.utc).isoformat(),
                    "symbol": request.symbol,
                    "timeframe": request.timeframe,
                    "action": action,
                    "entry": round(entry, 6),
                    "exit": round(exit_price, 6),
                    "pnl_pips": round(pnl_pips, 3),
                    "confidence": confidence,
                    "reasoning": signal["reasoning"],
                })
                curve.append({"time": trades[-1]["time"], "equity_pips": round(equity, 3)})
                i += horizon
            else:
                if i % 10 == 0:
                    curve.append({"time": datetime.fromtimestamp(int(bars.iloc[i]["timestamp"]) / 1000, tz=timezone.utc).isoformat(), "equity_pips": round(equity, 3)})
                i += 1
        wins = [t for t in trades if float(t["pnl_pips"]) > 0]
        losses = [t for t in trades if float(t["pnl_pips"]) < 0]
        gross_profit = sum(float(t["pnl_pips"]) for t in wins)
        gross_loss = abs(sum(float(t["pnl_pips"]) for t in losses))
        profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else (round(gross_profit, 3) if gross_profit else 0.0)
        result = {
            "ok": True,
            "schema": "quantgod.vibe_backtest.v1",
            "generatedAt": utc_now(),
            "strategy_id": request.strategy_id,
            "version": strategy_meta.get("version"),
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "days": request.days,
            "metrics": {
                "trades": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(trades), 3) if trades else 0.0,
                "profit_factor": profit_factor,
                "net_pips": round(sum(float(t["pnl_pips"]) for t in trades), 3),
                "avg_pips": round(sum(float(t["pnl_pips"]) for t in trades) / len(trades), 3) if trades else 0.0,
            },
            "equity_curve": curve[-500:],
            "trades": trades[-500:],
            "source": {"mode": "local_mock_ohlcv_research_backtest", "bars": len(bars)},
            "safety": phase3_vibe_safety(),
        }
        result_path = self.config.history_dir / f"backtest_{request.strategy_id}_{strategy_meta.get('version')}_{utc_now().replace(':','')}.json"
        result["source"]["resultPath"] = str(result_path)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        self.registry.append_backtest(request.strategy_id, strategy_meta.get("version"), {"path": str(result_path), "metrics": result["metrics"], "generatedAt": result["generatedAt"]})
        return result
