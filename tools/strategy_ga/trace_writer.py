from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from .schema import (
    BLOCKER_FILE,
    CANDIDATE_RUNS_FILE,
    ELITE_FILE,
    EVOLUTION_PATH_FILE,
    GENERATION_LEDGER_FILE,
    LATEST_GENERATION_FILE,
    STATUS_FILE,
    ga_dir,
)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_trace(runtime_dir: Path, payload: Dict[str, Any]) -> None:
    root = ga_dir(runtime_dir)
    write_json(root / STATUS_FILE, payload["status"])
    write_json(root / LATEST_GENERATION_FILE, payload["generation"])
    write_json(root / ELITE_FILE, payload["elites"])
    write_json(root / BLOCKER_FILE, payload["blockers"])
    write_json(root / EVOLUTION_PATH_FILE, payload["evolutionPath"])
    append_jsonl(root / GENERATION_LEDGER_FILE, [payload["generation"]])
    append_jsonl(root / CANDIDATE_RUNS_FILE, payload["candidates"])

