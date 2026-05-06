from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.usdjpy_strategy_lab.data_loader import _write_json, first_json, to_float
except ModuleNotFoundError:  # pragma: no cover - CLI entrypoint runs from tools/
    from usdjpy_strategy_lab.data_loader import _write_json, first_json, to_float

from .builder import build_runtime_dataset
from .schema import FOCUS_SYMBOL, READ_ONLY_SAFETY, SCHEMA_REPLAY, utc_now_iso


def _load_dataset(runtime_dir: Path) -> Dict[str, Any]:
    payload = first_json(runtime_dir, "QuantGod_USDJPYRuntimeDataset.json") or {}
    if payload:
        return payload
    return build_runtime_dataset(runtime_dir, write=False)


def build_replay_report(runtime_dir: Path, write: bool = False) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    dataset = _load_dataset(runtime_dir)
    samples = dataset.get("samples") if isinstance(dataset.get("samples"), list) else []
    missed = []
    early_exits = []
    reasonable_blocks = []
    for sample in samples:
        reason = str(sample.get("blockReason") or sample.get("status") or "")
        did_enter = bool(sample.get("didEnter"))
        would_enter = bool(sample.get("wouldEnter"))
        profit = to_float(sample.get("profitUSC"), 0.0)
        mfe = to_float(sample.get("mfeR"), 0.0)
        if would_enter and not did_enter:
            missed.append({
                "timestamp": sample.get("timestamp"),
                "reason": reason or "RSI 买入信号未进入实盘",
                "strategy": sample.get("strategy"),
                "direction": sample.get("direction"),
            })
        elif not did_enter and reason:
            reasonable_blocks.append({"timestamp": sample.get("timestamp"), "reason": reason[:160]})
        if did_enter and profit >= 0 and mfe >= max(1.2, profit * 1.8):
            early_exits.append({
                "timestamp": sample.get("timestamp"),
                "profitUSC": profit,
                "mfeR": mfe,
                "exitReason": sample.get("exitReason") or "盈利保护可能过早",
            })
    status = "REPLAY_READY" if len(samples) >= 20 else "INSUFFICIENT_DATA"
    payload = {
        "ok": True,
        "schema": SCHEMA_REPLAY,
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "status": status,
        "statusZh": "已生成 USDJPY 回放复盘" if status == "REPLAY_READY" else "样本不足，先继续采集 USDJPY 运行数据",
        "safety": READ_ONLY_SAFETY,
        "summary": {
            "sampleCount": len(samples),
            "missedOpportunityCount": len(missed),
            "earlyExitCount": len(early_exits),
            "reasonableBlockCount": len(reasonable_blocks),
            "needsRetune": bool(missed or early_exits),
        },
        "missedOpportunities": missed[:30],
        "earlyExits": early_exits[:30],
        "reasonableBlocks": reasonable_blocks[:30],
        "nextStep": "生成 tester-only 参数候选，不自动修改实盘 preset。" if (missed or early_exits) else "继续采集，暂不需要改代码或参数。",
    }
    if write:
        out_dir = runtime_dir / "replay" / "usdjpy"
        _write_json(out_dir / "QuantGod_USDJPYReplayReport.json", payload)
        _write_json(out_dir / "QuantGod_USDJPYMissedOpportunityReport.json", {
            "schema": "quantgod.usdjpy_missed_opportunity.v1",
            "generatedAtIso": payload["generatedAtIso"],
            "symbol": FOCUS_SYMBOL,
            "summary": {"count": len(missed)},
            "items": missed,
            "safety": READ_ONLY_SAFETY,
        })
        _write_json(out_dir / "QuantGod_USDJPYExitHoldReport.json", {
            "schema": "quantgod.usdjpy_exit_hold.v1",
            "generatedAtIso": payload["generatedAtIso"],
            "symbol": FOCUS_SYMBOL,
            "summary": {"count": len(early_exits)},
            "items": early_exits,
            "safety": READ_ONLY_SAFETY,
        })
    return payload
