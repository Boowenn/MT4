from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.strategy_json.schema import base_strategy_seed
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.schema import base_strategy_seed

from .schema import (
    AGENT_VERSION,
    FOCUS_SYMBOL,
    SAFETY_BOUNDARY,
    equity_path,
    ingest_report_path,
    report_path,
    trades_path,
)
from .sqlite_store import connect, count_bars, ingest_runtime_snapshot, load_bars, latest_bar_time, write_sample_bars
from .strategy_runner import run_strategy


def status(runtime_dir: Path) -> Dict[str, Any]:
    with connect(runtime_dir) as conn:
        bar_counts = {timeframe: count_bars(conn, timeframe) for timeframe in ("M1", "M5", "M15", "H1", "H4", "D1")}
        latest_bars = {timeframe: latest_bar_time(conn, timeframe) for timeframe in ("M15", "H1", "H4", "D1")}
    report = _load_json(report_path(runtime_dir))
    ingest_report = _load_json(ingest_report_path(runtime_dir))
    return {
        "ok": True,
        "schema": "quantgod.strategy_backtest.status.v1",
        "agentVersion": AGENT_VERSION,
        "symbol": FOCUS_SYMBOL,
        "barCounts": bar_counts,
        "latestBars": latest_bars,
        "ingestReport": ingest_report,
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


def run_backtest(runtime_dir: Path, strategy_json: Dict[str, Any] | None = None, write: bool = True) -> Dict[str, Any]:
    seed = strategy_json or base_strategy_seed("STRATEGY-BACKTEST-USDJPY-RSI-LONG")
    ingest_report = ingest_runtime_snapshot(runtime_dir)
    with connect(runtime_dir) as conn:
        if count_bars(conn, "H1") < 40:
            write_sample_bars(runtime_dir, overwrite=False)
        bars = load_bars(conn, "H1", limit=5000)
        multi_timeframe = {
            timeframe: {
                "barCount": count_bars(conn, timeframe),
                "latestBar": latest_bar_time(conn, timeframe),
            }
            for timeframe in ("M15", "H1", "H4", "D1")
        }
    result = run_strategy(seed, bars)
    report = _report_payload(seed, result, bars, ingest_report, multi_timeframe)
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


def ingest_klines(runtime_dir: Path) -> Dict[str, Any]:
    return ingest_runtime_snapshot(runtime_dir)


def _report_payload(
    seed: Dict[str, Any],
    result: Dict[str, Any],
    bars: List[Any],
    ingest_report: Dict[str, Any],
    multi_timeframe: Dict[str, Any],
) -> Dict[str, Any]:
    strategy = result.get("strategyJson") if isinstance(result.get("strategyJson"), dict) else seed
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "ok": bool(result.get("ok")),
        "schema": "quantgod.strategy_backtest.report.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": now,
        "symbol": FOCUS_SYMBOL,
        "timeframe": "H1",
        "strategyId": strategy.get("strategyId"),
        "seedId": strategy.get("seedId"),
        "strategyFamily": strategy.get("strategyFamily"),
        "direction": strategy.get("direction"),
        "barCount": len(bars),
        "multiTimeframe": {
            "primaryTimeframe": "H1",
            "confirmationTimeframes": ["M15", "H4", "D1"],
            "contexts": multi_timeframe,
            "runnerZh": "当前回测以 H1 RSI 为主口径，并把 M15/H4/D1 真实快照入库作为多周期审计上下文。",
        },
        "klineIngest": ingest_report,
        "tradeCount": int(metrics.get("tradeCount", 0)),
        "metrics": metrics,
        "trades": result.get("trades", []),
        "equityCurve": result.get("equityCurve", []),
        "validation": result.get("validation", {}),
        "reasonZh": result.get("reasonZh"),
        "evidenceQuality": _evidence_quality(len(bars), int(metrics.get("tradeCount", 0))),
        "singleSourceOfTruth": "STRATEGY_JSON_USDJPY_SQLITE_BACKTEST",
        "safety": dict(SAFETY_BOUNDARY),
    }


def _evidence_quality(bar_count: int, trade_count: int) -> str:
    if bar_count >= 720 and trade_count >= 20:
        return "HIGH"
    if bar_count >= 160 and trade_count >= 3:
        return "MEDIUM"
    return "LOW"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}
