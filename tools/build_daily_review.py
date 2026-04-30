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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_DailyReview.json"
LEDGER_NAME = "QuantGod_DailyReviewLedger.csv"


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
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


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


def close_history_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    day = latest_date(rows, "CloseTime", "EventTime", "closeTime")
    day_rows = rows_on_date(rows, day, "CloseTime", "EventTime", "closeTime")
    net = sum(as_float(first(row.get("NetProfit"), row.get("netProfit"), row.get("Profit"))) for row in day_rows)
    by_strategy: dict[str, dict[str, Any]] = {}
    for row in day_rows:
        strategy = clean(first(row.get("Strategy"), row.get("strategy"), default="UNKNOWN")) or "UNKNOWN"
        bucket = by_strategy.setdefault(strategy, {"strategy": strategy, "trades": 0, "netUSC": 0.0})
        bucket["trades"] += 1
        bucket["netUSC"] += as_float(first(row.get("NetProfit"), row.get("netProfit"), row.get("Profit")))
    breakdown = sorted(by_strategy.values(), key=lambda item: abs(item["netUSC"]), reverse=True)
    for item in breakdown:
        item["netUSC"] = round(item["netUSC"], 3)
    return {
        "date": day,
        "closedTrades": len(day_rows),
        "netUSC": round(net, 3),
        "byStrategy": breakdown,
    }


def param_action_queue(scheduler: dict[str, Any], auto_tester: dict[str, Any], max_actions: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    can_run = bool(auto_tester.get("summary", {}).get("canRunTerminal"))
    blockers = as_list(auto_tester.get("gate", {}).get("blockers")) or as_list(auto_tester.get("summary", {}).get("blockers"))
    for task in as_list(scheduler.get("selectedTasks"))[:max_actions]:
        if not isinstance(task, dict):
            continue
        result_status = clean(first(task.get("resultStatus"), task.get("status"), task.get("scheduleAction")))
        if result_status.upper() in {"PARSED", "SCORED", "DONE"}:
            state = "DONE"
        elif can_run:
            state = "READY_TO_RUN_TESTER"
        else:
            state = "WAIT_GUARD"
        actions.append({
            "type": "PARAMLAB_TESTER_TASK",
            "state": state,
            "candidateId": task.get("candidateId", ""),
            "routeKey": task.get("routeKey", ""),
            "strategy": task.get("strategy", ""),
            "symbol": task.get("symbol", ""),
            "score": task.get("score", ""),
            "resultStatus": result_status,
            "blockers": blockers[:4],
            "testerOnly": True,
            "livePresetMutationAllowed": False,
        })
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

    daily_pnl = close_history_summary(close_rows)
    action_queue = param_action_queue(scheduler, auto_tester, max(1, int(args.max_actions)))
    promotions = promotion_recommendations(version_gate, governance)
    tester_summary = auto_tester.get("summary", {}) if isinstance(auto_tester.get("summary"), dict) else {}
    recovery_summary = run_recovery.get("summary", {}) if isinstance(run_recovery.get("summary"), dict) else {}

    queue_counter = Counter(action.get("state") for action in action_queue)
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
            "dailyNetUSC": daily_pnl["netUSC"],
            "paramActionCount": len(action_queue),
            "paramReadyToRunCount": queue_counter.get("READY_TO_RUN_TESTER", 0),
            "paramWaitGuardCount": queue_counter.get("WAIT_GUARD", 0),
            "promotionReviewCount": len(promotions),
            "testerCanRun": bool(tester_summary.get("canRunTerminal")),
            "testerWindowOk": bool(tester_summary.get("windowOk")),
            "testerLockOk": bool(tester_summary.get("lockOk")),
            "recoveryRedCount": first(recovery_summary.get("riskRedCount"), 0),
            "recoveryYellowCount": first(recovery_summary.get("riskYellowCount"), 0),
        },
        "dailyPnl": daily_pnl,
        "actionQueue": action_queue,
        "strategyActions": strategy_actions,
        "promotionRecommendations": promotions,
        "polymarket": polymarket_summary(runtime_dir),
        "tester": {
            "summary": tester_summary,
            "blockers": as_list(auto_tester.get("gate", {}).get("blockers"))[:8],
        },
        "aiReview": {
            "status": "READY_FOR_CODEX_DAILY_REVIEW",
            "localDeterministicReviewBuilt": True,
            "externalLlmMode": "off_by_default",
            "note": "A Codex/app automation may read this artifact and propose code or strategy changes. Live promotion remains human-approved.",
        },
        "nextActions": [
            "Run due ParamLab tester-only tasks when AUTO_TESTER_WINDOW allows it.",
            "Parse reports and rebuild GovernanceAdvisor before any promotion review.",
            "If promotionRecommendations is non-empty, require human approval before any live preset mutation.",
        ],
    }
    write_json(output, payload)
    append_csv(
        ledger,
        {
            "GeneratedAtIso": payload["generatedAtIso"],
            "DailyClosedTrades": daily_pnl["closedTrades"],
            "DailyNetUSC": daily_pnl["netUSC"],
            "ParamActionCount": len(action_queue),
            "ParamReadyToRunCount": queue_counter.get("READY_TO_RUN_TESTER", 0),
            "ParamWaitGuardCount": queue_counter.get("WAIT_GUARD", 0),
            "PromotionReviewCount": len(promotions),
            "TesterCanRun": str(bool(tester_summary.get("canRunTerminal"))).lower(),
            "PolymarketWorkerStatus": payload["polymarket"]["workerStatus"],
            "PolymarketQueue": payload["polymarket"]["candidateQueueSize"],
        },
        [
            "GeneratedAtIso",
            "DailyClosedTrades",
            "DailyNetUSC",
            "ParamActionCount",
            "ParamReadyToRunCount",
            "ParamWaitGuardCount",
            "PromotionReviewCount",
            "TesterCanRun",
            "PolymarketWorkerStatus",
            "PolymarketQueue",
        ],
    )
    print(
        "DAILY_REVIEW "
        f"trades={daily_pnl['closedTrades']} net={daily_pnl['netUSC']} "
        f"actions={len(action_queue)} promotions={len(promotions)} output={output}"
    )
    return payload


def main() -> int:
    build_review(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
