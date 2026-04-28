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
PARAM_LAB_RESULTS_NAME = "QuantGod_ParamLabResults.json"
PARAM_LAB_REPORT_WATCHER_NAME = "QuantGod_ParamLabReportWatcher.json"
AUTO_TESTER_WINDOW_NAME = "QuantGod_AutoTesterWindow.json"
PARAM_LAB_RUN_RECOVERY_NAME = "QuantGod_ParamLabRunRecovery.json"
STRATEGY_VERSION_REGISTRY_NAME = "QuantGod_StrategyVersionRegistry.json"
OPTIMIZER_V2_NAME = "QuantGod_OptimizerV2Plan.json"
VERSION_PROMOTION_GATE_NAME = "QuantGod_VersionPromotionGate.json"
PARAM_LAB_AUTO_SCHEDULER_NAME = "QuantGod_ParamLabAutoScheduler.json"

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
    ("param_lab_results", PARAM_LAB_RESULTS_NAME, 7 * 24 * 60 * 60),
    ("param_lab_report_watcher", PARAM_LAB_REPORT_WATCHER_NAME, 7 * 24 * 60 * 60),
    ("auto_tester_window", AUTO_TESTER_WINDOW_NAME, 7 * 24 * 60 * 60),
    ("param_lab_run_recovery", PARAM_LAB_RUN_RECOVERY_NAME, 7 * 24 * 60 * 60),
    ("strategy_version_registry", STRATEGY_VERSION_REGISTRY_NAME, 7 * 24 * 60 * 60),
    ("optimizer_v2", OPTIMIZER_V2_NAME, 7 * 24 * 60 * 60),
    ("version_promotion_gate", VERSION_PROMOTION_GATE_NAME, 7 * 24 * 60 * 60),
    ("param_lab_auto_scheduler", PARAM_LAB_AUTO_SCHEDULER_NAME, 7 * 24 * 60 * 60),
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

ACTION_LABELS = {
    "KEEP_LIVE": "保持实盘",
    "KEEP_LIVE_WATCH": "实盘观察",
    "DEMOTE_REVIEW": "降级复核",
    "KEEP_SIM_COLLECT": "模拟采样",
    "KEEP_SIM_ITERATE": "模拟迭代",
    "RETUNE_SIM": "模拟重调",
    "PROMOTION_REVIEW": "升实盘复核",
}

BLOCKER_FEEDBACK = {
    "live_forward_sample_lt_3": ("样本不足", "medium", "实盘 0.01 forward 平仓样本少于 3 笔，不能把短期结果当成稳定优势。"),
    "consecutive_losses_ge_2": ("连续亏损", "high", "最近实盘 forward 出现连续亏损，路线需要降级复核或至少停止扩大风险。"),
    "profit_factor_lt_1": ("PF 低于 1", "high", "已闭合样本的利润因子低于 1，说明当前参数版本没有覆盖亏损。"),
    "win_rate_lt_45": ("胜率偏低", "high", "实盘 forward 胜率低于 45%，需要检查过滤器、止损/止盈或信号质量。"),
    "open_position_drawdown_watch": ("持仓回撤", "high", "当前持仓浮亏触发观察阈值，需要确认 SL/TP 与安全保护仍有效。"),
    "sample_lt_20": ("候选样本不足", "medium", "候选 60m 后验样本少于 20 条，暂时只能用于学习和排序。"),
    "win_rate_lt_55": ("候选胜率未达标", "medium", "候选后验胜率低于 55%，还不能作为升实盘证据。"),
    "avg_signed_pips_not_positive": ("候选均值不正", "medium", "候选方向后验平均 pips 不为正，优先重调参数而不是升实盘。"),
    "candidate outcome sample is not ready": ("候选后验缺失", "medium", "候选路线还没有可用的 15/30/60 分钟后验样本。"),
}

ROUTE_PARAMETER_TEST_IDEAS = {
    "MA_Cross": [
        "比较 fresh-crossover lookback 5/8 与 pullback continuation 18/24/30 bars，保持 H1 trend filter 不放宽。",
        "按 ATR 和 spread 分桶检查 pullback 入场，优先减少 RANGE/RANGE_TIGHT 误入场。",
    ],
    "RSI_Reversal": [
        "围绕 USDJPY H1 测 RSI crossback 阈值与 oversold/overbought buffer，保持趋势扩张过滤。",
        "比较固定 TP/SL 与保本后移动止损在 H1 反转样本中的 MFE/MAE 表现。",
    ],
    "BB_Triple": [
        "测试 Bollinger touch buffer、band width 最小值和 H1 趋势反向过滤，减少单边行情逆势接刀。",
        "把三重确认拆成 touch / RSI / candle confirmation 权重，优先保留 MFE/MAE 正偏的组合。",
    ],
    "MACD_Divergence": [
        "测试 histogram momentum turn 最小幅度、divergence lookback bars 和 H1 trend filter。",
        "增加 downtrend 禁买 / uptrend 禁卖的 regime guard 对比，避免背离信号逆趋势过早入场。",
    ],
    "SR_Breakout": [
        "测试 breakout buffer、retest confirmation 与 ATR-normalized distance，减少假突破。",
        "按 session 和 spread 分桶比较 M15 突破后 15/30/60 分钟 directional outcome。",
    ],
}


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
                "routeKey": top.get("routeKey", route_key),
                "variant": top.get("variant", ""),
                "symbol": top.get("symbol", ""),
                "timeframe": top.get("timeframe", ""),
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
            "rank": task.get("rank"),
            "score": task.get("score"),
            "configPath": task.get("configPath", ""),
            "reportPath": task.get("reportPath", ""),
            "presetPath": task.get("presetPath", ""),
            "hfmPresetPath": task.get("hfmPresetPath", ""),
            "testerProfileSynced": bool(task.get("testerProfileSynced", False)),
            "terminalExitCode": task.get("terminalExitCode"),
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


