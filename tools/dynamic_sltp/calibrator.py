from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .data_loader import load_fastlane_quality, load_shadow_outcomes, load_strategy_eval
from .schema import assert_safe_payload, safety_payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], q: float) -> float:
    clean = sorted(v for v in values if math.isfinite(v) and v >= 0)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[int(pos)]
    return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)


def _round(value: float, digits: int = 4) -> float:
    try:
        return round(float(value), digits)
    except Exception:
        return 0.0


def _state(sample_count: int, avg_pnl: float, win_rate: float, mae_p70: float, mfe_p50: float, min_samples: int) -> tuple[str, str]:
    if sample_count < min_samples:
        return "INSUFFICIENT_DATA", "样本不足，暂不生成强止盈止损建议"
    if mfe_p50 <= 0 or mae_p70 <= 0:
        return "PAUSED", "MFE/MAE 无有效分布，暂停该方向建议"
    if avg_pnl < 0 and win_rate < 0.45:
        return "PAUSED", "历史影子结果为负，暂停该方向建议"
    if avg_pnl < 0:
        return "WATCH_ONLY", "平均收益为负，仅允许观察复核"
    return "CALIBRATED", "样本满足最低要求，可用于影子级动态止盈止损建议"


def _direction_cn(direction: str) -> str:
    return "买入观察" if direction == "LONG" else "卖出观察" if direction == "SHORT" else direction


def build_calibration(runtime_dir: str | Path, symbols: list[str] | None = None, min_samples: int = 8, write: bool = True) -> dict[str, Any]:
    runtime = Path(runtime_dir)
    outcomes = load_shadow_outcomes(runtime)
    strategy_eval = load_strategy_eval(runtime)
    fastlane = load_fastlane_quality(runtime)
    allowed = {s.strip() for s in symbols or [] if s.strip()}

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        if allowed and row["symbol"] not in allowed:
            continue
        groups[(row["symbol"], row["strategy"], row["direction"], row["regime"])].append(row)

    plans: list[dict[str, Any]] = []
    for (symbol, strategy, direction, regime), rows in sorted(groups.items()):
        mfe = [abs(float(r.get("mfe", 0.0))) for r in rows]
        mae = [abs(float(r.get("mae", 0.0))) for r in rows]
        pnl = [float(r.get("pnl", 0.0)) for r in rows]
        sample_count = len(rows)
        wins = sum(1 for v in pnl if v > 0)
        win_rate = wins / sample_count if sample_count else 0.0
        avg_pnl = mean(pnl) if pnl else 0.0
        mfe_p50 = _percentile(mfe, 0.50)
        mfe_p70 = _percentile(mfe, 0.70)
        mfe_p85 = _percentile(mfe, 0.85)
        mae_p50 = _percentile(mae, 0.50)
        mae_p70 = _percentile(mae, 0.70)
        mae_p85 = _percentile(mae, 0.85)
        eval_stats = strategy_eval.get(symbol, {})
        atr = float(eval_stats.get("atr", 0.0) or 0.0)
        atr_floor = atr * 1.25 if atr > 0 else 0.0
        initial_stop = max(mae_p70, atr_floor, 0.0001)
        tp1 = max(mfe_p50, initial_stop * 0.6)
        tp2 = max(mfe_p70, initial_stop * 1.0)
        tp3 = max(mfe_p85, initial_stop * 1.35)
        break_even_at_r = 0.70 if win_rate >= 0.5 else 0.95
        trail_after_r = 1.20 if win_rate >= 0.5 else 1.50
        state, reason = _state(sample_count, avg_pnl, win_rate, mae_p70, mfe_p50, min_samples)
        fastlane_quality = "UNKNOWN"
        for item in fastlane.get("symbols", []) if isinstance(fastlane, dict) else []:
            if item.get("symbol") == symbol:
                fastlane_quality = str(item.get("quality", "UNKNOWN"))
        if fastlane_quality in {"DEGRADED", "STALE", "FAILED"} and state == "CALIBRATED":
            state = "WATCH_ONLY"
            reason = "快通道质量降级，仅保留观察建议"
        plans.append({
            "symbol": symbol,
            "strategy": strategy,
            "direction": direction,
            "directionText": _direction_cn(direction),
            "regime": regime,
            "state": state,
            "reason": reason,
            "sampleCount": sample_count,
            "winRate": _round(win_rate),
            "averagePnl": _round(avg_pnl),
            "mfe": {"p50": _round(mfe_p50), "p70": _round(mfe_p70), "p85": _round(mfe_p85)},
            "mae": {"p50": _round(mae_p50), "p70": _round(mae_p70), "p85": _round(mae_p85)},
            "atrReference": _round(atr),
            "initialStop": _round(initial_stop),
            "targets": {"tp1": _round(tp1), "tp2": _round(tp2), "tp3": _round(tp3)},
            "management": {
                "breakEvenAtR": _round(break_even_at_r, 2),
                "trailAfterR": _round(trail_after_r, 2),
                "mfeGivebackPct": 0.45,
                "timeStopBars": 4 if "M15" in str(rows[0].get("horizon", "")) else 3,
            },
            "fastlaneQuality": fastlane_quality,
            "execution": {
                "mayPlaceOrder": False,
                "mayModifyOrder": False,
                "advisoryOnly": True,
            },
        })

    payload = {
        "schema": "quantgod.dynamic_sltp.calibration.v1",
        "generatedAt": _now(),
        "runtimeDir": str(runtime),
        "minSamples": min_samples,
        "sourceCounts": {
            "shadowOutcomes": len(outcomes),
            "groups": len(groups),
        },
        "plans": plans,
        "safety": safety_payload(),
    }
    assert_safe_payload(payload)
    if write:
        out_dir = runtime / "adaptive"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "QuantGod_DynamicSLTPCalibration.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with (out_dir / "QuantGod_DynamicSLTPCalibrationLedger.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "strategy", "direction", "regime", "state", "sampleCount", "winRate", "averagePnl", "initialStop", "tp1", "tp2", "tp3", "reason"])
            writer.writeheader()
            for plan in plans:
                writer.writerow({
                    "symbol": plan["symbol"],
                    "strategy": plan["strategy"],
                    "direction": plan["direction"],
                    "regime": plan["regime"],
                    "state": plan["state"],
                    "sampleCount": plan["sampleCount"],
                    "winRate": plan["winRate"],
                    "averagePnl": plan["averagePnl"],
                    "initialStop": plan["initialStop"],
                    "tp1": plan["targets"]["tp1"],
                    "tp2": plan["targets"]["tp2"],
                    "tp3": plan["targets"]["tp3"],
                    "reason": plan["reason"],
                })
    return payload


