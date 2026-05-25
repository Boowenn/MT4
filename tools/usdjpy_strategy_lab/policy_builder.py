from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List

try:
    from tools.autonomous_lifecycle.account_registry import mt5_account_registry
    from tools.news_gate.classifier import classify_news_gate
    from tools.news_gate.policy import apply_news_gate_to_live_policy
except ModuleNotFoundError:  # CLI execution from tools/
    from autonomous_lifecycle.account_registry import mt5_account_registry
    from news_gate.classifier import classify_news_gate
    from news_gate.policy import apply_news_gate_to_live_policy

from .data_loader import (
    adaptive_policy,
    dynamic_sltp,
    entry_trigger_plan,
    fastlane_quality,
    first_json,
    focus_runtime_snapshot,
)
from .schema import (
    ENTRY_BLOCKED,
    ENTRY_OPPORTUNITY,
    ENTRY_STANDARD,
    FOCUS_SYMBOL,
    PolicyItem,
    READ_ONLY_SAFETY,
    STATUS_PAUSED,
    STATUS_RUNNABLE,
    STATUS_WATCH_ONLY,
    STRATEGY_CATALOG_VERSION,
    assert_no_secret_or_execution_flags,
    utc_now_iso,
)
from .strategy_signals import build_candidate_signals
from .strategy_scoreboard import build_strategy_scoreboard

