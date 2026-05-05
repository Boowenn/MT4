from __future__ import annotations

from statistics import median
from typing import Any

from .data_loader import RuntimeEvidence, first_value, latest_snapshot_for_symbol, parse_iso_age_seconds
from .schema import PolicyThresholds, safe_float

def _price_block(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    block = snapshot.get("current_price") or snapshot.get("currentPrice") or snapshot.get("price") or {}
    if isinstance(block, dict):
        return block
    return {}

def _spread(snapshot: dict[str, Any] | None) -> float:
    price = _price_block(snapshot)
    spread = first_value(price, "spread", "Spread", default=None)
    if spread is None and snapshot:
        spread = first_value(snapshot, "spread", "Spread", default=None)
    return safe_float(spread, 0.0)

def _spread_gate(evidence: RuntimeEvidence, symbol: str | None, current_spread: float, thresholds: PolicyThresholds) -> tuple[bool, str]:
    if current_spread <= 0:
        return True, "当前点差未上报或为 0，暂不因点差阻断"
    rows = evidence.outcome_rows + evidence.close_history_rows + evidence.strategy_eval_rows
    values: list[float] = []
    for row in rows:
        if symbol and str(first_value(row, "symbol", "Symbol", default="")).upper() != symbol.upper():
            continue
        value = safe_float(first_value(row, "spread", "Spread", "spreadPips", "SpreadPips", default=0), 0)
        if value > 0:
            values.append(value)
    if not values:
        return True, f"当前点差={current_spread}；暂无历史点差基准，先不阻断"
    baseline = median(values)
    limit = baseline * thresholds.max_spread_multiplier
    return current_spread <= limit, f"当前点差={current_spread}；历史中位点差={baseline:.5g}；上限={limit:.5g}"

def _age(snapshot: dict[str, Any] | None) -> int | None:
    if not snapshot:
        return None
    explicit = first_value(snapshot, "runtimeAgeSeconds", "ageSeconds", "tickAgeSeconds", default=None)
    if explicit is not None:
        return int(safe_float(explicit, 0))
    price = _price_block(snapshot)
    return parse_iso_age_seconds(first_value(snapshot, "generatedAt", "timeIso", "timestamp", default=None) or first_value(price, "timeIso", "time", default=None))

def _fallback(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return True
    raw = first_value(snapshot, "fallback", "isFallback", default=False)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "是"}

def _source(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "missing_runtime"
    return str(first_value(snapshot, "source", "snapshotSource", default="runtime_files"))

def _indicator_valid(evidence: RuntimeEvidence, symbol: str | None, thresholds: PolicyThresholds) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    rows = evidence.strategy_eval_rows
    if symbol:
        rows = [row for row in rows if str(first_value(row, "symbol", "Symbol", default="")).upper() == symbol.upper()]
    if not rows:
        return True, ["未找到指标评价表，先按运行快照处理"]
    latest = rows[-1]
    atr = safe_float(first_value(latest, "atr", "ATR", "atr14", "ATR14", default=0), 0)
    adx = safe_float(first_value(latest, "adx", "ADX", default=0), 0)
    bb_width = safe_float(first_value(latest, "bbWidth", "BBWidth", "bb_width", default=0), 0)
    ok = True
    if atr <= thresholds.min_atr:
        ok = False
        reasons.append("ATR 无效或为零")
    if adx <= 0:
        ok = False
        reasons.append("ADX 无效或为零")
    if bb_width <= 0:
        ok = False
        reasons.append("布林带宽无效或为零")
    if ok:
        reasons.append("指标有效")
    return ok, reasons

def evaluate_entry_gate(
    evidence: RuntimeEvidence,
    scored_route: dict[str, Any] | None,
    thresholds: PolicyThresholds,
    symbol: str | None = None,
) -> dict[str, Any]:
    snapshot = latest_snapshot_for_symbol(evidence, symbol)
    age = _age(snapshot)
    fallback = _fallback(snapshot)
    spread = _spread(snapshot)
    source = _source(snapshot)
    runtime_fresh = age is not None and age <= thresholds.max_runtime_age_seconds
    spread_ok, spread_reason = _spread_gate(evidence, symbol, spread, thresholds)

    indicator_ok, indicator_reasons = _indicator_valid(evidence, symbol, thresholds)
    route_ok = bool(scored_route and scored_route.get("state") in {"ACTIVE_SHADOW_OK", "WATCH_ONLY"})
    paused = bool(scored_route and scored_route.get("state") == "PAUSED")

    checks = [
        {"name": "运行快照", "passed": bool(snapshot) and runtime_fresh and not fallback, "reason": f"来源={source}；新鲜={runtime_fresh}；回退={fallback}；年龄={age}秒"},
        {"name": "点差", "passed": spread_ok, "reason": spread_reason},
        {"name": "指标", "passed": indicator_ok, "reason": "；".join(indicator_reasons)},
        {"name": "历史方向", "passed": route_ok and not paused, "reason": (scored_route or {}).get("reason", "未找到有效历史方向")},
    ]
    passed = all(item["passed"] for item in checks)
    conclusion = "通过，仅允许观察复核" if passed else "未通过，暂停该方向建议"
    return {
        "symbol": symbol or (scored_route or {}).get("symbol") or "UNKNOWN",
        "snapshotSource": source,
        "fallback": fallback,
        "runtimeFresh": runtime_fresh,
        "runtimeAgeSeconds": age,
        "spread": spread,
        "routeState": (scored_route or {}).get("state", "NO_ROUTE"),
        "passed": passed,
        "conclusion": conclusion,
        "checks": checks,
    }
