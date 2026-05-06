from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
    from tools.usdjpy_autonomous_agent.agent_state import build_agent_state
    from tools.usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
    from usdjpy_autonomous_agent.agent_state import build_agent_state
    from usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso


REPORT_NAME = "QuantGod_DailyAutopilotV2.json"


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stage_text(route: Dict[str, Any]) -> str:
    return str(route.get("promotionStageZh") or route.get("promotionStage") or "模拟观察")


def _top_mt5_routes(mt5_shadow: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    routes = [row for row in _safe_list(mt5_shadow.get("routes")) if isinstance(row, dict)]
    items: List[Dict[str, Any]] = []
    for row in routes[:limit]:
        items.append({
            "strategy": row.get("strategy", ""),
            "direction": row.get("direction", ""),
            "stage": row.get("promotionStage", ""),
            "stageZh": _stage_text(row),
            "sampleCount": row.get("sampleCount", 0),
            "avgR": row.get("avgR", 0),
            "profitFactor": row.get("profitFactor", 0),
            "reasonZh": row.get("reasonZh", ""),
        })
    return items


def _build_morning_plan(agent: Dict[str, Any], lifecycle: Dict[str, Any]) -> Dict[str, Any]:
    cent = _safe_dict(lifecycle.get("centAccount") or agent.get("centAccount"))
    lanes = _safe_dict(lifecycle.get("lanes") or agent.get("lanes"))
    live = _safe_dict(lanes.get("live"))
    mt5_shadow = _safe_dict(lanes.get("mt5Shadow"))
    polymarket = _safe_dict(lanes.get("polymarketShadow"))
    patch = _safe_dict(agent.get("currentPatch"))
    limits = _safe_dict(patch.get("limits"))
    stage = str(agent.get("executionStage") or agent.get("stage") or "SHADOW")
    return {
        "titleZh": "QuantGod 今日自动作战计划",
        "accountMode": cent.get("accountMode", "cent"),
        "accountCurrencyUnit": cent.get("accountCurrencyUnit", "USC"),
        "centAccountAcceleration": bool(cent.get("centAccountAcceleration", True)),
        "liveLane": {
            "symbol": live.get("symbol", FOCUS_SYMBOL),
            "strategy": live.get("strategy", "RSI_Reversal"),
            "direction": live.get("direction", "LONG"),
            "stage": stage,
            "stageZh": agent.get("stageZh") or stage,
            "stageMaxLot": limits.get("stageMaxLot", 0),
            "maxLot": limits.get("maxLot", cent.get("maxLot", 2.0)),
        },
        "mt5ShadowLane": {
            "summary": mt5_shadow.get("summary", {}),
            "topRoutes": _top_mt5_routes(mt5_shadow),
        },
        "polymarketShadowLane": {
            "stage": polymarket.get("stage", "SHADOW"),
            "stageZh": polymarket.get("stageZh", "模拟观察"),
            "summary": polymarket.get("summary", {}),
            "reasonZh": polymarket.get("reasonZh", "继续模拟账本和事件风险，不触碰真实钱包。"),
        },
        "todayForbiddenZh": [
            "USDJPY SELL 实盘",
            "非 RSI 实盘",
            "非 USDJPY 实盘",
            "Polymarket 钱包交易",
            "新闻阻断时入场",
            "快通道或 runtime 陈旧时入场",
            "固定 2 手下单",
        ],
    }


def _build_evening_review(agent: Dict[str, Any], lifecycle: Dict[str, Any]) -> Dict[str, Any]:
    lanes = _safe_dict(lifecycle.get("lanes") or agent.get("lanes"))
    mt5_shadow = _safe_dict(lanes.get("mt5Shadow"))
    polymarket = _safe_dict(lanes.get("polymarketShadow"))
    patch = _safe_dict(agent.get("currentPatch"))
    rollback = _safe_dict(patch.get("rollback"))
    blockers = [str(item) for item in _safe_list(rollback.get("hardBlockers"))]
    mt5_summary = _safe_dict(mt5_shadow.get("summary"))
    return {
        "titleZh": "QuantGod 今日自动复盘",
        "liveLane": {
            "stage": agent.get("executionStage") or agent.get("stage") or "SHADOW",
            "stageZh": agent.get("stageZh") or "模拟观察",
            "rollbackTriggered": bool(blockers),
            "rollbackReasons": blockers,
            "patchWritable": bool(agent.get("patchWritable")),
            "liveMutationAllowed": False,
        },
        "mt5ShadowLane": {
            "promotedCount": int(mt5_summary.get("fastShadow", 0) or 0) + int(mt5_summary.get("testerOnly", 0) or 0),
            "pausedCount": int(mt5_summary.get("paused", 0) or 0),
            "rejectedCount": int(mt5_summary.get("rejected", 0) or 0),
            "routeCount": int(mt5_summary.get("routeCount", 0) or 0),
            "topRoutes": _top_mt5_routes(mt5_shadow),
        },
        "polymarketShadowLane": {
            "stage": polymarket.get("stage", "SHADOW"),
            "stageZh": polymarket.get("stageZh", "模拟观察"),
            "summary": polymarket.get("summary", {}),
            "riskContextOnly": True,
        },
        "tomorrowStageZh": agent.get("stageZh") or "继续自主治理门评估",
    }


def build_daily_autopilot_v2(
    runtime_dir: Path,
    *,
    repo_root: Path | None = None,
    write: bool = False,
) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    lifecycle = build_autonomous_lifecycle(runtime_dir, repo_root=repo_root, write=write)
    agent = build_agent_state(runtime_dir, write=write)
    payload: Dict[str, Any] = {
        "ok": True,
        "schema": "quantgod.daily_autopilot_v2.v1",
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "titleZh": "USDJPY 美分账户三车道自动日报",
        "sloganZh": "实盘要窄，模拟要宽，升降级要快，回滚要硬。",
        "morningPlan": _build_morning_plan(agent, lifecycle),
        "eveningReview": _build_evening_review(agent, lifecycle),
        "autonomousAgent": {
            "stage": agent.get("executionStage") or agent.get("stage"),
            "stageZh": agent.get("stageZh"),
            "patchWritable": bool(agent.get("patchWritable")),
            "requiresManualReview": False,
            "requiresAutonomousGovernance": True,
            "autoApplyAllowed": "stage_gated",
        },
        "lanes": lifecycle.get("lanes"),
        "centAccount": lifecycle.get("centAccount"),
        "eaReproducibility": lifecycle.get("eaReproducibility"),
        "safety": {
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "liveMutationAllowed": False,
            "livePresetMutationAllowed": False,
            "polymarketRealMoneyAllowed": False,
            "telegramCommandExecutionAllowed": False,
            "deepSeekCanApproveLive": False,
        },
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / REPORT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

