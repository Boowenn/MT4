#!/usr/bin/env python3
"""Build the QuantGod daily review and safe iteration queue.

The review consumes local QuantGod evidence files only. It may recommend
tester-only work, simulation retunes, and human-reviewed live promotion, but it
never mutates live presets, starts order paths, sends orders, or changes wallet
state.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_DailyReview.json"
LEDGER_NAME = "QuantGod_DailyReviewLedger.csv"
JST = timezone(timedelta(hours=9), "JST")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod daily review JSON.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--max-actions", type=int, default=8)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            text = raw.decode(encoding)
            if text.count("\x00") > max(8, len(text) // 10):
                continue
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = read_text(path)
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_csv(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        existing_header = rows[0] if rows else []
        if existing_header != fieldnames:
            migrated_rows: list[dict[str, Any]] = []
            for values in rows[1:]:
                source_header = fieldnames if len(values) == len(fieldnames) else existing_header
                migrated_rows.append(dict(zip(source_header, values)))
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for existing_row in migrated_rows:
                    writer.writerow({key: existing_row.get(key, "") for key in fieldnames})
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def first(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean(value: Any) -> str:
    return str(value or "").strip()


def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def generated_at(payload: dict[str, Any]) -> datetime | None:
    return parse_iso_datetime(first(payload.get("generatedAtIso"), payload.get("generatedAt"), payload.get("timestamp")))


def tester_window_plan(now: datetime | None = None) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(JST)
    windows_by_weekday = {
        0: [(time(0, 0), time(2, 30)), (time(20, 10), time(23, 30))],
        1: [(time(0, 0), time(2, 30)), (time(20, 10), time(23, 30))],
        2: [(time(0, 0), time(2, 30)), (time(20, 10), time(23, 30))],
        3: [(time(0, 0), time(2, 30)), (time(20, 10), time(23, 30))],
        4: [(time(0, 0), time(2, 30)), (time(20, 10), time(23, 30))],
        5: [(time(0, 0), time(2, 30)), (time(7, 10), time(9, 30)), (time(20, 10), time(23, 30))],
        6: [(time(0, 0), time(2, 30)), (time(8, 0), time(9, 30)), (time(20, 10), time(23, 30))],
    }
    for offset in range(8):
        day = (current + timedelta(days=offset)).date()
        for start_time, end_time in windows_by_weekday[day.weekday()]:
            start = datetime.combine(day, start_time, tzinfo=JST)
            end = datetime.combine(day, end_time, tzinfo=JST)
            if current <= end:
                return {
                    "nowJstIso": current.isoformat(),
                    "openNow": start <= current <= end,
                    "dueToday": offset == 0,
                    "nextWindowStartJstIso": start.isoformat(),
                    "nextWindowEndJstIso": end.isoformat(),
                    "nextWindowLabel": f"{start:%Y-%m-%d %H:%M}-{end:%H:%M} JST",
                    "windowRule": "Daily closeout 00:00-02:30 JST, daily 20:10-23:30 JST, Sat 07:10-09:30 JST, Sun 08:00-09:30 JST",
                }
    return {"nowJstIso": current.isoformat(), "openNow": False, "dueToday": False}


def date_key(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    return text[:10].replace(".", "-").replace("/", "-")


def latest_date(rows: list[dict[str, Any]], *fields: str) -> str:
    keys = []
    for row in rows:
        for field in fields:
            key = date_key(row.get(field))
            if key:
                keys.append(key)
                break
    return sorted(keys).pop() if keys else ""


def rows_on_date(rows: list[dict[str, Any]], target: str, *fields: str) -> list[dict[str, Any]]:
    if not target:
        return []
    selected = []
    for row in rows:
        if any(date_key(row.get(field)) == target for field in fields):
            selected.append(row)
    return selected


def close_history_summary(rows: list[dict[str, str]], target_day: str | None = None) -> dict[str, Any]:
    day = clean(target_day) or latest_date(rows, "CloseTime", "EventTime", "closeTime")
    day_rows = rows_on_date(rows, day, "CloseTime", "EventTime", "closeTime")
    net = sum(as_float(first(row.get("NetProfit"), row.get("netProfit"), row.get("Profit"))) for row in day_rows)
    by_strategy: dict[str, dict[str, Any]] = {}
    by_strategy_side: dict[str, dict[str, Any]] = {}
    for row in day_rows:
        strategy = clean(first(row.get("Strategy"), row.get("strategy"), default="UNKNOWN")) or "UNKNOWN"
        side = clean(first(row.get("Type"), row.get("Side"), row.get("side"), default="UNKNOWN")).upper() or "UNKNOWN"
        net_profit = as_float(first(row.get("NetProfit"), row.get("netProfit"), row.get("Profit")))
        bucket = by_strategy.setdefault(strategy, {"strategy": strategy, "trades": 0, "netUSC": 0.0})
        bucket["trades"] += 1
        bucket["netUSC"] += net_profit
        side_key = f"{strategy}:{side}"
        side_bucket = by_strategy_side.setdefault(side_key, {"strategy": strategy, "side": side, "trades": 0, "netUSC": 0.0})
        side_bucket["trades"] += 1
        side_bucket["netUSC"] += net_profit
    breakdown = sorted(by_strategy.values(), key=lambda item: abs(item["netUSC"]), reverse=True)
    for item in breakdown:
        item["netUSC"] = round(item["netUSC"], 3)
    side_breakdown = sorted(by_strategy_side.values(), key=lambda item: abs(item["netUSC"]), reverse=True)
    for item in side_breakdown:
        item["netUSC"] = round(item["netUSC"], 3)
    return {
        "date": day,
        "closedTrades": len(day_rows),
        "netUSC": round(net, 3),
        "byStrategy": breakdown,
        "byStrategySide": side_breakdown,
        "lossByStrategySide": [item for item in side_breakdown if item["netUSC"] < 0],
    }


def daily_pnl_resolved_by_policy(daily_pnl: dict[str, Any], governance: dict[str, Any]) -> bool:
    if as_float(daily_pnl.get("netUSC")) >= 0:
        return True
    losses = as_list(daily_pnl.get("lossByStrategySide"))
    if not losses:
        return False
    governance_by_route = {
        clean(row.get("key") or row.get("routeKey") or row.get("strategy")): row
        for row in as_list(governance.get("routeDecisions"))
        if isinstance(row, dict)
    }
    for loss in losses:
        if not isinstance(loss, dict):
            return False
        strategy = clean(loss.get("strategy"))
        side = clean(loss.get("side")).upper()
        if strategy != "RSI_Reversal" or side != "SELL":
            return False
        side_policy = governance_by_route.get("RSI_Reversal", {}).get("sidePolicy")
        if not isinstance(side_policy, dict) or side_policy.get("sellLiveAllowed") is not False:
            return False
    return True


def recovery_by_candidate(run_recovery: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in as_list(run_recovery.get("candidateDrilldown")):
        if not isinstance(row, dict):
            continue
        candidate_id = clean(row.get("candidateId"))
        if candidate_id:
            rows[candidate_id] = row
    return rows


def recovery_blockers(row: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    latest_stop = clean(row.get("latestStopReason"))
    risk_reason = clean(row.get("riskReason"))
    if latest_stop:
        blockers.append(latest_stop)
    if risk_reason and risk_reason not in blockers:
        blockers.append(risk_reason)
    for code in as_list(row.get("terminalExitCodes")):
        text = clean(code)
        if text:
            blockers.append(f"terminal_exit_{text}")
    failures = row.get("failureReasons", {})
    if isinstance(failures, dict):
        for key, value in failures.items():
            if as_int(value) > 0:
                blockers.append(clean(key))
    return list(dict.fromkeys(blockers))


def param_action_queue(
    scheduler: dict[str, Any],
    auto_tester: dict[str, Any],
    max_actions: int,
    run_recovery: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    can_run = bool(auto_tester.get("summary", {}).get("canRunTerminal"))
    blockers = as_list(auto_tester.get("gate", {}).get("blockers")) or as_list(auto_tester.get("summary", {}).get("blockers"))
    blocker_keys = {clean(blocker).lower() for blocker in blockers if clean(blocker)}
    only_waiting_window = bool(blocker_keys) and blocker_keys <= {"outside_strategy_tester_window"}
    window_plan = tester_window_plan()
    recovery_rows = recovery_by_candidate(run_recovery or {})
    for task in as_list(scheduler.get("selectedTasks"))[:max_actions]:
        if not isinstance(task, dict):
            continue
        candidate_id = clean(task.get("candidateId"))
        recovery = recovery_rows.get(candidate_id, {})
        recovery_risk = clean(recovery.get("riskLevel")).lower()
        recovery_reason = clean(recovery.get("riskReason")).lower()
        recovery_stop = clean(recovery.get("latestStopReason")).lower()
        recovery_latest_state = clean(recovery.get("latestState")).lower()
        recovery_retry_ready = recovery_risk in {"yellow", "green"} and recovery_reason == "account_context_synced_retry_ready"
        recovery_terminal_nonzero = (
            not recovery_retry_ready
            and (
                recovery_risk == "red"
                or recovery_stop in {"terminal_nonzero", "terminal_exit_nonzero"}
                or as_int(recovery.get("terminalNonzeroCount")) > 0
            )
        )
        result_status = clean(first(task.get("resultStatus"), task.get("status"), task.get("scheduleAction")))
        guard_class = ""
        status_label = ""
        if result_status.upper() in {"PARSED", "PARSED_AGENT_ARTIFACTS", "SCORED", "DONE"} or (
            recovery_risk == "green" and recovery_latest_state == "parsed"
        ):
            state = "DONE"
        elif recovery_terminal_nonzero:
            state = "NEEDS_CODEX_TRIAGE"
            guard_class = "RUN_RECOVERY_RED"
            status_label = "TERMINAL_EXIT_NONZERO"
        elif can_run:
            state = "READY_TO_RUN_TESTER"
            status_label = "ACCOUNT_CONTEXT_SYNCED_RETRY_READY" if recovery_retry_ready else "READY_TO_RUN_TESTER"
        else:
            state = "WAIT_GUARD"
            if only_waiting_window:
                guard_class = "WAIT_TESTER_WINDOW"
                status_label = "ACCOUNT_CONTEXT_SYNCED_RETRY_READY" if recovery_retry_ready else "SCHEDULED_TESTER_WINDOW"
            else:
                guard_class = "WAIT_GUARD"
                status_label = "ACCOUNT_CONTEXT_SYNCED_RETRY_READY" if recovery_retry_ready else "WAIT_GUARD"
        action = {
            "type": "PARAMLAB_TESTER_TASK",
            "state": state,
            "guardClass": guard_class,
            "statusLabel": status_label,
            "candidateId": candidate_id,
            "routeKey": task.get("routeKey", ""),
            "strategy": task.get("strategy", ""),
            "symbol": task.get("symbol", ""),
            "score": task.get("score", ""),
            "resultStatus": result_status,
            "blockers": (recovery_blockers(recovery) or blockers)[:6],
            "testerOnly": True,
            "livePresetMutationAllowed": False,
        }
        if recovery:
            action["recovery"] = {
                "riskLevel": recovery.get("riskLevel", ""),
                "riskReason": recovery.get("riskReason", ""),
                "latestRunId": recovery.get("latestRunId", ""),
                "latestStopReason": recovery.get("latestStopReason", ""),
                "latestRecoveryAction": recovery.get("latestRecoveryAction", ""),
                "terminalExitCodes": as_list(recovery.get("terminalExitCodes")),
                "retryRemaining": recovery.get("retryRemaining", ""),
            }
        if guard_class == "WAIT_TESTER_WINDOW":
            action.update({
                "dueToday": window_plan.get("dueToday", False),
                "nextWindowStartJstIso": window_plan.get("nextWindowStartJstIso", ""),
                "nextWindowEndJstIso": window_plan.get("nextWindowEndJstIso", ""),
                "nextWindowLabel": window_plan.get("nextWindowLabel", ""),
            })
        actions.append(action)
    return actions


def promotion_recommendations(version_gate: dict[str, Any], governance: dict[str, Any]) -> list[dict[str, Any]]:
    governance_by_route = {
        clean(row.get("key") or row.get("routeKey") or row.get("strategy")): row
        for row in as_list(governance.get("routeDecisions"))
        if isinstance(row, dict)
    }
    recommendations: list[dict[str, Any]] = []
    for row in as_list(version_gate.get("versionDecisions")):
        if not isinstance(row, dict):
            continue
        decision = clean(row.get("decision")).upper()
        readiness = clean(row.get("evidence", {}).get("paramLabResult", {}).get("promotionReadiness")).upper()
        if decision != "PROMOTE_CANDIDATE" and readiness != "PROMOTION_REVIEW":
            continue
        route_key = clean(row.get("routeKey"))
        metrics = row.get("evidence", {}).get("paramLabResult", {}).get("metrics", {})
        recommendations.append({
            "routeKey": route_key,
            "candidateId": row.get("candidateId", ""),
            "versionId": row.get("versionId", ""),
            "decision": decision or readiness,
            "profitFactor": metrics.get("profitFactor"),
            "winRatePct": metrics.get("winRate"),
            "closedTrades": metrics.get("closedTrades"),
            "reason": row.get("reason", ""),
            "blockers": as_list(row.get("blockers")),
            "governanceAction": governance_by_route.get(route_key, {}).get("recommendedAction", ""),
            "recommendedNextStep": "HUMAN_APPROVE_LIVE_OBSERVATION_ONLY",
            "autoApplyLive": False,
            "requiresHumanApproval": True,
            "livePresetMutationAllowed": False,
            "orderSendAllowed": False,
        })
    return recommendations


def polymarket_summary(runtime_dir: Path) -> dict[str, Any]:
    worker = read_json(runtime_dir / "QuantGod_PolymarketRadarWorkerV2.json")
    ai_score = read_json(runtime_dir / "QuantGod_PolymarketAiScoreV1.json")
    auto_gov = read_json(runtime_dir / "QuantGod_PolymarketAutoGovernance.json")
    daily_review = polymarket_daily_review(runtime_dir)
    return {
        "workerStatus": first(worker.get("status"), default="MISSING"),
        "candidateQueueSize": first(worker.get("summary", {}).get("candidateQueueSize"), 0),
        "uniqueMarkets": first(worker.get("summary", {}).get("uniqueMarkets"), 0),
        "aiYellow": first(ai_score.get("summary", {}).get("yellow"), 0),
        "aiGreen": first(ai_score.get("summary", {}).get("green"), 0),
        "quarantine": first(auto_gov.get("summary", {}).get("quarantine"), 0),
        "dailyTodoCount": len(daily_review["actionQueue"]),
        "lossQuarantine": daily_review["summary"]["lossQuarantine"],
        "executedProfitFactor": daily_review["summary"]["executedProfitFactor"],
        "executedNetUSDC": daily_review["summary"]["executedNetUSDC"],
        "shadowProfitFactor": daily_review["summary"]["shadowProfitFactor"],
        "shadowNetUSDC": daily_review["summary"]["shadowNetUSDC"],
        "dailyReview": daily_review,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
    }


def metric_group_key(row: dict[str, Any]) -> str:
    return clean(first(
        row.get("experimentKey"),
        row.get("marketScope"),
        row.get("entryStatus"),
        row.get("signalSource"),
        default="UNKNOWN",
    )) or "UNKNOWN"


def compact_metric_group(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": metric_group_key(row),
        "experimentKey": row.get("experimentKey", ""),
        "marketScope": row.get("marketScope", ""),
        "entryStatus": row.get("entryStatus", ""),
        "signalSource": row.get("signalSource", ""),
        "closed": as_int(row.get("closed"), 0),
        "wins": as_int(row.get("wins"), 0),
        "losses": as_int(row.get("losses"), 0),
        "winRatePct": round(as_float(row.get("winRatePct")), 2),
        "profitFactor": round(as_float(row.get("profitFactor")), 4),
        "realizedPnl": round(as_float(row.get("realizedPnl")), 4),
        "avgPnl": round(as_float(row.get("avgPnl")), 4),
    }


def polymarket_daily_review(runtime_dir: Path) -> dict[str, Any]:
    research = read_json(runtime_dir / "QuantGod_PolymarketResearch.json")
    retune = read_json(runtime_dir / "QuantGod_PolymarketRetunePlanner.json")
    auto_gov = read_json(runtime_dir / "QuantGod_PolymarketAutoGovernance.json")
    outcome = read_json(runtime_dir / "QuantGod_PolymarketDryRunOutcomeWatcher.json")
    gate = read_json(runtime_dir / "QuantGod_PolymarketExecutionGate.json")
    summary = research.get("summary") if isinstance(research.get("summary"), dict) else {}
    executed = summary.get("executed") if isinstance(summary.get("executed"), dict) else {}
    shadow = summary.get("shadow") if isinstance(summary.get("shadow"), dict) else {}
    outcome_summary = outcome.get("summary") if isinstance(outcome.get("summary"), dict) else {}
    auto_summary = auto_gov.get("summary") if isinstance(auto_gov.get("summary"), dict) else {}
    gate_summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    retune_counts = retune.get("recommendationCounts") if isinstance(retune.get("recommendationCounts"), dict) else {}
    evidence_times = [generated_at(item) for item in (research, retune, auto_gov, outcome, gate)]
    evidence_times = [item for item in evidence_times if item]
    latest_evidence_at = max(evidence_times) if evidence_times else None
    review_fresh_for_day = bool(latest_evidence_at and latest_evidence_at.astimezone(JST).date() >= utc_now().astimezone(JST).date())
    global_blockers = [clean(item) for item in as_list(auto_gov.get("globalBlockers")) if clean(item)]
    executed_pf = as_float(executed.get("profitFactor"), 0.0)
    executed_net = as_float(executed.get("realizedPnl"), 0.0)
    shadow_pf = as_float(shadow.get("profitFactor"), 0.0)
    shadow_net = as_float(shadow.get("realizedPnl"), 0.0)
    loss_quarantine = (
        "GLOBAL_LOSS_QUARANTINE" in global_blockers
        or "EXECUTED_PF_BELOW_1" in global_blockers
        or executed_net < 0
        or executed_pf < 1.0
    )
    group_rows = [
        row for row in as_list(research.get("recentJournalGroups") or research.get("journalGroups"))
        if isinstance(row, dict) and as_float(row.get("realizedPnl")) < 0
    ]
    top_loss_sources = [
        compact_metric_group(row)
        for row in sorted(group_rows, key=lambda item: as_float(item.get("realizedPnl")))[:5]
    ]
    experiment_rows = [
        row for row in as_list(research.get("recentExperimentGroups") or research.get("experimentGroups"))
        if isinstance(row, dict) and as_float(row.get("realizedPnl")) < 0
    ]
    retune_sources = [
        compact_metric_group(row)
        for row in sorted(experiment_rows, key=lambda item: as_float(item.get("realizedPnl")))[:3]
    ]
    action_queue: list[dict[str, Any]] = []
    if loss_quarantine:
        action_queue.append({
            "type": "POLY_LOSS_SOURCE_REVIEW",
            "state": "DONE" if review_fresh_for_day else "DUE_TODAY",
            "title": "Polymarket 亏损来源复盘",
            "market": "GLOBAL",
            "detail": (
                f"executed PF {executed_pf:.4g} / 胜率 {as_float(executed.get('winRatePct')):.2f}% "
                f"/ 净 {executed_net:.4g} USDC"
            ),
            "nextStep": "按 experimentKey、marketScope、entryStatus 拆亏损来源；继续只读/dry-run。",
            "blockers": global_blockers[:4],
            "completionEvidence": "fresh_readonly_research_and_auto_governance" if review_fresh_for_day else "",
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
        })
    if shadow_pf < 1.0 or shadow_net < 0:
        action_queue.append({
            "type": "POLY_SHADOW_RETUNE_REVIEW",
            "state": "DONE" if review_fresh_for_day and retune.get("status") == "OK" else "DUE_TODAY",
            "title": "Polymarket Shadow 参数复盘",
            "market": "SHADOW",
            "detail": f"shadow PF {shadow_pf:.4g} / 净 {shadow_net:.4g} USDC",
            "nextStep": "优先保留接近 PF>=1 的实验，淘汰低胜率 autonomous/esports 变体。",
            "blockers": ["SHADOW_PF_BELOW_1"],
            "completionEvidence": "fresh_retune_planner" if review_fresh_for_day and retune.get("status") == "OK" else "",
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
        })
    if as_int(outcome_summary.get("wouldExit"), 0) > 0:
        action_queue.append({
            "type": "POLY_EXIT_POSTERIOR_REVIEW",
            "state": "DONE" if review_fresh_for_day else "DUE_TODAY",
            "title": "Polymarket 退出后验复盘",
            "market": "DRY_RUN",
            "detail": (
                f"wouldExit {as_int(outcome_summary.get('wouldExit'))} / "
                f"SL {as_int(outcome_summary.get('stopLoss'))} / trailing {as_int(outcome_summary.get('trailingExit'))}"
            ),
            "nextStep": "检查 stop-loss/trailing/time-exit 是否过早或价格源延迟；只更新研究参数建议。",
            "blockers": ["EXIT_POSTERIOR_REVIEW"],
            "completionEvidence": "fresh_dry_run_outcome_watcher" if review_fresh_for_day else "",
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
        })
    for source in retune_sources[:2]:
        action_queue.append({
            "type": "POLY_RETUNE_EXPERIMENT",
            "state": "DONE" if review_fresh_for_day and retune.get("status") == "OK" else "DUE_TODAY",
            "title": f"重调 {source['key']}",
            "market": source.get("marketScope") or "experiment",
            "detail": f"PF {source['profitFactor']} / 胜率 {source['winRatePct']}% / 净 {source['realizedPnl']}",
            "nextStep": "降低该实验优先级或收紧入场阈值，生成下一轮 shadow-only retune。",
            "source": source,
            "blockers": ["NEGATIVE_EXPERIMENT_SOURCE"],
            "completionEvidence": "fresh_shadow_only_retune_recommendation" if review_fresh_for_day and retune.get("status") == "OK" else "",
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
        })
    active_queue = [item for item in action_queue if item.get("state") != "DONE"]
    completed_queue = [item for item in action_queue if item.get("state") == "DONE"]
    return {
        "status": "REVIEW_REQUIRED" if active_queue else "DONE_HIDE_UNTIL_NEXT_REFRESH",
        "summary": {
            "lossQuarantine": bool(loss_quarantine),
            "reviewFreshForDay": review_fresh_for_day,
            "latestEvidenceAtIso": latest_evidence_at.isoformat() if latest_evidence_at else "",
            "globalBlockers": global_blockers,
            "executedClosed": as_int(executed.get("closed"), 0),
            "executedWinRatePct": round(as_float(executed.get("winRatePct")), 2),
            "executedProfitFactor": round(executed_pf, 4),
            "executedNetUSDC": round(executed_net, 4),
            "shadowClosed": as_int(shadow.get("closed"), 0),
            "shadowWinRatePct": round(as_float(shadow.get("winRatePct")), 2),
            "shadowProfitFactor": round(shadow_pf, 4),
            "shadowNetUSDC": round(shadow_net, 4),
            "quarantineCount": first(auto_summary.get("quarantine"), 0),
            "autoCanaryEligible": first(auto_summary.get("autoCanaryEligible"), 0),
            "gateCanBet": first(gate_summary.get("canBet"), 0),
            "gateBlocked": first(gate_summary.get("blocked"), 0),
            "retuneTotal": first(retune_counts.get("total"), 0),
            "retuneRed": first(retune_counts.get("red"), 0),
            "retuneYellow": first(retune_counts.get("yellow"), 0),
            "wouldExit": as_int(outcome_summary.get("wouldExit"), 0),
            "todoCount": len(active_queue),
            "completedCount": len(completed_queue),
        },
        "topLossSources": top_loss_sources,
        "retuneSources": retune_sources,
        "actionQueue": active_queue[:6],
        "completedActionQueue": completed_queue[:6],
        "safety": {
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "startsExecutor": False,
            "mutatesMt5": False,
        },
    }


def mt5_terminal_risk(runtime_dir: Path, now: datetime) -> dict[str, Any]:
    mt5_root = runtime_dir.parent.parent if runtime_dir.name == "Files" and runtime_dir.parent.name == "MQL5" else None
    dashboard = read_json(runtime_dir / "QuantGod_Dashboard.json")
    runtime = dashboard.get("runtime") if isinstance(dashboard.get("runtime"), dict) else {}
    summary = {
        "investorModeCount": 0,
        "tradeDisabledCount": 0,
        "orderSendFailureCount": 0,
        "retcodes": [],
        "latestEvidence": "",
        "currentTradeStatus": first(runtime.get("tradeStatus"), default=""),
        "currentTradeAllowed": runtime.get("tradeAllowed"),
        "currentTerminalTradeAllowed": runtime.get("terminalTradeAllowed"),
        "currentProgramTradeAllowed": runtime.get("programTradeAllowed"),
        "currentAccountTradeAllowed": runtime.get("accountTradeAllowed"),
        "currentAccountExpertTradeAllowed": runtime.get("accountExpertTradeAllowed"),
        "currentFocusSymbolTradeAllowed": runtime.get("focusSymbolTradeAllowed"),
        "currentTradePermissionBlocker": first(runtime.get("tradePermissionBlocker"), default=""),
        "currentTradePermissionRecovered": False,
        "requiresCodexReview": False,
    }
    permission_flags = [
        runtime.get("tradeAllowed"),
        runtime.get("terminalTradeAllowed"),
        runtime.get("programTradeAllowed"),
        runtime.get("accountTradeAllowed"),
        runtime.get("accountExpertTradeAllowed"),
        runtime.get("focusSymbolTradeAllowed"),
    ]
    current_permission_ok = bool(runtime) and all(flag is True for flag in permission_flags)
    current_status_ready = clean(runtime.get("tradeStatus")).upper() in {"READY", "LIVE_READY", "TRADE_READY"}
    current_blocker_empty = not clean(runtime.get("tradePermissionBlocker"))
    if not mt5_root or not mt5_root.exists():
        summary["currentTradePermissionRecovered"] = current_permission_ok and current_status_ready and current_blocker_empty
        return summary

    today_key = now.strftime("%Y%m%d")
    evidence: list[str] = []
    retcodes: list[str] = []
    for log_dir in (mt5_root / "logs", mt5_root / "MQL5" / "Logs"):
        if not log_dir.exists():
            continue
        for path in sorted(log_dir.glob("*.log")):
            if today_key not in path.name and date_key(datetime.fromtimestamp(path.stat().st_mtime).isoformat()) != now.date().isoformat():
                continue
            text = read_text(path)
            investor_matches = re.findall(r"trading has been disabled\s*-\s*investor mode", text, flags=re.I)
            trade_disabled_matches = re.findall(r"\[Trade disabled\]|comment=Trade disabled", text, flags=re.I)
            order_fail_matches = re.findall(r"pilot order failed:.*?retcode[=: ]+([0-9]+).*?(?:comment=([^\r\n]+))?", text, flags=re.I)
            summary["investorModeCount"] += len(investor_matches)
            summary["tradeDisabledCount"] += len(trade_disabled_matches)
            summary["orderSendFailureCount"] += len(order_fail_matches)
            for retcode, comment in order_fail_matches:
                if retcode:
                    retcodes.append(retcode)
                    evidence.append(f"{path.name}: retcode={retcode} {comment}".strip())
            if investor_matches:
                evidence.append(f"{path.name}: investor mode")
            if trade_disabled_matches and not order_fail_matches:
                evidence.append(f"{path.name}: Trade disabled")

    summary["retcodes"] = sorted(set(retcodes))
    summary["latestEvidence"] = evidence[-1] if evidence else ""
    summary["currentTradePermissionRecovered"] = (
        current_permission_ok
        and current_status_ready
        and current_blocker_empty
        and bool(summary["investorModeCount"] or summary["tradeDisabledCount"] or summary["orderSendFailureCount"])
    )
    summary["requiresCodexReview"] = bool(
        (summary["investorModeCount"] or summary["tradeDisabledCount"] or summary["orderSendFailureCount"])
        and not summary["currentTradePermissionRecovered"]
    )
    return summary


def codex_review_queue(
    daily_pnl: dict[str, Any],
    action_queue: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    governance: dict[str, Any],
    auto_tester: dict[str, Any],
    recovery_summary: dict[str, Any],
    poly_summary: dict[str, Any],
    mt5_risk: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    targets: set[str] = set()

    if daily_pnl.get("requiresReview") is not False and as_int(daily_pnl.get("closedTrades")) > 0 and as_float(daily_pnl.get("netUSC")) < 0:
        reasons.append({
            "code": "DAILY_PNL_NEGATIVE",
            "target": "strategy",
            "detail": f"netUSC={daily_pnl.get('netUSC')} trades={daily_pnl.get('closedTrades')}",
        })
        targets.add("strategy")

    for row in as_list(governance.get("routeDecisions")):
        if not isinstance(row, dict):
            continue
        action = clean(row.get("recommendedAction")).upper()
        route = clean(row.get("key") or row.get("routeKey") or row.get("strategy"))
        if "DEMOTE" in action:
            reasons.append({
                "code": "GOVERNANCE_DEMOTE_REVIEW",
                "target": "strategy",
                "routeKey": route,
                "detail": action,
            })
            targets.add("strategy")

    ready_tasks = [row for row in action_queue if row.get("state") == "READY_TO_RUN_TESTER"]
    if ready_tasks:
        reasons.append({
            "code": "PARAMLAB_TESTER_READY",
            "target": "evidence",
            "detail": f"readyTasks={len(ready_tasks)}",
        })
        targets.add("evidence")

    if promotions:
        reasons.append({
            "code": "LIVE_PROMOTION_REVIEW_REQUIRED",
            "target": "strategy",
            "detail": f"promotionRecommendations={len(promotions)}",
        })
        targets.add("strategy")

    tester_blockers = [
        clean(blocker)
        for blocker in (
            as_list(auto_tester.get("gate", {}).get("blockers"))
            or as_list(auto_tester.get("summary", {}).get("blockers"))
        )
        if clean(blocker)
    ]
    unexpected_blockers = [
        blocker for blocker in tester_blockers
        if blocker.lower() != "outside_strategy_tester_window"
    ]
    if unexpected_blockers:
        reasons.append({
            "code": "TESTER_UNEXPECTED_BLOCKER",
            "target": "code_or_environment",
            "detail": ", ".join(unexpected_blockers[:4]),
        })
        targets.add("code_or_environment")

    recovery_red = as_int(first(recovery_summary.get("riskRedCount"), recovery_summary.get("redCount"), 0))
    if recovery_red > 0:
        reasons.append({
            "code": "PARAMLAB_RECOVERY_RED",
            "target": "code_or_data",
            "detail": f"redCount={recovery_red}",
        })
        targets.add("code_or_data")

    if clean(poly_summary.get("workerStatus")).upper() == "ERROR":
        reasons.append({
            "code": "POLYMARKET_WORKER_ERROR",
            "target": "code_or_network",
            "detail": "Polymarket worker status ERROR",
        })
        targets.add("code_or_network")

    if mt5_risk.get("requiresCodexReview"):
        reasons.append({
            "code": "MT5_TRADE_PERMISSION_OR_ORDER_SEND_FAILURE",
            "target": "code_or_environment",
            "detail": (
                f"investorMode={mt5_risk.get('investorModeCount')} "
                f"tradeDisabled={mt5_risk.get('tradeDisabledCount')} "
                f"retcodes={','.join(mt5_risk.get('retcodes') or []) or '--'}"
            ),
        })
        targets.add("code_or_environment")

    required = bool(reasons)
    return {
        "required": required,
        "status": "REQUIRES_CODEX_TRIAGE" if required else "OK_HIDE_UNTIL_NEXT_DAILY_REFRESH",
        "reasons": reasons,
        "triageTargets": sorted(targets),
        "recommendedAction": (
            "CODEX_TRIAGE_CODE_STRATEGY_OR_EVIDENCE_FIX"
            if required else
            "NO_DISPLAY_UNTIL_NEXT_DAILY_REFRESH"
        ),
        "safeActionsAllowed": [
            "read evidence",
            "summarize review",
            "fix code/frontend/evidence pipeline",
            "run tests",
            "commit and push safe fixes",
            "write human-approved live promotion recommendation",
        ],
        "forbiddenActions": [
            "send orders",
            "close positions",
            "cancel orders",
            "mutate live preset",
            "auto-apply live promotion",
            "loosen risk gates",
        ],
    }


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    now = utc_now()

    close_rows = read_csv(runtime_dir / "QuantGod_CloseHistory.csv")
    scheduler = read_json(runtime_dir / "QuantGod_ParamLabAutoScheduler.json")
    auto_tester = read_json(runtime_dir / "QuantGod_AutoTesterWindow.json")
    version_gate = read_json(runtime_dir / "QuantGod_VersionPromotionGate.json")
    governance = read_json(runtime_dir / "QuantGod_GovernanceAdvisor.json")
    run_recovery = read_json(runtime_dir / "QuantGod_ParamLabRunRecovery.json")

    review_day = (now.astimezone(JST).date() - timedelta(days=1)).isoformat()
    daily_pnl = close_history_summary(close_rows, review_day)
    daily_pnl["resolvedByCurrentPolicy"] = daily_pnl_resolved_by_policy(daily_pnl, governance)
    daily_pnl["requiresReview"] = bool(as_float(daily_pnl.get("netUSC")) < 0 and not daily_pnl["resolvedByCurrentPolicy"])
    all_action_queue = param_action_queue(scheduler, auto_tester, max(1, int(args.max_actions)), run_recovery)
    completed_action_queue = [action for action in all_action_queue if action.get("state") == "DONE"]
    action_queue = [action for action in all_action_queue if action.get("state") != "DONE"]
    promotions = promotion_recommendations(version_gate, governance)
    poly = polymarket_summary(runtime_dir)
    mt5_risk = mt5_terminal_risk(runtime_dir, now)
    tester_summary = auto_tester.get("summary", {}) if isinstance(auto_tester.get("summary"), dict) else {}
    recovery_summary = run_recovery.get("summary", {}) if isinstance(run_recovery.get("summary"), dict) else {}
    codex_review = codex_review_queue(
        daily_pnl,
        action_queue,
        promotions,
        governance,
        auto_tester,
        recovery_summary,
        poly,
        mt5_risk,
    )

    queue_counter = Counter(action.get("state") for action in action_queue)
    wait_window_count = sum(1 for action in action_queue if action.get("guardClass") == "WAIT_TESTER_WINDOW")
    current_window_plan = tester_window_plan(now)
    if not action_queue and completed_action_queue:
        today_todo_status = "DONE_OR_NO_ACTIONS"
    elif queue_counter.get("NEEDS_CODEX_TRIAGE", 0) > 0:
        today_todo_status = "NEEDS_CODEX_TRIAGE"
    elif action_queue and wait_window_count == len(action_queue):
        today_todo_status = "SCHEDULED_FOR_TESTER_WINDOW"
    elif queue_counter.get("READY_TO_RUN_TESTER", 0) > 0:
        today_todo_status = "READY_TO_RUN_TESTER"
    elif action_queue:
        today_todo_status = "WAIT_GUARD"
    else:
        today_todo_status = "DONE_OR_NO_ACTIONS"
    strategy_actions = [
        {
            "routeKey": row.get("key") or row.get("routeKey") or row.get("strategy"),
            "recommendedAction": row.get("recommendedAction"),
            "blockers": as_list(row.get("blockers"))[:5],
            "liveForward": row.get("liveForward", {}),
        }
        for row in as_list(governance.get("routeDecisions"))
        if isinstance(row, dict)
    ]

    payload = {
        "schemaVersion": 1,
        "mode": "QUANTGOD_DAILY_REVIEW_SAFE_AUTOMATION",
        "generatedAtIso": now.isoformat(),
        "reviewDateJst": review_day,
        "runtimeDir": str(runtime_dir),
        "safety": {
            "mutatesMt5": False,
            "orderSendAllowed": False,
            "walletWriteAllowed": False,
            "livePresetMutationAllowed": False,
            "autoApplyLivePromotion": False,
            "livePromotionRequiresHumanApproval": True,
            "externalAiTransmissionAllowedByDefault": False,
        },
        "summary": {
            "dailyClosedTrades": daily_pnl["closedTrades"],
            "dailyReviewDateJst": review_day,
            "dailyNetUSC": daily_pnl["netUSC"],
            "paramActionCount": len(action_queue),
            "paramReadyToRunCount": queue_counter.get("READY_TO_RUN_TESTER", 0),
            "paramWaitGuardCount": queue_counter.get("WAIT_GUARD", 0),
            "paramWaitWindowCount": wait_window_count,
            "promotionReviewCount": len(promotions),
            "todayTodoStatus": today_todo_status,
            "nextTesterWindowLabel": current_window_plan.get("nextWindowLabel", ""),
            "nextTesterWindowDueToday": current_window_plan.get("dueToday", False),
            "testerCanRun": bool(tester_summary.get("canRunTerminal")),
            "testerWindowOk": bool(tester_summary.get("windowOk")),
            "testerLockOk": bool(tester_summary.get("lockOk")),
            "recoveryRedCount": first(recovery_summary.get("riskRedCount"), 0),
            "recoveryYellowCount": first(recovery_summary.get("riskYellowCount"), 0),
            "mt5TradeDisabledCount": mt5_risk["tradeDisabledCount"],
            "mt5InvestorModeCount": mt5_risk["investorModeCount"],
            "polymarketTodoCount": poly["dailyReview"]["summary"]["todoCount"],
            "polymarketLossQuarantine": poly["dailyReview"]["summary"]["lossQuarantine"],
            "polymarketExecutedPF": poly["dailyReview"]["summary"]["executedProfitFactor"],
            "polymarketShadowPF": poly["dailyReview"]["summary"]["shadowProfitFactor"],
            "codexReviewRequired": codex_review["required"],
        },
        "dailyPnl": daily_pnl,
        "actionQueue": action_queue,
        "completedActionQueue": completed_action_queue[:6],
        "strategyActions": strategy_actions,
        "promotionRecommendations": promotions,
        "polymarket": poly,
        "mt5TerminalRisk": mt5_risk,
        "tester": {
            "summary": tester_summary,
            "blockers": as_list(auto_tester.get("gate", {}).get("blockers"))[:8],
        },
        "codexReview": codex_review,
        "aiReview": {
            "status": "READY_FOR_CODEX_DAILY_REVIEW",
            "localDeterministicReviewBuilt": True,
            "externalLlmMode": "off_by_default",
            "note": "A Codex/app automation should triage codexReview.required=true items and may propose code or strategy changes. Live promotion remains human-approved.",
        },
        "nextActions": [
            "Run due ParamLab tester-only tasks when AUTO_TESTER_WINDOW allows it.",
            "Parse reports and rebuild GovernanceAdvisor before any promotion review.",
            "If codexReview.required is true, ask Codex automation to judge code, strategy, or evidence fixes.",
            "If promotionRecommendations is non-empty, require human approval before any live preset mutation.",
        ],
    }
    write_json(output, payload)
    append_csv(
        ledger,
        {
            "GeneratedAtIso": payload["generatedAtIso"],
            "DailyClosedTrades": daily_pnl["closedTrades"],
            "DailyReviewDateJst": review_day,
            "DailyNetUSC": daily_pnl["netUSC"],
            "ParamActionCount": len(action_queue),
            "ParamReadyToRunCount": queue_counter.get("READY_TO_RUN_TESTER", 0),
            "ParamWaitGuardCount": queue_counter.get("WAIT_GUARD", 0),
            "ParamWaitWindowCount": wait_window_count,
            "PromotionReviewCount": len(promotions),
            "TodayTodoStatus": today_todo_status,
            "NextTesterWindowLabel": current_window_plan.get("nextWindowLabel", ""),
            "TesterCanRun": str(bool(tester_summary.get("canRunTerminal"))).lower(),
            "Mt5InvestorModeCount": mt5_risk["investorModeCount"],
            "Mt5TradeDisabledCount": mt5_risk["tradeDisabledCount"],
            "PolymarketWorkerStatus": payload["polymarket"]["workerStatus"],
            "PolymarketQueue": payload["polymarket"]["candidateQueueSize"],
            "CodexReviewRequired": str(codex_review["required"]).lower(),
        },
        [
            "GeneratedAtIso",
            "DailyClosedTrades",
            "DailyReviewDateJst",
            "DailyNetUSC",
            "ParamActionCount",
            "ParamReadyToRunCount",
            "ParamWaitGuardCount",
            "ParamWaitWindowCount",
            "PromotionReviewCount",
            "TodayTodoStatus",
            "NextTesterWindowLabel",
            "TesterCanRun",
            "Mt5InvestorModeCount",
            "Mt5TradeDisabledCount",
            "PolymarketWorkerStatus",
            "PolymarketQueue",
            "CodexReviewRequired",
        ],
    )
    print(
        "DAILY_REVIEW "
        f"trades={daily_pnl['closedTrades']} net={daily_pnl['netUSC']} "
        f"actions={len(action_queue)} promotions={len(promotions)} "
        f"codexReview={codex_review['required']} output={output}"
    )
    return payload


def main() -> int:
    build_review(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
