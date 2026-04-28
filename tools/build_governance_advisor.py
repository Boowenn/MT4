#!/usr/bin/env python3
"""Build QuantGod governance advice from local MT5 runtime evidence.

This is a file-based, no-trade adapter inspired by QuantDinger's product
workflow: combine live results, backtests, shadow ledgers, candidate outcomes,
and manual alpha into one strategy lifecycle snapshot. It never connects to a
broker and never sends orders.
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
OUTPUT_NAME = "QuantGod_GovernanceAdvisor.json"
PARAM_OPTIMIZATION_NAME = "QuantGod_ParamOptimizationPlan.json"
PARAM_LAB_STATUS_NAME = "QuantGod_ParamLabStatus.json"

RUNTIME_FILE_HEALTH = [
    ("dashboard", "QuantGod_Dashboard.json", 180),
    ("backtest", "QuantGod_BacktestSummary.json", 7 * 24 * 60 * 60),
    ("live_forward", "QuantGod_CloseHistory.csv", 7 * 24 * 60 * 60),
    ("shadow_signal", "QuantGod_ShadowSignalLedger.csv", 24 * 60 * 60),
    ("shadow_outcome", "QuantGod_ShadowOutcomeLedger.csv", 24 * 60 * 60),
    ("candidate_signal", "QuantGod_ShadowCandidateLedger.csv", 24 * 60 * 60),
    ("candidate_outcome", "QuantGod_ShadowCandidateOutcomeLedger.csv", 24 * 60 * 60),
    ("manual_alpha", "QuantGod_ManualAlphaLedger.csv", 24 * 60 * 60),
    ("param_optimization", PARAM_OPTIMIZATION_NAME, 7 * 24 * 60 * 60),
    ("param_lab", PARAM_LAB_STATUS_NAME, 7 * 24 * 60 * 60),
]

ROUTES = [
    {
        "key": "MA_Cross",
        "label": "MA_Cross M15+H1",
        "strategy": "MA_Cross",
        "symbol": "EURUSDc/USDJPYc",
        "timeframe": "M15+H1",
        "live": True,
        "candidateRoute": "TREND_CONT_NO_CROSS",
    },
    {
        "key": "RSI_Reversal",
        "label": "USDJPY RSI_Reversal H1",
        "strategy": "RSI_Reversal",
        "symbol": "USDJPYc",
        "timeframe": "H1",
        "live": True,
        "candidateRoute": "RSI_REVERSAL_SHADOW",
    },
    {
        "key": "BB_Triple",
        "label": "BB_Triple H1",
        "strategy": "BB_Triple",
        "symbol": "EURUSDc/USDJPYc",
        "timeframe": "H1",
        "live": False,
        "candidateRoute": "BB_TRIPLE_SHADOW",
    },
    {
        "key": "MACD_Divergence",
        "label": "MACD_Divergence H1",
        "strategy": "MACD_Divergence",
        "symbol": "EURUSDc/USDJPYc",
        "timeframe": "H1",
        "live": False,
        "candidateRoute": "MACD_MOMENTUM_TURN",
    },
    {
        "key": "SR_Breakout",
        "label": "SR_Breakout M15",
        "strategy": "SR_Breakout",
        "symbol": "EURUSDc/USDJPYc",
        "timeframe": "M15",
        "live": False,
        "candidateRoute": "SR_BREAKOUT_SHADOW",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QuantGod governance advisor JSON.")
    parser.add_argument(
        "--runtime-dir",
        default=str(DEFAULT_RUNTIME_DIR),
        help="Directory containing QuantGod runtime JSON/CSV exports.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON path. Defaults to <runtime-dir>/QuantGod_GovernanceAdvisor.json.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = read_text(path)
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def summarize_runtime_health(runtime_dir: Path) -> dict[str, Any]:
    now_ts = datetime.now(timezone.utc).timestamp()
    files = []
    missing = []
    stale = []
    for key, file_name, max_age_seconds in RUNTIME_FILE_HEALTH:
        path = runtime_dir / file_name
        if not path.exists():
            missing.append(key)
            files.append({
                "key": key,
                "file": file_name,
                "status": "missing",
                "ageSeconds": None,
                "bytes": 0,
                "maxAgeSeconds": max_age_seconds,
                "modifiedAtIso": "",
            })
            continue
        stat = path.stat()
        age_seconds = max(0.0, now_ts - stat.st_mtime)
        status = "fresh" if age_seconds <= max_age_seconds else "stale"
        if status == "stale":
            stale.append(key)
        files.append({
            "key": key,
            "file": file_name,
            "status": status,
            "ageSeconds": round(age_seconds, 1),
            "bytes": stat.st_size,
            "maxAgeSeconds": max_age_seconds,
            "modifiedAtIso": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })

    source_circuits = {}
    for item in files:
        source_circuits[item["key"]] = {
            "state": "closed" if item["status"] == "fresh" else "open",
            "reason": item["status"],
            "ageSeconds": item["ageSeconds"],
        }
    return {
        "status": "healthy" if not missing and not stale else "attention",
        "checkedAtIso": datetime.now(timezone.utc).isoformat(),
        "missingFiles": missing,
        "staleFiles": stale,
        "files": files,
        "sourceCircuits": source_circuits,
        "borrowedBackendIdeas": [
            "QuantDinger-style health snapshot",
            "TTL freshness checks for local runtime files",
            "Circuit-breaker style source states for missing or stale evidence",
            "Read-only no-store dashboard fetches instead of direct trading APIs",
        ],
    }


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def money(value: float) -> float:
    return round(float(value), 4)


def pct(part: float, total: float) -> float | None:
    if total <= 0:
        return None
    return round(part / total * 100.0, 2)


def profit_factor(wins: float, losses: float) -> float | None:
    if losses < 0:
        return round(wins / abs(losses), 4) if wins > 0 else 0.0
    if wins > 0:
        return None
    return None


def parse_time_key(row: dict[str, Any]) -> str:
    for key in ("CloseTime", "EventTime", "OutcomeLabelTimeServer", "LabelTimeServer", "OpenTime"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def summarize_live_forward(close_rows: list[dict[str, str]]) -> dict[str, Any]:
    by_strategy: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in close_rows:
        if str(row.get("Source", "")).upper() != "EA":
            continue
        strategy = str(row.get("Strategy", "")).strip() or "UNKNOWN"
        by_strategy[strategy].append(row)

    summaries: dict[str, dict[str, Any]] = {}
    for strategy, rows in by_strategy.items():
        sorted_rows = sorted(rows, key=parse_time_key)
        profits = [as_float(row.get("NetProfit")) for row in sorted_rows]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]
        consecutive_losses = 0
        for p in reversed(profits):
            if p < 0:
                consecutive_losses += 1
            else:
                break
        summaries[strategy] = {
            "closedTrades": len(sorted_rows),
            "wins": len(wins),
            "losses": len(losses),
            "netProfitUSC": money(sum(profits)),
            "winRatePct": pct(len(wins), len(sorted_rows)),
            "profitFactor": profit_factor(sum(wins), sum(losses)),
            "consecutiveLosses": consecutive_losses,
            "latestCloseTime": parse_time_key(sorted_rows[-1]) if sorted_rows else "",
        }
    return summaries


def summarize_open_positions(dashboard: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"total": 0, "byStrategy": {}}
    open_trades = dashboard.get("openTrades") or []
    if not isinstance(open_trades, list):
        return result
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in open_trades:
        if not isinstance(trade, dict):
            continue
        strategy = str(trade.get("strategy") or trade.get("Strategy") or "UNKNOWN")
        by_strategy[strategy].append(trade)
    result["total"] = sum(len(v) for v in by_strategy.values())
    for strategy, trades in by_strategy.items():
        floating = sum(as_float(t.get("profit", t.get("floatingProfit", 0))) for t in trades)
        result["byStrategy"][strategy] = {
            "openTrades": len(trades),
            "floatingProfitUSC": money(floating),
            "symbols": sorted({str(t.get("symbol", "")).strip() for t in trades if t.get("symbol")}),
        }
    return result


def summarize_shadow(rows: list[dict[str, str]]) -> dict[str, Any]:
    blockers = Counter()
    statuses = Counter()
    symbols = Counter()
    signals = 0
    for row in rows:
        blockers[str(row.get("Blocker", "") or "NONE").strip() or "NONE"] += 1
        statuses[str(row.get("SignalStatus", "") or "UNKNOWN").strip() or "UNKNOWN"] += 1
        symbols[str(row.get("Symbol", "") or "UNKNOWN").strip() or "UNKNOWN"] += 1
        direction = str(row.get("SignalDirection", "")).upper()
        action = str(row.get("ExecutionAction", "")).upper()
        if direction in ("BUY", "SELL") or "ORDER_SENT" in action:
            signals += 1
    recent = rows[-40:]
    recent_blockers = Counter(str(r.get("Blocker", "") or "NONE").strip() or "NONE" for r in recent)
    return {
        "rows": len(rows),
        "signals": signals,
        "signalRatePct": pct(signals, len(rows)),
        "dominantBlockers": blockers.most_common(6),
        "recentBlockers": recent_blockers.most_common(4),
        "statuses": statuses.most_common(6),
        "symbols": symbols.most_common(),
    }


def summarize_candidate_outcomes(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        route = str(row.get("CandidateRoute", "")).strip() or "UNKNOWN"
        grouped[route].append(row)

    summary: dict[str, dict[str, Any]] = {}
    for route, route_rows in grouped.items():
        horizon_60 = [r for r in route_rows if as_int(r.get("HorizonMinutes")) == 60]
        if not horizon_60:
            horizon_60 = route_rows
        wins = sum(1 for r in horizon_60 if str(r.get("DirectionalOutcome", "")).upper() == "WIN")
        losses = sum(1 for r in horizon_60 if str(r.get("DirectionalOutcome", "")).upper() == "LOSS")
        flats = len(horizon_60) - wins - losses
        signed_pips = []
        for row in horizon_60:
            direction = str(row.get("CandidateDirection", "")).upper()
            signed_pips.append(
                as_float(row.get("LongClosePips")) if direction == "BUY" else as_float(row.get("ShortClosePips"))
            )
        summary[route] = {
            "rows": len(route_rows),
            "horizonRows": len(horizon_60),
            "wins": wins,
            "losses": losses,
            "flats": flats,
            "winRatePct": pct(wins, len(horizon_60)),
            "avgSignedPips": round(sum(signed_pips) / len(signed_pips), 3) if signed_pips else None,
            "latestOutcomeTime": parse_time_key(horizon_60[-1]) if horizon_60 else "",
        }
    return summary


def summarize_manual(rows: list[dict[str, str]]) -> dict[str, Any]:
    closed = [r for r in rows if str(r.get("Status", "")).upper() == "CLOSED"]
    open_rows = [r for r in rows if str(r.get("Status", "")).upper() == "OPEN"]
    net = sum(as_float(r.get("NetProfit")) for r in rows)
    best = max(rows, key=lambda r: as_float(r.get("NetProfit")), default={})
    return {
        "rows": len(rows),
        "open": len(open_rows),
        "closed": len(closed),
        "netProfitUSC": money(net),
        "best": {
            "symbol": best.get("Symbol", ""),
            "side": best.get("Side", ""),
            "netProfitUSC": money(as_float(best.get("NetProfit"))),
            "entryRegime": best.get("EntryRegime", ""),
            "exitRegime": best.get("CurrentOrExitRegime", ""),
        } if best else {},
    }


def summarize_backtest(summary: dict[str, Any]) -> dict[str, Any]:
    runs = summary.get("runs") if isinstance(summary, dict) else []
    if not isinstance(runs, list):
        runs = []
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if isinstance(run, dict):
            by_strategy[str(run.get("strategy", "") or "UNKNOWN")].append(run)
    return {
        "status": summary.get("status", "MISSING") if summary else "MISSING",
        "generatedAtIso": summary.get("generatedAtIso", "") if summary else "",
        "runsByStrategy": {
            strategy: [
                {
                    "symbol": run.get("symbol"),
                    "status": run.get("status"),
                    "closedTrades": run.get("closedTrades"),
                    "netProfit": run.get("netProfit"),
                    "profitFactor": run.get("profitFactor"),
                    "winRate": run.get("winRate"),
                }
                for run in runs
            ]
            for strategy, runs in by_strategy.items()
        },
    }


def summarize_param_optimization(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or not plan:
        return {
            "status": "missing",
            "candidateCount": 0,
            "backtestTaskCount": 0,
            "topCandidateId": "",
            "livePresetMutation": False,
        }
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    route_plans = plan.get("routePlans") if isinstance(plan.get("routePlans"), list) else []
    top_by_route = {}
    for route in route_plans:
        if not isinstance(route, dict):
            continue
        route_key = str(route.get("routeKey") or route.get("strategy") or "")
        top = route.get("topCandidate")
        if route_key and isinstance(top, dict):
            top_by_route[route_key] = {
                "candidateId": top.get("candidateId", ""),
                "variant": top.get("variant", ""),
                "symbol": top.get("symbol", ""),
                "score": top.get("score"),
                "parameterSummary": top.get("parameterSummary", ""),
                "intent": top.get("intent", ""),
                "testerOnly": bool(top.get("testerOnly", True)),
                "livePresetMutation": bool(top.get("livePresetMutation", False)),
            }
    return {
        "status": "ready",
        "generatedAtIso": plan.get("generatedAtIso", ""),
        "mode": plan.get("mode", "OFFLINE_PARAM_CANDIDATE_ONLY"),
        "candidateCount": int(summary.get("candidateCount") or 0),
        "backtestTaskCount": int(summary.get("backtestTaskCount") or 0),
        "topCandidateId": str(summary.get("topCandidateId") or ""),
        "livePresetMutation": bool(summary.get("livePresetMutation", False)),
        "topByRoute": top_by_route,
    }


def summarize_param_lab(status: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(status, dict) or not status:
        return {
            "status": "missing",
            "mode": "",
            "runId": "",
            "selectedTaskCount": 0,
            "configReadyCount": 0,
            "runAttemptedCount": 0,
            "reportParsedCount": 0,
            "topByRoute": {},
        }
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    top_by_route = {}
    for route_key, task in (status.get("topByRoute") or {}).items():
        if not isinstance(task, dict):
            continue
        top_by_route[str(route_key)] = {
            "candidateId": task.get("candidateId", ""),
            "variant": task.get("variant", ""),
            "symbol": task.get("symbol", ""),
            "timeframe": task.get("timeframe", ""),
            "status": task.get("status", ""),
            "configPath": task.get("configPath", ""),
            "reportPath": task.get("reportPath", ""),
            "presetPath": task.get("presetPath", ""),
            "hfmPresetPath": task.get("hfmPresetPath", ""),
            "metrics": task.get("metrics") if isinstance(task.get("metrics"), dict) else {},
            "livePresetMutation": bool(task.get("livePresetMutation", False)),
        }
    return {
        "status": "ready",
        "generatedAtIso": status.get("generatedAtIso", ""),
        "runId": status.get("runId", ""),
        "mode": status.get("mode", ""),
        "runTerminal": bool(status.get("runTerminal", False)),
        "archiveDir": status.get("archiveDir", ""),
        "selectedTaskCount": int(status.get("selectedTaskCount") or 0),
        "configReadyCount": int(summary.get("configReadyCount") or 0),
        "runAttemptedCount": int(summary.get("runAttemptedCount") or 0),
        "reportParsedCount": int(summary.get("reportParsedCount") or 0),
        "topByRoute": top_by_route,
    }


def candidate_action(candidate: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    if not candidate or not candidate.get("horizonRows"):
        return "KEEP_SIM_COLLECT", "waiting", ["candidate outcome sample is not ready"]
    rows = int(candidate.get("horizonRows") or 0)
    win_rate = candidate.get("winRatePct")
    avg_pips = candidate.get("avgSignedPips")
    blockers: list[str] = []
    if rows < 20:
        blockers.append("sample_lt_20")
    if win_rate is None or win_rate < 55:
        blockers.append("win_rate_lt_55")
    if avg_pips is None or avg_pips <= 0:
        blockers.append("avg_signed_pips_not_positive")
    if rows >= 20 and win_rate is not None and win_rate >= 55 and avg_pips is not None and avg_pips > 0:
        return "PROMOTION_REVIEW", "supported", []
    if rows >= 20 and win_rate is not None and win_rate < 45:
        return "RETUNE_SIM", "conflict", blockers
    return "KEEP_SIM_ITERATE", "waiting", blockers


def live_action(live: dict[str, Any] | None, open_info: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    live = live or {}
    blockers: list[str] = []
    trades = int(live.get("closedTrades") or 0)
    pf = live.get("profitFactor")
    win_rate = live.get("winRatePct")
    consecutive_losses = int(live.get("consecutiveLosses") or 0)
    net = as_float(live.get("netProfitUSC"))
    floating = as_float((open_info or {}).get("floatingProfitUSC"))

    if trades < 3:
        blockers.append("live_forward_sample_lt_3")
    if consecutive_losses >= 2:
        blockers.append("consecutive_losses_ge_2")
    if trades >= 3 and pf is not None and pf < 1.0:
        blockers.append("profit_factor_lt_1")
    if trades >= 3 and win_rate is not None and win_rate < 45:
        blockers.append("win_rate_lt_45")
    if floating <= -0.50:
        blockers.append("open_position_drawdown_watch")
    if consecutive_losses >= 2 or (trades >= 3 and net < 0 and (pf is not None and pf < 1.0)):
        return "DEMOTE_REVIEW", "conflict", blockers
    if blockers:
        return "KEEP_LIVE_WATCH", "waiting", blockers
    return "KEEP_LIVE", "supported", []


def build_advisor(runtime_dir: Path) -> dict[str, Any]:
    dashboard = read_json(runtime_dir / "QuantGod_Dashboard.json")
    close_rows = read_csv(runtime_dir / "QuantGod_CloseHistory.csv")
    shadow_rows = read_csv(runtime_dir / "QuantGod_ShadowSignalLedger.csv")
    candidate_rows = read_csv(runtime_dir / "QuantGod_ShadowCandidateLedger.csv")
    candidate_outcome_rows = read_csv(runtime_dir / "QuantGod_ShadowCandidateOutcomeLedger.csv")
    manual_rows = read_csv(runtime_dir / "QuantGod_ManualAlphaLedger.csv")
    backtest = read_json(runtime_dir / "QuantGod_BacktestSummary.json")
    param_optimization_plan = read_json(runtime_dir / PARAM_OPTIMIZATION_NAME)
    param_lab_status = read_json(runtime_dir / PARAM_LAB_STATUS_NAME)

    live_forward = summarize_live_forward(close_rows)
    open_positions = summarize_open_positions(dashboard)
    shadow = summarize_shadow(shadow_rows)
    candidate_routes = Counter(str(r.get("CandidateRoute", "") or "UNKNOWN").strip() for r in candidate_rows)
    candidate_outcomes = summarize_candidate_outcomes(candidate_outcome_rows)
    manual = summarize_manual(manual_rows)
    backtest_summary = summarize_backtest(backtest)
    param_optimization = summarize_param_optimization(param_optimization_plan)
    param_lab = summarize_param_lab(param_lab_status)
    runtime_health = summarize_runtime_health(runtime_dir)

    route_decisions = []
    for route in ROUTES:
        live = live_forward.get(route["strategy"], {})
        open_info = open_positions.get("byStrategy", {}).get(route["strategy"], {})
        candidate = candidate_outcomes.get(route["candidateRoute"], {})
        if route["live"]:
            action, tone, blockers = live_action(live, open_info)
        else:
            action, tone, blockers = candidate_action(candidate)
        route_decisions.append({
            **route,
            "mode": "LIVE_0_01" if route["live"] else "SIMULATION_CANDIDATE",
            "recommendedAction": action,
            "tone": tone,
            "blockers": blockers,
            "liveForward": live,
            "openPosition": open_info,
            "candidateSamples": {
                "ledgerRows": candidate_routes.get(route["candidateRoute"], 0),
                **candidate,
            },
            "paramOptimization": param_optimization.get("topByRoute", {}).get(route["strategy"], {}),
            "paramLab": param_lab.get("topByRoute", {}).get(route["strategy"], {}),
        })

    action_counts = Counter(item["recommendedAction"] for item in route_decisions)
    return {
        "schemaVersion": 1,
        "source": "QuantDinger-inspired local governance adapter",
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "runtimeDir": str(runtime_dir),
        "principles": [
            "No external order API was added.",
            "Live execution remains inside the existing QuantGod EA guardrails.",
            "Promotion requires backtest, candidate/outcome, and forward-style evidence.",
            "Demotion can be faster when live forward evidence or protection health weakens.",
        ],
        "hardGuards": {
            "lotSize": "0.01 only",
            "maxTotalPositions": "1 unless separately promoted after 15-30 day evidence",
            "orderPath": "existing EA OrderSend path only",
            "accountCredentials": "not stored here",
            "bbMacdSrLive": "off unless promoted by evidence",
        },
        "summary": {
            "routeCount": len(route_decisions),
            "actions": dict(action_counts),
            "healthStatus": runtime_health["status"],
            "missingRuntimeFiles": len(runtime_health["missingFiles"]),
            "staleRuntimeFiles": len(runtime_health["staleFiles"]),
            "shadowRows": shadow["rows"],
            "candidateRows": len(candidate_rows),
            "candidateOutcomeRows": len(candidate_outcome_rows),
            "manualAlphaRows": manual["rows"],
            "paramOptimizationCandidates": param_optimization["candidateCount"],
            "paramOptimizationBacktestTasks": param_optimization["backtestTaskCount"],
            "paramLabConfigReady": param_lab["configReadyCount"],
            "paramLabReportParsed": param_lab["reportParsedCount"],
            "openPositions": open_positions["total"],
        },
        "systemHealth": runtime_health,
        "backtest": backtest_summary,
        "liveForward": live_forward,
        "shadow": shadow,
        "candidateRouteCounts": candidate_routes.most_common(),
        "candidateOutcomes": candidate_outcomes,
        "manualAlpha": manual,
        "paramOptimization": param_optimization,
        "paramLab": param_lab,
        "routeDecisions": route_decisions,
        "nextOperatorSteps": [
            "Keep MA_Cross and USDJPY RSI_Reversal at 0.01 live only while samples remain thin.",
            "Keep BB/MACD/SR in simulation and retune routes with weak 60m candidate outcomes.",
            "Use ParamOptimizationPlan candidates as offline tester tasks only; never overwrite the live preset automatically.",
            "Use ParamLabStatus as the controlled Strategy Tester task queue; CONFIG_READY tasks still require an authorized tester run before promotion review.",
            "Use this JSON as advisory evidence only; do not bypass EA live switches or risk guards.",
        ],
    }


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    output = Path(args.output) if args.output else runtime_dir / OUTPUT_NAME
    advisor = build_advisor(runtime_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(advisor, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
