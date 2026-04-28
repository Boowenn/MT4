#!/usr/bin/env python3
"""Build a file-based strategy version registry for QuantGod MT5.

The registry borrows QuantDinger's strategy snapshot idea, but keeps QuantGod's
local-file and EA-only execution boundary. It records current route versions,
parameter hashes, evidence, and candidate children. It never changes the HFM
live preset, never starts MT5, and never sends orders.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_StrategyVersionRegistry.json"
LEDGER_NAME = "QuantGod_StrategyVersionRegistry.csv"
PARAM_PLAN_NAME = "QuantGod_ParamOptimizationPlan.json"
PARAM_RESULTS_NAME = "QuantGod_ParamLabResults.json"
GOVERNANCE_NAME = "QuantGod_GovernanceAdvisor.json"
LIVE_PRESET = DEFAULT_REPO_ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"


ROUTES: dict[str, dict[str, Any]] = {
    "MA_Cross": {
        "label": "MA_Cross live baseline",
        "shortLabel": "MA",
        "timeframe": "M15",
        "candidateRoute": "TREND_CONT_NO_CROSS",
        "liveSwitch": "EnablePilotMA",
        "candidateSwitch": "",
        "liveEligible": True,
        "parameterKeys": [
            "PilotFastMAPeriod",
            "PilotSlowMAPeriod",
            "PilotTrendMAPeriod",
            "PilotCrossLookbackBars",
            "PilotContinuationLookbackBars",
            "PilotATRPeriod",
            "PilotATRMulitplierSL",
        ],
    },
    "RSI_Reversal": {
        "label": "USDJPY RSI_Reversal H1",
        "shortLabel": "RSI",
        "timeframe": "H1",
        "candidateRoute": "RSI_REVERSAL_SHADOW",
        "liveSwitch": "EnablePilotRsiH1Live",
        "candidateSwitch": "EnablePilotRsiH1Candidate",
        "liveEligible": True,
        "parameterKeys": [
            "PilotRsiPeriod",
            "PilotRsiOverbought",
            "PilotRsiOversold",
            "PilotRsiBandTolerancePct",
            "PilotRsiATRMultiplierSL",
        ],
    },
    "BB_Triple": {
        "label": "BB_Triple H1",
        "shortLabel": "BB",
        "timeframe": "H1",
        "candidateRoute": "BB_TRIPLE_SHADOW",
        "liveSwitch": "EnablePilotBBH1Live",
        "candidateSwitch": "EnablePilotBBH1Candidate",
        "liveEligible": False,
        "parameterKeys": [
            "PilotBBPeriod",
            "PilotBBDeviation",
            "PilotBBRsiPeriod",
            "PilotBBRsiOverbought",
            "PilotBBRsiOversold",
        ],
    },
    "MACD_Divergence": {
        "label": "MACD_Divergence H1",
        "shortLabel": "MACD",
        "timeframe": "H1",
        "candidateRoute": "MACD_MOMENTUM_TURN",
        "liveSwitch": "EnablePilotMacdH1Live",
        "candidateSwitch": "EnablePilotMacdH1Candidate",
        "liveEligible": False,
        "parameterKeys": [
            "PilotMacdFast",
            "PilotMacdSlow",
            "PilotMacdSignal",
            "PilotMacdLookback",
        ],
    },
    "SR_Breakout": {
        "label": "SR_Breakout M15",
        "shortLabel": "SR",
        "timeframe": "M15",
        "candidateRoute": "SR_BREAKOUT_SHADOW",
        "liveSwitch": "EnablePilotSRM15Live",
        "candidateSwitch": "EnablePilotSRM15Candidate",
        "liveEligible": False,
        "parameterKeys": [
            "PilotSRLookback",
            "PilotSRBreakPips",
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod strategy version registry.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--live-preset", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def stable_hash(payload: Any, length: int = 12) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def parameter_summary(params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        short_key = key.replace("Pilot", "").replace("Mulitplier", "Mult").replace("Multiplier", "Mult")
        parts.append(f"{short_key}={normalize_param_value(value)}")
    return ", ".join(parts)


def route_decisions_by_strategy(advisor: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = advisor.get("routeDecisions")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy") or row.get("key") or ""): row
        for row in rows
        if isinstance(row, dict)
    }


def result_by_route(results_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    top = results_doc.get("topByRoute")
    return top if isinstance(top, dict) else {}


def plan_by_route(plan_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in plan_doc.get("routePlans") or []:
        if isinstance(row, dict) and row.get("routeKey"):
            result[str(row["routeKey"])] = row
    return result


def candidate_children(route_plan: dict[str, Any], parent_version_id: str) -> list[dict[str, Any]]:
    children = []
    for candidate in route_plan.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        params = candidate.get("presetOverrides") or {}
        route_params = {
            key: value
            for key, value in params.items()
            if key.startswith("Pilot") and key not in {"PilotLotSize", "PilotMaxTotalPositions", "PilotMaxPositionsPerSymbol"}
        }
        child_hash = stable_hash({
            "candidateId": candidate.get("candidateId", ""),
            "routeKey": candidate.get("routeKey", ""),
            "params": route_params,
        }, 10)
        children.append({
            "candidateId": candidate.get("candidateId", ""),
            "candidateVersionId": f"{candidate.get('routeKey', 'route')}-cand-{child_hash}",
            "parentVersionId": parent_version_id,
            "variant": candidate.get("variant", ""),
            "symbol": candidate.get("symbol", ""),
            "timeframe": candidate.get("timeframe", ""),
            "score": candidate.get("score", 0),
            "parameterSummary": candidate.get("parameterSummary", parameter_summary(route_params)),
            "testerOnly": True,
            "livePresetMutation": False,
        })
    children.sort(key=lambda row: as_float(row.get("score"), 0.0) or 0.0, reverse=True)
    return children


def build_route_version(
    route_key: str,
    route: dict[str, Any],
    *,
    preset_values: dict[str, str],
    advisor_routes: dict[str, dict[str, Any]],
    route_plan: dict[str, Any],
    route_result: dict[str, Any],
    preset_path: Path,
) -> dict[str, Any]:
    params = {key: preset_values.get(key, "") for key in route["parameterKeys"]}
    live_switch = route.get("liveSwitch", "")
    candidate_switch = route.get("candidateSwitch", "")
    live_enabled = as_bool(preset_values.get(live_switch, "false")) if live_switch else False
    candidate_enabled = as_bool(preset_values.get(candidate_switch, "false")) if candidate_switch else live_enabled
    status = "LIVE_GATED" if live_enabled else ("SIM_CANDIDATE" if candidate_enabled else "REGISTERED_OFF")
    parameter_hash = stable_hash({
        "routeKey": route_key,
        "params": params,
        "liveSwitch": live_switch,
        "liveEnabled": live_enabled,
        "candidateSwitch": candidate_switch,
        "candidateEnabled": candidate_enabled,
    })
    version_id = f"{route_key}-{status.lower().replace('_', '-')}-{parameter_hash[:8]}"
    advisor = advisor_routes.get(route_key, {})
    live_forward = advisor.get("liveForward") if isinstance(advisor.get("liveForward"), dict) else {}
    candidate_samples = advisor.get("candidateSamples") if isinstance(advisor.get("candidateSamples"), dict) else {}
    result_metrics = route_result.get("metrics") if isinstance(route_result.get("metrics"), dict) else {}
    result_grade = str(route_result.get("grade") or "PENDING_REPORT")
    result_score = as_float(route_result.get("resultScore"), 0.0) or 0.0
    recommended_action = str(advisor.get("recommendedAction") or route_plan.get("recommendedAction") or "WAIT_EVIDENCE")
    children = candidate_children(route_plan, version_id)
    top_child = children[0] if children else {}
    score_inputs = {
        "liveClosedTrades": live_forward.get("closedTrades", 0),
        "liveProfitFactor": live_forward.get("profitFactor", None),
        "candidateHorizonRows": candidate_samples.get("horizonRows", 0),
        "candidateWinRatePct": candidate_samples.get("winRatePct", None),
        "paramLabGrade": result_grade,
        "paramLabScore": result_score,
    }
    readiness = "WAIT_TESTER_REPORT"
    if result_grade in {"A", "B"} and recommended_action == "PROMOTION_REVIEW":
        readiness = "PROMOTION_REVIEW_READY"
    elif status == "LIVE_GATED":
        readiness = "LIVE_FORWARD_WATCH"
    elif recommended_action in {"RETUNE_SIM", "KEEP_SIM_ITERATE"}:
        readiness = "SIM_ITERATION"

    return {
        "routeKey": route_key,
        "strategy": route_key,
        "label": route["label"],
        "shortLabel": route["shortLabel"],
        "timeframe": route["timeframe"],
        "candidateRoute": route["candidateRoute"],
        "versionId": version_id,
        "parentVersionId": "",
        "status": status,
        "liveEligible": bool(route.get("liveEligible")),
        "liveSwitch": live_switch,
        "liveEnabled": live_enabled,
        "candidateSwitch": candidate_switch,
        "candidateEnabled": candidate_enabled,
        "sourcePreset": str(preset_path),
        "sourcePresetFound": preset_path.exists(),
        "parameterHash": parameter_hash,
        "parameters": params,
        "parameterSummary": parameter_summary(params),
        "lineage": {
            "currentVersionId": version_id,
            "candidateChildCount": len(children),
            "topCandidateVersionId": top_child.get("candidateVersionId", ""),
        },
        "evidence": {
            "governanceAction": recommended_action,
            "blockers": advisor.get("blockers", []),
            "liveForward": live_forward,
            "candidateSamples": candidate_samples,
            "paramOptimization": {
                "candidateCount": route_plan.get("candidateCount", 0),
                "topCandidateId": (route_plan.get("topCandidate") or {}).get("candidateId", ""),
                "topCandidateScore": (route_plan.get("topCandidate") or {}).get("score", 0),
            },
            "paramLabResult": {
                "candidateId": route_result.get("candidateId", ""),
                "grade": result_grade,
                "resultScore": result_score,
                "metrics": result_metrics,
            },
        },
        "scoreInputs": score_inputs,
        "promotionState": {
            "readiness": readiness,
            "recommendedAction": recommended_action,
            "canMutateLivePreset": False,
            "reason": "Strategy versions are registered for governance review only; EA live switches stay unchanged.",
        },
        "candidateChildren": children,
    }


def build_registry(repo_root: Path, runtime_dir: Path, preset_path: Path) -> dict[str, Any]:
    preset_values = read_preset(preset_path)
    advisor = read_json(runtime_dir / GOVERNANCE_NAME)
    param_plan = read_json(runtime_dir / PARAM_PLAN_NAME)
    param_results = read_json(runtime_dir / PARAM_RESULTS_NAME)
    advisor_routes = route_decisions_by_strategy(advisor)
    plans = plan_by_route(param_plan)
    results = result_by_route(param_results)

    routes = []
    for route_key, route in ROUTES.items():
        routes.append(build_route_version(
            route_key,
            route,
            preset_values=preset_values,
            advisor_routes=advisor_routes,
            route_plan=plans.get(route_key, {}),
            route_result=results.get(route_key, {}),
            preset_path=preset_path,
        ))

    version_index: dict[str, dict[str, Any]] = {}
    for route in routes:
        version_index[route["versionId"]] = {
            "routeKey": route["routeKey"],
            "status": route["status"],
            "parameterHash": route["parameterHash"],
            "liveEnabled": route["liveEnabled"],
            "candidateEnabled": route["candidateEnabled"],
        }
        for child in route["candidateChildren"]:
            version_index[child["candidateVersionId"]] = {
                "routeKey": route["routeKey"],
                "status": "TESTER_ONLY_CANDIDATE",
                "parentVersionId": route["versionId"],
                "candidateId": child.get("candidateId", ""),
            }

    live_count = sum(1 for route in routes if route["liveEnabled"])
    sim_count = sum(1 for route in routes if not route["liveEnabled"] and route["candidateEnabled"])
    child_count = sum(len(route["candidateChildren"]) for route in routes)
    promotion_watch = sum(1 for route in routes if route["promotionState"]["readiness"] == "PROMOTION_REVIEW_READY")
    retune_count = sum(1 for route in routes if route["promotionState"]["recommendedAction"] in {"RETUNE_SIM", "DEMOTE_REVIEW"})
    return {
        "schemaVersion": 1,
        "source": "QuantGod strategy version registry",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "repoRoot": str(repo_root),
        "mode": "FILE_ONLY_STRATEGY_VERSION_REGISTRY",
        "hardGuards": [
            "No HFM live preset is mutated by this registry.",
            "No terminal is launched.",
            "No broker connection or order path is added.",
            "Registered versions are evidence objects; live execution remains inside the EA.",
        ],
        "summary": {
            "routeCount": len(routes),
            "liveVersionCount": live_count,
            "simCandidateVersionCount": sim_count,
            "candidateChildVersionCount": child_count,
            "promotionReviewReadyCount": promotion_watch,
            "retuneCount": retune_count,
            "sourcePresetFound": preset_path.exists(),
            "livePresetMutation": False,
        },
        "quantDingerMigration": {
            "borrowedIdeas": [
                "Strategy snapshots become explicit version records.",
                "Parameter hashes provide stable identity for route versions.",
                "Backtest and forward evidence are attached to the version, not only the route name.",
                "Tester-only child candidates keep lineage to the current live/sim version.",
            ],
            "remainingWorthPorting": [
                "Database-backed version history is deferred; the current QuantGod runtime is file-first.",
                "Live exchange connectors are not ported because QuantGod execution must remain inside the EA guardrails.",
            ],
        },
        "routes": routes,
        "versionIndex": version_index,
    }


def ledger_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for route in registry.get("routes") or []:
        evidence = route.get("evidence") or {}
        result = evidence.get("paramLabResult") or {}
        rows.append({
            "GeneratedAtIso": registry.get("generatedAtIso", ""),
            "RouteKey": route.get("routeKey", ""),
            "VersionId": route.get("versionId", ""),
            "Status": route.get("status", ""),
            "LiveEnabled": route.get("liveEnabled", False),
            "CandidateEnabled": route.get("candidateEnabled", False),
            "ParameterHash": route.get("parameterHash", ""),
            "GovernanceAction": evidence.get("governanceAction", ""),
            "Readiness": (route.get("promotionState") or {}).get("readiness", ""),
            "CandidateChildCount": len(route.get("candidateChildren") or []),
            "TopCandidateVersionId": (route.get("lineage") or {}).get("topCandidateVersionId", ""),
            "ParamLabCandidateId": result.get("candidateId", ""),
            "ParamLabGrade": result.get("grade", ""),
            "ParamLabScore": result.get("resultScore", ""),
            "ParameterSummary": route.get("parameterSummary", ""),
        })
    return rows


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    preset_path = Path(args.live_preset) if args.live_preset else repo_root / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    registry = build_registry(repo_root, runtime_dir, preset_path)
    write_json(output, registry)
    write_csv(ledger, ledger_rows(registry), [
        "GeneratedAtIso",
        "RouteKey",
        "VersionId",
        "Status",
        "LiveEnabled",
        "CandidateEnabled",
        "ParameterHash",
        "GovernanceAction",
        "Readiness",
        "CandidateChildCount",
        "TopCandidateVersionId",
        "ParamLabCandidateId",
        "ParamLabGrade",
        "ParamLabScore",
        "ParameterSummary",
    ])
    print(f"Wrote {output}")
    print(f"Wrote {ledger}")
    print(
        f"Routes: {registry['summary']['routeCount']} | live versions: "
        f"{registry['summary']['liveVersionCount']} | candidate children: "
        f"{registry['summary']['candidateChildVersionCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
