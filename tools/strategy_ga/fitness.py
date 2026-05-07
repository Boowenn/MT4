from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _variant_metrics(report: Dict[str, Any], group: str, index: int) -> Dict[str, Any]:
    section = report.get(group) if isinstance(report.get(group), dict) else {}
    variants = section.get("variants") if isinstance(section.get("variants"), list) else []
    if len(variants) <= index or not isinstance(variants[index], dict):
        return {}
    metrics = variants[index].get("metrics")
    return metrics if isinstance(metrics, dict) else variants[index]


def evidence_metrics(runtime_dir: Path) -> Dict[str, Any]:
    replay = _load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYBarReplayReport.json")
    walk_forward = _load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYWalkForwardReport.json")
    entry_relaxed = _variant_metrics(replay, "entryComparison", 1)
    exit_let_run = _variant_metrics(replay, "exitComparison", 1)
    summary = replay.get("summary") if isinstance(replay.get("summary"), dict) else {}
    wf_summary = walk_forward.get("summary") if isinstance(walk_forward.get("summary"), dict) else {}
    return {
        "sampleCount": int(_num(summary.get("sampleCount") or wf_summary.get("sampleCount"), 0)),
        "netR": _num(entry_relaxed.get("netRDelta") or summary.get("relaxedNetRDelta") or wf_summary.get("netRDelta"), 0),
        "maxAdverseR": _num(entry_relaxed.get("maxAdverseR") or summary.get("maxAdverseR"), 0),
        "profitCaptureRatio": _num(exit_let_run.get("profitCaptureRatio") or summary.get("profitCaptureRatio"), 0),
        "missedOpportunityReduction": _num(entry_relaxed.get("missedOpportunityReduction") or summary.get("entryCountDelta"), 0),
        "validationNetRDelta": _num(wf_summary.get("validationNetRDelta"), 0),
        "forwardNetRDelta": _num(wf_summary.get("forwardNetRDelta"), 0),
        "evidenceQuality": entry_relaxed.get("evidenceQuality") or wf_summary.get("evidenceQuality") or "LOW",
    }


def score_seed(seed: Dict[str, Any], runtime_dir: Path) -> Dict[str, Any]:
    metrics = evidence_metrics(runtime_dir)
    family = seed.get("strategyFamily", "")
    direction = seed.get("direction", "")
    sample_count = metrics["sampleCount"]
    family_bonus = 0.25 if family == "RSI_Reversal" and direction == "LONG" else -0.15
    low_sample_penalty = max(0.0, (20 - sample_count) / 20.0)
    max_adverse_penalty = max(0.0, abs(min(0.0, metrics["maxAdverseR"])) - 0.5)
    overfit_penalty = 0.25 if metrics["validationNetRDelta"] < 0 or metrics["forwardNetRDelta"] < 0 else 0.0
    trade_frequency_penalty = 0.15 if sample_count == 0 else 0.0
    fitness = (
        metrics["netR"]
        + metrics["profitCaptureRatio"] * 0.5
        + metrics["missedOpportunityReduction"] * 0.2
        + family_bonus
        - max_adverse_penalty
        - overfit_penalty
        - low_sample_penalty
        - trade_frequency_penalty
    )
    blocker = None
    if sample_count < 5:
        blocker = "INSUFFICIENT_SAMPLES"
    elif overfit_penalty:
        blocker = "OVERFIT_RISK"
    elif max_adverse_penalty > 0.5:
        blocker = "MAX_ADVERSE_TOO_HIGH"
    elif fitness < 0:
        blocker = "FITNESS_TOO_LOW"
    return {
        **metrics,
        "fitness": round(fitness, 4),
        "overfitPenalty": round(overfit_penalty, 4),
        "lowSamplePenalty": round(low_sample_penalty, 4),
        "maxAdversePenalty": round(max_adverse_penalty, 4),
        "tradeFrequencyPenalty": round(trade_frequency_penalty, 4),
        "blockerCode": blocker,
    }

