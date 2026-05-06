from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schema import normalize_direction, safe_float

RUNTIME_SNAPSHOT_PATTERNS = (
    "QuantGod_MT5RuntimeSnapshot_*.json",
    "QuantGod_RuntimeSnapshot_*.json",
)
DASHBOARD_NAMES = ("QuantGod_Dashboard.json", "dashboard.json")
OUTCOME_LEDGER_PATTERNS = (
    "ShadowCandidateOutcomeLedger.csv",
    "QuantGod_ShadowCandidateOutcomeLedger.csv",
    "*OutcomeLedger*.csv",
)
CLOSE_HISTORY_PATTERNS = (
    "QuantGod_CloseHistory*.csv",
    "*CloseHistory*.csv",
)
STRATEGY_EVAL_PATTERNS = (
    "QuantGod_StrategyEvaluationReport.csv",
    "*StrategyEvaluation*.csv",
)
JOURNAL_NAMES = (
    "QuantGod_AIAdvisoryJournal.jsonl",
    "QuantGod_AIAdvisoryOutcomes.jsonl",
)
FASTLANE_QUALITY_NAMES = (
    "quality/QuantGod_MT5FastLaneQuality.json",
    "QuantGod_MT5FastLaneQuality.json",
)
STRATEGY_ALIASES = {
    "RSI_REVERSAL_SHADOW": "RSI_Reversal",
    "USDJPY_RSI_H1_LIVE_CANDIDATE": "RSI_Reversal",
    "QG_RSI_REV_MT5": "RSI_Reversal",
    "BB_TRIPLE_SHADOW": "BB_Triple",
    "BB_TRIPLE_H1_LEGACY_CANDIDATE": "BB_Triple",
    "MACD_DIVERGENCE_SHADOW": "MACD_Divergence",
    "MACD_DIVERGENCE_H1_LEGACY_CANDIDATE": "MACD_Divergence",
    "SR_BREAKOUT_SHADOW": "SR_Breakout",
    "SR_BREAKOUT_H1_LEGACY_CANDIDATE": "SR_Breakout",
}

@dataclass
class RuntimeEvidence:
    runtime_dir: Path
    snapshots: list[dict[str, Any]]
    dashboard: dict[str, Any] | None
    outcome_rows: list[dict[str, Any]]
    close_history_rows: list[dict[str, Any]]
    strategy_eval_rows: list[dict[str, Any]]
    journal_rows: list[dict[str, Any]]
    fastlane_quality: dict[str, Any] | None

    @property
    def symbols(self) -> list[str]:
        values: set[str] = set()
        for row in self.snapshots + self.outcome_rows + self.close_history_rows + self.strategy_eval_rows + self.journal_rows:
            symbol = first_value(row, "symbol", "Symbol", "sym", "instrument")
            if symbol:
                values.add(str(symbol))
        return sorted(values)

def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            mtime = path.stat().st_mtime
            payload.setdefault("_path", str(path))
            payload.setdefault("_fileMtimeIso", datetime.fromtimestamp(mtime, timezone.utc).isoformat())
            payload.setdefault("_fileAgeSeconds", max(0.0, time.time() - mtime))
        return payload
    except Exception:
        return None

