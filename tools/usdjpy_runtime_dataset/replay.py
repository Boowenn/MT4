from __future__ import annotations

from statistics import mean
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.usdjpy_strategy_lab.data_loader import _write_json, first_json, to_float
except ModuleNotFoundError:  # pragma: no cover - CLI entrypoint runs from tools/
    from usdjpy_strategy_lab.data_loader import _write_json, first_json, to_float

from .builder import build_runtime_dataset
from .schema import FOCUS_SYMBOL, READ_ONLY_SAFETY, SCHEMA_REPLAY, utc_now_iso


POSTERIOR_WINDOWS = ("15m", "30m", "60m", "120m")


def _load_dataset(runtime_dir: Path) -> Dict[str, Any]:
    payload = first_json(runtime_dir, "QuantGod_USDJPYRuntimeDataset.json") or {}
    if payload:
        return payload
    return build_runtime_dataset(runtime_dir, write=False)


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _posterior_r(sample: Dict[str, Any], window: str) -> float | None:
    posterior_r = sample.get("posteriorR") if isinstance(sample.get("posteriorR"), dict) else {}
    value = _maybe_float(posterior_r.get(window))
    if value is not None:
        return value
    posterior_pips = sample.get("posteriorPips") if isinstance(sample.get("posteriorPips"), dict) else {}
    pips = _maybe_float(posterior_pips.get(window))
    risk_pips = _maybe_float(sample.get("riskPips"))
    if pips is not None and risk_pips and risk_pips > 0:
        return round(pips / risk_pips, 4)
    return None


def _posterior_block(sample: Dict[str, Any]) -> Dict[str, Any]:
    posterior_pips = sample.get("posteriorPips") if isinstance(sample.get("posteriorPips"), dict) else {}
    values = {}
    for window in POSTERIOR_WINDOWS:
        values[window] = {
            "pips": _maybe_float(posterior_pips.get(window)),
            "r": _posterior_r(sample, window),
        }
    coverage = sum(1 for item in values.values() if item["r"] is not None or item["pips"] is not None)
    return {
        "windows": values,
        "evidenceQuality": "HAS_POSTERIOR_PATH" if coverage else "NEEDS_BAR_REPLAY",
    }


def _profit_capture_ratio(profit_r: float | None, mfe_r: float | None) -> float | None:
    if profit_r is None or mfe_r is None or mfe_r <= 0:
        return None
    return round(max(0.0, profit_r) / mfe_r, 4)


