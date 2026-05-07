from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
    from tools.news_gate.classifier import classify_news_gate
    from tools.usdjpy_autonomous_agent.agent_state import build_agent_state
    from tools.usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from autonomous_lifecycle.lifecycle import build_autonomous_lifecycle
    from news_gate.classifier import classify_news_gate
    from usdjpy_autonomous_agent.agent_state import build_agent_state
    from usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso


REPORT_NAME = "QuantGod_DailyAutopilotV2.json"
AGENT_VERSION = "v2.5"

NEXT_PHASE_TODOS: List[Dict[str, Any]] = [
    {
        "id": "strategyJsonTodo",
        "lane": "SYSTEM",
        "laneZh": "策略契约",
        "titleZh": "Strategy JSON DSL",
        "status": "WAITING_NEXT_PHASE",
        "stage": "NEXT_PHASE",
        "completedByAgent": False,
        "autoAppliedByAgent": False,
        "requiresAutonomousGovernance": True,
        "summaryZh": "等待下一阶段建立 Strategy JSON 全链路策略契约；当前不会假装已经完成。",
    },
    {
        "id": "gaEvolutionTodo",
        "lane": "MT5_SHADOW",
        "laneZh": "MT5 模拟车道",
        "titleZh": "GA Evolution Engine",
        "status": "WAITING_NEXT_PHASE",
        "stage": "NEXT_PHASE",
        "completedByAgent": False,
        "autoAppliedByAgent": False,
        "requiresAutonomousGovernance": True,
        "summaryZh": "等待下一阶段接入 GA population、mutation、crossover 和 fitness；当前仍使用 replay / walk-forward / shadow ranking。",
    },
    {
        "id": "telegramGatewayTodo",
        "lane": "NOTIFICATION",
        "laneZh": "Telegram 推送",
        "titleZh": "Telegram Gateway",
        "status": "WAITING_NEXT_PHASE",
        "stage": "NEXT_PHASE",
        "completedByAgent": False,
        "autoAppliedByAgent": False,
        "requiresAutonomousGovernance": True,
        "summaryZh": "等待下一阶段拆出独立 Telegram Gateway；当前 Telegram 仍只做中文 push-only，不接交易命令。",
    },
]


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _walk_forward_summary(agent: Dict[str, Any]) -> Dict[str, Any]:
    decision = _safe_dict(agent.get("promotionDecision"))
    selected = _safe_list(_safe_dict(decision.get("parameterSelection")).get("selected"))
    candidates = _safe_list(decision.get("candidates"))
    rows = [row for row in [*selected, *candidates] if isinstance(row, dict)]
    for row in rows:
        summary = _safe_dict(row.get("summary"))
        if summary:
            return summary
    return {}


def _runtime_metrics(runtime_dir: Path, agent: Dict[str, Any]) -> Dict[str, Any]:
    summary = _walk_forward_summary(agent)
    bar_replay = _load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYBarReplayReport.json")
    replay_summary = _safe_dict(bar_replay.get("summary"))
    entry = _safe_dict(bar_replay.get("entryComparison"))
    exit_cmp = _safe_dict(bar_replay.get("exitComparison"))
    entry_variants = _safe_list(entry.get("variants"))
    exit_variants = _safe_list(exit_cmp.get("variants"))
    current_entry = _safe_dict(entry_variants[0].get("metrics")) if len(entry_variants) > 0 and isinstance(entry_variants[0], dict) else {}
    relaxed_entry = _safe_dict(entry_variants[1].get("metrics")) if len(entry_variants) > 1 and isinstance(entry_variants[1], dict) else {}
    current_exit = _safe_dict(exit_variants[0].get("metrics")) if len(exit_variants) > 0 and isinstance(exit_variants[0], dict) else {}
    let_run_exit = _safe_dict(exit_variants[1].get("metrics")) if len(exit_variants) > 1 and isinstance(exit_variants[1], dict) else {}
    return {
        "unitPolicy": "R_PRIMARY_PIPS_SECONDARY_USC_REFERENCE",
        "sampleCount": summary.get("sampleCount") or replay_summary.get("sampleCount") or 0,
        "netR": summary.get("netRDelta") or replay_summary.get("relaxedNetRDelta") or 0,
        "validationNetRDelta": summary.get("validationNetRDelta"),
        "forwardNetRDelta": summary.get("forwardNetRDelta"),
        "maxAdverseR": relaxed_entry.get("maxAdverseR") or current_entry.get("maxAdverseR"),
        "profitCaptureRatio": let_run_exit.get("profitCaptureRatio") or current_exit.get("profitCaptureRatio"),
        "missedOpportunity": replay_summary.get("entryCountDelta") or relaxed_entry.get("missedOpportunityReduction") or 0,
        "earlyExit": replay_summary.get("letProfitRunNetRDelta") or 0,
        "entryCountDelta": relaxed_entry.get("entryCountDelta") or replay_summary.get("entryCountDelta") or 0,
        "falseEntryCount": relaxed_entry.get("falseEntryCount") or 0,
        "winRate": relaxed_entry.get("winRate") or current_entry.get("winRate"),
        "evidenceQuality": relaxed_entry.get("evidenceQuality") or current_entry.get("evidenceQuality") or "AGENT_SUMMARY",
    }


