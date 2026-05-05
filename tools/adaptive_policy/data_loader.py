from __future__ import annotations

import csv
import json
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
        return json.loads(path.read_text(encoding="utf-8"))
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
            dashboard.setdefault("_path", str(candidate))
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
        return evidence.dashboard
    def stamp(item: dict[str, Any]) -> str:
        return str(first_value(item, "generatedAt", "timeIso", "timestamp", default=""))
    return sorted(candidates, key=stamp)[-1]

def row_to_observation(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    symbol = str(first_value(row, "symbol", "Symbol", "sym", default="")).strip()
    if not symbol:
        return None
    strategy = str(first_value(row, "strategy", "Strategy", "route", "Route", "comment", "Comment", default="UNKNOWN")).strip() or "UNKNOWN"
    direction = normalize_direction(first_value(row, "direction", "Direction", "side", "Side", "action", "Action", "fusionFinalAction", "finalAction", "type"))
    regime = str(first_value(row, "regime", "Regime", "marketRegime", "state", "State", default="UNKNOWN")).strip() or "UNKNOWN"

    profit = first_value(row, "scoreR", "ScoreR", "r", "R", "profit", "Profit", "pnl", "PnL", "netProfit", "NetProfit", "pips", "Pips", "outcomePips", "OutcomePips", default=None)
    score_r = safe_float(profit, 0.0)

    # Some ledgers use directionCorrect or win flags rather than direct PnL.
    correct = first_value(row, "directionCorrect", "DirectionCorrect", "win", "Win", "isWin", "IsWin", default=None)
    if correct is not None and str(correct).strip() != "":
        text = str(correct).strip().lower()
        if text in {"true", "1", "yes", "y", "win", "correct", "盈利"}:
            score_r = max(score_r, 0.1)
        elif text in {"false", "0", "no", "n", "loss", "incorrect", "亏损"}:
            score_r = min(score_r, -0.1)

    mfe = safe_float(first_value(row, "mfe", "MFE", "maxFavorableMove", "MaxFavorableMove", "mfePips", "MFEPips", default=0.0), 0.0)
    mae = safe_float(first_value(row, "mae", "MAE", "maxAdverseMove", "MaxAdverseMove", "maePips", "MAEPips", default=0.0), 0.0)
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
