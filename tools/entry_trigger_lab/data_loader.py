from __future__ import annotations
import csv, json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def read_csv_rows(path: Path, limit: int = 5000) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    rows: List[Dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append({str(k): str(v) for k, v in row.items()})
                if len(rows) >= limit:
                    break
    except Exception:
        return []
    return rows

def discover_runtime_snapshot(runtime_dir: Path, symbol: str) -> Optional[Dict[str, Any]]:
    for candidate in [runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json", runtime_dir / f"QuantGod_RuntimeSnapshot_{symbol}.json", runtime_dir / "QuantGod_Dashboard.json"]:
        payload = read_json(candidate)
        if payload:
            return payload
    return None

def discover_fastlane_quality(runtime_dir: Path, symbol: str) -> Dict[str, Any]:
    for candidate in [runtime_dir / "quality" / "QuantGod_MT5FastLaneQuality.json", runtime_dir / "QuantGod_MT5FastLaneQuality.json"]:
        payload = read_json(candidate)
        if not payload:
            continue
        symbols = payload.get("symbols")
        if isinstance(symbols, dict):
            for row_symbol, row_payload in symbols.items():
                if not isinstance(row_payload, dict):
                    continue
                key = str(row_symbol or "")
                if key == symbol or key.upper().startswith("USDJPY"):
                    item = dict(row_payload)
                    item.setdefault("symbol", key or symbol)
                    item.setdefault("found", True)
                    item.setdefault("focusSymbolFound", True)
                    return item
            return {}
        if isinstance(symbols, list):
            for item in symbols:
                if not isinstance(item, dict):
                    continue
                row_symbol = str(item.get("symbol") or "")
                if row_symbol == symbol or row_symbol.upper().startswith("USDJPY"):
                    result = dict(item)
                    result.setdefault("found", True)
                    result.setdefault("focusSymbolFound", True)
                    result.setdefault("sourceQuality", payload.get("quality"))
                    return result
            return {}
        return payload
    return {}

def discover_adaptive_gate(runtime_dir: Path, symbol: str) -> Dict[str, Any]:
    for candidate in [runtime_dir / "adaptive" / "QuantGod_DynamicEntryGate.json", runtime_dir / "QuantGod_DynamicEntryGate.json"]:
        payload = read_json(candidate)
        if not payload:
            continue
        items = payload.get("entryGates") or payload.get("gates") or payload.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("symbol") == symbol:
                    return item
        if payload.get("symbol") == symbol:
            return payload
    return {}

def load_shadow_rows(runtime_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for candidate in [runtime_dir / "ShadowCandidateOutcomeLedger.csv", runtime_dir / "adaptive" / "QuantGod_AdaptivePolicyLedger.csv", runtime_dir / "QuantGod_AdaptivePolicyLedger.csv"]:
        rows.extend(read_csv_rows(candidate))
    return rows

def sample_runtime(runtime_dir: Path, symbols: Iterable[str], overwrite: bool = False) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "quality").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "adaptive").mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        snapshot = {
            "schema": "quantgod.mt5.runtime_snapshot.sample.v1",
            "symbol": symbol,
            "runtimeFresh": True,
            "fallback": False,
            "safety": {
                "readOnlyDataPlane": True,
                "orderSendAllowed": False,
                "brokerExecutionAllowed": False,
                "livePresetMutationAllowed": False,
            },
        }
        snapshot_target = runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json"
        if overwrite or not snapshot_target.exists():
            snapshot_target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    quality = {"schema":"quantgod.mt5.fastlane.quality.v1","quality":"OK","symbols":{symbol:{"quality":"OK","heartbeatFresh":True,"tickFresh":True,"indicatorFresh":True,"spreadOk":True} for symbol in symbols},"safety":{"readOnlyDataPlane":True,"orderSendAllowed":False,"brokerExecutionAllowed":False}}
    target = runtime_dir / "quality" / "QuantGod_MT5FastLaneQuality.json"
    if overwrite or not target.exists():
        target.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = {"schema":"quantgod.dynamic_entry_gate.v1","entryGates":[{"symbol":symbol,"direction":"LONG","passed":True,"state":"PASS","reasons":["sample runtime gate passed"]} for symbol in symbols],"safety":{"readOnlyDataPlane":True,"orderSendAllowed":False,"brokerExecutionAllowed":False}}
    target = runtime_dir / "adaptive" / "QuantGod_DynamicEntryGate.json"
    if overwrite or not target.exists():
        target.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"4.2","scoreR":"0.42"},
        {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"2.7","scoreR":"0.27"},
        {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"1.3","scoreR":"0.13"},
        {"symbol":"USDJPYc","direction":"SHORT","horizonMinutes":"15","pips":"-3.1","scoreR":"-0.31"},
    ]
    ledger = runtime_dir / "ShadowCandidateOutcomeLedger.csv"
    if overwrite or not ledger.exists():
        with ledger.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader(); writer.writerows(rows)
