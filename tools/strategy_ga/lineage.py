from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .schema import AGENT_VERSION, LINEAGE_FILE, SAFETY_BOUNDARY, ga_dir, utc_now_iso


def build_lineage(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = []
    edges = []
    for row in candidates:
        seed = row.get("strategyJson") if isinstance(row.get("strategyJson"), dict) else {}
        seed_id = str(row.get("seedId") or seed.get("seedId") or "")
        if not seed_id:
            continue
        nodes.append({
            "seedId": seed_id,
            "strategyId": row.get("strategyId"),
            "source": row.get("source"),
            "fitness": row.get("fitness"),
            "rank": row.get("rank"),
            "status": row.get("status"),
            "promotionStage": row.get("promotionStage"),
            "blockerCode": row.get("blockerCode"),
            "caseId": seed.get("caseId"),
            "mutationHint": seed.get("mutationHint"),
        })
        parent = seed.get("parentSeedId")
        if parent:
            edges.append({"from": parent, "to": seed_id, "type": "MUTATION"})
        for parent_id in seed.get("parentSeedIds", []) if isinstance(seed.get("parentSeedIds"), list) else []:
            if parent_id:
                edges.append({"from": parent_id, "to": seed_id, "type": "CROSSOVER"})
        case_id = seed.get("caseId")
        if case_id:
            edges.append({"from": case_id, "to": seed_id, "type": "CASE_MEMORY"})
    return {
        "schema": "quantgod.ga.lineage.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "nodes": nodes,
        "edges": edges,
        "safety": dict(SAFETY_BOUNDARY),
    }


def write_lineage(runtime_dir: Path, lineage: Dict[str, Any]) -> None:
    path = ga_dir(runtime_dir) / LINEAGE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")


def read_lineage(runtime_dir: Path) -> Dict[str, Any]:
    path = ga_dir(runtime_dir) / LINEAGE_FILE
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {
        "schema": "quantgod.ga.lineage.v1",
        "agentVersion": AGENT_VERSION,
        "nodes": [],
        "edges": [],
        "safety": dict(SAFETY_BOUNDARY),
    }