FASTLANE_PASS_STATES = {"OK", "PASS", "PASSED", "GOOD", "HEALTHY", "FAST", "EA_DASHBOARD_OK"}
LIVE_ELIGIBLE_STRATEGY = "RSI_Reversal"
LIVE_ELIGIBLE_DIRECTION = "LONG"
RUNTIME_FRESH_SECONDS = 30.0
RUNTIME_HARD_STALE_SECONDS = 90.0
HARD_RSI_DIAGNOSTIC_STATES = {
    "KILL_SWITCH",
    "SYMBOL_POSITION_FULL",
    "MANUAL_POSITION_BLOCK",
    "LOSS_COOLDOWN",
    "NEWS_BLOCK",
    "SESSION_CLOSED",
    "SPREAD_BLOCK",
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _round_lot(value: float, step: float = 0.01, min_lot: float = 0.01, max_lot: float = 2.0) -> float:
    if value <= 0:
        return 0.0
    value = max(min_lot, min(value, max_lot))
    steps = round(value / step)
    return round(max(min_lot, min(max_lot, steps * step)), 2)


def _runtime_thresholds() -> tuple[float, float]:
    fresh = max(5.0, _env_float("QG_USDJPY_RUNTIME_FRESH_SOFT_SECONDS", RUNTIME_FRESH_SECONDS))
    hard = max(fresh, _env_float("QG_USDJPY_RUNTIME_HARD_STALE_SECONDS", RUNTIME_HARD_STALE_SECONDS))
    return fresh, hard


def _price_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    current_price = snapshot.get("current_price") if isinstance(snapshot.get("current_price"), dict) else {}
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    return {**market, **current_price}


def _credible_price(snapshot: Dict[str, Any]) -> bool:
    price = _price_payload(snapshot)
    bid = _num(price.get("bid"), 0.0)
    ask = _num(price.get("ask"), 0.0)
    last = _num(price.get("last") or price.get("price"), 0.0)
    if bid > 0 and ask > 0 and ask >= bid:
        return True
    return last > 0


def _runtime_freshness(snapshot: Dict[str, Any]) -> tuple[str, bool, List[str]]:
    if not snapshot:
        return "MISSING", False, ["缺少 USDJPY 运行快照"]
    if not _credible_price(snapshot):
        return "NO_CREDIBLE_PRICE", False, ["运行快照缺少可信 bid/ask/current price，禁止自动入场"]
    fresh_limit, hard_limit = _runtime_thresholds()
    reasons: List[str] = []
    age = snapshot.get("runtimeAgeSeconds", snapshot.get("_fileAgeSeconds"))
    age_value = _num(age, -1.0)
    if bool(snapshot.get("fallback")):
        return "FALLBACK_BLOCKED", False, ["运行快照处于回退模式，禁止自动入场"]
    if age_value >= 0:
        if age_value > hard_limit:
            return "HARD_STALE", False, [f"运行快照严重陈旧：{age_value:.0f}s > {hard_limit:.0f}s"]
        if age_value > fresh_limit:
            reasons.append(f"运行快照轻微陈旧：{age_value:.0f}s，降为机会入场/小仓")
            return "SOFT_STALE", True, reasons
    if snapshot.get("runtimeFresh") is False:
        reasons.append("运行快照标记为不新鲜，降级观察")
        return "SOFT_STALE", True, reasons
    return "FRESH", True, ["运行快照通过"]


def _runtime_ok(snapshot: Dict[str, Any]) -> tuple[bool, List[str]]:
    _tier, ok, reasons = _runtime_freshness(snapshot)
    return ok, reasons


def _load_rsi_entry_diagnostics(runtime_dir: Path) -> Dict[str, Any]:
    diagnostics = first_json(runtime_dir, "QuantGod_USDJPYRsiEntryDiagnostics.json") or {}
    if diagnostics:
        return diagnostics
    dashboard = first_json(runtime_dir, "QuantGod_Dashboard.json") or {}
    embedded = dashboard.get("usdJpyRsiEntryDiagnostics")
    return embedded if isinstance(embedded, dict) else {}


def _rsi_diagnostic_ready(diagnostics: Dict[str, Any]) -> bool:
    state = str(diagnostics.get("state") or "").upper()
    if state == "READY_BUY_SIGNAL":
        return True
    rsi = diagnostics.get("rsi") if isinstance(diagnostics.get("rsi"), dict) else {}
    signal_direction = str(rsi.get("signalDirection") or diagnostics.get("direction") or "").upper()
    return bool(rsi.get("signalReady")) and signal_direction in {"BUY", "LONG"}


def _rsi_hard_gate(diagnostics: Dict[str, Any]) -> tuple[bool, List[str]]:
    if not diagnostics:
        return True, []
    state = str(diagnostics.get("state") or "").upper()
    if state not in HARD_RSI_DIAGNOSTIC_STATES:
        return True, []
    summary = diagnostics.get("summary") or diagnostics.get("stateZh") or state
    reasons = [f"EA RSI 诊断硬阻断：{summary}"]
    why = diagnostics.get("whyNoEntry") if isinstance(diagnostics.get("whyNoEntry"), list) else []
    for row in why[:2]:
        if isinstance(row, dict):
            detail = row.get("detail") or row.get("label") or row.get("code")
            if detail:
                reasons.append(str(detail))
    return False, reasons


def _fastlane_ok(quality: Dict[str, Any]) -> tuple[bool, List[str]]:
    if not quality.get("found"):
        return False, ["缺少 USDJPY 快通道质量证据"]
    state = str(quality.get("quality") or "MISSING").upper()
    if state not in FASTLANE_PASS_STATES:
        return False, [f"快通道质量未通过：{state}"]
    if quality.get("focusSymbolFound") is False:
        return False, ["快通道质量文件未包含 USDJPY"]
    if state == "EA_DASHBOARD_OK":
        return True, ["快通道质量降级可用：使用 HFM EA Dashboard 新鲜快照"]
    return True, ["快通道质量通过"]


def _is_live_route(item: PolicyItem) -> bool:
    return item.strategy == LIVE_ELIGIBLE_STRATEGY and str(item.direction).upper() == LIVE_ELIGIBLE_DIRECTION


def _is_live_eligible(item: PolicyItem) -> bool:
    return _is_live_route(item) and item.entryMode in {ENTRY_STANDARD, ENTRY_OPPORTUNITY} and bool(item.allowed)


def _trigger_state(plan: Dict[str, Any], direction: str) -> tuple[str, List[str], float, Dict[str, Any]]:
    items = plan.get("plans") or plan.get("triggers") or plan.get("items") or plan.get("decisions") or []
    if isinstance(items, dict):
        items = list(items.values())
    best = None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol") or "").upper().startswith("USDJPY") and str(item.get("direction") or "").upper() == direction:
            best = item
            break
    if not best:
        return "MISSING", ["缺少 USDJPY 入场触发计划"], 0.0, {
            "status": "MISSING",
            "missingConfirmations": ["trigger_plan"],
            "score": 0.0,
        }
    status = str(best.get("status") or best.get("state") or best.get("entryMode") or "UNKNOWN").upper()
    score = best.get("triggerScore") or best.get("score") or 0.0
    try:
        score = float(score)
        if score <= 1.0:
            score *= 100
    except Exception:
        score = 0.0
    missing = best.get("missingConfirmations") or best.get("missing") or []
    if isinstance(missing, str):
        missing = [missing]
    confirmations = best.get("confirmations") if isinstance(best.get("confirmations"), dict) else {}
    tactical = {
        "status": status,
        "missingConfirmations": [str(item) for item in missing],
        "score": score,
        "confirmations": confirmations,
    }
    if status in {"READY_FOR_CONFIRMATION", "WAIT_TRIGGER_CONFIRMATION", "STANDARD_ENTRY", "PASS", "READY", "OPPORTUNITY_ENTRY"}:
        if not missing:
            return "TACTICAL_OK", ["入场触发允许：核心项全部通过"], score, tactical
        if len(missing) <= 1:
            return "TACTICAL_PARTIAL", ["入场触发部分确认：核心项通过，战术确认缺一项"], score, tactical
    reasons = best.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    blocked_detail = missing or reasons
    return "BLOCKED", ["入场触发阻断" if not blocked_detail else "入场触发阻断：" + "、".join([str(item) for item in blocked_detail[:3]])], score, tactical


def _sltp_available(plan: Dict[str, Any], strategy: str, direction: str) -> tuple[bool, List[str], Dict[str, Any]]:
    plans = plan.get("plans") or plan.get("items") or plan.get("calibrations") or []
    if isinstance(plans, dict):
        plans = list(plans.values())
    for item in plans if isinstance(plans, list) else []:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol") or "").upper()
        item_strategy = str(item.get("strategy") or "").strip()
        item_direction = str(item.get("direction") or "").upper()
        status = str(item.get("status") or "").upper()
        if sym.startswith("USDJPY") and item_strategy == strategy and item_direction == direction and status not in {"PAUSED", "BLOCKED", "INSUFFICIENT_DATA"}:
            return True, ["动态止盈止损可用"], item
    direction_plans = plan.get("dynamicSltpPlans") or []
    if isinstance(direction_plans, dict):
        direction_plans = list(direction_plans.values())
    for item in direction_plans if isinstance(direction_plans, list) else []:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol") or "").upper()
        item_direction = str(item.get("direction") or "").upper()
        risk_mode = str(item.get("riskMode") or "").upper()
        if sym.startswith("USDJPY") and item_direction == direction and risk_mode != "暂停":
            return True, ["动态止盈止损方向级计划可用"], item
    if plan:
        return False, ["动态止盈止损未匹配当前策略方向"], {}
    return False, ["缺少动态止盈止损计划"], {}


def _soften_live_route_trigger(status: str, strategy: str, direction: str, trigger_status: str, trigger_reasons: List[str]) -> tuple[str, List[str]]:
    if status != STATUS_RUNNABLE:
        return trigger_status, trigger_reasons
    if strategy != LIVE_ELIGIBLE_STRATEGY or str(direction).upper() != LIVE_ELIGIBLE_DIRECTION:
        return trigger_status, trigger_reasons
    if trigger_status != "BLOCKED":
        return trigger_status, trigger_reasons
    text = "；".join(str(item) for item in trigger_reasons)
    if "影子样本" not in text:
        return trigger_status, trigger_reasons
    return "TACTICAL_PARTIAL", [
        "RSI 实盘买入 forward 为正；影子方向池偏弱不阻断现有 EA 路线，仍由 EA 的 RSI、新闻、session、spread 风控二次确认。"
    ]


def _hard_gate(
    *,
    runtime_ok: bool,
    runtime_reasons: List[str],
    fast_ok: bool,
    fast_reasons: List[str],
    sltp_ok: bool,
    sltp_reasons: List[str],
    news_gate: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> tuple[str, List[str]]:
    blockers: List[str] = []
    if not runtime_ok:
        blockers.extend(runtime_reasons)
    if not fast_ok:
        blockers.extend(fast_reasons)
    if not sltp_ok:
        blockers.extend(sltp_reasons)
    rsi_ok, rsi_reasons = _rsi_hard_gate(diagnostics)
    if not rsi_ok:
        blockers.extend(rsi_reasons)
    if news_gate.get("hardBlock") or str(news_gate.get("riskLevel") or "").upper() == "HARD":
        blockers.append(news_gate.get("reasonZh") or "高冲击新闻窗口，暂停 live。")
    return ("PASS", ["硬风控通过"]) if not blockers else ("BLOCKED", list(dict.fromkeys(blockers)))


def _signal_quorum(
    *,
    status: str,
    score: float,
    trigger_status: str,
    runtime_tier: str,
    diagnostics: Dict[str, Any],
    news_gate: Dict[str, Any],
) -> Dict[str, Any]:
    rsi_ready = _rsi_diagnostic_ready(diagnostics)
    direction_signal = status == STATUS_RUNNABLE or score >= 45
    trigger_signal = trigger_status in {"TACTICAL_OK", "TACTICAL_PARTIAL"} or (
        trigger_status == "MISSING" and rsi_ready
    )
    market_context = runtime_tier in {"FRESH", "SOFT_STALE"} and not (
        news_gate.get("hardBlock") or str(news_gate.get("riskLevel") or "").upper() == "HARD"
    )
    components = {
        "directionSignal": bool(direction_signal),
        "triggerSignal": bool(trigger_signal),
        "marketContext": bool(market_context),
    }
    return {
        "signalQuorum": sum(1 for value in components.values() if value),
        "signalQuorumRequired": 2,
        "components": components,
        "rsiDiagnosticReady": rsi_ready,
        "missingTriggerWithoutRsiDiagnostic": trigger_status == "MISSING" and not rsi_ready,
    }


def _recommended_lot(score: float, entry_mode: str, *, max_lot: float, min_lot: float, step: float) -> float:
    risk_pct = _env_float("QG_AUTO_RISK_PER_TRADE_PCT", 0.5)
    opportunity_mult = _env_float("QG_AUTO_OPPORTUNITY_LOT_MULTIPLIER", 0.35)
    standard_mult = _env_float("QG_AUTO_STANDARD_LOT_MULTIPLIER", 1.0)
    equity = _env_float("QG_AUTO_ACCOUNT_EQUITY", 1000.0)
    base = max_lot * max(0.10, min(1.0, score / 100.0)) * max(0.05, min(2.0, risk_pct / 0.5))
    if entry_mode == ENTRY_OPPORTUNITY:
        base *= opportunity_mult
    elif entry_mode == ENTRY_STANDARD:
        base *= standard_mult
    else:
        base = 0.0
    return _round_lot(base, step=step, min_lot=min_lot, max_lot=max_lot)


def build_usdjpy_policy(runtime_dir: Path, *, write: bool = False, min_samples: int = 5) -> Dict[str, Any]:
    max_lot = _env_float("QG_AUTO_MAX_LOT", 2.0)
    min_lot = _env_float("QG_AUTO_MIN_LOT", 0.01)
    step = _env_float("QG_AUTO_LOT_STEP", 0.01)
    scoreboard = build_strategy_scoreboard(runtime_dir, min_samples=min_samples)
    candidate_signals = build_candidate_signals(runtime_dir, limit=20)
    snapshot = focus_runtime_snapshot(runtime_dir)
    quality = fastlane_quality(runtime_dir)
    trigger = entry_trigger_plan(runtime_dir)
    sltp = dynamic_sltp(runtime_dir)
    adaptive = adaptive_policy(runtime_dir)
    news_gate = classify_news_gate(snapshot or {})
    account_registry = mt5_account_registry()
    runtime_tier, runtime_ok, runtime_reasons = _runtime_freshness(snapshot or {})
    fast_ok, fast_reasons = _fastlane_ok(quality)
    diagnostics = _load_rsi_entry_diagnostics(runtime_dir)
    policies: List[PolicyItem] = []
    for route in scoreboard.get("routes", []):
        status = route.get("status")
        strategy = route.get("strategy") or "UNKNOWN_STRATEGY"
        direction = route.get("direction") or "UNKNOWN"
        regime = route.get("regime") or "UNKNOWN"
        score = float(route.get("score") or 0.0)
        reasons = list(route.get("reasons") or [])
        reasons.extend(runtime_reasons)
        reasons.extend(fast_reasons)
        trigger_status, trigger_reasons, trigger_score, tactical_confirmations = _trigger_state(trigger, direction)
        trigger_status, trigger_reasons = _soften_live_route_trigger(status, strategy, direction, trigger_status, trigger_reasons)
        sltp_ok, sltp_reasons, sltp_item = _sltp_available(sltp, strategy, direction)
        reasons.extend(trigger_reasons)
        reasons.extend(sltp_reasons)
        hard_status, hard_reasons = _hard_gate(
            runtime_ok=runtime_ok,
            runtime_reasons=runtime_reasons,
            fast_ok=fast_ok,
            fast_reasons=fast_reasons,
            sltp_ok=sltp_ok,
            sltp_reasons=sltp_reasons,
            news_gate=news_gate,
            diagnostics=diagnostics if strategy == LIVE_ELIGIBLE_STRATEGY and str(direction).upper() == LIVE_ELIGIBLE_DIRECTION else {},
        )
        quorum = _signal_quorum(
            status=str(status or ""),
            score=score,
            trigger_status=trigger_status,
            runtime_tier=runtime_tier,
            diagnostics=diagnostics if strategy == LIVE_ELIGIBLE_STRATEGY and str(direction).upper() == LIVE_ELIGIBLE_DIRECTION else {},
            news_gate=news_gate,
        )
        reasons.extend(hard_reasons if hard_status == "BLOCKED" else [])
        live_route = strategy == LIVE_ELIGIBLE_STRATEGY and str(direction).upper() == LIVE_ELIGIBLE_DIRECTION
        entry_mode = STATUS_WATCH_ONLY
        allowed = False
        strictness = "WATCH_ONLY_QUORUM"
        if status == STATUS_PAUSED:
            entry_mode = ENTRY_BLOCKED
            strictness = "BLOCKED_STRATEGY_PAUSED"
            reasons.append("策略方向近期表现为负，暂停")
        elif not live_route:
            strictness = "SHADOW_ONLY_NON_RSI_LIVE_ROUTE"
            reasons.append("非 RSI_Reversal LONG 不进入 MT5 live；只保留 shadow/replay/GA 研究。")
        elif hard_status != "PASS":
            entry_mode = ENTRY_BLOCKED
            strictness = "BLOCKED_HARD_RISK_GATE"
            reasons.append("硬风控未通过，禁止机会入场")
        elif quorum.get("missingTriggerWithoutRsiDiagnostic"):
            strictness = "WATCH_ONLY_TRIGGER_MISSING_NO_RSI_DIAGNOSTIC"
            reasons.append("缺少 trigger plan 且 EA RSI 诊断未显示 READY_BUY_SIGNAL，只能观察。")
        elif trigger_status == "TACTICAL_OK" and int(quorum["signalQuorum"]) == 3 and score >= 70:
            entry_mode = ENTRY_STANDARD
            allowed = True
            strictness = "STANDARD_HARD_GATE_PASS_QUORUM_3"
        elif int(quorum["signalQuorum"]) >= 2 and score >= 45:
            entry_mode = ENTRY_OPPORTUNITY
            allowed = True
            strictness = "OPPORTUNITY_HARD_GATE_PASS_QUORUM_2_OF_3"
            reasons.append("硬风控通过，2/3 信号 quorum 达标，允许小仓机会观察")
        else:
            reasons.append("硬风控通过但 quorum/分数不足，保持观察不入场")
        if entry_mode == ENTRY_STANDARD and runtime_tier == "SOFT_STALE":
            entry_mode = ENTRY_OPPORTUNITY
            strictness = "RUNTIME_SOFT_STALE_STAGE_DOWNGRADED"
            reasons.append("runtime 轻微陈旧：标准入场降为机会入场并由仓位控制降风险。")
        lot = _recommended_lot(score, entry_mode, max_lot=max_lot, min_lot=min_lot, step=step)
        if live_route:
            entry_mode, allowed, lot, strictness, reasons = apply_news_gate_to_live_policy(
                entry_mode=entry_mode,
                allowed=allowed,
                recommended_lot=lot,
                strictness=strictness,
                reasons=reasons,
                news_gate=news_gate,
                min_lot=min_lot,
                max_lot=max_lot,
                step=step,
            )
        else:
            reasons.append("新闻风险只记录到 shadow / replay，不阻断 MT5 模拟策略。")
        policies.append(PolicyItem(
            symbol=FOCUS_SYMBOL,
            strategy=strategy,
            direction=direction,
            regime=regime,
            entryMode=entry_mode,
            allowed=allowed,
            recommendedLot=lot,
            maxLot=max_lot,
            score=round(score, 2),
            entryStrictness=strictness,
            exitMode="LET_PROFIT_RUN" if allowed else "NO_POSITION",
            breakevenDelayR=float(sltp_item.get("breakevenDelayR", 0.9)) if sltp_item else 0.9,
            trailStartR=float(sltp_item.get("trailStartR", 1.4)) if sltp_item else 1.4,
            timeStopBars=int(float(sltp_item.get("timeStopBars", 6))) if sltp_item else 6,
            reasons=list(dict.fromkeys([str(r) for r in reasons if r])),
            newsGate=dict(news_gate),
            hardGateStatus=hard_status if live_route else "SHADOW_ONLY",
            hardGateReasons=hard_reasons,
            runtimeFreshnessTier=runtime_tier,
            signalQuorum=int(quorum["signalQuorum"]),
            signalQuorumRequired=int(quorum["signalQuorumRequired"]),
            signalComponents=dict(quorum["components"]),
            tacticalConfirmations={**tactical_confirmations, "policyTriggerStatus": trigger_status, "triggerScore": trigger_score},
            entryDecision=entry_mode,
        ))

    policies.sort(key=lambda item: (item.entryMode == ENTRY_BLOCKED, -item.score, -item.recommendedLot, item.strategy))
    top_shadow_policy = policies[0].to_dict() if policies else None
    live_route_candidates = [item for item in policies if _is_live_route(item)]
    live_eligible_candidates = [item for item in policies if _is_live_eligible(item)]
    top_live_policy = live_eligible_candidates[0].to_dict() if live_eligible_candidates else None
    live_recovery_candidate = live_route_candidates[0].to_dict() if live_route_candidates else None
    top_policy = top_live_policy or live_recovery_candidate or top_shadow_policy
    payload = {
        "schema": "quantgod.usdjpy_auto_execution_policy.v1",
        "generatedAt": utc_now_iso(),
        "strategyCatalogVersion": STRATEGY_CATALOG_VERSION,
        "focusOnly": True,
        "symbol": FOCUS_SYMBOL,
        "allowedSymbols": [FOCUS_SYMBOL],
        "ignoredNonFocusSymbols": True,
        "marketRegime": (snapshot or {}).get("regime") or (snapshot or {}).get("marketRegime") or "UNKNOWN",
        "policyConstraints": {
            "focusOnly": True,
            "newStrategiesShadowOnlyUntilEvidencePass": True,
            "requiresBacktestBeforeLive": True,
            "requiresGovernanceBeforeLive": True,
            "requiresAutonomousGovernance": True,
            "operatorApprovalRequired": False,
            "unattendedLiveExpansionAllowed": True,
            "liveScopeExpansionMode": "autonomous_governance_stage_gated",
            "autoApplyAllowed": "stage_gated",
            "patchWritable": True,
            "liveMutationAllowed": False,
            "rsiLiveRoutePreserved": True,
            "newsGateDefaultMode": news_gate.get("mode"),
            "ordinaryNewsHardBlocksLive": False,
            "highImpactNewsHardBlocksLive": True,
        },
        "newsGate": news_gate,
        "accountRegistry": account_registry,
        "accountLanePolicy": {
            "centAccountCanUseOpportunityEntry": True,
            "usdAccountOpportunityEntryMode": "PAPER_MIRROR_ONLY",
            "usdAccountLiveEntryModes": ["STANDARD_ENTRY"],
            "polymarketLogicUnchanged": True,
        },
        "maxLot": max_lot,
        "standardEntryCount": sum(1 for item in policies if item.entryMode == ENTRY_STANDARD),
        "opportunityEntryCount": sum(1 for item in policies if item.entryMode == ENTRY_OPPORTUNITY),
        "watchOnlyCount": sum(1 for item in policies if item.entryMode == STATUS_WATCH_ONLY),
        "blockedCount": sum(1 for item in policies if item.entryMode == ENTRY_BLOCKED),
        "topPolicy": top_policy,
        "topShadowPolicy": top_shadow_policy,
        "topLiveEligiblePolicy": top_live_policy,
        "liveRecoveryCandidate": live_recovery_candidate,
        "strategies": [item.to_dict() for item in policies],
        "evidence": {
            "runtimeOk": runtime_ok,
            "runtimeFreshnessTier": runtime_tier,
            "fastlaneOk": fast_ok,
            "triggerPlanFound": bool(trigger),
            "dynamicSltpFound": bool(sltp),
            "adaptivePolicyFound": bool(adaptive),
            "scoreboardRoutes": len(scoreboard.get("routes", [])),
            "candidateSignalCount": candidate_signals.get("count", 0),
            "topLiveEligiblePolicyFound": bool(top_live_policy),
            "topShadowPolicyStrategy": (top_shadow_policy or {}).get("strategy"),
            "newsGateMode": news_gate.get("mode"),
            "newsRiskLevel": news_gate.get("riskLevel"),
            "newsHardBlock": bool(news_gate.get("hardBlock")),
            "decisionModel": "HARD_GATES_PLUS_SIGNAL_QUORUM_V1",
            "hardGatePassCount": sum(1 for item in policies if item.hardGateStatus == "PASS"),
            "quorumEligibleCount": sum(1 for item in policies if int(item.signalQuorum) >= int(item.signalQuorumRequired)),
        },
        "candidateSignals": candidate_signals.get("signals", []),
        "scoreboard": scoreboard,
        "safety": dict(READ_ONLY_SAFETY),
    }
    assert_no_secret_or_execution_flags(payload)
    if write:
        adaptive_dir = runtime_dir / "adaptive"
        adaptive_dir.mkdir(parents=True, exist_ok=True)
        policy_path = adaptive_dir / "QuantGod_USDJPYAutoExecutionPolicy.json"
        policy_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ledger_path = adaptive_dir / "QuantGod_USDJPYAutoExecutionPolicyLedger.csv"
        is_new = not ledger_path.exists()
        with ledger_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["generatedAt", "symbol", "standard", "opportunity", "blocked", "topStrategy", "topMode", "topLot"])
            if is_new:
                writer.writeheader()
            top = payload.get("topPolicy") or {}
            writer.writerow({
                "generatedAt": payload["generatedAt"],
                "symbol": FOCUS_SYMBOL,
                "standard": payload["standardEntryCount"],
                "opportunity": payload["opportunityEntryCount"],
                "blocked": payload["blockedCount"],
                "topStrategy": top.get("strategy", ""),
                "topMode": top.get("entryMode", ""),
                "topLot": top.get("recommendedLot", 0),
            })
    return payload
