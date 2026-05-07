from __future__ import annotations

from typing import Any, Dict


def evidence_os_to_chinese_text(report: Dict[str, Any]) -> str:
    parity = report.get("parity") if isinstance(report.get("parity"), dict) else {}
    feedback = report.get("executionFeedback") if isinstance(report.get("executionFeedback"), dict) else {}
    cases = report.get("caseMemory") if isinstance(report.get("caseMemory"), dict) else {}
    metrics = feedback.get("metrics") if isinstance(feedback.get("metrics"), dict) else {}
    return "\n".join(
        [
            "【QuantGod USDJPY 证据 OS 报告】",
            "",
            f"Parity：{parity.get('status', 'WAITING')}",
            f"执行反馈：样本 {feedback.get('sampleCount', 0)}，拒单 {metrics.get('rejectCount', 0)}，净 R {metrics.get('netR', 0)}",
            f"Case Memory：{cases.get('caseCount', 0)} 个案例，{cases.get('queuedForGA', 0)} 个进入 GA 线索",
            "",
            "安全边界：只读审计，不下单、不平仓、不撤单、不修改 live preset；Telegram 只 push，不接交易命令。",
        ]
    )

