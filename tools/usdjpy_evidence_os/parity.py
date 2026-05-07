from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .io_utils import load_json, utc_now_iso, write_json
from .schema import AGENT_VERSION, FOCUS_SYMBOL, SAFETY_BOUNDARY, parity_path


def build_parity_report(runtime_dir: Path, write: bool = True) -> Dict[str, Any]:
    backtest = load_json(runtime_dir / "backtest" / "QuantGod_StrategyBacktestReport.json")
    replay = load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYBarReplayReport.json")
    live_loop = load_json(runtime_dir / "live" / "QuantGod_USDJPYLiveLoopStatus.json")
    diagnostics = load_json(runtime_dir / "QuantGod_USDJPYRsiEntryDiagnostics.json")

    checks: List[Dict[str, Any]] = [
        _check_equal("symbol", backtest.get("symbol"), FOCUS_SYMBOL, required=True),
        _check_equal("strategy_family", backtest.get("strategyFamily"), "RSI_Reversal", required=False),
        _check_equal("direction", backtest.get("direction"), "LONG", required=False),
        _check_present("bar_replay_report", replay),
        _check_present("live_loop_status", live_loop),
        _check_present("ea_rsi_diagnostics", diagnostics),
        _check_safety("backtest_no_execution", backtest.get("safety")),
        _check_safety("live_loop_no_frontend_execution", live_loop.get("safety")),
    ]
    failed_required = [row for row in checks if row["status"] == "FAIL" and row.get("required")]
    warnings = [row for row in checks if row["status"] in {"WARN", "MISSING"}]
    status = "PARITY_FAIL" if failed_required else ("PARITY_WARN" if warnings else "PARITY_PASS")
    report = {
        "ok": status != "PARITY_FAIL",
        "schema": "quantgod.strategy_parity_report.v1",
        "agentVersion": AGENT_VERSION,
        "createdAt": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "status": status,
        "checks": checks,
        "reasonZh": _reason_zh(status),
        "singleSourceOfTruth": "STRATEGY_JSON_PYTHON_REPLAY_MQL5_EA_PARITY",
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        write_json(parity_path(runtime_dir), report)
    return report


def _check_equal(name: str, actual: Any, expected: Any, required: bool) -> Dict[str, Any]:
    if actual == expected:
        status = "PASS"
    elif actual in {None, ""} and not required:
        status = "MISSING"
    else:
        status = "FAIL" if required else "WARN"
    return {
        "name": name,
        "status": status,
        "required": required,
        "actual": actual,
        "expected": expected,
        "reasonZh": "一致" if status == "PASS" else "证据缺失或口径不一致",
    }


def _check_present(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    present = bool(payload)
    return {
        "name": name,
        "status": "PASS" if present else "MISSING",
        "required": False,
        "reasonZh": "已读取" if present else "尚未生成，保留为审计提醒，不阻断实盘",
    }


def _check_safety(name: str, safety: Any) -> Dict[str, Any]:
    data = safety if isinstance(safety, dict) else {}
    execution_allowed = any(bool(data.get(key)) for key in ("orderSendAllowed", "closeAllowed", "cancelAllowed", "livePresetMutationAllowed"))
    return {
        "name": name,
        "status": "FAIL" if execution_allowed else "PASS",
        "required": True,
        "reasonZh": "安全边界保持只读" if not execution_allowed else "发现越权执行字段",
    }


def _reason_zh(status: str) -> str:
    if status == "PARITY_PASS":
        return "Strategy JSON、Python 回放和 EA 证据口径当前一致。"
    if status == "PARITY_WARN":
        return "部分 EA 或回放证据尚未同步；不影响只读研究，但不能把该证据当完整 parity。"
    return "发现必需口径不一致，策略不能晋级。"