def read_jsonl(path: Path, limit: int = 2000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return rows
    return rows[-limit:]

def read_csv(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            rows = [dict(row) for row in reader if row]
            return rows[-limit:]
    except Exception:
        try:
            with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = [dict(row) for row in reader if row]
                return rows[-limit:]
        except Exception:
            return []

def find_files(runtime_dir: Path, patterns: Iterable[str], recursive: bool = True) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        iterator = runtime_dir.rglob(pattern) if recursive else runtime_dir.glob(pattern)
        found.extend(path for path in iterator if path.is_file())
    unique = sorted(set(found), key=lambda p: (p.stat().st_mtime if p.exists() else 0, str(p)))
    return unique

def load_runtime_evidence(runtime_dir: str | Path, max_records: int = 500) -> RuntimeEvidence:
    root = Path(runtime_dir).expanduser().resolve()
    snapshots: list[dict[str, Any]] = []
    for path in find_files(root, RUNTIME_SNAPSHOT_PATTERNS):
        item = read_json(path)
        if isinstance(item, dict):
            item.setdefault("_path", str(path))
            snapshots.append(item)

    dashboard = None
    for name in DASHBOARD_NAMES:
        candidate = root / name
        dashboard = read_json(candidate)
        if dashboard:
            dashboard = normalize_dashboard_snapshot(dashboard)
            break

    outcome_rows: list[dict[str, Any]] = []
    for path in find_files(root, OUTCOME_LEDGER_PATTERNS):
        outcome_rows.extend(read_csv(path, limit=max_records))

    close_history_rows: list[dict[str, Any]] = []
    for path in find_files(root, CLOSE_HISTORY_PATTERNS):
        close_history_rows.extend(read_csv(path, limit=max_records))

    strategy_eval_rows: list[dict[str, Any]] = []
    for path in find_files(root, STRATEGY_EVAL_PATTERNS):
        strategy_eval_rows.extend(read_csv(path, limit=max_records))

    journal_rows: list[dict[str, Any]] = []
    for name in JOURNAL_NAMES:
        direct = root / "journal" / name
        journal_rows.extend(read_jsonl(direct, limit=max_records))
        direct2 = root / name
        journal_rows.extend(read_jsonl(direct2, limit=max_records))

    fastlane_quality = None
    for name in FASTLANE_QUALITY_NAMES:
        candidate = root / name
        fastlane_quality = read_json(candidate)
        if fastlane_quality:
            fastlane_quality.setdefault("_path", str(candidate))
            break
    fastlane_quality = normalize_fastlane_quality(fastlane_quality, dashboard)

    return RuntimeEvidence(
        runtime_dir=root,
        snapshots=snapshots[-max_records:],
        dashboard=dashboard,
        outcome_rows=outcome_rows[-max_records:],
        close_history_rows=close_history_rows[-max_records:],
        strategy_eval_rows=strategy_eval_rows[-max_records:],
        journal_rows=journal_rows[-max_records:],
        fastlane_quality=fastlane_quality,
    )

def normalize_dashboard_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt the live HFM EA Dashboard into runtime-snapshot fields used by policy gates."""
    data = dict(payload)
    runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    market = data.get("market") if isinstance(data.get("market"), dict) else {}
    symbol = market.get("symbol") or data.get("watchlist") or data.get("symbol") or data.get("Symbol")
    file_age = safe_float(data.get("_fileAgeSeconds"), 9999.0)
    tick_age = safe_float(runtime.get("tickAgeSeconds"), 9999.0)
    runtime_fresh = bool(data.get("runtimeFresh")) or file_age <= 300 or tick_age <= 30
    data.setdefault("symbol", symbol)
    data.setdefault("source", "hfm_ea_dashboard")
    data.setdefault("snapshotSource", "hfm_ea_dashboard")
    data.setdefault("fallback", False)
    data.setdefault("runtimeAgeSeconds", 0 if tick_age <= 30 else file_age)
    data.setdefault("runtimeFresh", runtime_fresh)
    data.setdefault("current_price", {
        "bid": market.get("bid"),
        "ask": market.get("ask"),
        "spread": market.get("spread"),
        "timeIso": runtime.get("serverTime") or runtime.get("localTime") or data.get("timestamp"),
    })
    return data

def _empty_fastlane_exporter(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict) or payload.get("heartbeatFound") is not False:
        return False
    symbols = payload.get("symbols")
    rows: list[dict[str, Any]] = []
    if isinstance(symbols, list):
        rows = [item for item in symbols if isinstance(item, dict)]
    elif isinstance(symbols, dict):
        rows = [item for item in symbols.values() if isinstance(item, dict)]
    elif isinstance(payload, dict):
        rows = [payload]
    if not rows:
        return True
    for row in rows:
        tick_rows = safe_float(row.get("tickRows"), 0.0)
        tick_age = row.get("tickAgeSeconds")
        indicator_age = row.get("indicatorAgeSeconds")
        if tick_rows > 0 or tick_age not in (None, "", "null") or indicator_age not in (None, "", "null"):
            return False
    return True

def _dashboard_is_fresh(dashboard: dict[str, Any] | None) -> bool:
    if not dashboard:
        return False
    runtime = dashboard.get("runtime") if isinstance(dashboard.get("runtime"), dict) else {}
    return bool(dashboard.get("runtimeFresh")) or safe_float(dashboard.get("runtimeAgeSeconds"), 9999.0) <= 300 or safe_float(runtime.get("tickAgeSeconds"), 9999.0) <= 30

def normalize_fastlane_quality(payload: dict[str, Any] | None, dashboard: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _empty_fastlane_exporter(payload) or not _dashboard_is_fresh(dashboard):
        return payload
    market = dashboard.get("market") if isinstance(dashboard.get("market"), dict) else {}
    runtime = dashboard.get("runtime") if isinstance(dashboard.get("runtime"), dict) else {}
    symbol = market.get("symbol") or dashboard.get("symbol") or dashboard.get("watchlist") or "USDJPYc"
    return {
        "schema": "quantgod.mt5.fast_lane_quality.dashboard_fallback.v1",
        "heartbeatFound": False,
        "heartbeatFresh": True,
        "heartbeatAgeSeconds": dashboard.get("runtimeAgeSeconds"),
        "dashboardFallback": True,
        "quality": "EA_DASHBOARD_OK",
        "symbols": [{
            "symbol": symbol,
            "quality": "EA_DASHBOARD_OK",
            "tickAgeSeconds": runtime.get("tickAgeSeconds"),
            "indicatorAgeSeconds": None,
            "tickRows": 0,
            "spreadPoints": market.get("spread"),
            "note": "独立快通道未挂载，使用 HFM EA Dashboard 新鲜快照作为降级运行证据。",
        }],
        "safety": {
            "readOnlyDataPlane": True,
            "orderSendAllowed": False,
            "brokerExecutionAllowed": False,
            "livePresetMutationAllowed": False,
        },
    }

def first_value(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value not in (None, ""):
            return value
    return default

def canonical_strategy(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    upper = text.upper()
    return STRATEGY_ALIASES.get(upper, text)

def parse_iso_age_seconds(value: Any) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()))
    except Exception:
        return None

def latest_snapshot_for_symbol(evidence: RuntimeEvidence, symbol: str | None = None) -> dict[str, Any] | None:
    candidates = evidence.snapshots
    if symbol:
        candidates = [s for s in candidates if str(first_value(s, "symbol", "Symbol", default="")).upper() == symbol.upper()]
    if not candidates:
        dashboard = evidence.dashboard
        if not dashboard or not symbol:
            return dashboard
        dashboard_symbol = str(first_value(dashboard, "symbol", "Symbol", "watchlist", default="")).upper()
        market = dashboard.get("market") if isinstance(dashboard.get("market"), dict) else {}
        market_symbol = str(market.get("symbol") or "").upper()
        if dashboard_symbol == symbol.upper() or market_symbol == symbol.upper():
            return dashboard
        return None
    def stamp(item: dict[str, Any]) -> str:
        return str(first_value(item, "generatedAt", "timeIso", "timestamp", default=""))
    return sorted(candidates, key=stamp)[-1]

def row_to_observation(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    symbol = str(first_value(row, "symbol", "Symbol", "sym", default="")).strip()
    if not symbol:
        return None
    strategy = canonical_strategy(first_value(row, "strategy", "Strategy", "route", "Route", "CandidateRoute", "comment", "Comment", default="UNKNOWN"))
    direction = normalize_direction(first_value(row, "direction", "Direction", "CandidateDirection", "side", "Side", "Type", "action", "Action", "fusionFinalAction", "finalAction", "type"))
    regime = str(first_value(row, "regime", "Regime", "marketRegime", "state", "State", default="UNKNOWN")).strip() or "UNKNOWN"

    profit = first_value(row, "scoreR", "ScoreR", "r", "R", "profit", "Profit", "pnl", "PnL", "netProfit", "NetProfit", "pips", "Pips", "outcomePips", "OutcomePips", default=None)
    if profit is None:
        if direction == "LONG":
            profit = first_value(row, "LongClosePips", "LongPips", "LongOutcomePips", default=None)
        elif direction == "SHORT":
            profit = first_value(row, "ShortClosePips", "ShortPips", "ShortOutcomePips", default=None)
    score_r = safe_float(profit, 0.0)

    # Some ledgers use directionCorrect or win flags rather than direct PnL.
    correct = first_value(row, "directionCorrect", "DirectionCorrect", "win", "Win", "isWin", "IsWin", default=None)
    if correct is not None and str(correct).strip() != "":
        text = str(correct).strip().lower()
        if text in {"true", "1", "yes", "y", "win", "correct", "盈利"}:
            score_r = max(score_r, 0.1)
        elif text in {"false", "0", "no", "n", "loss", "incorrect", "亏损"}:
            score_r = min(score_r, -0.1)

    if direction == "LONG":
        mfe_value = first_value(row, "mfe", "MFE", "LongMFEPips", "maxFavorableMove", "MaxFavorableMove", "mfePips", "MFEPips", default=0.0)
        mae_value = first_value(row, "mae", "MAE", "LongMAEPips", "maxAdverseMove", "MaxAdverseMove", "maePips", "MAEPips", default=0.0)
    elif direction == "SHORT":
        mfe_value = first_value(row, "mfe", "MFE", "ShortMFEPips", "maxFavorableMove", "MaxFavorableMove", "mfePips", "MFEPips", default=0.0)
        mae_value = first_value(row, "mae", "MAE", "ShortMAEPips", "maxAdverseMove", "MaxAdverseMove", "maePips", "MAEPips", default=0.0)
    else:
        mfe_value = first_value(row, "mfe", "MFE", "maxFavorableMove", "MaxFavorableMove", "mfePips", "MFEPips", default=0.0)
        mae_value = first_value(row, "mae", "MAE", "maxAdverseMove", "MaxAdverseMove", "maePips", "MAEPips", default=0.0)
    mfe = safe_float(mfe_value, 0.0)
    mae = safe_float(mae_value, 0.0)
    spread = safe_float(first_value(row, "spread", "Spread", default=0.0), 0.0)

    return {
        "source": source,
        "symbol": symbol,
        "strategy": strategy,
        "direction": direction,
        "regime": regime,
        "scoreR": score_r,
        "win": score_r > 0,
        "mfe": mfe,
        "mae": mae,
        "spread": spread,
        "raw": row,
    }

def collect_observations(evidence: RuntimeEvidence) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for source, rows in (
        ("shadow_outcome", evidence.outcome_rows),
        ("close_history", evidence.close_history_rows),
        ("journal", evidence.journal_rows),
    ):
        for row in rows:
            obs = row_to_observation(row, source)
            if obs:
                observations.append(obs)
    return observations
