from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from tools.usdjpy_strategy_lab.data_loader import first_json
except ModuleNotFoundError:  # pragma: no cover
    from usdjpy_strategy_lab.data_loader import first_json

from .replay_engine import build_bar_replay_report


def load_or_build_report(runtime_dir: Path, refresh: bool = False, write: bool = False) -> Dict[str, Any]:
    if not refresh:
        payload = first_json(runtime_dir, "QuantGod_USDJPYBarReplayReport.json") or {}
        if payload:
            return payload
    return build_bar_replay_report(Path(runtime_dir), write=write)

