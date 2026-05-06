from __future__ import annotations

from typing import Any, Dict

from .cent_account_rules import cent_account_config
from .stage_machine import STAGE_MICRO_LIVE, STAGE_PAPER_LIVE_SIM, STAGE_TESTER_ONLY


def cent_accelerated_stage(base_stage: str, *, sample_count: int, net_r_delta: float) -> Dict[str, Any]:
    cfg = cent_account_config()
    if not cfg.get("centFastPromotion"):
        return {"stage": base_stage, "accelerated": False, "reasonZh": "未启用美分账户快速晋级。"}
    if base_stage == STAGE_PAPER_LIVE_SIM and sample_count >= int(cfg.get("microLiveMinSamples") or 10) and net_r_delta > 0:
        return {
            "stage": STAGE_MICRO_LIVE,
            "accelerated": True,
            "reasonZh": "美分账户允许从稳定 paper live 干跑快速进入极小仓 MICRO_LIVE。",
        }
    if base_stage == STAGE_TESTER_ONLY and sample_count >= int(cfg.get("testerOnlyMinSamples") or 20) and net_r_delta > 0:
        return {
            "stage": STAGE_PAPER_LIVE_SIM,
            "accelerated": True,
            "reasonZh": "美分账户允许把稳定 tester-only 候选推进到实盘行情干跑。",
        }
    return {"stage": base_stage, "accelerated": False, "reasonZh": "未达到美分账户快速晋级门槛。"}
