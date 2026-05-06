from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

STRATEGY_ALIASES = {
    "RSI_REVERSAL_SHADOW": "RSI_Reversal",
    "USDJPY_RSI_H1_LIVE_CANDIDATE": "RSI_Reversal",
    "QG_RSI_REV_MT5": "RSI_Reversal",
    "BB_TRIPLE_SHADOW": "BB_Triple",
    "BB_TRIPLE_H1_LEGACY_CANDIDATE": "BB_Triple",
    "MACD_DIVERGENCE_SHADOW": "MACD_Divergence",
    "MACD_DIVERGENCE_H1_LEGACY_CANDIDATE": "MACD_Divergence",
    "SR_BREAKOUT_SHADOW": "SR_Breakout",
    "SR_BREAKOUT_H1_LEGACY_CANDIDATE": "SR_Breakout",
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace("%", ""))
    except Exception:
        return default


def _first(row: dict[str, Any], names: list[str], default: str = "") -> str:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name])
        lower = name.lower()
        if lower in lowered and lowered[lower] not in (None, ""):
            return str(lowered[lower])
    return default


def _first_float(row: dict[str, Any], names: list[str], default: float = 0.0) -> float:
    return _float(_first(row, names, ""), default)


def _strategy(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    return STRATEGY_ALIASES.get(text.upper(), text)


def _direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BUY", "LONG", "BULL", "1", "多", "买", "买入"}:
        return "LONG"
    if text in {"SELL", "SHORT", "BEAR", "-1", "空", "卖", "卖出"}:
        return "SHORT"
    return text or "UNKNOWN"


def find_runtime_file(runtime_dir: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        for path in sorted(runtime_dir.rglob(pattern)):
            if path.is_file():
                return path
    return None


def load_shadow_outcomes(runtime_dir: Path) -> list[dict[str, Any]]:
    path = find_runtime_file(runtime_dir, ["ShadowCandidateOutcomeLedger.csv", "*Shadow*Outcome*.csv", "*OutcomeLedger.csv"])
    if not path:
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = _first(row, ["symbol", "Symbol", "pair"], "UNKNOWN")
            strategy = _strategy(_first(row, ["strategy", "Strategy", "route", "strategyName", "CandidateRoute"], "UNKNOWN"))
            direction = _direction(_first(row, ["direction", "Direction", "side", "Side", "Type", "signalDirection", "CandidateDirection", "SignalDirection"], "UNKNOWN"))
            regime = _first(row, ["regime", "Regime", "marketRegime", "state"], "UNKNOWN")
            horizon = _first(row, ["horizon", "Horizon", "horizonMinutes", "minutes"], "")
            if direction == "LONG":
                mfe = _first_float(row, ["mfePips", "MFE", "mfe", "LongMFEPips", "maxFavorablePips", "maxFavorableMove"], 0.0)
                mae = abs(_first_float(row, ["maePips", "MAE", "mae", "LongMAEPips", "maxAdversePips", "maxAdverseMove"], 0.0))
                pnl = _first_float(row, ["pnlPips", "pips", "pnl", "outcomePips", "scoreR", "DirectionalOutcomePips", "LongClosePips"], 0.0)
            elif direction == "SHORT":
                mfe = _first_float(row, ["mfePips", "MFE", "mfe", "ShortMFEPips", "maxFavorablePips", "maxFavorableMove"], 0.0)
                mae = abs(_first_float(row, ["maePips", "MAE", "mae", "ShortMAEPips", "maxAdversePips", "maxAdverseMove"], 0.0))
                pnl = _first_float(row, ["pnlPips", "pips", "pnl", "outcomePips", "scoreR", "DirectionalOutcomePips", "ShortClosePips"], 0.0)
            else:
                mfe = _first_float(row, ["mfePips", "MFE", "mfe", "maxFavorablePips", "maxFavorableMove"], 0.0)
                mae = abs(_first_float(row, ["maePips", "MAE", "mae", "maxAdversePips", "maxAdverseMove"], 0.0))
                pnl = _first_float(row, ["pnlPips", "pips", "pnl", "outcomePips", "scoreR", "DirectionalOutcomePips"], 0.0)
            rows.append({
                "symbol": symbol,
                "strategy": strategy,
                "direction": direction,
                "regime": regime,
                "horizon": horizon,
                "mfe": mfe,
                "mae": mae,
                "pnl": pnl,
                "raw": row,
            })
    return rows


def load_strategy_eval(runtime_dir: Path) -> dict[str, dict[str, float]]:
    path = find_runtime_file(runtime_dir, ["QuantGod_StrategyEvaluationReport.csv", "*StrategyEvaluation*.csv"])
    out: dict[str, dict[str, float]] = {}
    if not path:
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = _first(row, ["symbol", "Symbol"], "UNKNOWN")
            out[symbol] = {
                "atr": _first_float(row, ["ATR", "atr", "atrPips", "atr_points"], 0.0),
                "adx": _first_float(row, ["ADX", "adx"], 0.0),
                "bbWidth": _first_float(row, ["BBWidth", "bbWidth", "bb_width"], 0.0),
                "spread": _first_float(row, ["spread", "spreadPoints", "Spread"], 0.0),
            }
    return out


def load_fastlane_quality(runtime_dir: Path) -> dict[str, Any]:
    path = find_runtime_file(runtime_dir, ["QuantGod_MT5FastLaneQuality.json"])
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
