from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_loader import collect_observations, load_runtime_evidence
from .dynamic_sltp import build_dynamic_sltp_plan
from .entry_gate import evaluate_entry_gate
from .route_score import best_route_for_symbol, score_routes
from .schema import assert_safe_payload, safety_payload, thresholds_from_env, utc_now_iso

def _output_dir(runtime_dir: Path) -> Path:
    path = runtime_dir / "adaptive"
    path.mkdir(parents=True, exist_ok=True)
    return path

def build_adaptive_policy(
    runtime_dir: str | Path = "runtime",
    symbols: list[str] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds_from_env()
    evidence = load_runtime_evidence(runtime_dir, max_records=thresholds.max_plan_records)
    observations = collect_observations(evidence)
    scored_routes = score_routes(observations, thresholds)

    selected_symbols = symbols or evidence.symbols or sorted({route["symbol"] for route in scored_routes})
    gates: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for symbol in selected_symbols:
        route = best_route_for_symbol(scored_routes, symbol)
        gates.append(evaluate_entry_gate(evidence, route, thresholds, symbol=symbol))
        direction = route.get("direction") if route else None
        plans.append(build_dynamic_sltp_plan(route, observations, thresholds, symbol=symbol, direction=direction))

    payload: dict[str, Any] = {
        "schema": "quantgod.adaptive_policy.v1",
        "generatedAt": utc_now_iso(),
        "runtimeDir": str(Path(runtime_dir).expanduser()),
        "symbols": selected_symbols,
        "dataQuality": {
            "runtimeFound": Path(runtime_dir).exists(),
            "snapshotCount": len(evidence.snapshots),
            "dashboardFound": evidence.dashboard is not None,
            "outcomeRows": len(evidence.outcome_rows),
            "closeHistoryRows": len(evidence.close_history_rows),
            "strategyEvalRows": len(evidence.strategy_eval_rows),
            "journalRows": len(evidence.journal_rows),
            "fastlaneQualityFound": evidence.fastlane_quality is not None,
            "fastlaneHeartbeatFresh": bool((evidence.fastlane_quality or {}).get("heartbeatFresh")),
            "observationCount": len(observations),
        },
        "thresholds": thresholds.__dict__,
        "routes": scored_routes,
        "entryGates": gates,
        "dynamicSltpPlans": plans,
        "safety": safety_payload(),
    }
    assert_safe_payload(payload)

    if write:
        out = _output_dir(evidence.runtime_dir)
        (out / "QuantGod_AdaptivePolicy.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "QuantGod_DynamicEntryGate.json").write_text(json.dumps({"schema": payload["schema"], "generatedAt": payload["generatedAt"], "entryGates": gates, "safety": safety_payload()}, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "QuantGod_DynamicSLTPPlan.json").write_text(json.dumps({"schema": payload["schema"], "generatedAt": payload["generatedAt"], "dynamicSltpPlans": plans, "safety": safety_payload()}, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_policy_ledger(out / "QuantGod_AdaptivePolicyLedger.csv", scored_routes, payload["generatedAt"])

    return payload

def _write_policy_ledger(path: Path, routes: list[dict[str, Any]], generated_at: str) -> None:
    import csv

    fields = ["generatedAt", "symbol", "strategy", "direction", "regime", "samples", "winRate", "avgScoreR", "state", "riskMultiplier", "reason"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for route in routes:
            writer.writerow({field: generated_at if field == "generatedAt" else route.get(field, "") for field in fields})

def load_policy_file(runtime_dir: str | Path = "runtime") -> dict[str, Any] | None:
    path = Path(runtime_dir).expanduser() / "adaptive" / "QuantGod_AdaptivePolicy.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
