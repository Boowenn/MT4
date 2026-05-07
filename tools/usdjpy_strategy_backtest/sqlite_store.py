from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

from .schema import FOCUS_SYMBOL, db_path


@dataclass(frozen=True)
class Bar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


BAR_TABLES = {
    "M1": "bars_m1",
    "M5": "bars_m5",
    "M15": "bars_m15",
    "H1": "bars_h1",
}


def connect(runtime_dir: Path) -> sqlite3.Connection:
    path = db_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    for table in BAR_TABLES.values():
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (symbol, timestamp)
            )
            """
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_runs (
            run_id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            net_r REAL NOT NULL,
            trade_count INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_trades (
            run_id TEXT NOT NULL,
            trade_id TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            profit_r REAL NOT NULL,
            profit_pips REAL NOT NULL,
            PRIMARY KEY (run_id, trade_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_curves (
            run_id TEXT NOT NULL,
            index_no INTEGER NOT NULL,
            equity_r REAL NOT NULL,
            PRIMARY KEY (run_id, index_no)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fitness_cache (
            strategy_fingerprint TEXT PRIMARY KEY,
            report_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def upsert_bars(conn: sqlite3.Connection, timeframe: str, bars: Iterable[Bar]) -> None:
    table = BAR_TABLES[timeframe]
    conn.executemany(
        f"""
        INSERT OR REPLACE INTO {table}
        (symbol, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(FOCUS_SYMBOL, item.timestamp, item.open, item.high, item.low, item.close, item.volume) for item in bars],
    )
    conn.commit()


def load_bars(conn: sqlite3.Connection, timeframe: str, limit: int = 1000) -> List[Bar]:
    table = BAR_TABLES[timeframe]
    rows = conn.execute(
        f"""
        SELECT timestamp, open, high, low, close, volume
        FROM {table}
        WHERE symbol = ?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (FOCUS_SYMBOL, int(limit)),
    ).fetchall()
    return [
        Bar(
            timestamp=str(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for row in rows
    ]


def count_bars(conn: sqlite3.Connection, timeframe: str) -> int:
    table = BAR_TABLES[timeframe]
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE symbol = ?", (FOCUS_SYMBOL,)).fetchone()
    return int(row["count"] if row else 0)


def write_sample_bars(runtime_dir: Path, overwrite: bool = False) -> dict:
    with connect(runtime_dir) as conn:
        if overwrite:
            for table in BAR_TABLES.values():
                conn.execute(f"DELETE FROM {table} WHERE symbol = ?", (FOCUS_SYMBOL,))
            conn.commit()
        bars = sample_h1_bars()
        upsert_bars(conn, "H1", bars)
        return {"symbol": FOCUS_SYMBOL, "timeframe": "H1", "barCount": count_bars(conn, "H1")}


def sample_h1_bars(count: int = 180) -> List[Bar]:
    """Create deterministic USDJPY H1 bars with RSI oversold/recovery phases."""
    start = datetime(2026, 4, 28, 0, 0, tzinfo=timezone.utc)
    price = 156.20
    bars: List[Bar] = []
    for index in range(count):
        wave = math.sin(index / 5.0) * 0.035
        drift = -0.018 if index % 45 < 18 else 0.024
        pulse = 0.075 if index in {24, 25, 70, 71, 116, 117, 162, 163} else 0.0
        shock = -0.055 if index in {18, 64, 110, 156} else 0.0
        previous = price
        close = max(150.0, previous + wave + drift + pulse + shock)
        high = max(previous, close) + 0.035 + abs(wave) * 0.35
        low = min(previous, close) - 0.035 - abs(wave) * 0.35
        timestamp = (start + timedelta(hours=index)).isoformat().replace("+00:00", "Z")
        bars.append(
            Bar(
                timestamp=timestamp,
                open=round(previous, 5),
                high=round(high, 5),
                low=round(low, 5),
                close=round(close, 5),
                volume=1000 + (index % 12) * 37,
            )
        )
        price = close
    return bars

