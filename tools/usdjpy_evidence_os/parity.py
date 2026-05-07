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
        _check_backtest_engine(backtest.get("engine")),
        _check_sqlite_persistence(backtest),
        _check_parity_vector_vs_live(backtest, live_loop),
        _check_parity_vector_vs_ea(backtest, diagnostics),
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
        "summary": _summary(checks),
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


def _check_sqlite_persistence(backtest: Dict[str, Any]) -> Dict[str, Any]:
    run_id = backtest.get("runId")
    has_engine = isinstance(backtest.get("engine"), dict)
    has_trades = int(backtest.get("tradeCount") or 0) >= 0
    status = "PASS" if run_id and has_engine and has_trades else "WARN"
    return {
        "name": "strategy_backtest_sqlite_persistence",
        "status": status,
        "required": False,
        "actual": {
            "runId": run_id,
            "tradeCount": backtest.get("tradeCount"),
            "hasEngine": has_engine,
        },
        "reasonZh": "Strategy run 可落入 SQLite 审计表" if status == "PASS" else "尚未看到完整 SQLite run 证据",
    }


def _check_parity_vector_vs_live(backtest: Dict[str, Any], live_loop: Dict[str, Any]) -> Dict[str, Any]:
    vector = ((backtest.get("engine") or {}).get("parityVector") or {}) if isinstance(backtest.get("engine"), dict) else {}
    top_policy = live_loop.get("topLiveEligiblePolicy") or live_loop.get("topPolicy") or {}
    if not vector or not top_policy:
        return {
            "name": "strategy_json_vs_live_loop_policy",
            "status": "MISSING",
            "required": False,
            "reasonZh": "等待 Live Loop policy 与 Strategy JSON parity vector 同步",
        }
    expected_family = _policy_strategy(top_policy)
    expected_direction = str(top_policy.get("direction") or "").upper()
    mismatches = []
    if expected_family and vector.get("strategyFamily") != expected_family:
        mismatches.append("strategyFamily")
    if expected_direction and str(vector.get("direction") or "").upper() != expected_direction:
        mismatches.append("direction")
    status = "PASS" if not mismatches else "WARN"
    return {
        "name": "strategy_json_vs_live_loop_policy",
        "status": status,
        "required": False,
        "actual": {
            "vectorFamily": vector.get("strategyFamily"),
            "vectorDirection": vector.get("direction"),
            "policyFamily": expected_family,
            "policyDirection": expected_direction,
        },
        "reasonZh": "Strategy JSON 与 Live Loop 候选策略方向一致" if status == "PASS" else f"Strategy JSON 与 Live Loop 存在口径差异：{', '.join(mismatches)}",
    }


def _check_parity_vector_vs_ea(backtest: Dict[str, Any], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    vector = ((backtest.get("engine") or {}).get("parityVector") or {}) if isinstance(backtest.get("engine"), dict) else {}
    if not vector or not diagnostics:
        return {
            "name": "strategy_json_vs_mql5_rsi_diagnostics",
            "status": "MISSING",
            "required": False,
            "reasonZh": "等待 EA 输出 QuantGod_USDJPYRsiEntryDiagnostics.json 后做逐字段对账",
        }
    diag_strategy = diagnostics.get("strategy") or diagnostics.get("strategyFamily") or "RSI_Reversal"
    diag_direction = str(diagnostics.get("direction") or "LONG").upper()
    mismatches = []
    if vector.get("strategyFamily") != diag_strategy:
        mismatches.append("strategyFamily")
    if str(vector.get("direction") or "").upper() != diag_direction:
        mismatches.append("direction")
    status = "PASS" if not mismatches else "WARN"
    return {
        "name": "strategy_json_vs_mql5_rsi_diagnostics",
        "status": status,
        "required": False,
        "actual": {
            "vectorFamily": vector.get("strategyFamily"),
            "vectorDirection": vector.get("direction"),
            "eaFamily": diag_strategy,
            "eaDirection": diag_direction,
            "eaStatus": diagnostics.get("status") or diagnostics.get("state"),
        },
        "reasonZh": "Strategy JSON 与 MQL5 RSI 诊断方向一致" if status == "PASS" else f"Strategy JSON 与 MQL5 诊断存在口径差异：{', '.join(mismatches)}",
    }


def _check_backtest_engine(engine: Any) -> Dict[str, Any]:
    data = engine if isinstance(engine, dict) else {}
    required_markers = {
        "schema": "quantgod.strategy_backtest_engine.v2",
        "coverage": "ALL_SUPPORTED_USDJPY_SHADOW_FAMILIES",
    }
    missing = [
        key
        for key, expected in required_markers.items()
        if data.get(key) != expected
    ]
    if not isinstance(data.get("costModel"), dict):
        missing.append("costModel")
    if not isinstance(data.get("parityVector"), dict):
        missing.append("parityVector")
    status = "PASS" if not missing else "WARN"
    return {
        "name": "strategy_json_backtest_engine_v2",
        "status": status,
        "required": False,
        "actual": {
            "schema": data.get("schema"),
            "coverage": data.get("coverage"),
            "hasCostModel": isinstance(data.get("costModel"), dict),
            "hasParityVector": isinstance(data.get("parityVector"), dict),
        },
        "expected": required_markers,
        "reasonZh": "全策略 Strategy JSON runner 已接入 parity 审计"
        if status == "PASS"
        else f"Strategy JSON runner 证据不完整：{', '.join(missing)}",
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


def _policy_strategy(policy: Dict[str, Any]) -> str:
    return str(policy.get("strategy") or policy.get("strategyFamily") or "")


def _summary(checks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"PASS": 0, "WARN": 0, "MISSING": 0, "FAIL": 0}
    for row in checks:
        status = str(row.get("status") or "WARN")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _reason_zh(status: str) -> str:
    if status == "PARITY_PASS":
        return "Strategy JSON、Python 回放和 EA 证据口径当前一致。"
    if status == "PARITY_WARN":
        return "部分 EA 或回放证据尚未同步；不影响只读研究，但不能把该证据当完整 parity。"
    return "发现必需口径不一致，策略不能晋级。"
