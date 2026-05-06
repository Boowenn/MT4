from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.usdjpy_runtime_dataset.builder import build_runtime_dataset
    from tools.usdjpy_strategy_lab.data_loader import first_json, to_float
except ModuleNotFoundError:  # pragma: no cover - CLI entrypoint runs from tools/
    from usdjpy_runtime_dataset.builder import build_runtime_dataset
    from usdjpy_strategy_lab.data_loader import first_json, to_float

from .schema import FOCUS_SYMBOL


def _load_dataset_payload(runtime_dir: Path) -> Dict[str, Any]:
    payload = first_json(runtime_dir, "QuantGod_USDJPYRuntimeDataset.json") or {}
    if payload and isinstance(payload.get("samples"), list):
        return payload
    return build_runtime_dataset(runtime_dir, write=False)


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "Y", "READY", "PASS", "OK"}


def load_replay_samples(runtime_dir: Path) -> List[Dict[str, Any]]:
    payload = _load_dataset_payload(Path(runtime_dir))
    samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    normalized: List[Dict[str, Any]] = []
    for row in samples:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or FOCUS_SYMBOL).upper().replace(".", "").replace("_", "") not in {"USDJPY", "USDJPYC"}:
            continue
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        normalized.append({
            **row,
            "symbol": FOCUS_SYMBOL,
            "strategy": row.get("strategy") or "RSI_Reversal",
            "direction": row.get("direction") or "LONG",
            "didEnter": _boolish(row.get("didEnter")),
            "wouldEnter": _boolish(row.get("wouldEnter")),
            "profitR": _maybe_float(row.get("profitR")),
            "profitUSC": to_float(row.get("profitUSC"), 0.0),
            "riskPips": _maybe_float(row.get("riskPips")),
            "mfeR": _maybe_float(row.get("mfeR")),
            "maeR": _maybe_float(row.get("maeR")),
            "mfePips": _maybe_float(row.get("mfePips")),
            "maePips": _maybe_float(row.get("maePips")),
            "blockReason": row.get("blockReason") or row.get("status") or "",
            "raw": raw,
        })
    return normalized


def sample_runtime(runtime_dir: Path, overwrite: bool = False) -> Dict[str, Any]:
    import csv

    runtime_dir = Path(runtime_dir)
    out = runtime_dir / "QuantGod_EntryBlockers.csv"
    if out.exists() and not overwrite:
        return {"ok": True, "skipped": True, "path": str(out), "reason": "sample already exists"}
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "symbol": FOCUS_SYMBOL,
            "strategy": "RSI_Reversal",
            "direction": "LONG",
            "status": "READY_BUY_SIGNAL",
            "reason": "NO_CROSS tactical confirmation missing",
            "riskPips": "5",
            "posteriorR60": "0.72",
            "posteriorPips60": "3.6",
            "maeR": "-0.35",
        },
        {
            "symbol": FOCUS_SYMBOL,
            "strategy": "RSI_Reversal",
            "direction": "LONG",
            "status": "NEWS_BLOCK",
            "reason": "NEWS_BLOCK positive posterior must not trigger",
            "riskPips": "5",
            "posteriorR60": "1.20",
            "posteriorPips60": "6.0",
            "maeR": "-0.20",
        },
    ]
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    close = runtime_dir / "QuantGod_CloseHistory.csv"
    with close.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "strategy", "direction", "profitUSC", "profitR", "mfeR", "maeR", "exitReason"])
        writer.writeheader()
        writer.writerow({
            "symbol": FOCUS_SYMBOL,
            "strategy": "RSI_Reversal",
            "direction": "LONG",
            "profitUSC": "0.35",
            "profitR": "0.28",
            "mfeR": "1.65",
            "maeR": "-0.32",
            "exitReason": "breakeven_or_trailing",
        })
    return {"ok": True, "path": str(out), "closeHistory": str(close)}

