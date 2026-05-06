from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import normalize_direction


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_seconds(value: Any) -> Optional[float]:
    dt = _parse_ts(value)
    if not dt:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_csv_rows(path: Path, limit: int = 5000) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
            if len(rows) >= limit:
                break
    return rows


def write_csv_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _first_number(record: Dict[str, Any], keys: List[str], default: float = 0.0) -> float:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            try:
                return float(record[key])
            except (TypeError, ValueError):
                continue
    return default


def _first_text(record: Dict[str, Any], keys: List[str], default: str = "") -> str:
    for key in keys:
        if key in record and str(record[key]).strip():
            return str(record[key]).strip()
    return default


@dataclass
class RuntimeEvidence:
    symbol: str
    snapshot: Dict[str, Any]
    runtime_fresh: bool
    fallback: bool
    age_seconds: Optional[float]
    spread: Optional[float]
    source: str


@dataclass
class FastLaneQuality:
    quality: str
    ok: bool
    reason: str


@dataclass
class EntryGateEvidence:
    passed: bool
    status: str
    reason: str
    raw: Dict[str, Any]


@dataclass
class DynamicSLTPPlan:
    available: bool
    status: str
    initial_stop: str
    targets: str
    raw: Dict[str, Any]


@dataclass
class ShadowStats:
    samples: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    avg_pips: float = 0.0
    consecutive_losses: int = 0


