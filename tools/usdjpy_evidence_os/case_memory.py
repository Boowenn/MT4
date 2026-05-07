from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .io_utils import append_jsonl, load_json, utc_now_iso, write_json
from .schema import AGENT_VERSION, FOCUS_SYMBOL, SAFETY_BOUNDARY, case_memory_path, case_summary_path


def build_case_memory(runtime_dir: Path, write: bool = True) -> Dict[str, Any]:
    cases = _cases_from_replay(runtime_dir) + _cases_from_execution(runtime_dir)
    summary = {
        "ok": True,
        "schema": "quantgod.case_memory_summary.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "caseCount": len(cases),
        "cases": cases[-50:],
        "queuedForGA": sum(1 for item in cases if item.get("status") == "QUEUED_FOR_GA"),
        "reasonZh": "Case Memory 把错失机会、早出场、执行偏差和过拟合风险转成下一轮 Strategy JSON/GA 种子线索。",
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        if cases:
            append_jsonl(case_memory_path(runtime_dir), cases)
        write_json(case_summary_path(runtime_dir), summary)
    return summary


def _cases_from_replay(runtime_dir: Path) -> List[Dict[str, Any]]:
    replay = load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYBarReplayReport.json")
    cases: List[Dict[str, Any]] = []
    entry_variants = ((replay.get("entryComparison") or {}).get("variants") or []) if isinstance(replay.get("entryComparison"), dict) else []
    for variant in entry_variants:
        metrics = variant.get("metrics") if isinstance(variant, dict) and isinstance(variant.get("metrics"), dict) else variant
        if not isinstance(metrics, dict):
            continue
        if float(metrics.get("entryCountDelta") or 0) > 0:
            cases.append(_case("MISSED_BIG_MOVE", "RSI crossback 或战术确认过严，产生错失机会", metrics, "relax_rsi_crossback"))
    exit_variants = ((replay.get("exitComparison") or {}).get("variants") or []) if isinstance(replay.get("exitComparison"), dict) else []
    for variant in exit_variants:
        metrics = variant.get("metrics") if isinstance(variant, dict) and isinstance(variant.get("metrics"), dict) else variant
        if isinstance(metrics, dict) and float(metrics.get("profitCaptureRatio") or 0) > 0.35:
            cases.append(_case("EARLY_EXIT", "出场可能过早，盈利捕获率有改善空间", metrics, "let_profit_run"))
    return cases


def _cases_from_execution(runtime_dir: Path) -> List[Dict[str, Any]]:
    feedback = load_json(runtime_dir / "evidence_os" / "QuantGod_LiveExecutionQualityReport.json")
    metrics = feedback.get("metrics") if isinstance(feedback.get("metrics"), dict) else {}
    cases: List[Dict[str, Any]] = []
    if int(metrics.get("rejectCount") or 0) > 0:
        cases.append(_case("POLICY_MISMATCH", "EA 执行或券商拒单需要进入执行反馈复盘", metrics, "inspect_execution_quality"))
    if float(metrics.get("avgAbsSlippagePips") or 0) > 0.8:
        cases.append(_case("EXECUTION_SLIPPAGE", "平均滑点偏高，需要限制触发窗口或降仓", metrics, "tighten_execution_filter"))
    return cases


def _case(case_type: str, root_cause: str, evidence: Dict[str, Any], mutation_hint: str) -> Dict[str, Any]:
    return {
        "schema": "quantgod.case_memory.v1",
        "caseId": f"USDJPY-{case_type}-{utc_now_iso()}",
        "createdAt": utc_now_iso(),
        "type": case_type,
        "symbol": FOCUS_SYMBOL,
        "strategy": "RSI_Reversal",
        "rootCause": root_cause,
        "evidence": evidence,
        "proposedAction": {
            "generateStrategyJsonCandidate": True,
            "mutationHint": mutation_hint,
        },
        "status": "QUEUED_FOR_GA",
        "safety": dict(SAFETY_BOUNDARY),
    }

