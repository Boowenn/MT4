from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.strategy_json.schema import ALLOWED_STRATEGY_FAMILIES, base_strategy_seed
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.schema import ALLOWED_STRATEGY_FAMILIES, base_strategy_seed

from .schema import (
    AGENT_VERSION,
    FOCUS_SYMBOL,
    SAFETY_BOUNDARY,
    equity_path,
    history_sync_report_path,
    ingest_report_path,
    report_path,
    trades_path,
)
from .sqlite_store import (
    bar_coverage_summary,
    connect,
    count_bars,
    ingest_runtime_snapshot,
    load_bars,
    latest_bar_time,
    write_sample_bars,
    write_strategy_run,
)
from .strategy_runner import SUPPORTED_BACKTEST_FAMILIES, run_strategy


def status(runtime_dir: Path) -> Dict[str, Any]:
    with connect(runtime_dir) as conn:
        bar_counts = {timeframe: count_bars(conn, timeframe) for timeframe in ("M1", "M5", "M15", "H1", "H4", "D1")}
        latest_bars = {timeframe: latest_bar_time(conn, timeframe) for timeframe in ("M1", "M5", "M15", "H1", "H4", "D1")}
        history_coverage = bar_coverage_summary(conn)
    report = _load_json(report_path(runtime_dir))
    ingest_report = _load_json(ingest_report_path(runtime_dir))
    history_sync_report = _load_json(history_sync_report_path(runtime_dir))
    return {
        "ok": True,
        "schema": "quantgod.strategy_backtest.status.v1",
        "agentVersion": AGENT_VERSION,
        "symbol": FOCUS_SYMBOL,
        "barCounts": bar_counts,
        "latestBars": latest_bars,
        "historyCoverage": history_coverage,
        "ingestReport": ingest_report,
        "historySyncReport": history_sync_report,
        "latestReport": report,
        "paths": {
            "sqlite": str((runtime_dir / "backtest" / "usdjpy.sqlite").resolve()),
            "report": str(report_path(runtime_dir).resolve()),
            "trades": str(trades_path(runtime_dir).resolve()),
            "equity": str(equity_path(runtime_dir).resolve()),
        },
        "safety": dict(SAFETY_BOUNDARY),
    }


def build_sample(runtime_dir: Path, overwrite: bool = False) -> Dict[str, Any]:
    result = write_sample_bars(runtime_dir, overwrite=overwrite)
    return {
        "ok": True,
        "schema": "quantgod.strategy_backtest.sample.v1",
        "agentVersion": AGENT_VERSION,
        **result,
        "safety": dict(SAFETY_BOUNDARY),
    }


def run_backtest(
    runtime_dir: Path,
    strategy_json: Dict[str, Any] | None = None,
    write: bool = True,
    include_coverage_matrix: bool = True,
) -> Dict[str, Any]:
    seed = strategy_json or base_strategy_seed("STRATEGY-BACKTEST-USDJPY-RSI-LONG")
    ingest_report = ingest_runtime_snapshot(runtime_dir)
    with connect(runtime_dir) as conn:
        if count_bars(conn, "H1") < 40:
            write_sample_bars(runtime_dir, overwrite=False)
        bars_by_timeframe = {
            timeframe: load_bars(conn, timeframe, limit=5000)
            for timeframe in ("M1", "M5", "M15", "H1", "H4", "D1")
        }
        multi_timeframe = {
            timeframe: {
                "barCount": count_bars(conn, timeframe),
                "latestBar": latest_bar_time(conn, timeframe),
            }
            for timeframe in ("M1", "M5", "M15", "H1", "H4", "D1")
        }
        history_coverage = bar_coverage_summary(conn)
    result = run_strategy(seed, bars_by_timeframe)
    strategy_coverage = (
        _multi_strategy_coverage_matrix(bars_by_timeframe)
        if include_coverage_matrix
        else _coverage_matrix_skipped("per-seed GA scoring skips full multi-strategy matrix to keep evolution fast")
    )
    report = _report_payload(
        seed,
        result,
        bars_by_timeframe,
        ingest_report,
        multi_timeframe,
        history_coverage,
        strategy_coverage,
    )
    if write:
        write_outputs(runtime_dir, report, result.get("trades", []), result.get("equityCurve", []))
    return report


