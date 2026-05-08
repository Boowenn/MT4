from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .schema import RUN_LIMIT_FILE, ga_dir, utc_now_iso


def min_interval_seconds() -> int:
    try:
        return max(0, int(os.environ.get("QG_GA_MIN_RUN_INTERVAL_SECONDS", "0")))
    except Exception:
        return 0


def check_run_allowed(runtime_dir: Path, force: bool = False) -> Dict[str, Any]:
    interval = min_interval_seconds()
    last = _load(runtime_dir)
    last_run_at = str(last.get("lastRunAt") or "")
    remaining = 0
    if interval > 0 and last_run_at and not force:
        try:
            last_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            remaining = max(0, int(interval - elapsed))
        except Exception:
            remaining = 0
    allowed = force or remaining <= 0
    return {
        "schema": "quantgod.ga.run_limiter.v1",
        "allowed": allowed,
        "minIntervalSeconds": interval,
        "lastRunAt": last_run_at,
        "remainingSeconds": remaining,
        "reasonZh": "允许运行 GA generation" if allowed else f"GA 运行频率限制中，约 {remaining} 秒后可再次运行",
    }


def record_run(runtime_dir: Path, generation_id: str) -> Dict[str, Any]:
    payload = {
        "schema": "quantgod.ga.run_limiter.v1",
        "lastRunAt": utc_now_iso(),
        "lastGenerationId": generation_id,
        "minIntervalSeconds": min_interval_seconds(),
    }
    path = ga_dir(runtime_dir) / RUN_LIMIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _load(runtime_dir: Path) -> Dict[str, Any]:
    path = ga_dir(runtime_dir) / RUN_LIMIT_FILE
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}
