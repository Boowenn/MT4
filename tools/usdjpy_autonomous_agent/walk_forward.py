from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from tools.usdjpy_walk_forward.selector import build_parameter_selection, build_walk_forward_report
except ModuleNotFoundError:  # pragma: no cover
    from usdjpy_walk_forward.selector import build_parameter_selection, build_walk_forward_report


def build_autonomous_walk_forward(runtime_dir: Path, *, write: bool = False) -> Dict[str, Any]:
    """Build the train/validation/forward evidence consumed by the autonomous gate."""
    report = build_walk_forward_report(runtime_dir, write=write)
    selection = build_parameter_selection(runtime_dir, write=write)
    return {
        "ok": True,
        "report": report,
        "selection": selection,
        "causalReplayRequired": True,
        "posteriorUsedForScoringOnly": True,
        "requiresAutonomousGovernance": True,
    }
