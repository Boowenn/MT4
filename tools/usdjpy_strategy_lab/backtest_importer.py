from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .data_loader import _get, to_float
from .schema import (
    DEFAULT_STRATEGIES,
    FOCUS_SYMBOL,
    READ_ONLY_SAFETY,
    STRATEGY_DISPLAY_NAMES,
    assert_no_secret_or_execution_flags,
    is_focus_symbol,
    normalize_symbol,
    utc_now_iso,
)

IMPORT_SCHEMA = "quantgod.usdjpy_backtest_import.v1"
IMPORT_LEDGER_NAME = "QuantGod_USDJPYBacktestImports.jsonl"
LATEST_IMPORT_NAME = "QuantGod_USDJPYBacktestImportsLatest.json"


def _adaptive_dir(runtime_dir: Path) -> Path:
    path = runtime_dir / "adaptive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rows_from_json(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("rows", "results", "backtests", "topRows", "strategies"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return [payload]


def _rows_from_csv(path: Path) -> List[Dict[str, Any]]:
    for encoding in ("utf-8-sig", "utf-8", "shift_jis", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except Exception:
            continue
    return []


def _read_source_rows(source: Path) -> List[Dict[str, Any]]:
    suffix = source.suffix.lower()
    if suffix == ".json":
        return _rows_from_json(source)
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for line in source.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows
    return _rows_from_csv(source)


def _strategy(row: Dict[str, Any], fallback: str = "") -> str:
    value = str(_get(row, "strategy", "strategyName", "route", "CandidateRoute", "name", default=fallback)).strip()
    if value in DEFAULT_STRATEGIES:
        return value
    for key in DEFAULT_STRATEGIES:
        if key.lower() in value.lower():
            return key
    return value or "UNKNOWN_STRATEGY"


def _clean_row(row: Dict[str, Any], source: Path, generated_at: str, fallback_strategy: str = "") -> Dict[str, Any] | None:
    symbol = normalize_symbol(_get(row, "symbol", "Symbol", default=FOCUS_SYMBOL))
    if not is_focus_symbol(symbol):
        return None
    strategy = _strategy(row, fallback=fallback_strategy)
    if strategy not in DEFAULT_STRATEGIES:
        return None
    trades = int(to_float(_get(row, "trades", "totalTrades", "Total trades", "closedTrades", default=0)))
    profit_factor = to_float(_get(row, "pf", "PF", "profitFactor", "Profit Factor", default=0.0))
    win_rate = to_float(_get(row, "winRate", "winRatePct", "Win rate", "win_rate", default=0.0))
    if win_rate > 1.0:
        win_rate = win_rate / 100.0
    net_profit = to_float(_get(row, "netProfit", "netProfitUSC", "profit", "pnl", default=0.0))
    max_drawdown = abs(to_float(_get(row, "maxDrawdown", "drawdown", "dd", default=0.0)))
    timeframe = str(_get(row, "timeframe", "tf", "period", default="M15") or "M15").strip()
    window = str(_get(row, "window", "dateRange", "range", "periodRange", default="") or "").strip()
    status = "PROMOTABLE" if trades >= 60 and profit_factor >= 1.15 and win_rate >= 0.5 else "WATCH_ONLY"
    if trades <= 0 or profit_factor <= 0:
        status = "NEEDS_RETEST"
    return {
        "schema": IMPORT_SCHEMA,
        "generatedAt": generated_at,
        "importedAt": generated_at,
        "sourceFile": str(source),
        "symbol": FOCUS_SYMBOL,
        "strategy": strategy,
        "strategyName": STRATEGY_DISPLAY_NAMES.get(strategy, strategy),
        "timeframe": timeframe,
        "window": window,
        "trades": trades,
        "profitFactor": round(profit_factor, 4),
        "winRate": round(win_rate, 4),
        "netProfit": round(net_profit, 4),
        "maxDrawdown": round(max_drawdown, 4),
        "status": status,
        "summary": _get(row, "summary", "comment", "note", default="导入的 USDJPY 回测结果"),
        "safety": dict(READ_ONLY_SAFETY),
    }


def load_imported_backtests(runtime_dir: Path, *, limit: int = 50) -> Dict[str, Any]:
    ledger = _adaptive_dir(runtime_dir) / IMPORT_LEDGER_NAME
    rows: List[Dict[str, Any]] = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    rows = rows[-max(1, limit):]
    rows.reverse()
    payload = {
        "schema": "quantgod.usdjpy_backtest_imports.v1",
        "generatedAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "count": len(rows),
        "imports": rows,
        "safety": dict(READ_ONLY_SAFETY),
    }
    assert_no_secret_or_execution_flags(payload)
    return payload


def import_backtest_results(
    runtime_dir: Path,
    source_path: str | Path,
    *,
    fallback_strategy: str = "",
) -> Dict[str, Any]:
    source = Path(source_path).expanduser()
    generated_at = utc_now_iso()
    if not source.exists() or not source.is_file():
        return {
            "ok": False,
            "error": "BACKTEST_SOURCE_NOT_FOUND",
            "sourceFile": str(source),
            "safety": dict(READ_ONLY_SAFETY),
        }
    rows = _read_source_rows(source)
    accepted = []
    for row in rows:
        cleaned = _clean_row(row, source, generated_at, fallback_strategy=fallback_strategy)
        if cleaned:
            accepted.append(cleaned)
    adaptive = _adaptive_dir(runtime_dir)
    ledger = adaptive / IMPORT_LEDGER_NAME
    if accepted:
        with ledger.open("a", encoding="utf-8") as handle:
            for row in accepted:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    payload = {
        "ok": True,
        "schema": "quantgod.usdjpy_backtest_import_result.v1",
        "generatedAt": generated_at,
        "sourceFile": str(source),
        "sourceRows": len(rows),
        "acceptedRows": len(accepted),
        "skippedRows": max(0, len(rows) - len(accepted)),
        "imports": accepted,
        "safety": dict(READ_ONLY_SAFETY),
    }
    (adaptive / LATEST_IMPORT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    assert_no_secret_or_execution_flags(payload)
    return payload