class EvidenceLoader:
    def __init__(self, runtime_dir: str | Path, max_age_seconds: int = 180):
        self.runtime_dir = Path(runtime_dir)
        self.max_age_seconds = max_age_seconds

    def snapshot_for(self, symbol: str) -> RuntimeEvidence:
        candidates = [
            self.runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json",
            self.runtime_dir / f"QuantGod_RuntimeSnapshot_{symbol}.json",
            self.runtime_dir / "QuantGod_Dashboard.json",
        ]
        data: Dict[str, Any] = {}
        for path in candidates:
            loaded = read_json(path, None)
            if isinstance(loaded, dict):
                data = loaded
                break
        current_price = data.get("current_price") or data.get("currentPrice") or data.get("price") or {}
        source = str(data.get("source") or data.get("snapshotSource") or "missing_runtime")
        generated = data.get("generatedAt") or data.get("timeIso") or current_price.get("timeIso") or data.get("timestamp")
        age = _age_seconds(generated)
        fallback = bool(data.get("fallback", False)) or source in {"mock", "fallback", "mt5_python_unavailable", "missing_runtime"}
        runtime_fresh = bool(data) and not fallback and (age is None or age <= self.max_age_seconds)
        spread = None
        for value in [current_price.get("spread"), data.get("spread"), data.get("spreadPoints")]:
            if value not in (None, ""):
                try:
                    spread = float(value)
                    break
                except (TypeError, ValueError):
                    pass
        return RuntimeEvidence(symbol=symbol, snapshot=data, runtime_fresh=runtime_fresh, fallback=fallback, age_seconds=age, spread=spread, source=source)

    def fastlane_quality(self, symbol: str) -> FastLaneQuality:
        paths = [
            self.runtime_dir / "quality" / "QuantGod_MT5FastLaneQuality.json",
            self.runtime_dir / "adaptive" / "QuantGod_MT5FastLaneQuality.json",
            self.runtime_dir / "QuantGod_MT5FastLaneQuality.json",
        ]
        data: Dict[str, Any] = {}
        for path in paths:
            loaded = read_json(path, None)
            if isinstance(loaded, dict):
                data = loaded
                break
        if not data:
            return FastLaneQuality("MISSING", False, "缺少快通道质量证据")
        symbol_rows = data.get("symbols")
        if isinstance(symbol_rows, list):
            symbol_data = next(
                (
                    row
                    for row in symbol_rows
                    if isinstance(row, dict) and str(row.get("symbol") or "") == symbol
                ),
                data,
            )
        elif isinstance(symbol_rows, dict):
            symbol_data = symbol_rows.get(symbol) or data.get(symbol) or data
        else:
            symbol_data = data.get(symbol) or data
        quality = str(symbol_data.get("quality") or symbol_data.get("status") or data.get("quality") or "UNKNOWN").upper()
        ok = quality in {"OK", "PASS", "PASSED", "GOOD", "HEALTHY", "FAST", "EA_DASHBOARD_OK"}
        reason = str(symbol_data.get("reason") or data.get("reason") or ("快通道质量通过" if ok else f"快通道质量为 {quality}"))
        return FastLaneQuality(quality, ok, reason)

    def entry_gate(self, symbol: str, direction: str) -> EntryGateEvidence:
        data = read_json(self.runtime_dir / "adaptive" / "QuantGod_DynamicEntryGate.json", {})
        rows: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            for key in ("entryGates", "gates", "rows", "policies"):
                if isinstance(data.get(key), list):
                    rows = data[key]
                    break
        direction = normalize_direction(direction)
        for row in rows:
            row_symbol = str(row.get("symbol") or "")
            row_direction = normalize_direction(row.get("direction") or row.get("side"))
            if row_symbol == symbol and row_direction == direction:
                status = str(row.get("status") or row.get("state") or row.get("gateStatus") or "UNKNOWN").upper()
                passed = bool(row.get("passed", False)) or status in {"PASS", "PASSED", "ACTIVE_SHADOW_OK", "WATCH_ONLY_OK"}
                reason = str(row.get("reason") or row.get("conclusion") or status)
                return EntryGateEvidence(passed, status, reason, row)
        return EntryGateEvidence(False, "MISSING", "缺少自适应入场闸门证据", {})

    def sltp_plan(self, symbol: str, direction: str) -> DynamicSLTPPlan:
        paths = [
            self.runtime_dir / "adaptive" / "QuantGod_DynamicSLTPCalibration.json",
            self.runtime_dir / "adaptive" / "QuantGod_DynamicSLTPPlan.json",
        ]
        data: Dict[str, Any] = {}
        for path in paths:
            loaded = read_json(path, None)
            if isinstance(loaded, dict):
                data = loaded
                break
        rows: List[Dict[str, Any]] = []
        for key in ("plans", "rows", "calibrations", "sltpPlans"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        direction = normalize_direction(direction)
        for row in rows:
            if str(row.get("symbol") or "") == symbol and normalize_direction(row.get("direction") or row.get("side")) == direction:
                status = str(row.get("status") or row.get("state") or "UNKNOWN").upper()
                available = status in {"CALIBRATED", "WATCH_ONLY", "ACTIVE_SHADOW_OK"} or bool(row.get("available"))
                initial_stop = str(row.get("initialStop") or row.get("initialStopReference") or row.get("stopLoss") or "动态止损参考已生成")
                targets = str(row.get("targets") or row.get("targetReference") or row.get("takeProfit") or "动态止盈参考已生成")
                return DynamicSLTPPlan(available, status, initial_stop, targets, row)
        return DynamicSLTPPlan(False, "MISSING", "缺少动态止损计划", "缺少动态止盈计划", {})

    def shadow_stats(self, symbol: str, direction: str, limit: int = 200) -> ShadowStats:
        paths = [
            self.runtime_dir / "ShadowCandidateOutcomeLedger.csv",
            self.runtime_dir / "journal" / "QuantGod_AIAdvisoryOutcomes.jsonl",
        ]
        direction = normalize_direction(direction)
        rows = read_csv_rows(paths[0], limit=5000) if paths[0].exists() else []
        values: List[float] = []
        pips: List[float] = []
        wins = 0
        consecutive_losses = 0
        seen = 0
        for row in reversed(rows):
            if symbol and _first_text(row, ["symbol", "Symbol"]) != symbol:
                continue
            row_dir = normalize_direction(_first_text(row, ["direction", "side", "Direction"], direction))
            if row_dir != direction:
                continue
            score = _first_number(row, ["scoreR", "r", "R", "outcomeR", "expectancyR"], None)  # type: ignore[arg-type]
            pip_value = _first_number(row, ["pips", "pnlPips", "movePips", "profitPips"], 0.0)
            if score is None:
                score = pip_value / 10.0 if pip_value else _first_number(row, ["profit", "pnl", "netProfit"], 0.0)
            values.append(float(score))
            pips.append(float(pip_value))
            if score > 0:
                wins += 1
                if seen == consecutive_losses:
                    pass
            elif seen == consecutive_losses:
                consecutive_losses += 1
            seen += 1
            if len(values) >= limit:
                break
        if not values:
            return ShadowStats()
        return ShadowStats(
            samples=len(values),
            win_rate=wins / len(values),
            avg_r=sum(values) / len(values),
            avg_pips=sum(pips) / len(pips) if pips else 0.0,
            consecutive_losses=consecutive_losses,
        )
