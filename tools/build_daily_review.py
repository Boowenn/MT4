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


def tester_window_plan(now: datetime | None = None) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(JST)
    windows = {
        0: (time(20, 10), time(23, 30)),
        1: (time(20, 10), time(23, 30)),
        2: (time(20, 10), time(23, 30)),
        3: (time(20, 10), time(23, 30)),
        4: (time(20, 10), time(23, 30)),
        5: (time(7, 10), time(9, 30)),
        6: (time(8, 0), time(9, 30)),
    }
    for offset in range(8):
        day = (current + timedelta(days=offset)).date()
        start_time, end_time = windows[day.weekday()]
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
                "windowRule": "Weekday 20:10-23:30 JST, Sat 07:10-09:30 JST, Sun 08:00-09:30 JST",
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


def param_action_queue(scheduler: dict[str, Any], auto_tester: dict[str, Any], max_actions: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    can_run = bool(auto_tester.get("summary", {}).get("canRunTerminal"))
    blockers = as_list(auto_tester.get("gate", {}).get("blockers")) or as_list(auto_tester.get("summary", {}).get("blockers"))
    blocker_keys = {clean(blocker).lower() for blocker in blockers if clean(blocker)}
    only_waiting_window = bool(blocker_keys) and blocker_keys <= {"outside_strategy_tester_window"}
    window_plan = tester_window_plan()
    for task in as_list(scheduler.get("selectedTasks"))[:max_actions]:
        if not isinstance(task, dict):
            continue
        result_status = clean(first(task.get("resultStatus"), task.get("status"), task.get("scheduleAction")))
        guard_class = ""
        status_label = ""
        if result_status.upper() in {"PARSED", "SCORED", "DONE"}:
            state = "DONE"
        elif can_run:
            state = "READY_TO_RUN_TESTER"
            status_label = "READY_TO_RUN_TESTER"
        else:
            state = "WAIT_GUARD"
            if only_waiting_window:
                guard_class = "WAIT_TESTER_WINDOW"
                status_label = "SCHEDULED_TESTER_WINDOW"
            else:
                guard_class = "WAIT_GUARD"
                status_label = "WAIT_GUARD"
        action = {
            "type": "PARAMLAB_TESTER_TASK",
            "state": state,
            "guardClass": guard_class,
            "statusLabel": status_label,
            "candidateId": task.get("candidateId", ""),
            "routeKey": task.get("routeKey", ""),
            "strategy": task.get("strategy", ""),
            "symbol": task.get("symbol", ""),
            "score": task.get("score", ""),
            "resultStatus": result_status,
            "blockers": blockers[:4],
            "testerOnly": True,
            "livePresetMutationAllowed": False,
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
    return {
        "workerStatus": first(worker.get("status"), default="MISSING"),
        "candidateQueueSize": first(worker.get("summary", {}).get("candidateQueueSize"), 0),
        "uniqueMarkets": first(worker.get("summary", {}).get("uniqueMarkets"), 0),
        "aiYellow": first(ai_score.get("summary", {}).get("yellow"), 0),
        "aiGreen": first(ai_score.get("summary", {}).get("green"), 0),
        "quarantine": first(auto_gov.get("summary", {}).get("quarantine"), 0),
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
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
    action_queue = param_action_queue(scheduler, auto_tester, max(1, int(args.max_actions)))
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
    if action_queue and wait_window_count == len(action_queue):
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
            "codexReviewRequired": codex_review["required"],
        },
        "dailyPnl": daily_pnl,
        "actionQueue": action_queue,
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
