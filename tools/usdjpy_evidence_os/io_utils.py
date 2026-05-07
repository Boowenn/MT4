from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl_unique(path: Path, rows: Iterable[Dict[str, Any]], key: str) -> int:
    existing = {str(row.get(key)) for row in read_jsonl_tail(path, 2000) if row.get(key)}
    to_write: List[Dict[str, Any]] = []
    for row in rows:
        value = str(row.get(key) or "")
        if not value or value in existing:
            continue
        existing.add(value)
        to_write.append(row)
    append_jsonl(path, to_write)
    return len(to_write)


def read_jsonl_tail(path: Path, limit: int = 200) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
        except Exception:
            continue
    return rows
