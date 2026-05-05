from __future__ import annotations

from dataclasses import dataclass

from .data_loader import DynamicSLTPPlan, ShadowStats
from .schema import ENTRY_BLOCKED, ENTRY_OPPORTUNITY, ENTRY_STANDARD


@dataclass
class ExitTuning:
    exit_mode: str
    breakeven_delay_r: float
    trail_start_r: float
    time_stop_bars: int
    reason: str


def tune_exit(entry_mode: str, sltp: DynamicSLTPPlan, shadow: ShadowStats) -> ExitTuning:
    if entry_mode == ENTRY_BLOCKED:
        return ExitTuning("NO_POSITION", 0.0, 0.0, 0, "阻断状态，不生成出场参数")

    if shadow.samples >= 5 and shadow.avg_r > 0.15:
        return ExitTuning(
            "LET_PROFIT_RUN",
            0.9 if entry_mode == ENTRY_STANDARD else 1.0,
            1.5 if entry_mode == ENTRY_STANDARD else 1.7,
            6 if entry_mode == ENTRY_STANDARD else 4,
            "近期影子样本为正，保本与移动止损延后半档，减少过早出场",
        )

    if entry_mode == ENTRY_OPPORTUNITY:
        return ExitTuning(
            "PROBE_AND_PROTECT",
            0.75,
            1.25,
            4,
            "机会入场仅小仓试探，较早保护本金",
        )

    return ExitTuning(
        "BALANCED_PROTECTION",
        0.8,
        1.4,
        5,
        "样本优势一般，采用平衡型保护",
    )
