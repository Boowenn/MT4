from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .case_memory import build_case_memory
from .execution_feedback import build_execution_feedback
from .io_utils import utc_now_iso, write_json
from .parity import build_parity_report
from .schema import AGENT_VERSION, FOCUS_SYMBOL, SAFETY_BOUNDARY, os_status_path
from .telegram_gateway import build_notification_event, dispatch_event
from .telegram_text import evidence_os_to_chinese_text


def build_evidence_os(runtime_dir: Path, write: bool = True, send: bool = False) -> Dict[str, Any]:
    parity = build_parity_report(runtime_dir, write=write)
    feedback = build_execution_feedback(runtime_dir, write=write)
    cases = build_case_memory(runtime_dir, write=write)
    report: Dict[str, Any] = {
        "ok": True,
        "schema": "quantgod.usdjpy_evidence_os_status.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "parity": parity,
        "executionFeedback": feedback,
        "caseMemory": cases,
        "nextActionZh": "把 Strategy JSON 回测、parity、执行反馈和 Case Memory 送入下一代 GA 评分。",
        "singleSourceOfTruth": "USDJPY_STRATEGY_JSON_BACKTEST_PARITY_FEEDBACK_CASE_MEMORY",
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        write_json(os_status_path(runtime_dir), report)
    if send:
        event = build_notification_event(
            "usdjpy_evidence_os",
            "USDJPY_EVIDENCE_OS_STATUS",
            "INFO",
            evidence_os_to_chinese_text(report),
            {"statusPath": str(os_status_path(runtime_dir))},
        )
        report["telegramGateway"] = dispatch_event(runtime_dir, event, send=True)
    return report


def status(runtime_dir: Path) -> Dict[str, Any]:
    from .io_utils import load_json

    payload = load_json(os_status_path(runtime_dir))
    if payload:
        return {"ok": True, **payload}
    return {
        "ok": True,
        "schema": "quantgod.usdjpy_evidence_os_status.v1",
        "agentVersion": AGENT_VERSION,
        "symbol": FOCUS_SYMBOL,
        "status": "WAITING_FIRST_RUN",
        "reasonZh": "等待生成 Strategy JSON 回测、parity、执行反馈和 Case Memory 证据。",
        "safety": dict(SAFETY_BOUNDARY),
    }