def _news_gate_summary(runtime_dir: Path) -> Dict[str, Any]:
    policy = _load_json(runtime_dir / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json")
    news_gate = _safe_dict(policy.get("newsGate"))
    if news_gate:
        return news_gate
    dashboard = _load_json(runtime_dir / "QuantGod_Dashboard.json")
    snapshot = dashboard if dashboard else _load_json(runtime_dir / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json")
    return classify_news_gate(snapshot)


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


def _next_phase_todos() -> Dict[str, Any]:
    todos = [dict(item) for item in NEXT_PHASE_TODOS]
    return {
        "status": "WAITING_NEXT_PHASE",
        "completedByAgent": False,
        "autoAppliedByAgent": False,
        "requiresAutonomousGovernance": True,
        "summaryZh": "Strategy JSON、GA Evolution 和独立 Telegram Gateway 是 v2.5 自动生成的下一阶段任务；当前不假装完成。",
        "items": todos,
        "strategyJsonTodo": todos[0],
        "gaEvolutionTodo": todos[1],
        "telegramGatewayTodo": todos[2],
    }


def _build_morning_plan(agent: Dict[str, Any], lifecycle: Dict[str, Any], news_gate: Dict[str, Any]) -> Dict[str, Any]:
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
        "newsGate": {
            "mode": news_gate.get("mode", "SOFT"),
            "riskLevel": news_gate.get("riskLevel", "UNKNOWN"),
            "hardBlock": bool(news_gate.get("hardBlock")),
            "lotMultiplier": news_gate.get("lotMultiplier", 1.0),
            "stageDowngrade": bool(news_gate.get("stageDowngrade", False)),
            "reasonZh": news_gate.get("reasonZh", "普通新闻不阻断，高冲击新闻硬阻断。"),
            "highImpactEvent": news_gate.get("highImpactEvent"),
        },
        "todayForbiddenZh": [
            "USDJPY SELL 实盘",
            "非 RSI 实盘",
            "非 USDJPY 实盘",
            "Polymarket 钱包交易",
            "高冲击新闻窗口入场",
            "快通道或 runtime 陈旧时入场",
            "固定 2 手下单",
        ],
    }


def _build_evening_review(agent: Dict[str, Any], lifecycle: Dict[str, Any], news_gate: Dict[str, Any]) -> Dict[str, Any]:
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
            "autoAppliedByAgent": bool(agent.get("autoAppliedByAgent")),
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
        "newsGateReview": {
            "mode": news_gate.get("mode", "SOFT"),
            "riskLevel": news_gate.get("riskLevel", "UNKNOWN"),
            "ordinaryNewsBlocksLive": False,
            "highImpactNewsBlocksLive": True,
            "reasonZh": news_gate.get("reasonZh", "普通新闻只降仓/降级，高冲击新闻硬阻断。"),
        },
        "tomorrowStageZh": agent.get("stageZh") or "继续自主治理门评估",
    }


