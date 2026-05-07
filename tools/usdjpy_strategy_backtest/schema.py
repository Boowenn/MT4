from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

AGENT_VERSION = "perfect-v1.0"
FOCUS_SYMBOL = "USDJPYc"
DB_FILE = "usdjpy.sqlite"
REPORT_FILE = "QuantGod_StrategyBacktestReport.json"
TRADES_FILE = "QuantGod_StrategyTrades.csv"
EQUITY_FILE = "QuantGod_StrategyEquityCurve.csv"
INGEST_REPORT_FILE = "QuantGod_USDJPYKlineIngestReport.json"

SAFETY_BOUNDARY: Dict[str, Any] = {
    "usdJpyOnly": True,
    "strategyJsonContract": True,
    "readOnlyResearchPlane": True,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "livePresetMutationAllowed": False,
    "polymarketRealMoneyAllowed": False,
    "telegramCommandExecutionAllowed": False,
    "backtestDirectLiveAllowed": False,
}


def backtest_dir(runtime_dir: Path) -> Path:
    return runtime_dir / "backtest"


def db_path(runtime_dir: Path) -> Path:
    return backtest_dir(runtime_dir) / DB_FILE


def report_path(runtime_dir: Path) -> Path:
    return backtest_dir(runtime_dir) / REPORT_FILE


def trades_path(runtime_dir: Path) -> Path:
    return backtest_dir(runtime_dir) / TRADES_FILE


def equity_path(runtime_dir: Path) -> Path:
    return backtest_dir(runtime_dir) / EQUITY_FILE


def ingest_report_path(runtime_dir: Path) -> Path:
    return backtest_dir(runtime_dir) / INGEST_REPORT_FILE