def summarize_param_lab_results(results: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(results, dict) or not results:
        return {
            "status": "missing",
            "resultCount": 0,
            "parsedReportCount": 0,
            "pendingReportCount": 0,
            "promotionReadyCount": 0,
            "topByRoute": {},
        }
    summary = results.get("summary") if isinstance(results.get("summary"), dict) else {}
    top_by_route = {}
    for route_key, result in (results.get("topByRoute") or {}).items():
        if not isinstance(result, dict):
            continue
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        top_by_route[str(route_key)] = {
            "candidateId": result.get("candidateId", ""),
            "routeKey": result.get("routeKey", route_key),
            "variant": result.get("variant", ""),
            "symbol": result.get("symbol", ""),
            "timeframe": result.get("timeframe", ""),
            "status": result.get("status", ""),
            "resultScore": result.get("resultScore"),
            "grade": result.get("grade", ""),
            "promotionReadiness": result.get("promotionReadiness", ""),
            "blockers": result.get("blockers") if isinstance(result.get("blockers"), list) else [],
            "configPath": result.get("configPath", ""),
            "reportPath": result.get("reportPath", ""),
            "presetPath": result.get("presetPath", ""),
            "metrics": {
                "closedTrades": metrics.get("closedTrades"),
                "profitFactor": metrics.get("profitFactor"),
                "winRate": metrics.get("winRate"),
                "netProfit": metrics.get("netProfit"),
                "maxDrawdown": metrics.get("maxDrawdown"),
                "relativeDrawdownPct": metrics.get("relativeDrawdownPct"),
                "reportExists": bool(metrics.get("reportExists")),
            },
        }
    return {
        "status": "ready",
        "generatedAtIso": results.get("generatedAtIso", ""),
        "mode": results.get("mode", "OFFLINE_RESULT_LEDGER_ONLY"),
        "resultCount": int(summary.get("resultCount") or 0),
        "parsedReportCount": int(summary.get("parsedReportCount") or 0),
        "pendingReportCount": int(summary.get("pendingReportCount") or 0),
        "promotionReadyCount": int(summary.get("promotionReadyCount") or 0),
        "topByRoute": top_by_route,
    }


def summarize_param_lab_report_watcher(watcher: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(watcher, dict) or not watcher:
        return {
            "status": "missing",
            "knownTaskCount": 0,
            "reportFileCount": 0,
            "parsedReportCount": 0,
            "pendingReportCount": 0,
            "malformedReportCount": 0,
            "newlyParsedReportCount": 0,
            "orphanReportCount": 0,
            "runTerminal": False,
            "livePresetMutation": False,
        }
    summary = watcher.get("summary") if isinstance(watcher.get("summary"), dict) else {}
    return {
        "status": "ready",
        "generatedAtIso": watcher.get("generatedAtIso", ""),
        "mode": watcher.get("mode", "FILE_ONLY_REPORT_WATCHER"),
        "knownTaskCount": int(summary.get("knownTaskCount") or 0),
        "reportFileCount": int(summary.get("reportFileCount") or 0),
        "parsedReportCount": int(summary.get("parsedReportCount") or 0),
        "pendingReportCount": int(summary.get("pendingReportCount") or 0),
        "malformedReportCount": int(summary.get("malformedReportCount") or 0),
        "newlyParsedReportCount": int(summary.get("newlyParsedReportCount") or 0),
        "orphanReportCount": int(summary.get("orphanReportCount") or 0),
        "promotionReadyCount": int(summary.get("promotionReadyCount") or 0),
        "runTerminal": False,
        "livePresetMutation": False,
    }


def summarize_auto_tester_window(window: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(window, dict) or not window:
        return {
            "status": "missing",
            "mode": "",
            "canRunTerminal": False,
            "runTerminalRequested": False,
            "runAttempted": False,
            "selectedTaskCount": 0,
            "queueCount": 0,
            "windowOk": False,
            "lockOk": False,
            "queueOk": False,
            "environmentOk": False,
            "blockerCount": 0,
            "blockers": ["auto_tester_window_missing"],
            "runTerminal": False,
            "livePresetMutation": False,
        }
    summary = window.get("summary") if isinstance(window.get("summary"), dict) else {}
    gate = window.get("gate") if isinstance(window.get("gate"), dict) else {}
    return {
        "status": "ready",
        "generatedAtIso": window.get("generatedAtIso", ""),
        "mode": window.get("mode", summary.get("mode", "EVALUATE_ONLY")),
        "canRunTerminal": bool(summary.get("canRunTerminal")),
        "runTerminalRequested": bool(summary.get("runTerminalRequested")),
        "runAttempted": bool(summary.get("runAttempted")),
        "selectedTaskCount": int(summary.get("selectedTaskCount") or 0),
        "queueCount": int(summary.get("queueCount") or 0),
        "windowOk": bool(summary.get("windowOk")),
        "lockOk": bool(summary.get("lockOk")),
        "queueOk": bool(summary.get("queueOk")),
        "environmentOk": bool(summary.get("environmentOk")),
        "blockerCount": int(summary.get("blockerCount") or 0),
        "blockers": gate.get("blockers") if isinstance(gate.get("blockers"), list) else [],
        "configOnlyCommand": window.get("configOnlyCommand", ""),
        "guardedRunCommand": window.get("guardedRunCommand", ""),
        "runTerminal": bool(summary.get("runTerminal")),
        "livePresetMutation": False,
    }


def summarize_param_lab_run_recovery(recovery: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recovery, dict) or not recovery:
        return {
            "status": "missing",
            "mode": "",
            "runCount": 0,
            "guardedRunCount": 0,
            "configOnlyCount": 0,
            "runAttemptedCount": 0,
            "reportParsedCount": 0,
            "reportMissingCount": 0,
            "reportMalformedCount": 0,
            "retryCount": 0,
            "recoveryQueueCount": 0,
            "candidateDrilldownCount": 0,
            "riskRedCount": 0,
            "riskYellowCount": 0,
            "riskGreenCount": 0,
            "retryBudget": 0,
            "retryBudgetExhaustedCount": 0,
            "latestRunId": "",
            "latestStopReason": "missing",
            "canRunTerminalNow": False,
            "currentBlockerCount": 0,
            "runTerminal": False,
            "livePresetMutation": False,
            "runs": [],
            "recoveryQueue": [],
            "candidateDrilldown": [],
        }
    summary = recovery.get("summary") if isinstance(recovery.get("summary"), dict) else {}
    return {
        "status": "ready",
        "generatedAtIso": recovery.get("generatedAtIso", ""),
        "mode": recovery.get("mode", "FILE_ONLY_RUN_HISTORY_RECOVERY"),
        "runCount": int(summary.get("runCount") or 0),
        "guardedRunCount": int(summary.get("guardedRunCount") or 0),
        "configOnlyCount": int(summary.get("configOnlyCount") or 0),
        "runAttemptedCount": int(summary.get("runAttemptedCount") or 0),
        "reportParsedCount": int(summary.get("reportParsedCount") or 0),
        "reportMissingCount": int(summary.get("reportMissingCount") or 0),
        "reportMalformedCount": int(summary.get("reportMalformedCount") or 0),
        "retryCount": int(summary.get("retryCount") or 0),
        "recoveryQueueCount": int(summary.get("recoveryQueueCount") or 0),
        "candidateDrilldownCount": int(summary.get("candidateDrilldownCount") or 0),
        "riskRedCount": int(summary.get("riskRedCount") or 0),
        "riskYellowCount": int(summary.get("riskYellowCount") or 0),
        "riskGreenCount": int(summary.get("riskGreenCount") or 0),
        "retryBudget": int(summary.get("retryBudget") or 0),
        "retryBudgetExhaustedCount": int(summary.get("retryBudgetExhaustedCount") or 0),
        "latestRunId": str(summary.get("latestRunId") or ""),
        "latestStopReason": str(summary.get("latestStopReason") or ""),
        "canRunTerminalNow": bool(summary.get("canRunTerminalNow")),
        "currentBlockerCount": int(summary.get("currentBlockerCount") or 0),
        "runTerminal": False,
        "livePresetMutation": False,
        "currentGuard": recovery.get("currentGuard", {}) if isinstance(recovery.get("currentGuard"), dict) else {},
        "runs": recovery.get("runs") if isinstance(recovery.get("runs"), list) else [],
        "recoveryQueue": recovery.get("recoveryQueue") if isinstance(recovery.get("recoveryQueue"), list) else [],
        "candidateDrilldown": recovery.get("candidateDrilldown") if isinstance(recovery.get("candidateDrilldown"), list) else [],
    }


def summarize_strategy_version_registry(registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(registry, dict) or not registry:
        return {
            "status": "missing",
            "routeCount": 0,
            "liveVersionCount": 0,
            "simCandidateVersionCount": 0,
            "candidateChildVersionCount": 0,
            "topByRoute": {},
        }
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    top_by_route = {}
    for route in registry.get("routes") or []:
        if not isinstance(route, dict):
            continue
        route_key = str(route.get("routeKey") or route.get("strategy") or "")
        if not route_key:
            continue
        top_by_route[route_key] = {
            "versionId": route.get("versionId", ""),
            "status": route.get("status", ""),
            "parameterHash": route.get("parameterHash", ""),
            "parameterSummary": route.get("parameterSummary", ""),
            "liveEnabled": bool(route.get("liveEnabled", False)),
            "candidateEnabled": bool(route.get("candidateEnabled", False)),
            "readiness": (route.get("promotionState") or {}).get("readiness", ""),
            "candidateChildCount": len(route.get("candidateChildren") or []),
            "topCandidateVersionId": (route.get("lineage") or {}).get("topCandidateVersionId", ""),
            "livePresetMutation": False,
        }
    return {
        "status": "ready",
        "generatedAtIso": registry.get("generatedAtIso", ""),
        "mode": registry.get("mode", "FILE_ONLY_STRATEGY_VERSION_REGISTRY"),
        "routeCount": int(summary.get("routeCount") or len(top_by_route)),
        "liveVersionCount": int(summary.get("liveVersionCount") or 0),
        "simCandidateVersionCount": int(summary.get("simCandidateVersionCount") or 0),
        "candidateChildVersionCount": int(summary.get("candidateChildVersionCount") or 0),
        "promotionReviewReadyCount": int(summary.get("promotionReviewReadyCount") or 0),
        "retuneCount": int(summary.get("retuneCount") or 0),
        "topByRoute": top_by_route,
    }


def summarize_optimizer_v2(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or not plan:
        return {
            "status": "missing",
            "proposalCount": 0,
            "readyToQueueCount": 0,
            "waitingReportCount": 0,
            "topByRoute": {},
        }
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    top_by_route = {}
    for route in plan.get("routePlans") or []:
        if not isinstance(route, dict):
            continue
        route_key = str(route.get("routeKey") or route.get("strategy") or "")
        proposals = route.get("proposals") if isinstance(route.get("proposals"), list) else []
        top = proposals[0] if proposals and isinstance(proposals[0], dict) else {}
        if route_key:
            top_by_route[route_key] = {
                "currentVersionId": route.get("currentVersionId", ""),
                "primaryAction": route.get("primaryAction", ""),
                "resultState": route.get("resultState", ""),
                "proposalCount": int(route.get("proposalCount") or 0),
                "topProposalId": route.get("topProposalId", ""),
                "topRankScore": route.get("topRankScore"),
                "topCandidateVersionId": top.get("candidateVersionId", ""),
                "topParameterSummary": top.get("parameterSummary", ""),
                "topObjective": top.get("objective", ""),
                "testerOnlyCommand": top.get("testerOnlyCommand", ""),
                "livePresetMutation": False,
            }
    return {
        "status": "ready",
        "generatedAtIso": plan.get("generatedAtIso", ""),
        "mode": plan.get("mode", "VERSION_AWARE_TESTER_ONLY_OPTIMIZER"),
        "routeCount": int(summary.get("routeCount") or len(top_by_route)),
        "proposalCount": int(summary.get("proposalCount") or 0),
        "readyToQueueCount": int(summary.get("readyToQueueCount") or 0),
        "waitingReportCount": int(summary.get("waitingReportCount") or 0),
        "retuneRouteCount": int(summary.get("retuneRouteCount") or 0),
        "topProposalId": str(summary.get("topProposalId") or ""),
        "topByRoute": top_by_route,
    }


def summarize_version_promotion_gate(gate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(gate, dict) or not gate:
        return {
            "status": "missing",
            "versionDecisionCount": 0,
            "promoteCandidateCount": 0,
            "demoteLiveCount": 0,
            "retuneCount": 0,
            "waitReportCount": 0,
            "waitForwardCount": 0,
            "topByRoute": {},
        }
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    top_by_route = {}
    for route in gate.get("routeDecisions") or []:
        if not isinstance(route, dict):
            continue
        route_key = str(route.get("routeKey") or route.get("strategy") or "")
        if not route_key:
            continue
        top_by_route[route_key] = {
            "currentVersionId": route.get("currentVersionId", ""),
            "currentDecision": route.get("currentDecision", ""),
            "currentReason": route.get("currentReason", ""),
            "promotionCandidateCount": int(route.get("promotionCandidateCount") or 0),
            "waitingReportCount": int(route.get("waitingReportCount") or 0),
            "retuneCount": int(route.get("retuneCount") or 0),
            "demoteLiveCount": int(route.get("demoteLiveCount") or 0),
            "blockers": route.get("blockers") if isinstance(route.get("blockers"), list) else [],
            "dryRun": True,
            "livePresetMutation": False,
        }
    return {
        "status": "ready",
        "generatedAtIso": gate.get("generatedAtIso", ""),
        "mode": gate.get("mode", "VERSION_PROMOTION_GATE_DRY_RUN"),
        "versionDecisionCount": int(summary.get("versionDecisionCount") or 0),
        "routeCount": int(summary.get("routeCount") or len(top_by_route)),
        "promoteCandidateCount": int(summary.get("promoteCandidateCount") or 0),
        "demoteLiveCount": int(summary.get("demoteLiveCount") or 0),
        "retuneCount": int(summary.get("retuneCount") or 0),
        "waitReportCount": int(summary.get("waitReportCount") or 0),
        "waitForwardCount": int(summary.get("waitForwardCount") or 0),
        "livePresetMutation": False,
        "dryRun": True,
        "topByRoute": top_by_route,
    }


def summarize_param_lab_auto_scheduler(scheduler: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scheduler, dict) or not scheduler:
        return {
            "status": "missing",
            "queueCount": 0,
            "waitReportQueueCount": 0,
            "retuneQueueCount": 0,
            "waitForwardObserveCount": 0,
            "topByRoute": {},
        }
    summary = scheduler.get("summary") if isinstance(scheduler.get("summary"), dict) else {}
    top_by_route = {}
    for route in scheduler.get("routePlans") or []:
        if not isinstance(route, dict):
            continue
        route_key = str(route.get("routeKey") or "")
        candidates = route.get("candidates") if isinstance(route.get("candidates"), list) else []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        if route_key:
            top_by_route[route_key] = {
                "currentDecision": route.get("currentDecision", ""),
                "queueMode": route.get("queueMode", ""),
                "scheduledTaskCount": int(route.get("scheduledTaskCount") or 0),
                "topCandidateId": top.get("candidateId", ""),
                "topAction": top.get("scheduleAction", ""),
                "topPriorityScore": top.get("priorityScore", ""),
                "topParameterSummary": top.get("parameterSummary", ""),
                "configOnlyCommand": top.get("configOnlyCommand", ""),
                "livePresetMutation": False,
                "runTerminalDefault": False,
            }
    return {
        "status": "ready",
        "generatedAtIso": scheduler.get("generatedAtIso", ""),
        "mode": scheduler.get("mode", "CONFIG_ONLY_AUTO_SCHEDULER"),
        "queueCount": int(summary.get("queueCount") or 0),
        "waitReportQueueCount": int(summary.get("waitReportQueueCount") or 0),
        "retuneQueueCount": int(summary.get("retuneQueueCount") or 0),
        "waitForwardObserveCount": int(summary.get("waitForwardObserveCount") or 0),
        "routeCount": int(summary.get("routeCount") or len(top_by_route)),
        "topCandidateId": str(summary.get("topCandidateId") or ""),
        "configOnly": True,
        "runTerminal": False,
        "livePresetMutation": False,
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


def fmt_metric(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "--"
    try:
        number = float(value)
    except Exception:
        return str(value)
    if math.isfinite(number):
        return f"{number:.{digits}f}{suffix}"
    return "--"


def param_lab_tester_command(candidate_id: str = "", route_key: str = "") -> str:
    parts = [r"tools\run_param_lab.bat"]
    if candidate_id:
        parts.extend(["--candidate-id", candidate_id])
    elif route_key:
        parts.extend(["--route", route_key, "--max-tasks", "1"])
    return " ".join(parts)


def build_param_task_link(
    *,
    text: str,
    route_decision: dict[str, Any],
    source: str,
    candidate: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = candidate or {}
    task = task or {}
    result = result or {}
    route_key = str(
        candidate.get("routeKey")
        or task.get("routeKey")
        or result.get("routeKey")
        or route_decision.get("strategy")
        or route_decision.get("key")
        or ""
    )
    candidate_id = str(candidate.get("candidateId") or task.get("candidateId") or result.get("candidateId") or "")
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    if not metrics and isinstance(task.get("metrics"), dict):
        metrics = task.get("metrics") or {}
    report_exists = bool(metrics.get("reportExists"))
    task_status = str(task.get("status") or ("QUEUE_PENDING" if candidate_id else "ROUTE_IDEA"))
    result_status = str(result.get("status") or metrics.get("parseStatus") or ("REPORT_READY" if report_exists else "PENDING_REPORT"))
    command_scope = "candidate" if candidate_id else "route"
    has_task_context = bool(candidate_id or task.get("configPath") or task.get("presetPath") or result.get("reportPath"))
    return {
        "text": text,
        "source": source,
        "routeKey": route_key,
        "candidateId": candidate_id,
        "variant": candidate.get("variant") or task.get("variant") or result.get("variant") or "",
        "symbol": candidate.get("symbol") or task.get("symbol") or result.get("symbol") or "",
        "timeframe": candidate.get("timeframe") or task.get("timeframe") or result.get("timeframe") or "",
        "candidateScore": candidate.get("score") or task.get("score"),
        "taskStatus": task_status,
        "resultStatus": result_status,
        "resultScore": result.get("resultScore"),
        "grade": result.get("grade", ""),
        "promotionReadiness": result.get("promotionReadiness", ""),
        "reportExists": report_exists,
        "configPath": task.get("configPath") or result.get("configPath") or "",
        "reportPath": task.get("reportPath") or result.get("reportPath") or "",
        "presetPath": task.get("presetPath") or result.get("presetPath") or "",
        "testerProfileSynced": bool(task.get("testerProfileSynced", False)),
        "terminalExitCode": task.get("terminalExitCode"),
        "testerOnlyCommand": param_lab_tester_command(candidate_id, route_key) if has_task_context else "",
        "testerOnly": True,
        "commandScope": command_scope,
        "livePresetMutation": bool(
            candidate.get("livePresetMutation")
            or task.get("livePresetMutation")
            or result.get("livePresetMutation")
            or False
        ),
        "metrics": {
            "closedTrades": metrics.get("closedTrades"),
            "profitFactor": metrics.get("profitFactor"),
            "winRate": metrics.get("winRate"),
            "netProfit": metrics.get("netProfit"),
            "maxDrawdown": metrics.get("maxDrawdown"),
            "relativeDrawdownPct": metrics.get("relativeDrawdownPct"),
        },
        "note": (
            "授权 Strategy Tester 窗口内可按 candidateId 精确运行。"
            if candidate_id
            else "这是路线级参数方向，先按 route 生成/运行 top tester-only 任务。"
        ),
    }


def feedback_risk_item(blocker: str) -> dict[str, str]:
    label, severity, detail = BLOCKER_FEEDBACK.get(
        blocker,
        ("证据 blocker", "medium", f"Governance Advisor 标记了 `{blocker}`，需要在下一轮回测/forward 中复核。"),
    )
    return {
        "code": blocker,
        "label": label,
        "severity": severity,
        "detail": detail,
    }


def build_route_feedback(route_decision: dict[str, Any]) -> dict[str, Any]:
    strategy = route_decision["strategy"]
    action = route_decision["recommendedAction"]
    live = route_decision.get("liveForward") or {}
    candidate = route_decision.get("candidateSamples") or {}
    param = route_decision.get("paramOptimization") or {}
    lab = route_decision.get("paramLab") or {}
    lab_result = route_decision.get("paramLabResult") or {}
    result_metrics = lab_result.get("metrics") if isinstance(lab_result.get("metrics"), dict) else {}
    blockers = list(route_decision.get("blockers") or [])
    live_trades = int(live.get("closedTrades") or 0)
    live_pf = live.get("profitFactor")
    live_win = live.get("winRatePct")
    live_net = as_float(live.get("netProfitUSC"))
    candidate_rows = int(candidate.get("horizonRows") or 0)
    candidate_win = candidate.get("winRatePct")
    candidate_avg = candidate.get("avgSignedPips")

    why: list[str] = [
        f"当前建议是 `{ACTION_LABELS.get(action, action)}`，因为路线处于 {route_decision.get('mode', '--')}，且必须继续遵守 0.01、单仓、SL/TP、session/spread/news/cooldown/order-send 风控。",
    ]
    if route_decision.get("live"):
        why.append(
            "实盘 forward: "
            f"{live_trades} 笔 closed trades，PF {fmt_metric(live_pf, 2)}，"
            f"胜率 {fmt_metric(live_win, 1, '%')}，净值 {fmt_metric(live_net, 2)} USC。"
        )
        consecutive_losses = int(live.get("consecutiveLosses") or 0)
        if consecutive_losses:
            why.append(f"最近连续亏损 {consecutive_losses} 笔，任何扩仓或放宽都应暂停。")
    else:
        why.append(
            "候选后验: "
            f"60m 样本 {candidate_rows} 条，胜率 {fmt_metric(candidate_win, 1, '%')}，"
            f"平均方向收益 {fmt_metric(candidate_avg, 2)} pips。"
        )
        why.append("该路线仍在 simulation/candidate/backtest 阶段，不能直接发送真实订单。")

    risk_areas = [feedback_risk_item(blocker) for blocker in blockers]
    if not risk_areas:
        risk_areas.append({
            "code": "no_hard_blocker",
            "label": "无硬反证",
            "severity": "low",
            "detail": "当前汇总没有硬性 blocker，但仍需等待足够样本和参数版本评分。",
        })
    if not lab_result.get("candidateId"):
        risk_areas.append({
            "code": "parameter_version_unscored",
            "label": "参数未评分",
            "severity": "medium",
            "detail": "还没有 Strategy Tester 结果回灌，不能按参数版本升实盘。",
        })

    next_parameter_tests: list[str] = []
    next_parameter_task_links: list[dict[str, Any]] = []
    if param.get("candidateId"):
        text = (
            f"优先复核候选 `{param.get('candidateId')}` ({param.get('variant') or '--'}): "
            f"{param.get('parameterSummary') or '等待参数摘要'}。"
        )
        next_parameter_tests.append(text)
        next_parameter_task_links.append(build_param_task_link(
            text=text,
            route_decision=route_decision,
            source="param_optimization",
            candidate=param,
            task=lab if lab.get("candidateId") == param.get("candidateId") else {},
            result=lab_result if lab_result.get("candidateId") == param.get("candidateId") else {},
        ))
    if lab.get("candidateId"):
        text = (
            f"ParamLab 队列已有 `{lab.get('candidateId')}`，状态 {lab.get('status') or '--'}；授权 Strategy Tester 窗口内运行后再解析报告。"
        )
        next_parameter_tests.append(text)
        next_parameter_task_links.append(build_param_task_link(
            text=text,
            route_decision=route_decision,
            source="param_lab_task",
            candidate=param if param.get("candidateId") == lab.get("candidateId") else {},
            task=lab,
            result=lab_result if lab_result.get("candidateId") == lab.get("candidateId") else {},
        ))
    if lab_result.get("candidateId"):
        grade = lab_result.get("grade") or "--"
        score = lab_result.get("resultScore")
        text = (
            f"已评分 `{lab_result.get('candidateId')}`: grade {grade}, score {fmt_metric(score, 1)}, "
            f"PF {fmt_metric(result_metrics.get('profitFactor'), 2)}, 胜率 {fmt_metric(result_metrics.get('winRate'), 1, '%')}。"
        )
        next_parameter_tests.append(text)
        next_parameter_task_links.append(build_param_task_link(
            text=text,
            route_decision=route_decision,
            source="param_lab_result",
            candidate=param if param.get("candidateId") == lab_result.get("candidateId") else {},
            task=lab if lab.get("candidateId") == lab_result.get("candidateId") else {},
            result=lab_result,
        ))
    for idea in ROUTE_PARAMETER_TEST_IDEAS.get(strategy, []):
        next_parameter_tests.append(idea)
        next_parameter_task_links.append(build_param_task_link(
            text=idea,
            route_decision=route_decision,
            source="route_idea",
            candidate={},
            task=lab,
            result=lab_result if lab_result.get("candidateId") == lab.get("candidateId") else {},
        ))

    if action in {"DEMOTE_REVIEW", "RETUNE_SIM"}:
        next_step = "先降级或保持模拟，优先跑参数重调和候选后验，不要开新 live switch。"
    elif action == "PROMOTION_REVIEW":
        next_step = "进入升实盘复核队列；只有回测、结果回灌、forward-style 证据和风控全部通过后，才允许最小 live switch 变更。"
    elif action == "KEEP_LIVE":
        next_step = "继续 0.01 live forward 采样；关注是否保持无连续亏损、order-send 稳定和 SL/TP 保护正常。"
    elif action == "KEEP_LIVE_WATCH":
        next_step = "保持 live 但观察，不扩大仓位；优先补足 closed trades 和检查当前 blocker 是否解除。"
    else:
        next_step = "保持 candidate/backtest 采样；下一步先生成或运行 ParamLab 候选。"

    return {
        "key": route_decision["key"],
        "strategy": strategy,
        "label": route_decision["label"],
        "mode": route_decision["mode"],
        "recommendedAction": action,
        "actionLabel": ACTION_LABELS.get(action, action),
        "tone": route_decision.get("tone", "waiting"),
        "why": why,
        "riskAreas": risk_areas,
        "nextParameterTests": next_parameter_tests[:5],
        "nextParameterTaskLinks": next_parameter_task_links[:5],
        "nextStep": next_step,
        "evidence": {
            "liveClosedTrades": live_trades,
            "liveProfitFactor": live_pf,
            "liveWinRatePct": live_win,
            "liveNetProfitUSC": round(live_net, 4),
            "candidateHorizonRows": candidate_rows,
            "candidateWinRatePct": candidate_win,
            "candidateAvgSignedPips": candidate_avg,
            "paramCandidateId": param.get("candidateId", ""),
            "paramLabCandidateId": lab.get("candidateId", ""),
            "paramLabResultCandidateId": lab_result.get("candidateId", ""),
        },
    }


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
    param_lab_results_doc = read_json(runtime_dir / PARAM_LAB_RESULTS_NAME)
    param_lab_report_watcher_doc = read_json(runtime_dir / PARAM_LAB_REPORT_WATCHER_NAME)
    auto_tester_window_doc = read_json(runtime_dir / AUTO_TESTER_WINDOW_NAME)
    param_lab_run_recovery_doc = read_json(runtime_dir / PARAM_LAB_RUN_RECOVERY_NAME)
    strategy_version_registry_doc = read_json(runtime_dir / STRATEGY_VERSION_REGISTRY_NAME)
    optimizer_v2_doc = read_json(runtime_dir / OPTIMIZER_V2_NAME)
    version_promotion_gate_doc = read_json(runtime_dir / VERSION_PROMOTION_GATE_NAME)
    param_lab_auto_scheduler_doc = read_json(runtime_dir / PARAM_LAB_AUTO_SCHEDULER_NAME)

    live_forward = summarize_live_forward(close_rows)
    open_positions = summarize_open_positions(dashboard)
    shadow = summarize_shadow(shadow_rows)
    candidate_routes = Counter(str(r.get("CandidateRoute", "") or "UNKNOWN").strip() for r in candidate_rows)
    candidate_outcomes = summarize_candidate_outcomes(candidate_outcome_rows)
    manual = summarize_manual(manual_rows)
    backtest_summary = summarize_backtest(backtest)
    param_optimization = summarize_param_optimization(param_optimization_plan)
    param_lab = summarize_param_lab(param_lab_status)
    param_lab_results = summarize_param_lab_results(param_lab_results_doc)
    param_lab_report_watcher = summarize_param_lab_report_watcher(param_lab_report_watcher_doc)
    auto_tester_window = summarize_auto_tester_window(auto_tester_window_doc)
    param_lab_run_recovery = summarize_param_lab_run_recovery(param_lab_run_recovery_doc)
    strategy_version_registry = summarize_strategy_version_registry(strategy_version_registry_doc)
    optimizer_v2 = summarize_optimizer_v2(optimizer_v2_doc)
    version_promotion_gate = summarize_version_promotion_gate(version_promotion_gate_doc)
    param_lab_auto_scheduler = summarize_param_lab_auto_scheduler(param_lab_auto_scheduler_doc)
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
        route_decision = {
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
            "paramLabResult": param_lab_results.get("topByRoute", {}).get(route["strategy"], {}),
        }
        route_decision["feedback"] = build_route_feedback(route_decision)
        route_decisions.append(route_decision)

    action_counts = Counter(item["recommendedAction"] for item in route_decisions)
    governance_feedback = [item["feedback"] for item in route_decisions]
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
            "paramLabResultCount": param_lab_results["resultCount"],
            "paramLabResultParsed": param_lab_results["parsedReportCount"],
            "paramLabPromotionReady": param_lab_results["promotionReadyCount"],
            "paramLabReportWatcherParsed": param_lab_report_watcher["parsedReportCount"],
            "paramLabReportWatcherPending": param_lab_report_watcher["pendingReportCount"],
            "paramLabReportWatcherMalformed": param_lab_report_watcher["malformedReportCount"],
            "autoTesterWindowCanRun": auto_tester_window["canRunTerminal"],
            "autoTesterWindowBlockers": auto_tester_window["blockerCount"],
            "paramLabRunRecoveryRuns": param_lab_run_recovery["runCount"],
            "paramLabRunRecoveryQueue": param_lab_run_recovery["recoveryQueueCount"],
            "paramLabRunRecoveryLatestStop": param_lab_run_recovery["latestStopReason"],
            "paramLabRunRecoveryRiskRed": param_lab_run_recovery["riskRedCount"],
            "paramLabRunRecoveryRiskYellow": param_lab_run_recovery["riskYellowCount"],
            "paramLabRunRecoveryRetryBudgetExhausted": param_lab_run_recovery["retryBudgetExhaustedCount"],
            "strategyVersionCount": strategy_version_registry["routeCount"],
            "optimizerV2Proposals": optimizer_v2["proposalCount"],
            "optimizerV2WaitingReport": optimizer_v2["waitingReportCount"],
            "versionGateDecisions": version_promotion_gate["versionDecisionCount"],
            "versionGatePromoteCandidates": version_promotion_gate["promoteCandidateCount"],
            "versionGateDemoteLive": version_promotion_gate["demoteLiveCount"],
            "versionGateRetune": version_promotion_gate["retuneCount"],
            "paramLabAutoSchedulerQueue": param_lab_auto_scheduler["queueCount"],
            "paramLabAutoSchedulerWaitReport": param_lab_auto_scheduler["waitReportQueueCount"],
            "paramLabAutoSchedulerRetune": param_lab_auto_scheduler["retuneQueueCount"],
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
        "paramLabResults": param_lab_results,
        "paramLabReportWatcher": param_lab_report_watcher,
        "autoTesterWindow": auto_tester_window,
        "paramLabRunRecovery": param_lab_run_recovery,
        "strategyVersionRegistry": strategy_version_registry,
        "optimizerV2": optimizer_v2,
        "versionPromotionGate": version_promotion_gate,
        "paramLabAutoScheduler": param_lab_auto_scheduler,
        "routeDecisions": route_decisions,
        "governanceFeedback": governance_feedback,
        "nextOperatorSteps": [
            "Keep MA_Cross and USDJPY RSI_Reversal at 0.01 live only while samples remain thin.",
            "Keep BB/MACD/SR in simulation and retune routes with weak 60m candidate outcomes.",
            "Use ParamOptimizationPlan candidates as offline tester tasks only; never overwrite the live preset automatically.",
            "Use ParamLabStatus as the controlled Strategy Tester task queue; CONFIG_READY tasks still require an authorized tester run before promotion review.",
            "Use ParamLabReportWatcher to discover landed Strategy Tester reports, then use ParamLabResults as the parameter-version ranking source; pending or malformed reports are not promotion evidence.",
            "Use VersionPromotionGate as dry-run promotion/demotion review; it never mutates live switches by itself.",
            "Use ParamLabAutoScheduler as the config-only queue for the next tester-only batch; it never adds -RunTerminal.",
            "Use AUTO_TESTER_WINDOW as the only guarded run-terminal bridge; it requires the tester window, an authorization lock, tester-only queue, and profile/config validation.",
            "Use ParamLabRunRecovery to inspect guarded-run history, report missing/parsed/malformed state, retry budget drilldown, and recovery actions before rerunning tasks.",
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
