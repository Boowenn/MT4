from __future__ import annotations

from typing import Any, Dict

from .stage_machine import STAGE_PAUSED, STAGE_ROLLBACK


def demotion_from_rollback(rollback: Dict[str, Any]) -> Dict[str, Any]:
    blockers = rollback.get("hardBlockers") if isinstance(rollback.get("hardBlockers"), list) else []
    if not rollback.get("ok") and blockers:
        return {
            "stage": STAGE_ROLLBACK,
            "stageZh": "自动回滚",
            "reasonZh": "；".join(str(item) for item in blockers[:3]),
            "pauseLiveForDay": True,
        }
    if not rollback.get("ok"):
        return {
            "stage": STAGE_PAUSED,
            "stageZh": "暂停",
            "reasonZh": "硬风控状态未通过，但没有结构化原因。",
            "pauseLiveForDay": True,
        }
    return {"stage": "", "stageZh": "", "reasonZh": "", "pauseLiveForDay": False}