def write_outputs(runtime_dir: Path, report: Dict[str, Any], trades: List[Dict[str, Any]], equity: List[float]) -> None:
    root = runtime_dir / "backtest"
    root.mkdir(parents=True, exist_ok=True)
    report_path(runtime_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    trade_fields = [
        "tradeId",
        "symbol",
        "direction",
        "entryTime",
        "exitTime",
        "entryPrice",
        "exitPrice",
        "exitReason",
        "riskPips",
        "profitPips",
        "profitR",
        "mfeR",
        "maeR",
    ]
    with trades_path(runtime_dir).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=trade_fields)
        writer.writeheader()
        for row in trades:
            writer.writerow({field: row.get(field, "") for field in trade_fields})

    with equity_path(runtime_dir).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["index", "equityR"])
        writer.writeheader()
        for index, value in enumerate(equity, start=1):
            writer.writerow({"index": index, "equityR": value})
    with connect(runtime_dir) as conn:
        write_strategy_run(conn, report)


def ingest_klines(runtime_dir: Path) -> Dict[str, Any]:
    return ingest_runtime_snapshot(runtime_dir)


def _report_payload(
    seed: Dict[str, Any],
    result: Dict[str, Any],
    bars_by_timeframe: Dict[str, List[Any]],
    ingest_report: Dict[str, Any],
    multi_timeframe: Dict[str, Any],
    history_coverage: Dict[str, Any],
    strategy_coverage: Dict[str, Any],
) -> Dict[str, Any]:
    strategy = result.get("strategyJson") if isinstance(result.get("strategyJson"), dict) else seed
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    engine = result.get("engine") if isinstance(result.get("engine"), dict) else {}
    primary_timeframe = str(engine.get("primaryTimeframe") or "H1")
    primary_bars = bars_by_timeframe.get(primary_timeframe, [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = _run_id(strategy, now)
    return {
        "ok": bool(result.get("ok")),
        "schema": "quantgod.strategy_backtest.report.v1",
        "agentVersion": AGENT_VERSION,
        "runId": run_id,
        "createdAt": now,
        "symbol": FOCUS_SYMBOL,
        "timeframe": primary_timeframe,
        "strategyId": strategy.get("strategyId"),
        "seedId": strategy.get("seedId"),
        "strategyFamily": strategy.get("strategyFamily"),
        "direction": strategy.get("direction"),
        "barCount": len(primary_bars),
        "multiTimeframe": {
            "primaryTimeframe": primary_timeframe,
            "confirmationTimeframes": [
                item
                for item in ("M1", "M5", "M15", "H1", "H4", "D1")
                if item != primary_timeframe
            ],
            "contexts": multi_timeframe,
            "runnerZh": "Strategy JSON runner 会读取 USDJPY 多周期 SQLite K线，并按策略族选择主执行周期。",
        },
        "engine": engine,
        "klineIngest": ingest_report,
        "historyCoverage": history_coverage,
        "strategyCoverageMatrix": strategy_coverage,
        "tradeCount": int(metrics.get("tradeCount", 0)),
        "metrics": metrics,
        "trades": result.get("trades", []),
        "equityCurve": result.get("equityCurve", []),
        "validation": result.get("validation", {}),
        "reasonZh": result.get("reasonZh"),
        "evidenceQuality": _evidence_quality(len(primary_bars), int(metrics.get("tradeCount", 0))),
        "singleSourceOfTruth": "STRATEGY_JSON_USDJPY_SQLITE_BACKTEST",
        "safety": dict(SAFETY_BOUNDARY),
    }


def _evidence_quality(bar_count: int, trade_count: int) -> str:
    if bar_count >= 720 and trade_count >= 20:
        return "HIGH"
    if bar_count >= 160 and trade_count >= 3:
        return "MEDIUM"
    return "LOW"


def _coverage_matrix_skipped(reason: str) -> Dict[str, Any]:
    return {
        "schema": "quantgod.strategy_backtest_coverage_matrix.v1",
        "status": "SKIPPED",
        "reasonZh": reason,
        "families": sorted(ALLOWED_STRATEGY_FAMILIES),
        "rows": [],
        "summary": {
            "familyCount": len(ALLOWED_STRATEGY_FAMILIES),
            "routeCount": 0,
            "coveredFamilyCount": len(SUPPORTED_BACKTEST_FAMILIES),
            "okRouteCount": 0,
            "tradeRouteCount": 0,
        },
    }


def _multi_strategy_coverage_matrix(bars_by_timeframe: Dict[str, List[Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for family in sorted(ALLOWED_STRATEGY_FAMILIES):
        for direction in ("LONG", "SHORT"):
            seed = base_strategy_seed(f"COVERAGE-{family}-{direction}", family=family, direction=direction)
            try:
                result = run_strategy(seed, bars_by_timeframe)
            except Exception as exc:  # pragma: no cover - defensive audit path
                result = {
                    "ok": False,
                    "metrics": {},
                    "engine": {},
                    "reasonZh": f"coverage runner failed: {exc}",
                }
            metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
            engine = result.get("engine") if isinstance(result.get("engine"), dict) else {}
            trade_count = int(float(metrics.get("tradeCount") or 0))
            ok = bool(result.get("ok"))
            rows.append(
                {
                    "strategyFamily": family,
                    "direction": direction,
                    "runnerCovered": family in SUPPORTED_BACKTEST_FAMILIES,
                    "ok": ok,
                    "status": "PASS" if ok else "FAILED",
                    "tradeCount": trade_count,
                    "netR": metrics.get("netR", 0),
                    "profitFactor": metrics.get("profitFactor", 0),
                    "winRate": metrics.get("winRate", 0),
                    "maxDrawdownR": metrics.get("maxDrawdownR", 0),
                    "sharpe": metrics.get("sharpe", 0),
                    "sortino": metrics.get("sortino", 0),
                    "parityVectorPresent": isinstance(engine.get("parityVector"), dict),
                    "signalCount": engine.get("signalCount", 0),
                    "reasonZh": result.get("reasonZh") or ("covered" if ok else "runner failed"),
                }
            )
    ok_routes = [row for row in rows if row["ok"]]
    trade_routes = [row for row in rows if int(row.get("tradeCount") or 0) > 0]
    return {
        "schema": "quantgod.strategy_backtest_coverage_matrix.v1",
        "status": "PASS" if len(ok_routes) == len(rows) else "WARN",
        "families": sorted(ALLOWED_STRATEGY_FAMILIES),
        "directions": ["LONG", "SHORT"],
        "rows": rows,
        "summary": {
            "familyCount": len(ALLOWED_STRATEGY_FAMILIES),
            "routeCount": len(rows),
            "coveredFamilyCount": len({row["strategyFamily"] for row in ok_routes}),
            "okRouteCount": len(ok_routes),
            "tradeRouteCount": len(trade_routes),
            "parityVectorRouteCount": sum(1 for row in rows if row.get("parityVectorPresent")),
        },
        "reasonZh": "全部 USDJPY Strategy JSON 策略族已进入多策略回测覆盖矩阵；实盘仍只允许 RSI_Reversal LONG。",
    }


def _run_id(strategy: Dict[str, Any], created_at: str) -> str:
    raw = json.dumps(
        {
            "strategyId": strategy.get("strategyId"),
            "seedId": strategy.get("seedId"),
            "createdAt": created_at,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"BT-{digest}"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}
