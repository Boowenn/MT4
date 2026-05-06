from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence
from .data_loader import discover_adaptive_gate, discover_fastlane_quality, discover_runtime_snapshot, load_shadow_rows
from .schema import SAFETY_DEFAULTS, TriggerDecision, assert_safe_payload, utc_now_iso

def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool): return value
    if isinstance(value, str): return value.strip().lower() in {"1","true","yes","ok","pass","passed"}
    return default

def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None): return default
        return float(value)
    except Exception:
        return default

def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None

def _runtime_is_fresh(snapshot: Dict[str, Any], max_age_seconds: int = 300) -> bool:
    for key in ("runtimeFresh", "fresh", "isFresh"):
        if key in snapshot:
            return _as_bool(snapshot.get(key), False)
    for key in ("runtimeAgeSeconds", "_fileAgeSeconds"):
        if key in snapshot:
            return _as_float(snapshot.get(key), max_age_seconds + 1) <= max_age_seconds
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    if runtime.get("tickAgeSeconds") is not None:
        return _as_float(runtime.get("tickAgeSeconds"), max_age_seconds + 1) <= 30
    ts = _parse_iso(snapshot.get("generatedAt") or snapshot.get("generatedAtIso") or snapshot.get("timeIso"))
    if ts is None and isinstance(snapshot.get("current_price"), dict):
        ts = _parse_iso(snapshot["current_price"].get("timeIso"))
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() <= max_age_seconds

def _rows_for(rows: Sequence[Dict[str, str]], symbol: str, direction: str) -> List[Dict[str, str]]:
    aliases = {"LONG":{"LONG","BUY","买入","偏多"}, "SHORT":{"SHORT","SELL","卖出","偏空"}}
    allowed = aliases.get(direction.upper(), {direction.upper()})
    out=[]
    for row in rows:
        row_symbol = row.get("symbol") or row.get("Symbol") or row.get("sym") or ""
        row_dir = (row.get("direction") or row.get("Direction") or row.get("CandidateDirection") or row.get("side") or "").upper()
        if row_symbol == symbol and (not row_dir or row_dir in allowed): out.append(row)
    return out

def _shadow_value(row: Dict[str, str], direction: str) -> float:
    direct = row.get("scoreR") or row.get("r") or row.get("pips") or row.get("movePips")
    if direct not in ("", None):
        return _as_float(direct, 0.0)
    if direction.upper() == "LONG":
        return _as_float(row.get("LongClosePips") or row.get("LongPips") or row.get("LongOutcomePips"), 0.0)
    if direction.upper() == "SHORT":
        return _as_float(row.get("ShortClosePips") or row.get("ShortPips") or row.get("ShortOutcomePips"), 0.0)
    return 0.0

def _shadow_score(rows: Sequence[Dict[str, str]], direction: str) -> Dict[str, Any]:
    if not rows: return {"sampleCount":0,"hitRate":None,"avgR":None,"ok":False}
    values=[]; wins=0
    for row in rows:
        val = _shadow_value(row, direction)
        values.append(val); wins += 1 if val > 0 else 0
    avg = mean(values) if values else 0.0
    hit = wins / len(values) if values else 0.0
    return {"sampleCount":len(values),"hitRate":hit,"avgR":avg,"ok":len(values)>=3 and avg>=-0.1 and hit>=0.4}

def build_trigger_plan(runtime_dir: Path, symbols: Iterable[str], directions: Iterable[str] = ("LONG","SHORT"), timeframe: str = "M1/M5") -> Dict[str, Any]:
    rows = load_shadow_rows(runtime_dir); decisions=[]
    for symbol in symbols:
        snapshot = discover_runtime_snapshot(runtime_dir, symbol) or {}
        fastlane = discover_fastlane_quality(runtime_dir, symbol)
        gate = discover_adaptive_gate(runtime_dir, symbol)
        snapshot_found = bool(snapshot)
        fastlane_found = bool(fastlane)
        gate_found = bool(gate)
        runtime_fresh = snapshot_found and _runtime_is_fresh(snapshot)
        fallback = snapshot_found and _as_bool(snapshot.get("fallback") or snapshot.get("isFallback"), False)
        fastlane_quality = str(fastlane.get("quality", fastlane.get("state", ""))).upper()
        fastlane_ok = fastlane_found and fastlane_quality not in {"DEGRADED","FAIL","FAILED","BAD","STALE","MISSING",""}
        adaptive_gate_ok = gate_found and _as_bool(gate.get("passed", gate.get("entryGatePassed", False)), False)
        for direction in directions:
            score = _shadow_score(_rows_for(rows, symbol, direction), direction)
            confirmations = {"运行快照存在": snapshot_found, "运行快照新鲜": bool(runtime_fresh), "没有回退数据": snapshot_found and not bool(fallback), "快通道质量存在": fastlane_found, "快通道质量通过": bool(fastlane_ok), "自适应入场闸门存在": gate_found, "自适应入场闸门通过": bool(adaptive_gate_ok), "影子样本未显示负期望": bool(score["ok"])}
            reasons=[]
            if not snapshot_found: reasons.append("缺少运行快照，暂停方向触发")
            elif not runtime_fresh: reasons.append("运行快照不新鲜，等待下一次快通道心跳")
            if fallback: reasons.append("当前使用回退数据，暂停方向触发")
            if not fastlane_found: reasons.append("缺少 MT5 快通道质量证据，暂停方向触发")
            elif not fastlane_ok: reasons.append("MT5 快通道质量降级，暂停方向触发")
            if not gate_found: reasons.append("缺少自适应入场闸门证据，暂停方向触发")
            elif not adaptive_gate_ok: reasons.append("自适应入场闸门未通过")
            if not score["ok"]: reasons.append(f"影子样本不足或近期表现弱，样本数={score['sampleCount']}")
            passed = all(confirmations.values())
            decision_score = round(sum(1 for v in confirmations.values() if v)/max(1,len(confirmations)),3)
            state = "WAIT_TRIGGER_CONFIRMATION" if passed else "BLOCKED"
            suggested_wait = "等待 M1/M5 二次确认：bar close、回踩确认、点差回落确认" if passed else "暂停该方向，继续观察新鲜 runtime 与影子样本"
            decisions.append(TriggerDecision(symbol=symbol,direction=direction.upper(),timeframe=timeframe,state=state,score=decision_score,reasons=reasons or ["基础条件通过，但仍只允许人工复核"],confirmations=confirmations,suggested_wait=suggested_wait,generated_at=utc_now_iso()).to_dict())
    payload={"schema":"quantgod.entry_trigger_lab.v1","generatedAt":utc_now_iso(),"runtimeDir":str(runtime_dir),"decisions":decisions,"safety":dict(SAFETY_DEFAULTS)}
    assert_safe_payload(payload)
    return payload

def write_trigger_plan(runtime_dir: Path, payload: Dict[str, Any]) -> Path:
    target_dir = runtime_dir / "adaptive"; target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "QuantGod_EntryTriggerPlan.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
