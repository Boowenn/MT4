from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .freshness import freshness_report, utc_now_iso
from .schema import (
    ALLOWED_TIMEFRAMES,
    RUNTIME_SNAPSHOT_SCHEMA,
    bridge_safety_payload,
    build_sample_snapshot,
    normalize_symbol,
    safe_symbol_filename,
    validate_runtime_snapshot,
)


class RuntimeBridgeReader:
    """Read HFM/MT5 EA runtime files without mutating MT5 state."""

    def __init__(self, runtime_dir: str | Path, *, max_age_seconds: int = 1800, allow_stale: bool = False) -> None:
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.max_age_seconds = int(max_age_seconds)
        self.allow_stale = bool(allow_stale)

    def candidate_paths(self, symbol: str) -> list[Path]:
        safe_symbol = safe_symbol_filename(symbol)
        names = [
            f"QuantGod_MT5RuntimeSnapshot_{safe_symbol}.json",
            f"QuantGod_MT5RuntimeSnapshot_{normalize_symbol(symbol)}.json",
            f"QuantGod_RuntimeSnapshot_{safe_symbol}.json",
        ]
        candidates: list[Path] = []
        for name in names:
            path = self.runtime_dir / name
            if path not in candidates:
                candidates.append(path)
        if self.runtime_dir.exists():
            for path in sorted(self.runtime_dir.glob("QuantGod_MT5RuntimeSnapshot_*.json")):
                if path not in candidates:
                    candidates.append(path)
        dashboard = self.runtime_dir / "QuantGod_Dashboard.json"
        if dashboard not in candidates:
            candidates.append(dashboard)
        return candidates

    def read_json(self, path: Path) -> Any:
        try:
            if not path.exists() or not path.is_file():
                return None
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return {"_readError": str(exc), "_path": str(path)}

    def load_snapshot(self, symbol: str) -> tuple[dict[str, Any] | None, Path | None, str]:
        clean_symbol = normalize_symbol(symbol)
        for path in self.candidate_paths(clean_symbol):
            data = self.read_json(path)
            if not isinstance(data, dict):
                continue
            if data.get("_readError"):
                continue
            if path.name == "QuantGod_Dashboard.json":
                embedded = self._extract_from_dashboard(data, clean_symbol)
                if embedded is not None:
                    return embedded, path, "dashboard_embedded_runtime"
                continue
            candidate_symbol = normalize_symbol(data.get("symbol") or data.get("brokerSymbol") or data.get("canonicalSymbol"))
            if candidate_symbol and candidate_symbol.upper() != clean_symbol.upper():
                continue
            return data, path, "runtime_snapshot_file"
        return None, None, "missing_runtime_snapshot"

    def validate_symbol(self, symbol: str) -> dict[str, Any]:
        snapshot, path, source_kind = self.load_snapshot(symbol)
        if snapshot is None:
            return {
                "ok": False,
                "symbol": normalize_symbol(symbol),
                "runtimeDir": str(self.runtime_dir),
                "sourceKind": source_kind,
                "fresh": False,
                "errors": [source_kind],
                "warnings": [],
                "snapshotPath": "",
                "safety": bridge_safety_payload(),
            }
        validation = validate_runtime_snapshot(snapshot, expected_symbol=symbol)
        fresh = freshness_report(snapshot, max_age_seconds=self.max_age_seconds)
        ok = bool(validation["ok"] and (fresh["fresh"] or self.allow_stale))
        errors = list(validation.get("errors") or [])
        if not fresh["fresh"] and not self.allow_stale:
            errors.append(str(fresh.get("reason") or "stale_runtime_snapshot"))
        return {
            "ok": ok,
            "symbol": validation.get("symbol") or normalize_symbol(symbol),
            "runtimeDir": str(self.runtime_dir),
            "sourceKind": source_kind,
            "snapshotPath": str(path or ""),
            "schema": validation.get("schema") or RUNTIME_SNAPSHOT_SCHEMA,
            "fresh": bool(fresh["fresh"]),
            "freshness": fresh,
            "errors": errors,
            "warnings": list(validation.get("warnings") or []),
            "snapshot": snapshot if ok else None,
            "safety": bridge_safety_payload(),
        }

    def status(self, symbols: Iterable[str]) -> dict[str, Any]:
        clean_symbols = [normalize_symbol(item) for item in symbols if normalize_symbol(item)]
        items = [self.validate_symbol(symbol) for symbol in clean_symbols]
        found = [item for item in items if item.get("snapshotPath")]
        fresh = [item for item in items if item.get("fresh")]
        return {
            "ok": bool(items and all(item.get("ok") for item in items)),
            "mode": "QUANTGOD_MT5_RUNTIME_EVIDENCE_BRIDGE_STATUS_V1",
            "runtimeDir": str(self.runtime_dir),
            "runtimeDirExists": self.runtime_dir.exists(),
            "runtimeFound": bool(found),
            "symbolsRequested": clean_symbols,
            "symbols": len(items),
            "freshSymbols": len(fresh),
            "generatedAt": utc_now_iso(),
            "items": [_redact_snapshot(item) for item in items],
            "safety": bridge_safety_payload(),
        }

    def collect_for_ai_snapshot(self, symbol: str, timeframes: Iterable[str] | None = None) -> dict[str, Any]:
        requested = [str(item).strip().upper() for item in (timeframes or ALLOWED_TIMEFRAMES)]
        requested = [item for item in requested if item in ALLOWED_TIMEFRAMES] or list(ALLOWED_TIMEFRAMES)
        report = self.validate_symbol(symbol)
        if not report.get("ok"):
            return {
                "fallback": True,
                "source": "runtime_files_missing_or_stale",
                "fallbackReason": ",".join(str(item) for item in report.get("errors") or []),
                "runtimeFresh": bool(report.get("fresh", False)),
                "runtimeAgeSeconds": (report.get("freshness") or {}).get("ageSeconds") if isinstance(report.get("freshness"), dict) else None,
                "runtimePath": str(report.get("snapshotPath") or ""),
                "runtime": _redact_snapshot(report),
                "safety": bridge_safety_payload(),
            }
        snapshot = report.get("snapshot") if isinstance(report.get("snapshot"), dict) else {}
        payload: dict[str, Any] = {
            "fallback": False,
            "source": str(snapshot.get("source") or "hfm_ea_runtime"),
            "runtimeFresh": bool(report.get("fresh")),
            "runtimeAgeSeconds": (report.get("freshness") or {}).get("ageSeconds") if isinstance(report.get("freshness"), dict) else None,
            "runtimePath": str(report.get("snapshotPath") or ""),
            "runtime": _redact_snapshot(report),
            "current_price": snapshot.get("current_price") or snapshot.get("currentPrice") or {},
            "symbol_info": snapshot.get("symbol_info") or snapshot.get("symbolInfo") or {"name": normalize_symbol(symbol)},
            "open_positions": snapshot.get("open_positions") or snapshot.get("openPositions") or [],
            "kill_switch_status": snapshot.get("kill_switch_status") or snapshot.get("killSwitch") or {},
            "news_filter_status": snapshot.get("news_filter_status") or snapshot.get("newsFilter") or {},
            "consecutive_loss_state": snapshot.get("consecutive_loss_state") or snapshot.get("consecutiveLoss") or {},
            "daily_pnl": snapshot.get("daily_pnl") or snapshot.get("dailyPnl") or 0.0,
            "safety": bridge_safety_payload(),
        }
        for timeframe in requested:
            lower = timeframe.lower()
            for key in (f"kline_{lower}", f"kline{timeframe}", timeframe):
                value = snapshot.get(key)
                if isinstance(value, list):
                    payload[f"kline_{lower}"] = value
                    break
        return payload

    def write_sample_files(self, symbols: Iterable[str], *, overwrite: bool = False) -> dict[str, Any]:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        skipped: list[str] = []
        for symbol in symbols:
            clean = normalize_symbol(symbol)
            if not clean:
                continue
            path = self.runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{safe_symbol_filename(clean)}.json"
            if path.exists() and not overwrite:
                skipped.append(str(path))
                continue
            snapshot = build_sample_snapshot(clean)
            path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            written.append(str(path))
        return {
            "ok": True,
            "runtimeDir": str(self.runtime_dir),
            "written": written,
            "skipped": skipped,
            "safety": bridge_safety_payload(),
        }

    def _extract_from_dashboard(self, dashboard: dict[str, Any], symbol: str) -> dict[str, Any] | None:
        clean = normalize_symbol(symbol).upper()
        for key in ("mt5RuntimeSnapshots", "runtimeSnapshots", "snapshots"):
            value = dashboard.get(key)
            if isinstance(value, dict):
                for name, snapshot in value.items():
                    if str(name).upper() == clean and isinstance(snapshot, dict):
                        return _with_dashboard_defaults(snapshot, dashboard, symbol)
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    item_symbol = normalize_symbol(item.get("symbol") or item.get("brokerSymbol") or item.get("canonicalSymbol"))
                    if item_symbol.upper() == clean:
                        return _with_dashboard_defaults(item, dashboard, symbol)
        symbols = dashboard.get("symbols")
        if isinstance(symbols, list):
            for item in symbols:
                if not isinstance(item, dict):
                    continue
                names = {str(item.get(key, "")).upper() for key in ("symbol", "brokerSymbol", "canonicalSymbol", "name")}
                if clean not in names:
                    continue
                price = item.get("current_price") or item.get("currentPrice") or {
                    "symbol": symbol,
                    "bid": item.get("bid"),
                    "ask": item.get("ask"),
                    "last": item.get("last") or item.get("price"),
                    "spread": item.get("spread") or item.get("spreadPoints"),
                    "timeIso": item.get("timeIso") or _dashboard_timestamp(dashboard),
                }
                return _with_dashboard_defaults(
                    {
                        "schema": RUNTIME_SNAPSHOT_SCHEMA,
                        "source": "dashboard_runtime",
                        "generatedAt": _dashboard_timestamp(dashboard),
                        "symbol": symbol,
                        "current_price": price,
                        "symbol_info": item.get("symbolInfo") or item,
                        "open_positions": item.get("positions") or [],
                        "kill_switch_status": dashboard.get("killSwitch") or dashboard.get("kill_switch") or {},
                        "news_filter_status": dashboard.get("news") or dashboard.get("newsFilter") or {},
                        "consecutive_loss_state": dashboard.get("consecutiveLoss") or dashboard.get("consecutive_loss") or {},
                        "daily_pnl": dashboard.get("dailyPnl") or dashboard.get("daily_pnl") or 0.0,
                    },
                    dashboard,
                    symbol,
                )
        return None


