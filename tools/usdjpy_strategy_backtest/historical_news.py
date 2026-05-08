from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from tools.news_gate.schema import HIGH_IMPACT_KEYWORDS, SOFT_RISK_KEYWORDS
except ModuleNotFoundError:  # pragma: no cover
    from news_gate.schema import HIGH_IMPACT_KEYWORDS, SOFT_RISK_KEYWORDS


DEFAULT_PRE_MINUTES = 30
DEFAULT_POST_MINUTES = 30


def load_historical_news_events(runtime_dir: Path) -> Dict[str, Any]:
    paths = [
        runtime_dir / "news" / "QuantGod_USDJPYNewsEvents.json",
        runtime_dir / "news" / "QuantGod_USDJPYHighImpactEvents.json",
        runtime_dir / "QuantGod_USDJPYNewsEvents.json",
        runtime_dir / "QuantGod_USDJPYHighImpactEvents.json",
    ]
    csv_paths = [
        runtime_dir / "news" / "QuantGod_USDJPYNewsEvents.csv",
        runtime_dir / "news" / "QuantGod_USDJPYHighImpactEvents.csv",
    ]
    events: List[Dict[str, Any]] = []
    sources: List[str] = []
    for path in paths:
        loaded = _load_json_events(path)
        if loaded:
            events.extend(loaded)
            sources.append(str(path))
    for path in csv_paths:
        loaded = _load_csv_events(path)
        if loaded:
            events.extend(loaded)
            sources.append(str(path))
    normalized = sorted((_normalize_event(item) for item in events), key=lambda item: item.get("timeIso") or "")
    normalized = [item for item in normalized if item.get("timeIso")]
    return {
        "schema": "quantgod.usdjpy_historical_news_events.v1",
        "sourceAvailable": bool(sources),
        "sources": sources,
        "eventCount": len(normalized),
        "digest": _events_digest(normalized),
        "events": normalized,
        "reasonZh": (
            "已加载历史新闻事件，回测会按 HARD/SOFT/UNKNOWN 新闻门禁评估每个入场。"
            if sources
            else "未发现历史新闻事件文件；回测不会凭空阻断，只在报告中标记新闻样本待补。"
        ),
    }


def classify_historical_news(timestamp: str, news: Dict[str, Any]) -> Dict[str, Any]:
    events = news.get("events") if isinstance(news.get("events"), list) else []
    if not news.get("sourceAvailable"):
        return {
            "riskLevel": "UNKNOWN",
            "hardBlock": False,
            "lotMultiplier": 1.0,
            "stageDowngrade": False,
            "sourceAvailable": False,
            "reasonZh": "历史新闻源未接入：不阻断回测，只记录 UNKNOWN。",
            "event": None,
        }
    current = _parse_time(timestamp)
    if current is None:
        return {
            "riskLevel": "UNKNOWN",
            "hardBlock": False,
            "lotMultiplier": 0.75,
            "stageDowngrade": False,
            "sourceAvailable": True,
            "reasonZh": "无法解析 bar 时间：新闻风险 UNKNOWN，轻微降权。",
            "event": None,
        }
    active = [event for event in events if _event_active_at(event, current)]
    if not active:
        return {
            "riskLevel": "NONE",
            "hardBlock": False,
            "lotMultiplier": 1.0,
            "stageDowngrade": False,
            "sourceAvailable": True,
            "reasonZh": "无历史新闻风险。",
            "event": None,
        }
    hard = next((event for event in active if event.get("riskLevel") == "HARD"), None)
    if hard:
        return {
            "riskLevel": "HARD",
            "hardBlock": True,
            "lotMultiplier": 0.0,
            "stageDowngrade": True,
            "sourceAvailable": True,
            "reasonZh": f"高冲击历史新闻窗口：{hard.get('title') or hard.get('event') or '高冲击事件'}。",
            "event": hard,
        }
    soft = active[0]
    return {
        "riskLevel": "SOFT",
        "hardBlock": False,
        "lotMultiplier": 0.5,
        "stageDowngrade": True,
        "sourceAvailable": True,
        "reasonZh": f"普通历史新闻风险：{soft.get('title') or soft.get('event') or '普通新闻'}，只降仓不阻断。",
        "event": soft,
    }


def _load_json_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("events", "items", "highImpactEvents"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return []


def _load_csv_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append(dict(row))
    except Exception:
        return []
    return rows


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    time_iso = _event_time(event)
    text = _upper_text(
        event.get("event"),
        event.get("eventName"),
        event.get("title"),
        event.get("name"),
        event.get("impact"),
        event.get("severity"),
        event.get("currency"),
        event.get("country"),
    )
    impact = str(event.get("impact") or event.get("severity") or event.get("importance") or "").upper()
    risk = "HARD" if impact in {"HIGH", "CRITICAL", "RED", "3", "重大", "高"} or any(key in text for key in HIGH_IMPACT_KEYWORDS) else "SOFT"
    if risk != "HARD" and not any(key in text for key in SOFT_RISK_KEYWORDS):
        risk = "SOFT"
    return {
        "timeIso": time_iso,
        "riskLevel": risk,
        "title": event.get("title") or event.get("eventName") or event.get("event") or event.get("name") or "",
        "currency": event.get("currency") or event.get("country") or "",
        "impact": event.get("impact") or event.get("severity") or event.get("importance") or "",
        "windowBeforeMinutes": int(_num(event.get("windowBeforeMinutes") or event.get("beforeMinutes"), DEFAULT_PRE_MINUTES)),
        "windowAfterMinutes": int(_num(event.get("windowAfterMinutes") or event.get("afterMinutes"), DEFAULT_POST_MINUTES)),
    }


def _event_active_at(event: Dict[str, Any], current: datetime) -> bool:
    event_time = _parse_time(event.get("timeIso"))
    if event_time is None:
        return False
    before = timedelta(minutes=int(_num(event.get("windowBeforeMinutes"), DEFAULT_PRE_MINUTES)))
    after = timedelta(minutes=int(_num(event.get("windowAfterMinutes"), DEFAULT_POST_MINUTES)))
    return event_time - before <= current <= event_time + after


def _event_time(event: Dict[str, Any]) -> str | None:
    for key in ("timeIso", "timestamp", "time", "datetime", "dateTime", "eventTime"):
        parsed = _parse_time(event.get(key))
        if parsed is not None:
            return _iso(parsed)
    return None


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _upper_text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).upper()


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _events_digest(events: Iterable[Dict[str, Any]]) -> str:
    payload = json.dumps(list(events), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