def _agent_todo_items(agent: Dict[str, Any], lifecycle: Dict[str, Any], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    lanes = _safe_dict(lifecycle.get("lanes") or agent.get("lanes"))
    mt5_shadow = _safe_dict(lanes.get("mt5Shadow"))
    polymarket = _safe_dict(lanes.get("polymarketShadow"))
    patch = _safe_dict(agent.get("currentPatch"))
    rollback = _safe_dict(patch.get("rollback"))
    rollback_triggered = bool(_safe_list(rollback.get("hardBlockers")))
    live_stage = str(agent.get("executionStage") or agent.get("stage") or "SHADOW")
    auto_applied = bool(agent.get("autoAppliedByAgent"))
    return [
        {
            "id": "live_lane_governance",
            "lane": "LIVE",
            "laneZh": "实盘车道",
            "status": "ROLLBACK" if rollback_triggered else ("MICRO_LIVE" if live_stage == "MICRO_LIVE" else "COMPLETED_BY_AGENT"),
            "completedByAgent": True,
            "autoAppliedByAgent": auto_applied,
            "requiresAutonomousGovernance": True,
            "promotionDecision": live_stage,
            "rollbackTriggered": rollback_triggered,
            "metrics": metrics,
            "summaryZh": "Agent 已检查 USDJPY RSI LONG 实盘车道；硬风控未通过则自动回滚，未触发则等待 EA 自身守门。",
        },
        {
            "id": "mt5_shadow_lane_iteration",
            "lane": "MT5_SHADOW",
            "laneZh": "MT5 模拟车道",
            "status": "PROMOTED" if int(_safe_dict(mt5_shadow.get("summary")).get("fastShadow") or 0) else "COMPLETED_BY_AGENT",
            "completedByAgent": True,
            "autoAppliedByAgent": False,
            "requiresAutonomousGovernance": True,
            "promotionDecision": "FAST_SHADOW_OR_TESTER_ONLY",
            "rollbackTriggered": False,
            "metrics": _safe_dict(mt5_shadow.get("summary")),
            "summaryZh": "Agent 已复盘多策略 shadow 排名；强策略可进入 fast-shadow/tester-only，不能抢实盘 RSI LONG 路线。",
        },
        {
            "id": "polymarket_shadow_lane_iteration",
            "lane": "POLYMARKET_SHADOW",
            "laneZh": "Polymarket 模拟车道",
            "status": "COMPLETED_BY_AGENT",
            "completedByAgent": True,
            "autoAppliedByAgent": False,
            "requiresAutonomousGovernance": True,
            "promotionDecision": polymarket.get("stage", "SHADOW"),
            "rollbackTriggered": False,
            "metrics": _safe_dict(polymarket.get("summary")),
            "summaryZh": "Agent 已复盘预测市场模拟账本；只做 shadow 和事件风险，不连接真钱钱包。",
        },
    ]


def _build_daily_todo(agent: Dict[str, Any], lifecycle: Dict[str, Any], metrics: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    items = _agent_todo_items(agent, lifecycle, metrics)
    next_phase = _next_phase_todos()
    rollback_triggered = any(bool(item.get("rollbackTriggered")) for item in items)
    auto_applied = any(bool(item.get("autoAppliedByAgent")) for item in items)
    return {
        "ok": True,
        "schema": "quantgod.daily_todo_agent.v2_5",
        "agentVersion": AGENT_VERSION,
        "generatedAtIso": generated_at,
        "timestamp": generated_at,
        "symbol": FOCUS_SYMBOL,
        "status": "ROLLBACK" if rollback_triggered else "COMPLETED_BY_AGENT",
        "completed": True,
        "completedByAgent": True,
        "autoAppliedByAgent": auto_applied,
        "requiresAutonomousGovernance": True,
        "lane": "MULTI_LANE",
        "promotionDecision": agent.get("executionStage") or agent.get("stage"),
        "rollbackTriggered": rollback_triggered,
        "metrics": metrics,
        "items": items,
        "nextPhaseTodos": next_phase,
        "strategyJsonTodo": next_phase["strategyJsonTodo"],
        "gaEvolutionTodo": next_phase["gaEvolutionTodo"],
        "telegramGatewayTodo": next_phase["telegramGatewayTodo"],
        "summaryZh": "今日待办已由 Agent 自动检查、生成和闭环；无需人工回灌。",
    }


def _build_daily_review(agent: Dict[str, Any], lifecycle: Dict[str, Any], metrics: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    lanes = _safe_dict(lifecycle.get("lanes") or agent.get("lanes"))
    mt5_shadow = _safe_dict(lanes.get("mt5Shadow"))
    polymarket = _safe_dict(lanes.get("polymarketShadow"))
    patch = _safe_dict(agent.get("currentPatch"))
    rollback = _safe_dict(patch.get("rollback"))
    rollback_triggered = bool(_safe_list(rollback.get("hardBlockers")))
    return {
        "ok": True,
        "schema": "quantgod.daily_review_agent.v2_5",
        "agentVersion": AGENT_VERSION,
        "generatedAtIso": generated_at,
        "timestamp": generated_at,
        "symbol": FOCUS_SYMBOL,
        "lane": "MULTI_LANE",
        "completed": True,
        "completedByAgent": True,
        "autoAppliedByAgent": bool(agent.get("autoAppliedByAgent")),
        "requiresAutonomousGovernance": True,
        "promotionDecision": agent.get("executionStage") or agent.get("stage"),
        "rollbackTriggered": rollback_triggered,
        "metrics": metrics,
        "liveLane": {
            "stage": agent.get("executionStage") or agent.get("stage"),
            "stageZh": agent.get("stageZh"),
            "strategy": "RSI_Reversal",
            "direction": "LONG",
            "rollbackReasons": _safe_list(rollback.get("hardBlockers")),
        },
        "mt5ShadowLane": {
            "summary": _safe_dict(mt5_shadow.get("summary")),
            "topRoutes": _top_mt5_routes(mt5_shadow),
        },
        "polymarketShadowLane": {
            "stage": polymarket.get("stage", "SHADOW"),
            "stageZh": polymarket.get("stageZh", "模拟观察"),
            "summary": _safe_dict(polymarket.get("summary")),
            "riskContextOnly": True,
        },
        "nextPhaseTodos": _next_phase_todos(),
        "summaryZh": "每日复盘已由 Agent 自动完成：收集三车道样本、计算指标、更新升降级/回滚状态，不等待人工确认。",
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
    generated_at = utc_now_iso()
    metrics = _runtime_metrics(runtime_dir, agent)
    news_gate = _news_gate_summary(runtime_dir)
    daily_todo = _build_daily_todo(agent, lifecycle, metrics, generated_at)
    daily_review = _build_daily_review(agent, lifecycle, metrics, generated_at)
    payload: Dict[str, Any] = {
        "ok": True,
        "schema": "quantgod.daily_autopilot_v2.v1",
        "agentVersion": AGENT_VERSION,
        "generatedAtIso": generated_at,
        "timestamp": generated_at,
        "symbol": FOCUS_SYMBOL,
        "titleZh": "USDJPY 美分账户三车道自动日报",
        "sloganZh": "实盘要窄，模拟要宽，升降级要快，回滚要硬。",
        "morningPlan": _build_morning_plan(agent, lifecycle, news_gate),
        "eveningReview": _build_evening_review(agent, lifecycle, news_gate),
        "newsGate": news_gate,
        "dailyTodo": daily_todo,
        "dailyReview": daily_review,
        "nextPhaseTodos": _next_phase_todos(),
        "completedByAgent": True,
        "autoAppliedByAgent": bool(agent.get("autoAppliedByAgent")),
        "requiresAutonomousGovernance": True,
        "autonomousAgent": {
            "stage": agent.get("executionStage") or agent.get("stage"),
            "stageZh": agent.get("stageZh"),
            "patchWritable": bool(agent.get("patchWritable")),
            "completedByAgent": True,
            "autoAppliedByAgent": bool(agent.get("autoAppliedByAgent")),
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