def _avg(values: List[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _build_scenario_comparisons(
    samples: List[Dict[str, Any]],
    missed: List[Dict[str, Any]],
    early_exits: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    entered_r = [_maybe_float(sample.get("profitR")) for sample in samples if sample.get("didEnter")]
    entered_r = [value for value in entered_r if value is not None]
    relaxed_r = []
    relaxed_mae = []
    unresolved = 0
    for item in missed:
        posterior = item.get("posterior") if isinstance(item.get("posterior"), dict) else {}
        windows = posterior.get("windows") if isinstance(posterior.get("windows"), dict) else {}
        value = None
        for window in ("60m", "120m", "30m", "15m"):
            candidate = windows.get(window) if isinstance(windows.get(window), dict) else {}
            value = _maybe_float(candidate.get("r"))
            if value is not None:
                break
        if value is None:
            unresolved += 1
        else:
            relaxed_r.append(value)
        mae = _maybe_float(item.get("maeR"))
        if mae is not None:
            relaxed_mae.append(mae)
    let_profit_delta = []
    for item in early_exits:
        profit_r = _maybe_float(item.get("profitR"))
        mfe_r = _maybe_float(item.get("mfeR"))
        if profit_r is None or mfe_r is None:
            continue
        projected = max(profit_r, mfe_r * 0.6)
        let_profit_delta.append(round(projected - profit_r, 4))
    return [
        {
            "scenario": "current",
            "labelZh": "当前规则",
            "sampleCount": len(entered_r),
            "netR": round(sum(entered_r), 4) if entered_r else None,
            "avgR": _avg(entered_r),
            "missedOpportunityReduction": 0,
            "unresolvedPosteriorCount": 0,
            "verdict": "baseline",
        },
        {
            "scenario": "relaxed_entry_v1",
            "labelZh": "放宽入场一档",
            "sampleCount": len(relaxed_r),
            "netRDelta": round(sum(relaxed_r), 4) if relaxed_r else None,
            "avgRDelta": _avg(relaxed_r),
            "missedOpportunityReduction": len(relaxed_r),
            "maxAdverseR": min(relaxed_mae) if relaxed_mae else None,
            "unresolvedPosteriorCount": unresolved,
            "verdict": "shadow_only" if relaxed_r else "needs_bar_replay",
        },
        {
            "scenario": "let_profit_run_v1",
            "labelZh": "盈利单多拿一段",
            "sampleCount": len(let_profit_delta),
            "netRDelta": round(sum(let_profit_delta), 4) if let_profit_delta else None,
            "avgRDelta": _avg(let_profit_delta),
            "earlyExitReduction": len(let_profit_delta),
            "unresolvedPosteriorCount": 0,
            "verdict": "shadow_only" if let_profit_delta else "no_action",
        },
    ]


def build_replay_report(runtime_dir: Path, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    dataset = _load_dataset(runtime_dir)
    samples = dataset.get("samples") if isinstance(dataset.get("samples"), list) else []
    missed = []
    early_exits = []
    reasonable_blocks = []
    missing_r_for_exit = 0
    for sample in samples:
        reason = str(sample.get("blockReason") or sample.get("status") or "")
        did_enter = bool(sample.get("didEnter"))
        would_enter = bool(sample.get("wouldEnter"))
        profit_usc = to_float(sample.get("profitUSC"), 0.0)
        profit_r = _maybe_float(sample.get("profitR"))
        mfe_r = _maybe_float(sample.get("mfeR"))
        mae_r = _maybe_float(sample.get("maeR"))
        if would_enter and not did_enter:
            missed.append({
                "timestamp": sample.get("timestamp"),
                "reason": reason or "RSI 买入信号未进入实盘",
                "strategy": sample.get("strategy"),
                "direction": sample.get("direction"),
                "posterior": _posterior_block(sample),
                "maeR": mae_r,
            })
        elif not did_enter and reason:
            reasonable_blocks.append({"timestamp": sample.get("timestamp"), "reason": reason[:160]})
        capture_ratio = _profit_capture_ratio(profit_r, mfe_r)
        if did_enter and profit_r is None and mfe_r is not None and profit_usc >= 0:
            missing_r_for_exit += 1
        if did_enter and profit_r is not None and mfe_r is not None and profit_r >= 0 and mfe_r >= 1.2 and (capture_ratio is None or capture_ratio <= 0.55):
            early_exits.append({
                "timestamp": sample.get("timestamp"),
                "profitUSC": profit_usc,
                "profitR": profit_r,
                "mfeR": mfe_r,
                "maeR": mae_r,
                "profitCaptureRatio": capture_ratio,
                "exitReason": sample.get("exitReason") or "盈利保护可能过早",
            })
    scenario_comparisons = _build_scenario_comparisons(samples, missed, early_exits)
    posterior_ready = sum(1 for item in missed if item.get("posterior", {}).get("evidenceQuality") == "HAS_POSTERIOR_PATH")
    status = "REPLAY_READY" if len(samples) >= 20 else "INSUFFICIENT_DATA"
    payload = {
        "ok": True,
        "schema": SCHEMA_REPLAY,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "status": status,
        "statusZh": "已生成 USDJPY 回放复盘" if status == "REPLAY_READY" else "样本不足，先继续采集 USDJPY 运行数据",
        "safety": READ_ONLY_SAFETY,
        "summary": {
            "sampleCount": len(samples),
            "missedOpportunityCount": len(missed),
            "earlyExitCount": len(early_exits),
            "reasonableBlockCount": len(reasonable_blocks),
            "posteriorReadyCount": posterior_ready,
            "missingExitRCount": missing_r_for_exit,
            "needsRetune": bool(missed or early_exits),
        },
        "unitPolicy": {
            "primary": "R",
            "secondary": "pips",
            "note": "参数候选只使用 R 或 pips；USC 金额只保留为账面参考，不再与 MFE/MAE 混算。",
        },
        "scenarioComparisons": scenario_comparisons,
        "missedOpportunities": missed[:30],
        "earlyExits": early_exits[:30],
        "reasonableBlocks": reasonable_blocks[:30],
        "nextStep": "生成 tester-only 参数候选，不自动修改实盘 preset。" if (missed or early_exits) else "继续采集，暂不需要改代码或参数。",
    }
    if write:
        out_dir = runtime_dir / "replay" / "usdjpy"
        _write_json(out_dir / "QuantGod_USDJPYReplayReport.json", payload)
        _write_json(out_dir / "QuantGod_USDJPYMissedOpportunityReport.json", {
            "schema": "quantgod.usdjpy_missed_opportunity.v1",
            "generatedAtIso": payload["generatedAtIso"],
            "symbol": FOCUS_SYMBOL,
            "summary": {"count": len(missed), "posteriorReadyCount": posterior_ready},
            "items": missed,
            "safety": READ_ONLY_SAFETY,
        })
        _write_json(out_dir / "QuantGod_USDJPYExitHoldReport.json", {
            "schema": "quantgod.usdjpy_exit_hold.v1",
            "generatedAtIso": payload["generatedAtIso"],
            "symbol": FOCUS_SYMBOL,
            "summary": {"count": len(early_exits)},
            "items": early_exits,
            "safety": READ_ONLY_SAFETY,
        })
    return payload
