from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_report(runtime_dir: Path, report: Dict[str, Any]) -> Path:
    out_dir = runtime_dir / "safety"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "QuantGod_PilotSafetyLock.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_report(runtime_dir: Path) -> Dict[str, Any] | None:
    path = runtime_dir / "safety" / "QuantGod_PilotSafetyLock.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None