def select_plan(payload: dict[str, Any], symbol: str, strategy: str | None = None, direction: str | None = None) -> dict[str, Any] | None:
    plans = payload.get("plans", [])
    matches = []
    for plan in plans:
        if plan.get("symbol") != symbol:
            continue
        if strategy and plan.get("strategy") != strategy:
            continue
        if direction and plan.get("direction") != direction:
            continue
        matches.append(plan)
    if not matches:
        return None
    order = {"CALIBRATED": 0, "WATCH_ONLY": 1, "INSUFFICIENT_DATA": 2, "PAUSED": 3}
    return sorted(matches, key=lambda p: (order.get(p.get("state"), 99), -int(p.get("sampleCount", 0))))[0]


def write_sample_runtime(runtime_dir: str | Path, overwrite: bool = False) -> Path:
    runtime = Path(runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "ShadowCandidateOutcomeLedger.csv"
    if path.exists() and not overwrite:
        return path
    rows = []
    for idx in range(12):
        rows.append({
            "symbol": "USDJPYc",
            "strategy": "RSI_Reversal",
            "direction": "BUY",
            "regime": "TREND_EXP_DOWN",
            "horizonMinutes": "30",
            "mfePips": str(4.0 + idx * 0.3),
            "maePips": str(1.0 + (idx % 4) * 0.2),
            "pnlPips": str(1.0 + (idx % 5) * 0.2),
        })
    for idx in range(12):
        rows.append({
            "symbol": "USDJPYc",
            "strategy": "RSI_Reversal",
            "direction": "SELL",
            "regime": "RANGE",
            "horizonMinutes": "30",
            "mfePips": str(1.0 + idx * 0.1),
            "maePips": str(3.0 + (idx % 3) * 0.4),
            "pnlPips": str(-1.0 - (idx % 4) * 0.3),
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path
