from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .reader import age_seconds, latest_indicator_age, latest_tick_age, load_fastlane_evidence
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


def build_quality_report(runtime_dir: str | Path = "runtime", symbols: list[str] | None = None, write: bool = True) -> dict[str, Any]:
    thresholds = FastLaneThresholds()
    evidence = load_fastlane_evidence(runtime_dir, symbols=symbols)
    heartbeat_age = age_seconds((evidence.heartbeat or {}).get("generatedAt")) if evidence.heartbeat else None
    symbol_reports: list[dict[str, Any]] = []
    symbols_seen = sorted(set(evidence.ticks) | set(evidence.indicators) | set(symbols or []))
    for symbol in symbols_seen:
        rows = evidence.ticks.get(symbol, [])
        indicator = evidence.indicators.get(symbol)
        tick_age = latest_tick_age(rows)
        indicator_age = latest_indicator_age(indicator)
        spread_points = _spread_points(rows[-1] if rows else None)
        checks = [
            {"name": "tick_fast_lane", "passed": tick_age is not None and tick_age <= thresholds.max_tick_age_seconds, "reason": f"tick年龄={tick_age}秒"},
            {"name": "indicator_lane", "passed": indicator_age is not None and indicator_age <= thresholds.max_indicator_age_seconds, "reason": f"指标年龄={indicator_age}秒"},
            {"name": "tick_rows", "passed": len(rows) >= thresholds.min_tick_rows, "reason": f"tick样本={len(rows)}"},
            {"name": "spread", "passed": spread_points is None or spread_points <= thresholds.max_spread_points, "reason": f"点差={spread_points}点"},
        ]
        symbol_reports.append({
            "symbol": symbol,
            "tickAgeSeconds": tick_age,
            "indicatorAgeSeconds": indicator_age,
            "tickRows": len(rows),
            "spreadPoints": spread_points,
            "quality": "FAST" if all(c["passed"] for c in checks) else "DEGRADED",
            "checks": checks,
        })
    payload = {
        "schema": "quantgod.mt5.fast_lane_quality.v1",
        "runtimeDir": str(evidence.runtime_dir),
        "heartbeatFound": evidence.heartbeat is not None,
        "heartbeatAgeSeconds": heartbeat_age,
        "heartbeatFresh": heartbeat_age is not None and heartbeat_age <= thresholds.max_heartbeat_age_seconds,
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
    lines.append("")
    lines.append("品种质量：")
    for item in report.get("symbols", [])[:8]:
        status = "快速" if item.get("quality") == "FAST" else "降级"
        lines.append(f"- {item.get('symbol')}｜状态：{status}｜tick年龄：{item.get('tickAgeSeconds')}秒｜指标年龄：{item.get('indicatorAgeSeconds')}秒｜点差：{item.get('spreadPoints')}点")
    if not report.get("symbols"):
        lines.append("- 未发现快通道品种文件，请确认 EA 已挂载并写入 MQL5/Files。")
    lines.append("")
    lines.append("安全边界：")
    lines.append("仅采集运行证据；不会下单、不会平仓、不会撤单、不会修改实盘 preset。")
    return "\n".join(lines)
