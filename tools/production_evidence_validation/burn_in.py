from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .io_utils import ensure_dir, read_json, read_jsonl, write_json
from .report import build_report, write_reports
from .schema import (
    OUTPUT_DIR,
    PRODUCTION_BURN_IN_LEDGER,
    PRODUCTION_BURN_IN_REPORT,
    SAFETY,
)


LEDGER_FIELDS = [
    "generatedAt",
    "status",
    "productionEvidenceStatus",
    "historyStatus",
    "parityStatus",
    "feedbackStatus",
    "feedbackSourceGrade",
    "gaStatus",
    "caseMemoryStatus",
    "agentOpsStatus",
    "telegramStatus",
    "blockerCount",
    "watchCount",
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _file_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _age_seconds(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds())


def _status(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    if text in {"FAIL", "FAILED", "BLOCKED", "BLOCKED_BY_PARITY", "DEGRADED"}:
        return "FAIL"
    if text in {"WARN", "WARNING", "UNKNOWN", "MISSING", "STALE"}:
        return "WARN"
    if text in {"WATCH", "SHADOW_RESEARCH_ONLY"}:
        return "WATCH"
    if text in {"PASS", "PASSED", "OK", "READY", "COMPLETED", "COMPLETED_BY_AGENT"}:
        return "PASS"
    return text


def _agent_ops_section(runtime_dir: Path, now: datetime, max_stale_minutes: int) -> dict[str, Any]:
    path = runtime_dir / "agent" / "QuantGod_AgentOpsHealth.json"
    payload = read_json(path, {}) or {}
    generated = _parse_time(payload.get("generatedAtIso") or payload.get("generatedAt")) or _file_mtime(path)
    age = _age_seconds(generated, now)
    blockers = payload.get("blockers") or []
    stale = age is None or age > max_stale_minutes * 60
    status = "WARN" if blockers or stale else "PASS"
    return {
        "status": status,
        "path": str(path) if path.exists() else "",
        "generatedAt": _iso(generated) if generated else "",
        "ageSeconds": round(age, 3) if age is not None else None,
        "maxStaleMinutes": max_stale_minutes,
        "blockerCount": len(blockers) if isinstance(blockers, list) else 0,
        "reasonZh": "Agent ops health 已过期，需要确认 launchd/loop 仍在运行。" if stale else "Agent ops health 新鲜。",
    }


def _case_memory_section(runtime_dir: Path, now: datetime) -> dict[str, Any]:
    path = runtime_dir / "evidence_os" / "QuantGod_CaseMemorySummary.json"
    payload = read_json(path, {}) or {}
    generated = _parse_time(payload.get("createdAt") or payload.get("generatedAt")) or _file_mtime(path)
    age = _age_seconds(generated, now)
    case_count = int(payload.get("caseCount") or 0)
    status = "PASS" if case_count > 0 else "WATCH"
    if not path.exists():
        status = "WARN"
    return {
        "status": status,
        "path": str(path) if path.exists() else "",
        "generatedAt": _iso(generated) if generated else "",
        "ageSeconds": round(age, 3) if age is not None else None,
        "caseCount": case_count,
        "queuedForGA": int(payload.get("queuedForGA") or 0),
        "mutationHints": payload.get("mutationHints") or [],
        "reasonZh": "Case Memory 已产生复盘种子。" if case_count else "Case Memory 仍需更多异常/错失样本。",
    }


def _telegram_section(runtime_dir: Path) -> dict[str, Any]:
    queue = runtime_dir / "notifications" / "QuantGod_NotificationEventQueue.jsonl"
    ledger = runtime_dir / "notifications" / "QuantGod_TelegramGatewayLedger.jsonl"
    queue_rows = read_jsonl(queue, 2000)
    ledger_rows = read_jsonl(ledger, 2000)
    queue_count = len(queue_rows)
    delivered_count = len(ledger_rows)
    if queue_count > 50:
        status = "WARN"
        reason = "Telegram 队列积压偏高。"
    elif delivered_count > 0:
        status = "PASS"
        reason = "Telegram ledger 有投递记录，队列未明显积压。"
    else:
        status = "WATCH"
        reason = "暂无 Telegram 投递 ledger，需要继续观察。"
    return {
        "status": status,
        "queuePath": str(queue) if queue.exists() else "",
        "ledgerPath": str(ledger) if ledger.exists() else "",
        "queueCount": queue_count,
        "ledgerCount": delivered_count,
        "reasonZh": reason,
    }


def _ledger_path(runtime_dir: Path) -> Path:
    return runtime_dir / OUTPUT_DIR / PRODUCTION_BURN_IN_LEDGER


def _read_ledger(runtime_dir: Path) -> list[dict[str, str]]:
    path = _ledger_path(runtime_dir)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _append_ledger(runtime_dir: Path, row: dict[str, Any]) -> None:
    path = _ledger_path(runtime_dir)
    ensure_dir(path.parent)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in LEDGER_FIELDS})


