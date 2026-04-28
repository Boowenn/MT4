#!/usr/bin/env python3
"""Build offline parameter candidates for QuantGod legacy MT5 routes.

The output is a file-only optimization plan. It proposes parameter candidates
and Strategy Tester tasks for RSI/BB/MACD/SR, but it never changes the live
preset, never connects to HFM, and never sends orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_ParamOptimizationPlan.json"

ROUTES: dict[str, dict[str, Any]] = {
    "RSI_Reversal": {
        "label": "USDJPY RSI_Reversal H1",
        "candidateRoute": "RSI_REVERSAL_SHADOW",
        "symbols": ["USDJPYc"],
        "timeframe": "H1",
        "baseSymbol": "USDJPYc",
        "liveEligible": True,
    },
    "BB_Triple": {
        "label": "BB_Triple H1",
        "candidateRoute": "BB_TRIPLE_SHADOW",
        "symbols": ["EURUSDc", "USDJPYc"],
        "timeframe": "H1",
        "baseSymbol": "EURUSDc",
        "liveEligible": False,
    },
    "MACD_Divergence": {
        "label": "MACD_Divergence H1",
        "candidateRoute": "MACD_MOMENTUM_TURN",
        "symbols": ["EURUSDc", "USDJPYc"],
        "timeframe": "H1",
        "baseSymbol": "EURUSDc",
        "liveEligible": False,
    },
    "SR_Breakout": {
        "label": "SR_Breakout M15",
        "candidateRoute": "SR_BREAKOUT_SHADOW",
        "symbols": ["EURUSDc", "USDJPYc"],
        "timeframe": "M15",
        "baseSymbol": "EURUSDc",
        "liveEligible": False,
    },
}

ROUTE_LIVE_SWITCHES = {
    "RSI_Reversal": "EnablePilotRsiH1Live",
    "BB_Triple": "EnablePilotBBH1Live",
    "MACD_Divergence": "EnablePilotMacdH1Live",
    "SR_Breakout": "EnablePilotSRM15Live",
}

ROUTE_CANDIDATE_SWITCHES = {
    "RSI_Reversal": "EnablePilotRsiH1Candidate",
    "BB_Triple": "EnablePilotBBH1Candidate",
    "MACD_Divergence": "EnablePilotMacdH1Candidate",
    "SR_Breakout": "EnablePilotSRM15Candidate",
}

VARIANTS: dict[str, list[dict[str, Any]]] = {
    "RSI_Reversal": [
        {
            "name": "rsi_guarded_current",
            "intent": "Keep the proven old-route core as a control arm.",
            "bias": 4,
            "params": {
                "PilotRsiPeriod": 2,
                "PilotRsiOverbought": 80,
                "PilotRsiOversold": 20,
                "PilotRsiBandTolerancePct": 0.008,
                "PilotRsiATRMultiplierSL": 1.5,
            },
        },
        {
            "name": "rsi_strict_crossback",
            "intent": "Reduce weak reversals by requiring a more extreme RSI zone.",
            "bias": 8,
            "params": {
                "PilotRsiPeriod": 2,
                "PilotRsiOverbought": 85,
                "PilotRsiOversold": 15,
                "PilotRsiBandTolerancePct": 0.006,
                "PilotRsiATRMultiplierSL": 1.35,
            },
        },
        {
            "name": "rsi_smoother_h1",
            "intent": "Check whether a smoother H1 RSI improves post-outcome stability.",
            "bias": 2,
            "params": {
                "PilotRsiPeriod": 3,
                "PilotRsiOverbought": 78,
                "PilotRsiOversold": 22,
                "PilotRsiBandTolerancePct": 0.006,
                "PilotRsiATRMultiplierSL": 1.6,
            },
        },
    ],
    "BB_Triple": [
        {
            "name": "bb_current_control",
            "intent": "Control arm for the current MT5 BB port.",
            "bias": 0,
            "params": {
                "PilotBBPeriod": 20,
                "PilotBBDeviation": 2.0,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 65,
                "PilotBBRsiOversold": 35,
            },
        },
        {
            "name": "bb_strict_outer_band",
            "intent": "Demand a wider band touch and stronger RSI confirmation.",
            "bias": 7,
            "params": {
                "PilotBBPeriod": 20,
                "PilotBBDeviation": 2.25,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 70,
                "PilotBBRsiOversold": 30,
            },
        },
        {
            "name": "bb_smoother_regime",
            "intent": "Slow the band and keep confirmation strict for choppy regimes.",
            "bias": 5,
            "params": {
                "PilotBBPeriod": 24,
                "PilotBBDeviation": 2.1,
                "PilotBBRsiPeriod": 14,
                "PilotBBRsiOverbought": 68,
                "PilotBBRsiOversold": 32,
            },
        },
    ],
    "MACD_Divergence": [
        {
            "name": "macd_current_control",
            "intent": "Control arm for the current MACD divergence port.",
            "bias": 0,
            "params": {
                "PilotMacdFast": 12,
                "PilotMacdSlow": 26,
                "PilotMacdSignal": 9,
                "PilotMacdLookback": 24,
            },
        },
        {
            "name": "macd_fast_turn",
            "intent": "React faster to momentum turns after weak current outcomes.",
            "bias": 8,
            "params": {
                "PilotMacdFast": 8,
                "PilotMacdSlow": 21,
                "PilotMacdSignal": 5,
                "PilotMacdLookback": 18,
            },
        },
        {
            "name": "macd_slow_filter",
            "intent": "Filter noise by requiring slower momentum agreement.",
            "bias": 5,
            "params": {
                "PilotMacdFast": 16,
                "PilotMacdSlow": 34,
                "PilotMacdSignal": 9,
                "PilotMacdLookback": 30,
            },
        },
    ],
    "SR_Breakout": [
        {
            "name": "sr_current_control",
            "intent": "Control arm for the current support/resistance breakout port.",
            "bias": 0,
            "params": {
                "PilotSRLookback": 24,
                "PilotSRBreakPips": 2.0,
            },
        },
        {
            "name": "sr_strict_break",
            "intent": "Require a wider break and longer structure window.",
            "bias": 7,
            "params": {
                "PilotSRLookback": 48,
                "PilotSRBreakPips": 3.5,
            },
        },
        {
            "name": "sr_fast_retest",
            "intent": "Probe a shorter structure window without loosening the break too far.",
            "bias": 3,
            "params": {
                "PilotSRLookback": 16,
                "PilotSRBreakPips": 2.5,
            },
        },
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod offline parameter optimization plan.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--max-tasks", type=int, default=12)
    return parser.parse_args()


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
        return json.loads(read_text(path))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = read_text(path)
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
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


def pct(part: float, total: float) -> float | None:
    if total <= 0:
        return None
    return round(part / total * 100.0, 2)


def normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def read_preset(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def summarize_candidate_outcomes(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        route = str(row.get("CandidateRoute", "")).strip() or "UNKNOWN"
        grouped[route].append(row)

    result: dict[str, Any] = {}
    for route, route_rows in grouped.items():
        horizon = [row for row in route_rows if as_int(row.get("HorizonMinutes")) == 60] or route_rows
        wins = sum(1 for row in horizon if str(row.get("DirectionalOutcome", "")).upper() == "WIN")
        losses = sum(1 for row in horizon if str(row.get("DirectionalOutcome", "")).upper() == "LOSS")
        flats = max(0, len(horizon) - wins - losses)
        signed_pips = []
        for row in horizon:
            direction = str(row.get("CandidateDirection", "")).upper()
            signed_pips.append(
                as_float(row.get("LongClosePips")) if direction == "BUY" else as_float(row.get("ShortClosePips"))
            )
        result[route] = {
            "rows": len(route_rows),
            "horizonRows": len(horizon),
            "wins": wins,
            "losses": losses,
            "flats": flats,
            "winRatePct": pct(wins, len(horizon)),
            "avgSignedPips": round(sum(signed_pips) / len(signed_pips), 3) if signed_pips else None,
        }
    return result


def advisor_decisions_by_strategy(advisor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = advisor.get("routeDecisions")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy") or row.get("key") or ""): row
        for row in rows
        if isinstance(row, dict)
    }


def task_score(route_key: str, variant: dict[str, Any], evidence: dict[str, Any], action: str) -> float:
    rows = as_int(evidence.get("horizonRows"))
    win_rate = evidence.get("winRatePct")
    avg_pips = evidence.get("avgSignedPips")
    score = 40.0 + min(rows, 60) * 0.25 + float(variant.get("bias", 0))
    if win_rate is not None:
        score += (float(win_rate) - 50.0) * 0.65
    if avg_pips is not None:
        score += max(min(float(avg_pips), 12.0), -12.0) * 1.2
    if action == "RETUNE_SIM":
        score += 12.0
    elif action == "KEEP_SIM_ITERATE":
        score += 7.0
    elif action == "PROMOTION_REVIEW":
        score += 4.0
    elif action == "KEEP_LIVE_WATCH" and route_key == "RSI_Reversal":
        score += 4.0
    return round(score, 3)


def route_safety_overrides(route_key: str, symbol: str) -> dict[str, str]:
    overrides = {
        "DashboardBuild": "QuantGod-v3.12-param-lab-v1",
        "Watchlist": symbol,
        "PreferredSymbolSuffix": "AUTO",
        "ShadowMode": "false",
        "ReadOnlyMode": "false",
        "EnablePilotAutoTrading": "true",
        "EnablePilotMA": "false",
        "EnablePilotRsiH1Candidate": "false",
        "EnablePilotRsiH1Live": "false",
        "EnablePilotBBH1Candidate": "false",
        "EnablePilotBBH1Live": "false",
        "EnablePilotMacdH1Candidate": "false",
        "EnablePilotMacdH1Live": "false",
        "EnablePilotSRM15Candidate": "false",
        "EnablePilotSRM15Live": "false",
        "PilotLotSize": "0.01",
        "PilotMaxTotalPositions": "1",
        "PilotMaxPositionsPerSymbol": "1",
        "PilotBlockManualPerSymbol": "false",
        "EnablePilotNewsFilter": "false",
        "EnableManualSafetyGuard": "false",
        "PilotCloseOnKillSwitch": "true",
    }
    overrides[ROUTE_CANDIDATE_SWITCHES[route_key]] = "true"
    overrides[ROUTE_LIVE_SWITCHES[route_key]] = "true"
    return overrides


def parameter_summary(params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        short_key = key.replace("Pilot", "").replace("Multiplier", "Mult").replace("Mulitplier", "Mult")
        parts.append(f"{short_key}={normalize_param_value(value)}")
    return ", ".join(parts)


def build_plan(repo_root: Path, runtime_dir: Path, max_tasks: int) -> dict[str, Any]:
    advisor = read_json(runtime_dir / "QuantGod_GovernanceAdvisor.json")
    advisor_routes = advisor_decisions_by_strategy(advisor)
    candidate_rows = read_csv(runtime_dir / "QuantGod_ShadowCandidateLedger.csv")
    candidate_outcome_rows = read_csv(runtime_dir / "QuantGod_ShadowCandidateOutcomeLedger.csv")
    candidate_counts = Counter(str(row.get("CandidateRoute", "") or "UNKNOWN").strip() for row in candidate_rows)
    outcome_summary = summarize_candidate_outcomes(candidate_outcome_rows)

    route_plans = []
    all_candidates: list[dict[str, Any]] = []
    for route_key, route in ROUTES.items():
        route_evidence = outcome_summary.get(route["candidateRoute"], {})
        advisor_route = advisor_routes.get(route_key, {})
        action = str(advisor_route.get("recommendedAction") or ("KEEP_LIVE_WATCH" if route["liveEligible"] else "KEEP_SIM_COLLECT"))
        base_preset_path = repo_root / "MQL5" / "Presets" / f"QuantGod_MT5_HFM_Backtest_{route['baseSymbol']}.set"
        base_preset = read_preset(base_preset_path)
        route_candidates = []
        for variant in VARIANTS[route_key]:
            for symbol in route["symbols"]:
                preset_overrides = {
                    **route_safety_overrides(route_key, symbol),
                    **{key: normalize_param_value(value) for key, value in variant["params"].items()},
                }
                candidate_score = task_score(route_key, variant, route_evidence, action)
                candidate_id = f"{route_key}_{symbol}_{variant['name']}"
                candidate = {
                    "candidateId": candidate_id,
                    "routeKey": route_key,
                    "strategy": route_key,
                    "label": route["label"],
                    "symbol": symbol,
                    "timeframe": route["timeframe"],
                    "candidateRoute": route["candidateRoute"],
                    "variant": variant["name"],
                    "intent": variant["intent"],
                    "score": candidate_score,
                    "basePreset": str(base_preset_path),
                    "basePresetFound": bool(base_preset),
                    "presetName": f"QuantGod_MT5_ParamLab_{candidate_id}.set",
                    "presetOverrides": preset_overrides,
                    "parameterSummary": parameter_summary(variant["params"]),
                    "testerOnly": True,
                    "livePresetMutation": False,
                }
                route_candidates.append(candidate)
                all_candidates.append(candidate)

        route_candidates.sort(key=lambda item: item["score"], reverse=True)
        for rank, candidate in enumerate(route_candidates, start=1):
            candidate["routeRank"] = rank

        route_plans.append({
            "routeKey": route_key,
            "strategy": route_key,
            "label": route["label"],
            "mode": "LIVE_WATCH_PARAM_REVIEW" if route["liveEligible"] else "SIM_PARAM_ITERATION",
            "recommendedAction": action,
            "candidateRoute": route["candidateRoute"],
            "ledgerRows": candidate_counts.get(route["candidateRoute"], 0),
            "outcomeEvidence": route_evidence,
            "candidateCount": len(route_candidates),
            "topCandidate": route_candidates[0] if route_candidates else {},
            "candidates": route_candidates,
        })

    all_candidates.sort(key=lambda item: item["score"], reverse=True)
    selected_candidates: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for route_plan in route_plans:
        top = route_plan.get("topCandidate")
        if isinstance(top, dict) and top.get("candidateId") and top["candidateId"] not in selected_ids:
            selected_candidates.append(top)
            selected_ids.add(top["candidateId"])
    for candidate in all_candidates:
        if len(selected_candidates) >= max_tasks:
            break
        if candidate["candidateId"] not in selected_ids:
            selected_candidates.append(candidate)
            selected_ids.add(candidate["candidateId"])
    selected_candidates.sort(key=lambda item: item["score"], reverse=True)

    backtest_tasks = []
    for task_rank, candidate in enumerate(selected_candidates[:max_tasks], start=1):
        backtest_tasks.append({
            "rank": task_rank,
            "candidateId": candidate["candidateId"],
            "routeKey": candidate["routeKey"],
            "symbol": candidate["symbol"],
            "timeframe": candidate["timeframe"],
            "presetName": candidate["presetName"],
            "presetOverrides": candidate["presetOverrides"],
            "status": "PENDING_CONFIG_ONLY",
            "runMode": "manual_strategy_tester_or_weekend_authorized",
            "safety": "tester-only candidate; do not copy into HFM live preset",
        })

    return {
        "schemaVersion": 1,
        "source": "QuantGod offline parameter candidate loop",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "mode": "OFFLINE_PARAM_CANDIDATE_ONLY",
        "hardGuards": [
            "No live preset is mutated.",
            "No terminal is launched by this builder.",
            "No broker connection or OrderSend path is added.",
            "Every tester candidate keeps PilotLotSize=0.01 and PilotMaxTotalPositions=1.",
            "Promotion still requires Governance Advisor, Backtest Lab, candidate outcome, and live-forward review.",
        ],
        "summary": {
            "routeCount": len(route_plans),
            "candidateCount": len(all_candidates),
            "backtestTaskCount": len(backtest_tasks),
            "topCandidateId": all_candidates[0]["candidateId"] if all_candidates else "",
            "livePresetMutation": False,
        },
        "routePlans": route_plans,
        "backtestTasks": backtest_tasks,
        "nextOperatorSteps": [
            "Run these candidates through controlled Strategy Tester/backtest lab before touching live switches.",
            "Feed only verified winners back into a review preset; never overwrite the HFM live preset automatically.",
            "Use Governance Advisor ranking as the single dashboard entry point for promotion review.",
        ],
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    plan = build_plan(repo_root, runtime_dir, max(1, args.max_tasks))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Candidates: {plan['summary']['candidateCount']} | backtest tasks: {plan['summary']['backtestTaskCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
