from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.strategy_json.fingerprint import strategy_fingerprint
    from tools.strategy_json.normalizer import normalize_strategy_json
    from tools.strategy_json.validator import validate_strategy_json
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.fingerprint import strategy_fingerprint
    from strategy_json.normalizer import normalize_strategy_json
    from strategy_json.validator import validate_strategy_json

from .blocker_explainer import explain_blocker
from .fitness import score_seed
from .population import build_population, elite_count, population_size
from .schema import (
    AGENT_VERSION,
    BLOCKER_FILE,
    ELITE_FILE,
    EVOLUTION_PATH_FILE,
    LATEST_GENERATION_FILE,
    SAFETY_BOUNDARY,
    STATUS_FILE,
    ga_dir,
    utc_now_iso,
)
from .trace_writer import write_trace


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _existing_elites(runtime_dir: Path) -> List[Dict[str, Any]]:
    data = _load_json(ga_dir(runtime_dir) / ELITE_FILE)
    rows = data.get("elites") if isinstance(data.get("elites"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _next_generation_number(runtime_dir: Path) -> int:
    latest = _load_json(ga_dir(runtime_dir) / LATEST_GENERATION_FILE)
    try:
        return int(latest.get("generation", 0)) + 1
    except Exception:
        return 1


def _candidate_status(rank: int, blocker: str | None, fitness: float) -> str:
    if blocker == "SAFETY_REJECTED":
        return "SAFETY_REJECTED"
    if blocker == "INSUFFICIENT_SAMPLES":
        return "NEEDS_MORE_DATA"
    if blocker:
        return "REJECTED"
    if rank <= elite_count():
        return "ELITE_SELECTED"
    if fitness > 0.5:
        return "PROMOTED_TO_SHADOW"
    return "NEEDS_MORE_DATA"


def _promotion_stage(status: str) -> str:
    if status == "ELITE_SELECTED":
        return "TESTER_ONLY"
    if status == "PROMOTED_TO_SHADOW":
        return "FAST_SHADOW"
    if status == "NEEDS_MORE_DATA":
        return "SHADOW"
    return "REJECTED"


def _read_status(runtime_dir: Path) -> Dict[str, Any]:
    status = _load_json(ga_dir(runtime_dir) / STATUS_FILE)
    if status:
        return status
    return {
        "schema": "quantgod.ga.status.v1",
        "agentVersion": AGENT_VERSION,
        "status": "WAITING_FIRST_GENERATION",
        "currentGeneration": 0,
        "populationSize": population_size(),
        "bestFitness": 0,
        "bestSeedId": None,
        "completedGenerations": 0,
        "blockedCandidates": 0,
        "eliteCount": 0,
        "nextAction": "运行第一代 Strategy JSON GA 评分",
        "singleSourceOfTruth": "USDJPY_STRATEGY_JSON_GA_TRACE",
        "safety": dict(SAFETY_BOUNDARY),
    }


def build_ga_status(runtime_dir: Path) -> Dict[str, Any]:
    root = ga_dir(runtime_dir)
    return {
        "ok": True,
        "status": _read_status(runtime_dir),
        "generation": _load_json(root / LATEST_GENERATION_FILE),
        "elites": _load_json(root / ELITE_FILE),
        "blockers": _load_json(root / BLOCKER_FILE),
        "evolutionPath": _load_json(root / EVOLUTION_PATH_FILE),
        "safety": dict(SAFETY_BOUNDARY),
    }


def _score_candidates(runtime_dir: Path, generation_number: int, generation_id: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    runs: List[Dict[str, Any]] = []
    for seed in seeds:
        normalized = normalize_strategy_json(seed)
        fingerprint = strategy_fingerprint(normalized)
        validation = validate_strategy_json(normalized)
        blocker = None
        score = {
            "fitness": -99,
            "netR": 0,
            "maxAdverseR": 0,
            "profitCaptureRatio": 0,
            "missedOpportunityReduction": 0,
            "sampleCount": 0,
            "overfitPenalty": 0,
            "evidenceQuality": "LOW",
        }
        if fingerprint in seen:
            blocker = "DUPLICATE_STRATEGY"
        elif not validation.get("valid"):
            blocker = str(validation.get("blockerCode") or "SAFETY_REJECTED")
        else:
            score = score_seed(normalized, runtime_dir)
            blocker = score.get("blockerCode")
        seen.add(fingerprint)
        runs.append({
            "schema": "quantgod.ga.candidate_run.v1",
            "generation": generation_number,
            "generationId": generation_id,
            "seedId": normalized.get("seedId"),
            "strategyId": normalized.get("strategyId"),
            "strategyFamily": normalized.get("strategyFamily"),
            "direction": normalized.get("direction"),
            "source": normalized.get("source", "LLM_SEED"),
            "fingerprint": fingerprint,
            "strategyJson": normalized,
            "validation": validation,
            "fitnessBreakdown": score,
            "fitness": score["fitness"],
            "blockerCode": blocker,
            "blockerZh": explain_blocker(blocker),
            "safety": dict(SAFETY_BOUNDARY),
        })
    ranked = sorted(runs, key=lambda row: float(row.get("fitness", -99)), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
        row["status"] = _candidate_status(index, row.get("blockerCode"), float(row.get("fitness", -99)))
        row["promotionStage"] = _promotion_stage(row["status"])
    return ranked


def run_generation(runtime_dir: Path, write: bool = True) -> Dict[str, Any]:
    generation_number = _next_generation_number(runtime_dir)
    generation_id = f"GA-USDJPY-GEN-{generation_number:04d}"
    seeds = build_population(generation_number, _existing_elites(runtime_dir))
    candidates = _score_candidates(runtime_dir, generation_number, generation_id, seeds)
    elites = [row for row in candidates if row.get("status") == "ELITE_SELECTED"][: elite_count()]
    blocker_counts = Counter(str(row.get("blockerCode") or "PASSED") for row in candidates)
    best = candidates[0] if candidates else {}
    generation = {
        "schema": "quantgod.ga.generation.v1",
        "agentVersion": AGENT_VERSION,
        "generation": generation_number,
        "generationId": generation_id,
        "parentGenerationId": f"GA-USDJPY-GEN-{generation_number - 1:04d}" if generation_number > 1 else None,
        "createdAt": utc_now_iso(),
        "populationSize": len(candidates),
        "eliteCount": len(elites),
        "mutationRate": 0.18,
        "crossoverRate": 0.35,
        "status": "COMPLETED_BY_AGENT",
        "bestFitness": best.get("fitness", 0),
        "bestSeedId": best.get("seedId"),
        "bestStrategy": best.get("strategyId"),
        "avgFitness": round(sum(float(row.get("fitness", 0)) for row in candidates) / max(1, len(candidates)), 4),
        "blockedCount": sum(1 for row in candidates if row.get("blockerCode")),
        "mutationCount": sum(1 for row in candidates if row.get("source") == "MUTATION"),
        "crossoverCount": sum(1 for row in candidates if row.get("source") == "CROSSOVER"),
        "safety": dict(SAFETY_BOUNDARY),
    }
    path = _load_json(ga_dir(runtime_dir) / EVOLUTION_PATH_FILE)
    generations = path.get("generations") if isinstance(path.get("generations"), list) else []
    generations.append({
        "generation": generation_number,
        "generationId": generation_id,
        "bestFitness": best.get("fitness", 0),
        "avgFitness": generation["avgFitness"],
        "bestStrategy": best.get("strategyId"),
        "blockedCount": generation["blockedCount"],
        "eliteCount": generation["eliteCount"],
    })
    evolution_path = {
        "schema": "quantgod.ga.evolution_path.v1",
        "agentVersion": AGENT_VERSION,
        "generations": generations[-50:],
        "safety": dict(SAFETY_BOUNDARY),
    }
    blockers = {
        "schema": "quantgod.ga.blockers.v1",
        "agentVersion": AGENT_VERSION,
        "summary": [{"blockerCode": code, "reasonZh": explain_blocker(code), "count": count} for code, count in blocker_counts.items()],
        "safety": dict(SAFETY_BOUNDARY),
    }
    status = {
        "schema": "quantgod.ga.status.v1",
        "agentVersion": AGENT_VERSION,
        "status": "COMPLETED_BY_AGENT",
        "currentGeneration": generation_number,
        "populationSize": len(candidates),
        "bestFitness": best.get("fitness", 0),
        "bestSeedId": best.get("seedId"),
        "completedGenerations": generation_number,
        "blockedCandidates": generation["blockedCount"],
        "eliteCount": len(elites),
        "nextAction": f"基于 {len(elites)} 个 elite 生成第 {generation_number + 1} 代候选",
        "singleSourceOfTruth": "USDJPY_STRATEGY_JSON_GA_TRACE",
        "safety": dict(SAFETY_BOUNDARY),
    }
    payload = {
        "ok": True,
        "status": status,
        "generation": generation,
        "candidates": candidates,
        "elites": {
            "schema": "quantgod.ga.elites.v1",
            "agentVersion": AGENT_VERSION,
            "elites": elites,
            "safety": dict(SAFETY_BOUNDARY),
        },
        "blockers": blockers,
        "evolutionPath": evolution_path,
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        write_trace(runtime_dir, payload)
    return payload


def read_generations(runtime_dir: Path) -> Dict[str, Any]:
    return _load_json(ga_dir(runtime_dir) / EVOLUTION_PATH_FILE) or {"ok": True, "generations": []}


def read_candidates(runtime_dir: Path) -> Dict[str, Any]:
    latest = _load_json(ga_dir(runtime_dir) / LATEST_GENERATION_FILE)
    candidate_file = ga_dir(runtime_dir) / "QuantGod_GACandidateRuns.jsonl"
    rows: List[Dict[str, Any]] = []
    if candidate_file.exists():
        for line in candidate_file.read_text(encoding="utf-8").splitlines()[-256:]:
            try:
                row = json.loads(line)
                if row.get("generation") == latest.get("generation"):
                    rows.append(row)
            except Exception:
                continue
    return {"ok": True, "candidates": rows, "generation": latest.get("generation"), "safety": dict(SAFETY_BOUNDARY)}
