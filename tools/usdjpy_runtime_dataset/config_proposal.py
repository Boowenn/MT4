from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from tools.usdjpy_strategy_lab.data_loader import _write_json, first_json
except ModuleNotFoundError:  # pragma: no cover - CLI entrypoint runs from tools/
    from usdjpy_strategy_lab.data_loader import _write_json, first_json

from .param_tuner import build_param_tuning_report
from .schema import FOCUS_SYMBOL, READ_ONLY_SAFETY, SCHEMA_PROPOSAL, utc_now_iso


def build_live_config_proposal(runtime_dir: Path, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    tuning = first_json(runtime_dir, "QuantGod_USDJPYParamTuningReport.json") or build_param_tuning_report(runtime_dir, write=False)
    candidates = tuning.get("candidates") if isinstance(tuning.get("candidates"), list) else []
    actionable = [item for item in candidates if item.get("param") != "dataCollection"]
    generated = utc_now_iso()
    proposal_id = f"USDJPY-RSI-LONG-{generated.replace('-', '').replace(':', '')[:15]}"
    payload = {
        "ok": True,
        "schema": SCHEMA_PROPOSAL,
        "generatedAtIso": generated,
        "proposalId": proposal_id,
        "symbol": FOCUS_SYMBOL,
        "status": "PROPOSAL_READY_FOR_REVIEW" if actionable else "NO_CONFIG_CHANGE_REQUIRED",
        "statusZh": "已生成待人工复核的实盘参数提案" if actionable else "暂无足够证据修改实盘参数",
        "changeCount": len(actionable),
        "changes": [
            {
                "param": item.get("param"),
                "from": item.get("current"),
                "to": item.get("proposed"),
                "reason": item.get("reason"),
                "evidence": item.get("evidence"),
            }
            for item in actionable
        ],
        "autoApplyAllowed": False,
        "requiresManualReview": True,
        "requiresReplayEvidence": True,
        "requiresShadowValidation": True,
        "safety": READ_ONLY_SAFETY,
    }
    if write:
        _write_json(runtime_dir / "adaptive" / "QuantGod_USDJPYLiveConfigProposal.json", payload)
    return payload
