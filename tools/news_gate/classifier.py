from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .config import NewsGateConfig, read_news_gate_config
from .schema import (
    HIGH_IMPACT_KEYWORDS,
    NEWS_GATE_HARD,
    NEWS_GATE_HARD_ONLY,
    NEWS_GATE_OFF,
    NEWS_GATE_SOFT,
    NEWS_RISK_HARD,
    NEWS_RISK_NONE,
    NEWS_RISK_SOFT,
    NEWS_RISK_UNKNOWN,
    NewsGateDecision,
    SOFT_RISK_KEYWORDS,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "blocked", "active"}


def _upper_text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).upper()


def _collect_news_sources(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for key in (
        "newsGate",
        "news",
        "newsFilter",
        "newsFilterStatus",
        "news_filter_status",
        "economicCalendar",
        "macroNews",
    ):
        value = snapshot.get(key)
        for item in _as_list(value):
            if isinstance(item, dict):
                item = dict(item)
                item.setdefault("_sourceKey", key)
                sources.append(item)
    runtime = _as_dict(snapshot.get("runtime"))
    for key in ("news", "newsFilter", "newsFilterStatus"):
        value = runtime.get(key)
        for item in _as_list(value):
            if isinstance(item, dict):
                item = dict(item)
                item.setdefault("_sourceKey", f"runtime.{key}")
                sources.append(item)
    if not sources:
        direct = {
            "blocked": snapshot.get("newsBlocked"),
            "allowed": snapshot.get("newsAllowed"),
            "reason": snapshot.get("newsReason"),
            "impact": snapshot.get("newsImpact"),
            "event": snapshot.get("newsEvent"),
            "_sourceKey": "snapshot.direct",
        }
        if any(value not in (None, "") for key, value in direct.items() if key != "_sourceKey"):
            sources.append(direct)
    return sources


def _event_text(event: Dict[str, Any]) -> str:
    return _upper_text(
        event.get("event"),
        event.get("eventName"),
        event.get("name"),
        event.get("title"),
        event.get("label"),
        event.get("reason"),
        event.get("impact"),
        event.get("severity"),
        event.get("importance"),
        event.get("currency"),
        event.get("country"),
        event.get("tag"),
    )


def _is_high_impact(event: Dict[str, Any]) -> bool:
    text = _event_text(event)
    impact = str(event.get("impact") or event.get("severity") or event.get("importance") or "").upper()
    if impact in {"HIGH", "HIGH_IMPACT", "CRITICAL", "RED", "3", "重大", "高"}:
        return True
    return any(keyword in text for keyword in HIGH_IMPACT_KEYWORDS)


def _is_soft_risk(event: Dict[str, Any]) -> bool:
    text = _event_text(event)
    if any(keyword in text for keyword in SOFT_RISK_KEYWORDS):
        return True
    return any(_truthy(event.get(key)) for key in ("blocked", "active", "preBlockActive", "blockActive"))


def _reason_for_event(event: Dict[str, Any], fallback: str) -> str:
    for key in ("reasonZh", "reason", "eventName", "event", "name", "title", "label"):
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return fallback


def classify_news_gate(snapshot: Dict[str, Any], config: Optional[NewsGateConfig] = None) -> Dict[str, Any]:
    cfg = config or read_news_gate_config()
    snapshot = _as_dict(snapshot)
    events = _collect_news_sources(snapshot)
    if cfg.mode == NEWS_GATE_OFF:
        return NewsGateDecision(
            mode=cfg.mode,
            riskLevel=NEWS_RISK_NONE,
            hardBlock=False,
            lotMultiplier=1.0,
            stageDowngrade=False,
            reasonZh="新闻门禁关闭：只记录，不影响入场。",
            sourceAvailable=bool(events),
        ).to_dict()
    if not events:
        return NewsGateDecision(
            mode=cfg.mode,
            riskLevel=NEWS_RISK_UNKNOWN,
            hardBlock=False,
            lotMultiplier=cfg.unknownLotMultiplier,
            stageDowngrade=False,
            reasonZh="新闻源不可用或未同步：不阻断，只轻微降仓并记录数据质量问题。",
            sourceAvailable=False,
        ).to_dict()

    blocked_keys = ("blocked", "newsBlocked", "active", "preBlockActive", "blockActive")
    blocked_events = [
        event
        for event in events
        if any(_truthy(event.get(key)) for key in blocked_keys)
    ]
    high_event = next((event for event in events if _is_high_impact(event)), None)
    soft_event = next((event for event in events if _is_soft_risk(event)), None)
    blocked_by_source = bool(blocked_events)

    if cfg.mode == NEWS_GATE_HARD and (blocked_by_source or high_event or soft_event):
        event = high_event or soft_event or blocked_events[0]
        return NewsGateDecision(
            mode=cfg.mode,
            riskLevel=NEWS_RISK_HARD,
            hardBlock=True,
            lotMultiplier=0.0,
            stageDowngrade=True,
            reasonZh="新闻门禁 HARD：新闻风险按旧规则硬阻断。",
            highImpactEvent=event,
            sourceAvailable=True,
            blockedBySource=blocked_by_source,
            wouldHaveBlockedBeforeV251=blocked_by_source,
        ).to_dict()

    if high_event:
        return NewsGateDecision(
            mode=cfg.mode if cfg.mode != NEWS_GATE_HARD_ONLY else NEWS_GATE_HARD_ONLY,
            riskLevel=NEWS_RISK_HARD,
            hardBlock=True,
            lotMultiplier=0.0,
            stageDowngrade=True,
            reasonZh=f"高冲击新闻窗口：{_reason_for_event(high_event, '高冲击事件')}，暂停 live，shadow / replay 继续。",
            highImpactEvent=high_event,
            sourceAvailable=True,
            blockedBySource=blocked_by_source,
            wouldHaveBlockedBeforeV251=True,
        ).to_dict()

    if cfg.mode in {NEWS_GATE_SOFT, NEWS_GATE_HARD_ONLY} and (soft_event or blocked_by_source):
        event = soft_event or blocked_events[0]
        return NewsGateDecision(
            mode=cfg.mode,
            riskLevel=NEWS_RISK_SOFT,
            hardBlock=False,
            lotMultiplier=cfg.softLotMultiplier,
            stageDowngrade=cfg.softStageDowngrade,
            reasonZh=f"普通新闻风险：{_reason_for_event(event, '普通新闻')}，只降仓/降级，不阻断。",
            sourceAvailable=True,
            blockedBySource=blocked_by_source,
            wouldHaveBlockedBeforeV251=blocked_by_source,
        ).to_dict()

    return NewsGateDecision(
        mode=cfg.mode,
        riskLevel=NEWS_RISK_NONE,
        hardBlock=False,
        lotMultiplier=1.0,
        stageDowngrade=False,
        reasonZh="当前没有新闻风险，不影响入场。",
        sourceAvailable=True,
        blockedBySource=blocked_by_source,
        wouldHaveBlockedBeforeV251=blocked_by_source,
    ).to_dict()
