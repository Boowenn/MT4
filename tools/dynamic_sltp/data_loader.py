from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


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
            strategy = _first(row, ["strategy", "Strategy", "route", "strategyName"], "UNKNOWN")
            direction_raw = _first(row, ["direction", "Direction", "side", "signalDirection"], "UNKNOWN").upper()
            direction = "LONG" if direction_raw in {"BUY", "LONG", "BULL", "1"} else "SHORT" if direction_raw in {"SELL", "SHORT", "BEAR", "-1"} else direction_raw
            regime = _first(row, ["regime", "Regime", "marketRegime", "state"], "UNKNOWN")
            horizon = _first(row, ["horizon", "Horizon", "horizonMinutes", "minutes"], "")
            mfe = _first_float(row, ["mfePips", "MFE", "mfe", "maxFavorablePips", "maxFavorableMove"], 0.0)
            mae = abs(_first_float(row, ["maePips", "MAE", "mae", "maxAdversePips", "maxAdverseMove"], 0.0))
            pnl = _first_float(row, ["pnlPips", "pips", "pnl", "outcomePips", "scoreR"], 0.0)
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
