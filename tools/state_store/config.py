"""Configuration helpers for the QuantGod local SQLite state store."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Iterable, List

from .safety import safety_payload

DEFAULT_DB_RELATIVE_PATH = Path("runtime") / "quantgod_state.sqlite"


@dataclass(frozen=True)
class StateStoreConfig:
    repo_root: Path
    db_path: Path
    runtime_dir: Path
    dashboard_dir: Path
    docs_contract_path: Path | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "repoRoot": str(self.repo_root),
            "dbPath": str(self.db_path),
            "runtimeDir": str(self.runtime_dir),
            "dashboardDir": str(self.dashboard_dir),
            "docsContractPath": str(self.docs_contract_path) if self.docs_contract_path else None,
            "safety": safety_payload(),
        }


def repo_root_from_tools_file() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve(root: Path, value: str | os.PathLike[str] | None, fallback: Path) -> Path:
    if value is None or str(value).strip() == "":
        return fallback.resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def discover_docs_contract(repo_root: Path) -> Path | None:
    """Find the docs API contract from backend or a sibling QuantGodDocs checkout."""

    candidates = [
        repo_root / "docs" / "contracts" / "api-contract.json",
        repo_root.parent / "QuantGodDocs" / "docs" / "contracts" / "api-contract.json",
        repo_root.parent / "docs" / "docs" / "contracts" / "api-contract.json",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def build_config(
    *,
    repo_root: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    runtime_dir: str | os.PathLike[str] | None = None,
    dashboard_dir: str | os.PathLike[str] | None = None,
) -> StateStoreConfig:
    root = Path(repo_root).expanduser().resolve() if repo_root else repo_root_from_tools_file()
    env_db = os.environ.get("QG_STATE_DB")
    env_runtime = os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR")
    default_db = root / DEFAULT_DB_RELATIVE_PATH
    default_runtime = root / "runtime"
    default_dashboard = root / "Dashboard"
    return StateStoreConfig(
        repo_root=root,
        db_path=_resolve(root, str(db_path) if db_path else env_db, default_db),
        runtime_dir=_resolve(root, str(runtime_dir) if runtime_dir else env_runtime, default_runtime),
        dashboard_dir=_resolve(root, str(dashboard_dir) if dashboard_dir else None, default_dashboard),
        docs_contract_path=discover_docs_contract(root),
    )


def unique_existing_dirs(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        result.append(resolved)
    return result
