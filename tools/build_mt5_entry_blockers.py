#!/usr/bin/env python3
"""Build read-only MT5 entry blocker telemetry.

The report answers one narrow question: when the pilot did not enter, which
gate was responsible?  It only reads local dashboard/ledger exports and writes
derived Dashboard artifacts; it never connects to MT5 or mutates live presets.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
OUTPUT_NAME = "QuantGod_MT5EntryBlockers.json"
LEDGER_NAME = "QuantGod_MT5EntryBlockersLedger.csv"
DASHBOARD_NAME = "QuantGod_Dashboard.json"
SHADOW_STATUS_NAME = "QuantGod_MT5_ShadowStatus.txt"
SHADOW_SIGNAL_NAME = "QuantGod_ShadowSignalLedger.csv"
TRADE_JOURNAL_NAME = "QuantGod_TradeJournal.csv"
CLOSE_HISTORY_NAME = "QuantGod_CloseHistory.csv"
JST = timezone(timedelta(hours=9), "JST")

SAFETY = {
    "readOnly": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "symbolSelectAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "mutatesMt5": False,
}

LEDGER_FIELDS = [
    "GeneratedAtIso",
    "TargetDateJst",
    "EvidenceStatus",
    "DashboardFresh",
    "CurrentTradeStatus",
    "SignalRows",
    "BlockedRows",
    "ObservedRows",
    "OrderSentRows",
    "TopBlocker",
    "TopBlockerCount",
    "WaitSignalRows",
    "SessionBlocks",
    "NewsBlocks",
    "StartupGuardBlocks",
    "SpreadBlocks",
    "LossCooldownBlocks",
    "Recommendation",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MT5 entry blocker telemetry.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--target-date-jst", default="")
    parser.add_argument("--max-dashboard-age-seconds", type=int, default=60)
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
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


def read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(read_text(path))
        return payload if isinstance(payload, dict) else {}, None
    except Exception as exc:  # noqa: BLE001 - report parse failure as evidence.
        return {}, str(exc)


def read_csv(path: Path) -> list[dict[str, str]]:
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
        writer.writerow({field: row.get(field, "") for field in fieldnames})


def clean(value: Any) -> str:
    return str(value or "").strip()


def first(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def nested(row: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = row
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def parse_time(value: Any, default_tz: timezone = JST) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y.%m.%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(timezone.utc)


def date_key_jst(value: Any) -> str:
    parsed = parse_time(value)
    if not parsed:
        return clean(value)[:10].replace(".", "-").replace("/", "-")
    return parsed.astimezone(JST).date().isoformat()


def row_time(row: dict[str, Any]) -> str:
    return clean(first(row.get("LabelTimeLocal"), row.get("LabelTimeServer"), row.get("EventBarTime"), row.get("EventTime"), row.get("CloseTime")))


def evidence_freshness(
    dashboard_path: Path,
    dashboard: dict[str, Any],
    parse_error: str | None,
    *,
    now: datetime,
    max_dashboard_age_seconds: int,
) -> dict[str, Any]:
    if parse_error == "missing":
        return {
            "dashboardExists": False,
            "dashboardFresh": False,
            "dashboardUsableForCurrentState": False,
            "status": "EVIDENCE_MISSING_DASHBOARD",
            "reasons": ["EVIDENCE_MISSING:QuantGod_Dashboard.json"],
        }
    if parse_error:
        return {
            "dashboardExists": True,
            "dashboardFresh": False,
            "dashboardUsableForCurrentState": False,
            "status": "EVIDENCE_PARSE_FAIL",
            "reasons": [f"EVIDENCE_PARSE_FAIL:QuantGod_Dashboard.json:{parse_error}"],
        }

    mtime = datetime.fromtimestamp(dashboard_path.stat().st_mtime, timezone.utc)
    age = max(0.0, (now - mtime).total_seconds())
    content_time = parse_time(first(nested(dashboard, "runtime.localTime"), nested(dashboard, "runtime.timestamp"), dashboard.get("timestamp")))
    content_age = None if content_time is None else max(0.0, (now - content_time).total_seconds())
    reasons: list[str] = []
    if age > max_dashboard_age_seconds:
        reasons.append("EVIDENCE_STALE_DASHBOARD:mtime")
    if content_age is None:
        reasons.append("EVIDENCE_STALE_DASHBOARD:content_time_missing")
    elif content_age > max_dashboard_age_seconds * 3:
        reasons.append("EVIDENCE_STALE_DASHBOARD:content_time")
    fresh = not reasons
    return {
        "dashboardExists": True,
        "dashboardFresh": fresh,
        "dashboardUsableForCurrentState": fresh,
        "status": "OK" if fresh else "EVIDENCE_STALE_DASHBOARD",
        "reasons": reasons,
        "dashboardMtimeIso": iso_z(mtime),
        "dashboardAgeSeconds": round(age, 3),
        "dashboardContentTimeIso": iso_z(content_time) if content_time else None,
        "dashboardContentAgeSeconds": None if content_age is None else round(content_age, 3),
    }


def counter_rows(counter: Counter[str], key_name: str) -> list[dict[str, Any]]:
    return [{key_name: key, "count": count} for key, count in counter.most_common()]


def summarize_signal_rows(rows: list[dict[str, str]], target_date_jst: str) -> dict[str, Any]:
    selected = [row for row in rows if date_key_jst(row_time(row)) == target_date_jst]
    blockers: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    routes: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for row in selected:
        blocker = clean(row.get("Blocker")) or clean(row.get("SignalStatus")) or "NO_BLOCKER_LABEL"
        status = clean(row.get("SignalStatus")) or "UNKNOWN"
        action = clean(row.get("ExecutionAction")) or "UNKNOWN"
        blockers[blocker] += 1
        statuses[status] += 1
        actions[action] += 1
        routes[clean(row.get("Strategy")) or "UNKNOWN"] += 1
        symbols[clean(row.get("Symbol")) or "UNKNOWN"] += 1
        if len(examples) < 12:
            examples.append(
                {
                    "time": row_time(row),
                    "symbol": clean(row.get("Symbol")),
                    "strategy": clean(row.get("Strategy")),
                    "status": status,
                    "blocker": blocker,
                    "action": action,
                    "reason": clean(row.get("Reason"))[:240],
                }
            )
    return {
        "rows": selected,
        "totalRows": len(selected),
        "blockedRows": sum(count for action, count in actions.items() if action.upper() == "BLOCKED"),
        "observedRows": sum(count for action, count in actions.items() if action.upper() == "OBSERVED"),
        "orderSentRows": sum(count for action, count in actions.items() if action.upper() == "ORDER_SENT"),
        "byBlocker": counter_rows(blockers, "blocker"),
        "byStatus": counter_rows(statuses, "status"),
        "byAction": counter_rows(actions, "action"),
        "byStrategy": counter_rows(routes, "strategy"),
        "bySymbol": counter_rows(symbols, "symbol"),
        "examples": examples,
    }


def summarize_dashboard_diagnostics(dashboard: dict[str, Any], usable: bool) -> dict[str, Any]:
    if not usable:
        return {
            "rows": [],
            "totalRows": 0,
            "byStatus": [],
            "byRuntimeLabel": [],
            "byStrategy": [],
            "examples": [],
        }
    diagnostics = dashboard.get("diagnostics") if isinstance(dashboard.get("diagnostics"), dict) else {}
    rows: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    strategies: Counter[str] = Counter()
    for strategy, raw in diagnostics.items():
        if not isinstance(raw, dict):
            continue
        status = clean(raw.get("status")) or "UNKNOWN"
        runtime_label = clean(raw.get("runtimeLabel")) or clean(raw.get("adaptiveState")) or "UNKNOWN"
        item = {
            "strategy": clean(strategy),
            "status": status,
            "runtimeLabel": runtime_label,
            "enabled": raw.get("enabled"),
            "active": raw.get("active"),
            "score": raw.get("score"),
            "reason": clean(raw.get("reason"))[:240],
            "adaptiveState": raw.get("adaptiveState"),
            "riskMultiplier": raw.get("riskMultiplier"),
        }
        rows.append(item)
        statuses[status] += 1
        labels[runtime_label] += 1
        strategies[clean(strategy)] += 1
    return {
        "rows": rows,
        "totalRows": len(rows),
        "byStatus": counter_rows(statuses, "status"),
        "byRuntimeLabel": counter_rows(labels, "runtimeLabel"),
        "byStrategy": counter_rows(strategies, "strategy"),
        "examples": rows[:12],
    }


def recommendation(summary: dict[str, Any], freshness: dict[str, Any]) -> str:
    if not freshness.get("dashboardUsableForCurrentState"):
        return "REFRESH_LIVE_DASHBOARD_BEFORE_TUNING"
    top = (summary.get("byBlocker") or [{}])[0].get("blocker", "")
    top_diag = (summary.get("diagnostics") or {}).get("topStatus", "")
    if not top and top_diag in {"WAIT_BAR"}:
        return "WAIT_FOR_NEXT_BAR_OR_ADD_BAR_WAIT_TELEMETRY_BEFORE_TUNING"
    if not top and top_diag in {"ROUTE_DISABLED"}:
        return "CONFIRM_INTENDED_LIVE_ROUTE_SET_BEFORE_LOOSENING"
    if not top and top_diag in {"WAIT_SIGNAL"}:
        return "EXPAND_SHADOW_CANDIDATE_COVERAGE_BEFORE_LIVE_LOOSENING"
    if top in {"SESSION", "SESSION_BLOCK"}:
        return "REVIEW_SESSION_WINDOW_AFTER_CONFIRMING_SIGNAL_QUALITY"
    if top in {"STARTUP_GUARD"}:
        return "REVIEW_STARTUP_ENTRY_GUARD_ONLY_IF_RESTARTS_ARE_FREQUENT"
    if top in {"NO_SIGNAL", "WAIT_SIGNAL"}:
        return "EXPAND_SHADOW_CANDIDATE_COVERAGE_BEFORE_LIVE_LOOSENING"
    if top in {"NEWS_BLOCK", "NEWS_DIRECTION_FILTER"}:
        return "KEEP_NEWS_GUARD_AND_WAIT_FOR_CLEAR_WINDOW"
    if top in {"SPREAD", "SPREAD_BLOCK"}:
        return "CHECK_BROKER_SPREAD_WINDOW_BEFORE_TUNING"
    return "KEEP_LIVE_GUARDS_AND_COLLECT_MORE_BLOCKER_ROWS"


def status_text(freshness: dict[str, Any], signal_summary: dict[str, Any], diagnostic_summary: dict[str, Any]) -> str:
    if not freshness.get("dashboardUsableForCurrentState"):
        return str(freshness.get("status") or "EVIDENCE_NOT_CURRENT")
    if int(diagnostic_summary.get("totalRows") or 0) > 0 and int(signal_summary.get("totalRows") or 0) == 0:
        return "CURRENT_DIAGNOSTICS_OBSERVED"
    if int(signal_summary.get("totalRows") or 0) == 0:
        return "NO_SIGNAL_LEDGER_ROWS_FOR_TARGET_DATE"
    if int(signal_summary.get("orderSentRows") or 0) > 0:
        return "ENTRY_ACTIVITY_PRESENT"
    return "ENTRY_BLOCKERS_OBSERVED"


def build_report(
    runtime_dir: Path,
    *,
    generated_at: datetime | None = None,
    now: datetime | None = None,
    target_date_jst: str = "",
    max_dashboard_age_seconds: int = 60,
) -> dict[str, Any]:
    now = now or utc_now()
    generated = generated_at or now
    target_date = target_date_jst or now.astimezone(JST).date().isoformat()
    dashboard_path = runtime_dir / DASHBOARD_NAME
    dashboard, parse_error = read_json(dashboard_path)
    freshness = evidence_freshness(
        dashboard_path,
        dashboard,
        parse_error,
        now=now,
        max_dashboard_age_seconds=max_dashboard_age_seconds,
    )
    shadow_rows = read_csv(runtime_dir / SHADOW_SIGNAL_NAME)
    signal_summary = summarize_signal_rows(shadow_rows, target_date)
    current_state: dict[str, Any] = {"usable": bool(freshness.get("dashboardUsableForCurrentState"))}
    if current_state["usable"]:
        current_state.update(
            {
                "tradeStatus": nested(dashboard, "runtime.tradeStatus"),
                "executionEnabled": nested(dashboard, "runtime.executionEnabled"),
                "readOnlyMode": nested(dashboard, "runtime.readOnlyMode"),
                "pilotStartupEntryGuardActive": nested(dashboard, "runtime.pilotStartupEntryGuardActive"),
                "pilotStartupEntryGuardReason": nested(dashboard, "runtime.pilotStartupEntryGuardReason"),
                "newsBlocked": nested(dashboard, "news.blocked"),
                "newsStatus": nested(dashboard, "news.status"),
                "openPositions": len(dashboard.get("openPositions") or dashboard.get("openTrades") or []),
                "pendingOrders": len(dashboard.get("pendingOrders") or []),
            }
        )

    top = (signal_summary.get("byBlocker") or [{}])[0]
    diagnostic_summary = summarize_dashboard_diagnostics(dashboard, bool(freshness.get("dashboardUsableForCurrentState")))
    top_diag = (diagnostic_summary.get("byStatus") or [{}])[0]
    summary_for_recommendation = {
        **signal_summary,
        "diagnostics": {
            "topStatus": top_diag.get("status", ""),
            "topStatusCount": int(top_diag.get("count") or 0),
        },
    }
    rec = recommendation(summary_for_recommendation, freshness)
    payload = {
        "ok": True,
        "schemaVersion": 1,
        "mode": "MT5_ENTRY_BLOCKER_TELEMETRY_V1",
        "generatedAtIso": iso_z(generated),
        "runtimeDir": str(runtime_dir),
        "targetDateJst": target_date,
        "source": "local_dashboard_shadow_signal_ledger",
        "safety": SAFETY,
        "evidence": {
            **freshness,
            "shadowSignalLedger": {
                "file": SHADOW_SIGNAL_NAME,
                "exists": (runtime_dir / SHADOW_SIGNAL_NAME).exists(),
                "rows": len(shadow_rows),
            },
            "shadowStatus": {
                "file": SHADOW_STATUS_NAME,
                "exists": (runtime_dir / SHADOW_STATUS_NAME).exists(),
            },
            "tradeJournal": {
                "file": TRADE_JOURNAL_NAME,
                "exists": (runtime_dir / TRADE_JOURNAL_NAME).exists(),
            },
            "closeHistory": {
                "file": CLOSE_HISTORY_NAME,
                "exists": (runtime_dir / CLOSE_HISTORY_NAME).exists(),
            },
        },
        "currentState": current_state,
        "summary": {
            "status": status_text(freshness, signal_summary, diagnostic_summary),
            "targetDateJst": target_date,
            "signalRows": signal_summary["totalRows"],
            "diagnosticRows": diagnostic_summary["totalRows"],
            "topDiagnosticStatus": top_diag.get("status", ""),
            "topDiagnosticStatusCount": int(top_diag.get("count") or 0),
            "blockedRows": signal_summary["blockedRows"],
            "observedRows": signal_summary["observedRows"],
            "orderSentRows": signal_summary["orderSentRows"],
            "topBlocker": top.get("blocker", ""),
            "topBlockerCount": int(top.get("count") or 0),
            "waitSignalRows": sum(row["count"] for row in signal_summary["byStatus"] if row["status"] == "WAIT_SIGNAL"),
            "sessionBlocks": sum(row["count"] for row in signal_summary["byBlocker"] if row["blocker"] in {"SESSION", "SESSION_BLOCK"}),
            "newsBlocks": sum(row["count"] for row in signal_summary["byBlocker"] if row["blocker"] in {"NEWS_BLOCK", "NEWS_DIRECTION_FILTER"}),
            "startupGuardBlocks": sum(row["count"] for row in signal_summary["byBlocker"] if row["blocker"] == "STARTUP_GUARD"),
            "spreadBlocks": sum(row["count"] for row in signal_summary["byBlocker"] if row["blocker"] in {"SPREAD", "SPREAD_BLOCK"}),
            "lossCooldownBlocks": sum(row["count"] for row in signal_summary["byBlocker"] if row["blocker"] == "LOSS_COOLDOWN"),
            "recommendation": rec,
        },
        "breakdown": {
            **{key: signal_summary[key] for key in ("byBlocker", "byStatus", "byAction", "byStrategy", "bySymbol", "examples")},
            "currentDiagnostics": {
                key: diagnostic_summary[key]
                for key in ("byStatus", "byRuntimeLabel", "byStrategy", "examples")
            },
        },
    }
    return payload


def ledger_row(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    current = payload.get("currentState") or {}
    evidence = payload.get("evidence") or {}
    return {
        "GeneratedAtIso": payload.get("generatedAtIso", ""),
        "TargetDateJst": payload.get("targetDateJst", ""),
        "EvidenceStatus": summary.get("status", ""),
        "DashboardFresh": bool(evidence.get("dashboardFresh")),
        "CurrentTradeStatus": current.get("tradeStatus", "") if current.get("usable") else "",
        "SignalRows": summary.get("signalRows", 0),
        "BlockedRows": summary.get("blockedRows", 0),
        "ObservedRows": summary.get("observedRows", 0),
        "OrderSentRows": summary.get("orderSentRows", 0),
        "TopBlocker": summary.get("topBlocker", ""),
        "TopBlockerCount": summary.get("topBlockerCount", 0),
        "WaitSignalRows": summary.get("waitSignalRows", 0),
        "SessionBlocks": summary.get("sessionBlocks", 0),
        "NewsBlocks": summary.get("newsBlocks", 0),
        "StartupGuardBlocks": summary.get("startupGuardBlocks", 0),
        "SpreadBlocks": summary.get("spreadBlocks", 0),
        "LossCooldownBlocks": summary.get("lossCooldownBlocks", 0),
        "Recommendation": summary.get("recommendation", ""),
    }


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser()
    payload = build_report(
        runtime_dir,
        target_date_jst=args.target_date_jst,
        max_dashboard_age_seconds=max(1, int(args.max_dashboard_age_seconds or 60)),
    )
    output = Path(args.output).expanduser() if args.output else runtime_dir / OUTPUT_NAME
    ledger = Path(args.ledger).expanduser() if args.ledger else runtime_dir / LEDGER_NAME
    write_json(output, payload)
    append_csv(ledger, ledger_row(payload), LEDGER_FIELDS)
    if args.print_summary:
        print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
