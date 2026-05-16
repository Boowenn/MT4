from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Any

from .reader import age_seconds, latest_indicator_age, latest_tick_age, load_fastlane_evidence, parse_time, utc_now
from .schema import FastLaneThresholds, assert_safe_payload, safety_payload


def _spread_points(tick: dict[str, Any] | None) -> float | None:
    if not tick:
        return None
    for key in ("spreadPoints", "spread", "spread_points"):
        if key in tick:
            try:
                return float(tick[key])
            except Exception:
                return None
    bid = tick.get("bid")
    ask = tick.get("ask")
    point = tick.get("point") or 0.00001
    try:
        return abs(float(ask) - float(bid)) / float(point)
    except Exception:
        return None


def _is_fallback_payload(payload: dict[str, Any] | None) -> bool:
    return bool(payload and (payload.get("dashboardFallback") or payload.get("timerHeartbeatFallback") or payload.get("fallbackSource")))


def _market_closed_for_tick_idle(heartbeat: dict[str, Any] | None, tick: dict[str, Any] | None) -> bool:
    if not _is_fallback_payload(tick):
        return False
    candidates = []
    if heartbeat:
        candidates.extend([heartbeat.get("generatedAt"), heartbeat.get("gmtTime"), heartbeat.get("serverTime")])
    candidates.extend([tick.get("generatedAt"), tick.get("timeIso") if tick else None])
    for value in candidates:
        dt = parse_time(value)
        if dt:
            return dt.astimezone(timezone.utc).weekday() >= 5
    return utc_now().weekday() >= 5


def build_quality_report(runtime_dir: str | Path = "runtime", symbols: list[str] | None = None, write: bool = True) -> dict[str, Any]:
    thresholds = FastLaneThresholds()
    evidence = load_fastlane_evidence(runtime_dir, symbols=symbols)
    heartbeat_age = age_seconds((evidence.heartbeat or {}).get("generatedAt")) if evidence.heartbeat else None
    heartbeat_fallback = _is_fallback_payload(evidence.heartbeat)
    heartbeat_limit = thresholds.max_heartbeat_age_seconds
    if heartbeat_fallback:
        refresh_interval = 0
        try:
            refresh_interval = int((evidence.heartbeat or {}).get("refreshIntervalSeconds") or 0)
        except Exception:
            refresh_interval = 0
        heartbeat_limit = max(90, refresh_interval * 12, thresholds.max_heartbeat_age_seconds)
    heartbeat_fresh = heartbeat_age is not None and heartbeat_age <= heartbeat_limit
    symbol_reports: list[dict[str, Any]] = []
    symbols_seen = sorted(set(evidence.ticks) | set(evidence.indicators) | set(symbols or []))
    for symbol in symbols_seen:
        rows = evidence.ticks.get(symbol, [])
        indicator = evidence.indicators.get(symbol)
        tick_age = latest_tick_age(rows)
        indicator_age = latest_indicator_age(indicator)
        latest_tick = rows[-1] if rows else None
        spread_points = _spread_points(latest_tick)
        tick_fallback = _is_fallback_payload(latest_tick)
        indicator_fallback = _is_fallback_payload(indicator)
        market_closed_idle = _market_closed_for_tick_idle(evidence.heartbeat, latest_tick) and tick_age is not None and tick_age > thresholds.max_tick_age_seconds
        tick_ok = tick_age is not None and (tick_age <= thresholds.max_tick_age_seconds or market_closed_idle)
        indicator_limit = max(30, thresholds.max_indicator_age_seconds) if indicator_fallback else thresholds.max_indicator_age_seconds
        indicator_static_ok = bool(indicator_fallback and heartbeat_fresh and market_closed_idle and indicator_age is not None)
        indicator_ok = indicator_age is not None and (indicator_age <= indicator_limit or indicator_static_ok)
        rows_ok = len(rows) >= thresholds.min_tick_rows
        spread_ok = spread_points is None or spread_points <= thresholds.max_spread_points
        checks = [
            {
                "name": "tick_fast_lane",
                "passed": tick_ok,
                "reason": f"tick年龄={tick_age}秒" + ("；周末/休市 tick 静止，dashboard 心跳仍新鲜" if market_closed_idle else ""),
            },
            {
                "name": "indicator_lane",
                "passed": indicator_ok,
                "reason": f"指标年龄={indicator_age}秒" + ("；休市期间沿用 EA 诊断快照" if indicator_static_ok else ""),
            },
            {"name": "tick_rows", "passed": rows_ok, "reason": f"tick样本={len(rows)}"},
            {"name": "spread", "passed": spread_ok, "reason": f"点差={spread_points}点"},
        ]
        fallback_used = tick_fallback or indicator_fallback or heartbeat_fallback
        all_passed = all(c["passed"] for c in checks)
        quality = "EA_DASHBOARD_OK" if all_passed and fallback_used else ("FAST" if all_passed else "DEGRADED")
        symbol_reports.append({
            "symbol": symbol,
            "tickAgeSeconds": tick_age,
            "indicatorAgeSeconds": indicator_age,
            "tickRows": len(rows),
            "spreadPoints": spread_points,
            "quality": quality,
            "dashboardFallback": fallback_used,
            "marketClosedTickIdle": market_closed_idle,
            "source": (latest_tick or indicator or {}).get("source"),
            "checks": checks,
        })
    payload = {
        "schema": "quantgod.mt5.fast_lane_quality.v1",
        "runtimeDir": str(evidence.runtime_dir),
        "heartbeatFound": evidence.heartbeat is not None,
        "heartbeatAgeSeconds": heartbeat_age,
        "heartbeatFresh": heartbeat_fresh,
        "heartbeatFreshLimitSeconds": heartbeat_limit,
        "heartbeatFallback": heartbeat_fallback,
        "heartbeatSource": (evidence.heartbeat or {}).get("source") if evidence.heartbeat else None,
        "dashboardFallback": bool(evidence.fallback_sources),
        "fallbackSources": evidence.fallback_sources,
        "symbols": symbol_reports,
        "diagnosticRows": len(evidence.diagnostics),
        "tradeEventRows": len(evidence.trade_events),
        "safety": safety_payload(),
    }
    assert_safe_payload(payload)
    if write:
        out = evidence.runtime_dir / "quality"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_MT5FastLaneQuality.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_telegram_text(report: dict[str, Any]) -> str:
    lines = ["【QuantGod MT5 快通道质量审查】", ""]
    lines.append(f"心跳：{'新鲜' if report.get('heartbeatFresh') else '异常'}；年龄：{report.get('heartbeatAgeSeconds')}秒")
    if report.get("dashboardFallback"):
        lines.append("证据：独立快通道未完整产出，已使用 EA Dashboard/Timer 心跳作为只读运行证据。")
    lines.append("")
    lines.append("品种质量：")
    for item in report.get("symbols", [])[:8]:
        quality = str(item.get("quality") or "")
        status = "快速" if quality == "FAST" else ("Dashboard 可用" if quality == "EA_DASHBOARD_OK" else "降级")
        lines.append(f"- {item.get('symbol')}｜状态：{status}｜tick年龄：{item.get('tickAgeSeconds')}秒｜指标年龄：{item.get('indicatorAgeSeconds')}秒｜点差：{item.get('spreadPoints')}点")
    if not report.get("symbols"):
        lines.append("- 未发现快通道品种文件，请确认 EA 已挂载并写入 MQL5/Files。")
    lines.append("")
    lines.append("安全边界：")
    lines.append("仅采集运行证据；不会下单、不会平仓、不会撤单、不会修改实盘 preset。")
    return "\n".join(lines)
