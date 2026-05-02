#!/usr/bin/env python3
"""Phase 3 K-line enhancement helpers: AI overlays, Vibe indicators, polling config."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import os


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def runtime_dir() -> Path:
    return Path(os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR") or os.environ.get("QG_HFM_FILES") or Path.cwd() / "runtime").resolve()


def ai_history_dir() -> Path:
    return Path(os.environ.get("AI_ANALYSIS_HISTORY_DIR") or runtime_dir() / "ai_analysis").resolve()


def safety() -> dict:
    return {
        "mode": "QUANTGOD_PHASE3_KLINE_ENHANCEMENTS",
        "localOnly": True,
        "readOnly": True,
        "advisoryOnly": True,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "livePresetMutationAllowed": False,
        "canOverrideKillSwitch": False,
    }


def _decision_to_marker(report: dict, path: Path) -> dict | None:
    decision = report.get("decision") or {}
    action = str(decision.get("action") or "HOLD").upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        return None
    timestamp = report.get("generatedAt") or report.get("timestamp") or utc_now()
    try:
        time_ms = int(datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "id": path.name,
        "timestamp": time_ms,
        "symbol": report.get("symbol"),
        "action": action,
        "confidence": decision.get("confidence"),
        "reasoning": str(decision.get("reasoning") or "")[:500],
        "shape": "triangle" if action in {"BUY", "SELL"} else "circle",
        "source": "ai_analysis_v2" if str(report.get("schema", "")).endswith("v2") else "ai_analysis_v1",
    }


def ai_overlays(symbol: str | None = None, limit: int = 50) -> dict:
    candidates = list((ai_history_dir() / "history").glob("*.json")) + list((ai_history_dir() / "history").glob("*_v2.json"))
    seen = set()
    overlays = []
    for path in sorted(candidates, reverse=True):
        if path in seen:
            continue
        seen.add(path)
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if symbol and str(report.get("symbol", "")).lower() != symbol.lower():
            continue
        marker = _decision_to_marker(report, path)
        if marker:
            overlays.append(marker)
        if len(overlays) >= limit:
            break
    return {"ok": True, "schema": "quantgod.kline.ai_overlays.v1", "generatedAt": utc_now(), "symbol": symbol, "overlays": overlays, "safety": safety()}


def vibe_indicators(strategy_id: str | None = None) -> dict:
    base = Path(os.environ.get("QG_VIBE_STRATEGY_DIR") or runtime_dir() / "vibe_strategies")
    index_path = base / "index.json"
    if not index_path.exists():
        return {"ok": True, "schema": "quantgod.kline.vibe_indicators.v1", "strategies": [], "safety": safety()}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "safety": safety()}
    rows = []
    for rec in index.get("strategies", []):
        if strategy_id and rec.get("strategy_id") != strategy_id:
            continue
        rows.append({
            "strategy_id": rec.get("strategy_id"),
            "version": rec.get("version"),
            "name": rec.get("name"),
            "symbol": rec.get("symbol"),
            "timeframe": rec.get("timeframe"),
            "indicatorKeys": ["ma_fast", "ma_slow", "rsi"],
            "overlayType": "custom_vibe_indicator",
            "safety": rec.get("safety") or safety(),
        })
    return {"ok": True, "schema": "quantgod.kline.vibe_indicators.v1", "strategies": rows, "safety": safety()}


def realtime_config() -> dict:
    interval = int(os.environ.get("QG_KLINE_POLL_SECONDS", "30"))
    return {
        "ok": True,
        "schema": "quantgod.kline.realtime_poll.v1",
        "pollSeconds": max(10, min(interval, 300)),
        "transport": "polling",
        "websocketRequired": False,
        "incrementalUpdatePreferred": True,
        "safety": safety(),
    }


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="QuantGod Phase 3 K-line overlays")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ai-overlays")
    p.add_argument("--symbol", default=None)
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("vibe-indicators")
    p.add_argument("--strategy-id", default=None)
    sub.add_parser("realtime-config")
    args = parser.parse_args()
    if args.cmd == "ai-overlays":
        emit(ai_overlays(args.symbol, args.limit))
    elif args.cmd == "vibe-indicators":
        emit(vibe_indicators(args.strategy_id))
    elif args.cmd == "realtime-config":
        emit(realtime_config())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