def _window_summary(
    runtime_dir: Path,
    now: datetime,
    window_hours: int,
    sample_interval_minutes: int,
) -> dict[str, Any]:
    rows = _read_ledger(runtime_dir)
    cutoff = now - timedelta(hours=max(1, window_hours))
    window_rows = [row for row in rows if (_parse_time(row.get("generatedAt")) or now) >= cutoff]
    times = [_parse_time(row.get("generatedAt")) for row in window_rows]
    clean_times = [time for time in times if time is not None]
    observed_hours = 0.0
    if len(clean_times) >= 2:
        observed_hours = (max(clean_times) - min(clean_times)).total_seconds() / 3600
    expected = int(window_hours * 60 / max(1, sample_interval_minutes)) + 1
    status_counts: dict[str, int] = {}
    for row in window_rows:
        status = str(row.get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "ledgerPath": str(_ledger_path(runtime_dir)),
        "targetHours": int(window_hours),
        "sampleIntervalMinutes": int(sample_interval_minutes),
        "expectedSamples": expected,
        "observedSamples": len(window_rows),
        "observedHours": round(observed_hours, 4),
        "statusCounts": status_counts,
        "complete": len(window_rows) >= expected and observed_hours >= window_hours * 0.95,
    }


def _overall_status(sections: list[dict[str, Any]], window: dict[str, Any]) -> str:
    states = {_status(section.get("status")) for section in sections}
    if "FAIL" in states:
        return "FAIL"
    if "WARN" in states:
        return "WARN"
    if not window.get("complete"):
        return "WATCH"
    if "WATCH" in states:
        return "WATCH"
    return "PASS"


def _next_actions(sections: dict[str, dict[str, Any]], window: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if not window.get("complete"):
        actions.append("继续按 5 分钟节奏累计 burn-in ledger，直到覆盖完整 72 小时窗口。")
    if sections["agentOps"].get("status") != "PASS":
        actions.append("确认 Agent loop / launchd health 是否持续刷新。")
    attribution = sections["executionFeedback"].get("sourceAttribution") or {}
    if attribution.get("liveRealFillCount", 0) <= 0:
        actions.append("补齐 live_real_fill 来源分层，避免 shadow/backfilled 样本高估实盘质量。")
    if sections["caseMemory"].get("status") != "PASS":
        actions.append("继续收集 Case Memory 输入，验证复盘到 GA seed 的闭环。")
    if not actions:
        actions.append("burn-in 证据闭环可进入持续观察。")
    return actions


def build_burn_in_report(
    runtime_dir: Path,
    *,
    write: bool = False,
    window_hours: int = 72,
    sample_interval_minutes: int = 5,
    max_stale_minutes: int = 15,
) -> dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    now = _now()
    production = build_report(runtime_dir)
    if write:
        write_reports(runtime_dir, production)

    feedback = production.get("liveExecutionFeedbackCoverage") or {}
    sections = {
        "productionEvidence": {"status": production.get("status"), "summaryZh": production.get("summaryZh")},
        "historyProduction": production.get("historyProduction") or {},
        "strategyFamilyParity": production.get("strategyFamilyParity") or {},
        "executionFeedback": feedback,
        "gaMultiGenerationStability": production.get("gaMultiGenerationStability") or {},
        "caseMemory": _case_memory_section(runtime_dir, now),
        "agentOps": _agent_ops_section(runtime_dir, now, max_stale_minutes),
        "telegramDelivery": _telegram_section(runtime_dir),
    }
    provisional_window = _window_summary(runtime_dir, now, window_hours, sample_interval_minutes)
    status = _overall_status(list(sections.values()), provisional_window)
    blockers = production.get("blockersZh") or []
    watch_count = sum(1 for section in sections.values() if _status(section.get("status")) == "WATCH")
    row = {
        "generatedAt": _iso(now),
        "status": status,
        "productionEvidenceStatus": production.get("status"),
        "historyStatus": sections["historyProduction"].get("status"),
        "parityStatus": sections["strategyFamilyParity"].get("status"),
        "feedbackStatus": feedback.get("status"),
        "feedbackSourceGrade": (feedback.get("sourceAttribution") or {}).get("grade"),
        "gaStatus": sections["gaMultiGenerationStability"].get("status"),
        "caseMemoryStatus": sections["caseMemory"].get("status"),
        "agentOpsStatus": sections["agentOps"].get("status"),
        "telegramStatus": sections["telegramDelivery"].get("status"),
        "blockerCount": len(blockers),
        "watchCount": watch_count,
    }
    if write:
        _append_ledger(runtime_dir, row)
    window = _window_summary(runtime_dir, now, window_hours, sample_interval_minutes)
    status = _overall_status(list(sections.values()), window)
    report = {
        "schema": "quantgod.production_burn_in_report.v1",
        "generatedAt": _iso(now),
        "status": status,
        "summaryZh": "P4-9 burn-in 仍在观察窗口内" if status == "WATCH" else "P4-9 burn-in 需要处理 WARN/FAIL",
        "runtimeDir": str(runtime_dir),
        "window": window,
        "sections": sections,
        "blockersZh": blockers,
        "nextActionsZh": _next_actions(sections, window),
        "safety": SAFETY,
    }
    if status == "PASS":
        report["summaryZh"] = "P4-9 burn-in 观察窗口已闭合且证据稳定"
    if write:
        write_json(runtime_dir / OUTPUT_DIR / PRODUCTION_BURN_IN_REPORT, report)
    return report


def load_latest_burn_in(runtime_dir: Path) -> dict[str, Any] | None:
    return read_json(Path(runtime_dir) / OUTPUT_DIR / PRODUCTION_BURN_IN_REPORT, None)
