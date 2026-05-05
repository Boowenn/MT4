from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
    except Exception:
        return None
    return None


def first_existing_json(paths: list[Path]) -> Optional[Dict[str, Any]]:
    for path in paths:
        value = read_json(path)
        if value is not None:
            value["_sourcePath"] = str(path)
            return value
    return None


def load_runtime_evidence(runtime_dir: Path, symbol: str) -> Dict[str, Any]:
    adaptive_dir = runtime_dir / "adaptive"
    quality_dir = runtime_dir / "quality"
    snapshot = first_existing_json([
        runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json",
        runtime_dir / "QuantGod_Dashboard.json",
    ])
    fastlane = first_existing_json([
        quality_dir / "QuantGod_MT5FastLaneQuality.json",
        runtime_dir / "QuantGod_MT5FastLaneQuality.json",
    ])
    entry_gate = first_existing_json([
        adaptive_dir / "QuantGod_DynamicEntryGate.json",
    ])
    trigger_plan = first_existing_json([
        adaptive_dir / "QuantGod_EntryTriggerPlan.json",
    ])
    sltp_plan = first_existing_json([
        adaptive_dir / "QuantGod_DynamicSLTPCalibration.json",
        adaptive_dir / "QuantGod_DynamicSLTPPlan.json",
    ])
    adaptive_policy = first_existing_json([
        adaptive_dir / "QuantGod_AdaptivePolicy.json",
    ])
    return {
        "symbol": symbol,
        "snapshot": snapshot,
        "fastlaneQuality": fastlane,
        "entryGate": entry_gate,
        "entryTriggerPlan": trigger_plan,
        "dynamicSltp": sltp_plan,
        "adaptivePolicy": adaptive_policy,
    }


def symbol_fastlane_status(payload: Dict[str, Any] | None, symbol: str) -> str:
    if not payload:
        return "MISSING"
    symbols = payload.get("symbols")
    if isinstance(symbols, dict):
        item = symbols.get(symbol) or symbols.get(symbol.upper()) or symbols.get(symbol.lower())
        if isinstance(item, dict):
            return str(item.get("quality") or item.get("status") or "UNKNOWN").upper()
    return str(payload.get("quality") or payload.get("status") or "UNKNOWN").upper()


def symbol_gate_passed(payload: Dict[str, Any] | None, symbol: str, direction: str) -> Optional[bool]:
    if not payload:
        return None
    candidates = payload.get("entryGates") or payload.get("gates") or payload.get("decisions") or payload.get("items") or []
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    if not isinstance(candidates, list):
        return None
    direction = direction.upper()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        row_direction = str(row.get("direction") or row.get("side") or "").upper()
        if row_direction and row_direction != direction:
            continue
        state = str(row.get("state") or row.get("status") or row.get("decision") or "").upper()
        if state in {"PASS", "PASSED", "READY", "WAIT_CONFIRMATION", "WAITING_CONFIRMATION", "ACTIVE_SHADOW_OK"}:
            return True
        if state in {"FAIL", "FAILED", "BLOCKED", "PAUSED", "INSUFFICIENT_DATA", "WATCH_ONLY"}:
            return False
        if "passed" in row:
            return bool(row.get("passed"))
    return None
