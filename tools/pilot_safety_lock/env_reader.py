from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Optional

ENV_FILES = [".env.pilot.local", ".env.telegram.local", ".env.ai.local", ".env.deepseek.local"]


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env(repo_root: Path | None = None, extra_files: Optional[Iterable[str]] = None) -> Dict[str, str]:
    root = repo_root or Path.cwd()
    merged: Dict[str, str] = {}
    files = list(ENV_FILES)
    if extra_files:
        files.extend(extra_files)
    for name in files:
        merged.update(parse_env_file(root / name))
    for key, value in os.environ.items():
        if key.startswith("QG_"):
            merged[key] = value
    return merged


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def as_float(value: object, default: float) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def as_int(value: object, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default
