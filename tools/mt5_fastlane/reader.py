from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import assert_safe_payload, runtime_dir


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def age_seconds(value: Any) -> int | None:
    dt = parse_time(value)
    if not dt:
        return None
    return max(0, int((utc_now() - dt).total_seconds()))


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            assert_safe_payload(payload)
            return payload
    except Exception:
        return None
    return None


def read_jsonl_tail(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    assert_safe_payload(item)
                    rows.append(item)
            except Exception:
                continue
    except Exception:
        return []
    return rows


@dataclass
class FastLaneEvidence:
    runtime_dir: Path
    heartbeat: dict[str, Any] | None
    ticks: dict[str, list[dict[str, Any]]]
    indicators: dict[str, dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    trade_events: list[dict[str, Any]]


def _symbol_from_name(name: str, prefix: str, suffix: str) -> str:
    return name[len(prefix) : -len(suffix)]


def load_fastlane_evidence(path: str | Path = "runtime", symbols: list[str] | None = None) -> FastLaneEvidence:
    root = runtime_dir(path)
    heartbeat = read_json(root / "QuantGod_RuntimeHeartbeat.json")
    allowed = {s.upper() for s in symbols or []}
    ticks: dict[str, list[dict[str, Any]]] = {}
    indicators: dict[str, dict[str, Any]] = {}
    if root.exists():
        for file in root.glob("QuantGod_RuntimeTicks_*.jsonl"):
            sym = _symbol_from_name(file.name, "QuantGod_RuntimeTicks_", ".jsonl")
            if allowed and sym.upper() not in allowed:
                continue
            ticks[sym] = read_jsonl_tail(file, 120)
        for file in root.glob("QuantGod_RuntimeIndicators_*.json"):
            sym = _symbol_from_name(file.name, "QuantGod_RuntimeIndicators_", ".json")
            if allowed and sym.upper() not in allowed:
                continue
            payload = read_json(file)
            if payload:
                indicators[sym] = payload
    diagnostics = read_jsonl_tail(root / "QuantGod_RuntimeStrategyDiagnostics.jsonl", 120)
    trade_events = read_jsonl_tail(root / "QuantGod_RuntimeTradeEvents.jsonl", 120)
    return FastLaneEvidence(root, heartbeat, ticks, indicators, diagnostics, trade_events)


def latest_tick_age(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None
    latest = rows[-1]
    return age_seconds(latest.get("timeIso") or latest.get("generatedAt") or latest.get("time"))


def latest_indicator_age(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    return age_seconds(payload.get("generatedAt") or payload.get("timeIso") or payload.get("timestamp"))