def _with_dashboard_defaults(snapshot: dict[str, Any], dashboard: dict[str, Any], symbol: str) -> dict[str, Any]:
    out = dict(snapshot)
    out.setdefault("schema", RUNTIME_SNAPSHOT_SCHEMA)
    out.setdefault("source", "dashboard_runtime")
    out.setdefault("generatedAt", _dashboard_timestamp(dashboard))
    out.setdefault("symbol", symbol)
    out.setdefault("safety", bridge_safety_payload() | {"readOnly": True})
    return out


def _dashboard_timestamp(dashboard: dict[str, Any]) -> Any:
    runtime = dashboard.get("runtime") if isinstance(dashboard.get("runtime"), dict) else {}
    return (
        dashboard.get("generatedAt")
        or dashboard.get("generatedAtIso")
        or runtime.get("gmtTime")
        or runtime.get("serverTime")
        or dashboard.get("timestamp")
        or runtime.get("localTime")
    )


def _redact_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    out = {key: value for key, value in item.items() if key != "snapshot"}
    if "snapshot" in item:
        snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else {}
        out["snapshotPreview"] = {
            "schema": snapshot.get("schema"),
            "source": snapshot.get("source"),
            "symbol": snapshot.get("symbol"),
            "generatedAt": snapshot.get("generatedAt") or snapshot.get("generatedAtIso"),
            "current_price": snapshot.get("current_price") or snapshot.get("currentPrice"),
        }
    return out
