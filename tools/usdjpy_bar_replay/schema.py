from __future__ import annotations

from datetime import datetime, timezone


FOCUS_SYMBOL = "USDJPYc"
SCHEMA_REPORT = "quantgod.usdjpy_bar_replay_report.v1"
SCHEMA_ENTRY = "quantgod.usdjpy_entry_variant_comparison.v1"
SCHEMA_EXIT = "quantgod.usdjpy_exit_variant_comparison.v1"

VARIANT_CURRENT = "current"
VARIANT_RELAXED_ENTRY = "relaxed_entry_v1"
VARIANT_LET_PROFIT_RUN = "let_profit_run_v1"

CONCLUSION_REJECTED = "REJECTED"
CONCLUSION_SHADOW_ONLY = "SHADOW_ONLY"
CONCLUSION_TESTER_ONLY = "TESTER_ONLY"
CONCLUSION_LIVE_CONFIG_ELIGIBLE = "LIVE_CONFIG_PROPOSAL_ELIGIBLE"

POSTERIOR_WINDOWS = ("15m", "30m", "60m", "120m")

READ_ONLY_SAFETY = {
    "focusOnly": True,
    "focusSymbol": FOCUS_SYMBOL,
    "causalReplay": True,
    "posteriorMayAffectTrigger": False,
    "posteriorUsedForScoringOnly": True,
    "readOnlyDataPlane": True,
    "advisoryOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "livePresetMutationAllowed": False,
    "autoApplyAllowed": False,
    "telegramCommandExecutionAllowed": False,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

