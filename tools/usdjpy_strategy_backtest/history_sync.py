from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .schema import FOCUS_SYMBOL, SAFETY_BOUNDARY, history_sync_report_path
from .sqlite_store import (
    Bar,
    bar_coverage_summary,
    connect,
    count_bars,
    earliest_bar_time,
    ingest_runtime_snapshot,
    latest_bar_time,
    upsert_bars,
)

DEFAULT_HISTORY_TIMEFRAMES = ("M1", "M5", "M15", "H1")
TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}
MT5_TIMEFRAME_ATTRS = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "H1": "TIMEFRAME_H1",
}
CHUNK_DAYS = {"M1": 21, "M5": 60, "M15": 120, "H1": 180}


def sync_historical_klines(
    runtime_dir: Path,
    *,
    months: int = 12,
    lookback_days: int | None = None,
    timeframes: Iterable[str] | None = None,
    symbol: str | None = None,
    terminal_path: str | None = None,
    full_refresh: bool = False,
    max_bars_per_timeframe: int = 700000,
    write: bool = True,
) -> Dict[str, Any]:
    """Incrementally sync real USDJPY bars from the local MT5 terminal into SQLite."""
    runtime_dir = Path(runtime_dir)
    selected_timeframes = _normalize_timeframes(timeframes)
    target_days = int(lookback_days or max(180, int(months) * 31))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    target_start = now - timedelta(days=target_days)
    mt5_symbol = symbol or os.environ.get("QG_USDJPY_MT5_SYMBOL") or FOCUS_SYMBOL
    terminal = terminal_path or os.environ.get("QG_MT5_TERMINAL_PATH") or ""
    mt5, mt5_status = _load_mt5(terminal)
    report: Dict[str, Any] = {
        "ok": False,
        "schema": "quantgod.usdjpy_historical_kline_sync_report.v1",
        "agentVersion": "perfect-v1.0",
        "symbol": FOCUS_SYMBOL,
        "sourceSymbol": mt5_symbol,
        "source": "MT5_COPY_RATES_RANGE",
        "timeframes": selected_timeframes,
        "targetLookbackDays": target_days,
        "targetStart": _iso(target_start),
        "targetEnd": _iso(now),
        "fullRefresh": bool(full_refresh),
        "maxBarsPerTimeframe": int(max_bars_per_timeframe),
        "mt5": mt5_status,
        "sync": {},
        "fallback": {},
        "safety": dict(SAFETY_BOUNDARY),
    }
    try:
        if mt5 is not None:
            _select_symbol(mt5, mt5_symbol)
            with connect(runtime_dir) as conn:
                report["sync"] = _sync_from_mt5(
                    conn=conn,
                    mt5=mt5,
                    symbol=mt5_symbol,
                    timeframes=selected_timeframes,
                    target_start=target_start,
                    target_end=now,
                    full_refresh=full_refresh,
                    max_bars_per_timeframe=max_bars_per_timeframe,
                )
                report["historyCoverage"] = bar_coverage_summary(conn)
            report["ok"] = any(item.get("receivedBars", 0) > 0 for item in report["sync"].values())
            report["historyTargetSatisfied"] = _target_satisfied(report.get("historyCoverage", {}), target_days)
            report["reasonZh"] = _reason(report)
        else:
            report["source"] = "RUNTIME_SNAPSHOT_FALLBACK"
            report["fallback"] = ingest_runtime_snapshot(runtime_dir)
            with connect(runtime_dir) as conn:
                report["historyCoverage"] = bar_coverage_summary(conn)
            report["ok"] = bool(report["fallback"].get("ok"))
            report["historyTargetSatisfied"] = False
            report["reasonZh"] = "未连接到本机 MT5 Python 历史数据源，已回退到运行快照增量写入；GA 历史样本仍不足。"
    finally:
        _shutdown_mt5(mt5)
    if write:
        history_sync_report_path(runtime_dir).parent.mkdir(parents=True, exist_ok=True)
        history_sync_report_path(runtime_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _sync_from_mt5(
    *,
    conn: Any,
    mt5: Any,
    symbol: str,
    timeframes: List[str],
    target_start: datetime,
    target_end: datetime,
    full_refresh: bool,
    max_bars_per_timeframe: int,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for timeframe in timeframes:
        before_count = count_bars(conn, timeframe)
        start = _sync_start(conn, timeframe, target_start, full_refresh)
        received = 0
        chunks = 0
        errors: List[str] = []
        cursor = start
        while cursor < target_end and received < max_bars_per_timeframe:
            chunk_end = min(target_end, cursor + timedelta(days=CHUNK_DAYS.get(timeframe, 90)))
            bars, error = _copy_rates(mt5, symbol, timeframe, cursor, chunk_end)
            chunks += 1
            if error:
                errors.append(error)
            if bars:
                remaining = max_bars_per_timeframe - received
                selected = bars[:remaining]
                upsert_bars(conn, timeframe, selected)
                received += len(selected)
            cursor = chunk_end + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
        after_count = count_bars(conn, timeframe)
        result[timeframe] = {
            "timeframe": timeframe,
            "requestedStart": _iso(start),
            "requestedEnd": _iso(target_end),
            "chunkCount": chunks,
            "receivedBars": received,
            "barCountBefore": before_count,
            "barCountAfter": after_count,
            "newBarDelta": max(0, after_count - before_count),
            "earliestBar": earliest_bar_time(conn, timeframe),
            "latestBar": latest_bar_time(conn, timeframe),
            "errors": errors[:5],
        }
    return result


def _sync_start(conn: Any, timeframe: str, target_start: datetime, full_refresh: bool) -> datetime:
    if full_refresh:
        return target_start
    earliest = _parse_iso(earliest_bar_time(conn, timeframe))
    latest = _parse_iso(latest_bar_time(conn, timeframe))
    if earliest is None or latest is None:
        return target_start
    if earliest > target_start + timedelta(days=2):
        return target_start
    overlap = timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * 2)
    return max(target_start, latest - overlap)


def _copy_rates(mt5: Any, symbol: str, timeframe: str, start: datetime, end: datetime) -> Tuple[List[Bar], str | None]:
    try:
        rates = mt5.copy_rates_range(symbol, _mt5_timeframe(mt5, timeframe), start, end)
    except Exception as exc:
        return [], f"copy_rates_range failed: {exc}"
    if rates is None:
        return [], f"copy_rates_range returned no data: {_last_error(mt5)}"
    bars = _rates_to_bars(rates)
    return bars, None


def _rates_to_bars(rates: Any) -> List[Bar]:
    bars: List[Bar] = []
    for row in list(rates):
        timestamp = _row_value(row, "time")
        if timestamp is None:
            continue
        try:
            bars.append(
                Bar(
                    timestamp=_epoch_to_iso(timestamp),
                    open=float(_row_value(row, "open")),
                    high=float(_row_value(row, "high")),
                    low=float(_row_value(row, "low")),
                    close=float(_row_value(row, "close")),
                    volume=float(_row_value(row, "tick_volume", _row_value(row, "real_volume", 0)) or 0),
                )
            )
        except Exception:
            continue
    return sorted(bars, key=lambda item: item.timestamp)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return getattr(row, key, default)


def _load_mt5(terminal_path: str) -> Tuple[Any | None, Dict[str, Any]]:
    try:
        mt5 = importlib.import_module("MetaTrader5")
    except Exception as exc:
        return None, {"ok": False, "status": "PACKAGE_UNAVAILABLE", "detail": str(exc)}
    try:
        initialized = bool(mt5.initialize(path=terminal_path)) if terminal_path else bool(mt5.initialize())
    except Exception as exc:
        return None, {"ok": False, "status": "INITIALIZE_FAILED", "detail": str(exc)}
    if not initialized:
        return None, {"ok": False, "status": "INITIALIZE_FAILED", "detail": _last_error(mt5)}
    return mt5, {"ok": True, "status": "INITIALIZED", "terminalPath": terminal_path or "default"}


def _shutdown_mt5(mt5: Any | None) -> None:
    if mt5 is None:
        return
    try:
        mt5.shutdown()
    except Exception:
        return


def _select_symbol(mt5: Any, symbol: str) -> None:
    try:
        mt5.symbol_select(symbol, True)
    except Exception:
        return


def _mt5_timeframe(mt5: Any, timeframe: str) -> Any:
    return getattr(mt5, MT5_TIMEFRAME_ATTRS[timeframe])


def _last_error(mt5: Any) -> str:
    try:
        return str(mt5.last_error())
    except Exception:
        return ""


def _normalize_timeframes(timeframes: Iterable[str] | None) -> List[str]:
    raw = list(timeframes or DEFAULT_HISTORY_TIMEFRAMES)
    selected: List[str] = []
    for item in raw:
        value = str(item).strip().upper()
        if value in DEFAULT_HISTORY_TIMEFRAMES and value not in selected:
            selected.append(value)
    return selected or list(DEFAULT_HISTORY_TIMEFRAMES)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _epoch_to_iso(value: Any) -> str:
    timestamp = float(value)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _target_satisfied(history_coverage: Dict[str, Any], target_days: int) -> bool:
    timeframes = history_coverage.get("timeframes") if isinstance(history_coverage.get("timeframes"), dict) else {}
    required_days = min(float(target_days) * 0.85, float(target_days) - 7)
    if required_days < 150:
        required_days = 150
    for timeframe in DEFAULT_HISTORY_TIMEFRAMES:
        data = timeframes.get(timeframe) if isinstance(timeframes.get(timeframe), dict) else {}
        if float(data.get("spanDays") or 0) < required_days:
            return False
        if int(data.get("barCount") or 0) <= 0:
            return False
    return True


def _reason(report: Dict[str, Any]) -> str:
    if report.get("historyTargetSatisfied"):
        return "USDJPY M1/M5/M15/H1 历史 K 线已完成 6-12 个月级别增量同步，可用于更可信 GA 回测。"
    if report.get("ok"):
        return "USDJPY 历史 K 线已增量同步，但覆盖窗口还未达到目标；后续定时同步会继续补齐。"
    return "未从 MT5 拉取到 USDJPY 历史 K 线；请确认本机 MT5/HFM 终端已登录并允许 Python copy_rates_range。"
