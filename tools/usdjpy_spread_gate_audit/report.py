from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from zoneinfo import ZoneInfo

try:
    from tools.strategy_json.schema import SAFETY_BOUNDARY, base_strategy_seed
    from tools.usdjpy_strategy_backtest.report import run_backtest
    from tools.usdjpy_strategy_backtest.walk_forward import build_seed_walk_forward
except ModuleNotFoundError:  # pragma: no cover
    from strategy_json.schema import SAFETY_BOUNDARY, base_strategy_seed
    from usdjpy_strategy_backtest.report import run_backtest
    from usdjpy_strategy_backtest.walk_forward import build_seed_walk_forward

SCHEMA_AUDIT = "quantgod.usdjpy_spread_gate_impact_audit.v1"
SCHEMA_PROMOTION = "quantgod.tokyo_h4_promotion_review.v2"
FOCUS_SYMBOL = "USDJPYc"
TOKYO_FAMILY = "USDJPY_TOKYO_RANGE_BREAKOUT"
H4_FAMILY = "USDJPY_H4_TREND_PULLBACK"
FAMILY_DIRECTIONS: Tuple[Tuple[str, str], ...] = (
    (TOKYO_FAMILY, "LONG"),
    (TOKYO_FAMILY, "SHORT"),
    (H4_FAMILY, "LONG"),
    (H4_FAMILY, "SHORT"),
)
DEFAULT_THRESHOLDS = (2.0, 2.2, 2.5)


def build_spread_gate_impact_audit(
    runtime_dir: Path,
    *,
    start_date_jst: str | None = None,
    end_date_jst: str | None = None,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    write: bool = False,
    include_promotion_review: bool = True,
) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    start_date_jst, end_date_jst = _window(start_date_jst, end_date_jst)
    thresholds = tuple(sorted({round(float(item), 4) for item in thresholds}))
    m1_rows = _load_m1_spread_rows(runtime_dir, start_date_jst, end_date_jst)
    eval_rows = _load_shadow_eval_rows(runtime_dir, start_date_jst, end_date_jst)
    opportunities = _dedupe_opportunities(eval_rows)
    promotion = (
        build_tokyo_h4_promotion_review(
            runtime_dir,
            start_date_jst=start_date_jst,
            end_date_jst=end_date_jst,
            write=write,
        )
        if include_promotion_review
        else {}
    )
    threshold_rows = []
    previous: Dict[str, Any] | None = None
    for threshold in thresholds:
        item = _threshold_impact(threshold, m1_rows, eval_rows, opportunities)
        if previous:
            item["incrementalVsPrevious"] = {
                "previousThresholdPips": previous["thresholdPips"],
                "m1PassRowsDelta": item["m1PassRows"] - previous["m1PassRows"],
                "shadowEvaluationPassRowsDelta": item["shadowEvaluationPassRows"]
                - previous["shadowEvaluationPassRows"],
                "uniqueOpportunityDelta": item["uniqueOpportunityCount"]
                - previous["uniqueOpportunityCount"],
                "highScoreOpportunityDelta": item["highScoreOpportunityCount"]
                - previous["highScoreOpportunityCount"],
            }
        else:
            item["incrementalVsPrevious"] = {
                "previousThresholdPips": None,
                "m1PassRowsDelta": item["m1PassRows"],
                "shadowEvaluationPassRowsDelta": item["shadowEvaluationPassRows"],
                "uniqueOpportunityDelta": item["uniqueOpportunityCount"],
                "highScoreOpportunityDelta": item["highScoreOpportunityCount"],
            }
        threshold_rows.append(item)
        previous = item
    decision = _micro_live_decision(threshold_rows, promotion)
    payload = {
        "ok": True,
        "schema": SCHEMA_AUDIT,
        "generatedAtIso": _utc_now(),
        "symbol": FOCUS_SYMBOL,
        "window": {
            "startDateJst": start_date_jst,
            "endDateJst": end_date_jst,
            "inclusive": True,
            "shadowEvaluationDateSource": "generatedAtLocal",
            "m1SpreadDateSource": "MT5 exported bar timestamp",
        },
        "thresholdsPips": list(thresholds),
        "currentLiveMaxSpreadPips": 2.0,
        "probeMaxSpreadPips": 2.2 if 2.2 in thresholds else (thresholds[1] if len(thresholds) > 1 else thresholds[0]),
        "spreadDistribution": _spread_distribution(m1_rows, thresholds),
        "shadowEvaluationImpact": {
            "sourceFile": "QuantGod_StrategyJsonEAShadowEvaluationLedger.jsonl",
            "evaluationRows": len(eval_rows),
            "uniqueOpportunityCount": len(opportunities),
            "dedupePolicy": "family + direction + eventBarTime; repeated timer evaluations collapse to one opportunity",
            "byThreshold": threshold_rows,
            "byRoute": _opportunity_routes(opportunities, thresholds),
        },
        "promotionReview": promotion,
        "microLiveDecision": decision,
        "safety": {
            **dict(SAFETY_BOUNDARY),
            "readOnlyAudit": True,
            "writesLivePreset": False,
            "changesPilotMaxSpreadPips": False,
        },
    }
    if write:
        out_dir = runtime_dir / "replay" / "usdjpy"
        _write_json(out_dir / "QuantGod_USDJPYSpreadGateImpactAudit.json", payload)
        _write_audit_csv(out_dir / "QuantGod_USDJPYSpreadGateImpactAuditSummary.csv", payload)
    return payload


def build_tokyo_h4_promotion_review(
    runtime_dir: Path,
    *,
    start_date_jst: str | None = None,
    end_date_jst: str | None = None,
    write: bool = False,
) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    start_date_jst, end_date_jst = _window(start_date_jst, end_date_jst)
    eval_rows = _load_shadow_eval_rows(runtime_dir, start_date_jst, end_date_jst)
    opportunities = _dedupe_opportunities(eval_rows)
    shadow_strategy_rows = _load_latest_shadow_strategy_rows(runtime_dir)
    candidate_rows = _load_shadow_candidate_rows(runtime_dir, start_date_jst, end_date_jst)
    contract_params = _contract_family_parameters(runtime_dir)
    rows = []
    for family, direction in FAMILY_DIRECTIONS:
        seed = _review_seed(family, direction, contract_params)
        replay = run_backtest(runtime_dir, seed, write=False, include_coverage_matrix=False)
        wf = build_seed_walk_forward(runtime_dir, seed, write=False)
        row = _promotion_row(
            family,
            direction,
            replay,
            wf,
            shadow_strategy_rows,
            candidate_rows,
            opportunities,
        )
        rows.append(row)
    passed = [row for row in rows if row.get("recommendedStage") != "REMAIN_SHADOW"]
    payload = {
        "ok": True,
        "schema": SCHEMA_PROMOTION,
        "generatedAtIso": _utc_now(),
        "symbol": FOCUS_SYMBOL,
        "window": {
            "startDateJst": start_date_jst,
            "endDateJst": end_date_jst,
            "inclusive": True,
        },
        "status": "PASS" if passed else "BLOCKED",
        "statusZh": "已有 Tokyo/H4 路线通过晋级审查" if passed else "Tokyo/H4 路线仍未通过 shadow→replay→walk-forward 晋级审查",
        "summary": rows,
        "decision": {
            "promotionAllowed": bool(passed),
            "recommendedStage": "PAPER_LIVE_SIM_OR_MICRO_LIVE_REVIEW" if passed else "REMAIN_SHADOW",
            "reasonZh": "存在通过 shadow/replay/walk-forward 的路线，可进入更小范围治理审查。"
            if passed
            else "本轮没有路线同时通过 shadow 样本、回放净值、PF、回撤和 walk-forward 稳定性。",
        },
        "safety": {
            **dict(SAFETY_BOUNDARY),
            "readOnlyAudit": True,
            "writesLivePreset": False,
            "orderSendAllowed": False,
            "livePresetMutationAllowed": False,
        },
    }
    if write:
        out_dir = runtime_dir / "replay" / "usdjpy"
        _write_json(out_dir / "QuantGod_TokyoH4PromotionReview.json", payload)
        _write_promotion_csv(out_dir / "QuantGod_TokyoH4PromotionReviewSummary.csv", rows)
    return payload


def _window(start: str | None, end: str | None) -> Tuple[str, str]:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    if end:
        end_date = _parse_date(end)
    else:
        end_date = today
    if start:
        start_date = _parse_date(start)
    else:
        start_date = end_date - timedelta(days=6)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date.isoformat(), end_date.isoformat()


def _parse_date(value: str) -> datetime.date:
    text = str(value).strip().replace(".", "-")
    return datetime.strptime(text, "%Y-%m-%d").date()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_from_local(value: Any) -> str:
    text = str(value or "").strip().replace(".", "-")
    return text[:10]


def _load_m1_spread_rows(runtime_dir: Path, start: str, end: str) -> List[Dict[str, Any]]:
    path = runtime_dir / "backtest" / "exported_klines" / "QuantGod_USDJPYc_M1_rates.csv"
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            date = _date_from_local(row.get("timestamp"))
            if not (start <= date <= end):
                continue
            spread_points = _num(row.get("spread"))
            spread_pips = round(spread_points * 0.1, 4)
            rows.append(
                {
                    "timestamp": row.get("timestamp"),
                    "date": date,
                    "spreadPoints": spread_points,
                    "spreadPips": spread_pips,
                }
            )
    return rows


def _load_shadow_eval_rows(runtime_dir: Path, start: str, end: str) -> List[Dict[str, Any]]:
    path = runtime_dir / "QuantGod_StrategyJsonEAShadowEvaluationLedger.jsonl"
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            date = _date_from_local(item.get("generatedAtLocal"))
            if start <= date <= end:
                rows.append(item)
    return rows


def _dedupe_opportunities(eval_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in eval_rows:
        for item in _opportunities_from_eval(row):
            key = (item["family"], item["direction"], item["eventBarTime"])
            existing = best.get(key)
            if not existing or _num(item.get("score")) > _num(existing.get("score")):
                best[key] = item
    return sorted(best.values(), key=lambda item: (item["eventBarTime"], item["family"], item["direction"]))


def _opportunities_from_eval(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    spread = _num(row.get("spreadPips"))
    session_open = bool(row.get("sessionOpen", True))
    news_blocked = bool(row.get("newsBlocked", False))
    generated = row.get("generatedAtLocal")
    h4 = row.get("h4Pullback") if isinstance(row.get("h4Pullback"), dict) else {}
    h4_dir = int(_num(h4.get("signalDirection")))
    if h4_dir:
        items.append(
            {
                "family": H4_FAMILY,
                "direction": "LONG" if h4_dir > 0 else "SHORT",
                "eventBarTime": str(h4.get("eventBarTime") or generated),
                "generatedAtLocal": generated,
                "spreadPips": spread,
                "score": _num(h4.get("score")),
                "sessionOpen": session_open,
                "newsBlocked": news_blocked,
                "source": "strategy_json_shadow_h4Pullback",
            }
        )
    tokyo = row.get("tokyoRange") if isinstance(row.get("tokyoRange"), dict) else {}
    tokyo_dir = int(_num(tokyo.get("signalDirection")))
    if tokyo_dir:
        items.append(
            {
                "family": TOKYO_FAMILY,
                "direction": "LONG" if tokyo_dir > 0 else "SHORT",
                "eventBarTime": str(tokyo.get("eventBarTime") or generated),
                "generatedAtLocal": generated,
                "spreadPips": spread,
                "score": _num(tokyo.get("score")),
                "sessionOpen": session_open,
                "newsBlocked": news_blocked,
                "source": "strategy_json_shadow_tokyoRange",
            }
        )
    if bool(row.get("rsiLongSignal") or row.get("rsiCrossbackSignal")):
        direction = str(row.get("direction") or "LONG").upper()
        items.append(
            {
                "family": "RSI_Reversal",
                "direction": direction,
                "eventBarTime": str(row.get("generatedAtServer") or generated),
                "generatedAtLocal": generated,
                "spreadPips": spread,
                "score": 70.0,
                "sessionOpen": session_open,
                "newsBlocked": news_blocked,
                "source": "strategy_json_shadow_rsi",
            }
        )
    return items


def _spread_distribution(rows: List[Dict[str, Any]], thresholds: Sequence[float]) -> Dict[str, Any]:
    by_date: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("date"))].append(_num(row.get("spreadPips")))
    daily = []
    for date in sorted(by_date):
        values = by_date[date]
        threshold_counts = {
            f"le{threshold:g}PipsRows": sum(1 for value in values if value <= threshold)
            for threshold in thresholds
        }
        daily.append(
            {
                "date": date,
                "rows": len(values),
                "minPips": _round(_percentile(values, 0.0)),
                "p50Pips": _round(_percentile(values, 0.50)),
                "p90Pips": _round(_percentile(values, 0.90)),
                "p95Pips": _round(_percentile(values, 0.95)),
                "maxPips": _round(_percentile(values, 1.0)),
                **threshold_counts,
            }
        )
    values = [_num(row.get("spreadPips")) for row in rows]
    return {
        "sourceFile": "backtest/exported_klines/QuantGod_USDJPYc_M1_rates.csv",
        "rows": len(rows),
        "minPips": _round(_percentile(values, 0.0)),
        "p50Pips": _round(_percentile(values, 0.50)),
        "p90Pips": _round(_percentile(values, 0.90)),
        "p95Pips": _round(_percentile(values, 0.95)),
        "maxPips": _round(_percentile(values, 1.0)),
        "byDate": daily,
    }


def _threshold_impact(
    threshold: float,
    m1_rows: List[Dict[str, Any]],
    eval_rows: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    m1_pass = [row for row in m1_rows if _num(row.get("spreadPips")) <= threshold]
    eval_pass = [row for row in eval_rows if _num(row.get("spreadPips")) <= threshold]
    opp_pass = [row for row in opportunities if _num(row.get("spreadPips")) <= threshold]
    high_score = [
        row
        for row in opp_pass
        if _num(row.get("score")) >= 70.0 and row.get("sessionOpen") and not row.get("newsBlocked")
    ]
    return {
        "thresholdPips": threshold,
        "m1Rows": len(m1_rows),
        "m1PassRows": len(m1_pass),
        "m1PassRate": _rate(len(m1_pass), len(m1_rows)),
        "shadowEvaluationRows": len(eval_rows),
        "shadowEvaluationPassRows": len(eval_pass),
        "shadowEvaluationPassRate": _rate(len(eval_pass), len(eval_rows)),
        "uniqueOpportunityCount": len(opp_pass),
        "highScoreOpportunityCount": len(high_score),
        "opportunitiesByRoute": _count_by_route(opp_pass),
        "highScoreOpportunitiesByRoute": _count_by_route(high_score),
    }


def _opportunity_routes(opportunities: List[Dict[str, Any]], thresholds: Sequence[float]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in opportunities:
        grouped[(item["family"], item["direction"])].append(item)
    rows = []
    for (family, direction), items in sorted(grouped.items()):
        row = {
            "family": family,
            "direction": direction,
            "uniqueOpportunityCount": len(items),
            "minSpreadPips": _round(min((_num(item.get("spreadPips")) for item in items), default=0.0)),
            "medianSpreadPips": _round(_percentile([_num(item.get("spreadPips")) for item in items], 0.5)),
            "maxSpreadPips": _round(max((_num(item.get("spreadPips")) for item in items), default=0.0)),
        }
        for threshold in thresholds:
            row[f"le{threshold:g}Pips"] = sum(1 for item in items if _num(item.get("spreadPips")) <= threshold)
        rows.append(row)
    return rows


def _count_by_route(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[f"{row.get('family')}:{row.get('direction')}"] += 1
    return dict(sorted(counts.items()))


def _micro_live_decision(threshold_rows: List[Dict[str, Any]], promotion: Dict[str, Any]) -> Dict[str, Any]:
    probe = next((row for row in threshold_rows if math.isclose(float(row["thresholdPips"]), 2.2)), None)
    current = next((row for row in threshold_rows if math.isclose(float(row["thresholdPips"]), 2.0)), None)
    promotion_rows = promotion.get("summary") if isinstance(promotion.get("summary"), list) else []
    promoted = [row for row in promotion_rows if row.get("recommendedStage") != "REMAIN_SHADOW"]
    reasons = []
    if not probe:
        reasons.append("本轮没有 2.2 pips probe 档，不能评估 micro-live 扩门。")
    elif current and probe.get("uniqueOpportunityCount", 0) <= current.get("uniqueOpportunityCount", 0):
        reasons.append("2.2 pips 相比 2.0 pips 没有增加可去重机会。")
    if not promoted:
        reasons.append("Tokyo/H4 没有路线通过 shadow→replay→walk-forward 晋级审查。")
    if probe and int(probe.get("highScoreOpportunityCount") or 0) <= 0:
        reasons.append("2.2 pips 档没有新增高分且 session/news 可用的去重机会。")
    eligible = bool(probe and promoted and not reasons)
    return {
        "eligible": eligible,
        "recommendation": "STAGE_LIVE_CAP_2_2_MICRO_LIVE" if eligible else "KEEP_LIVE_CAP_2_0",
        "currentLiveMaxSpreadPips": 2.0,
        "reviewedProbeMaxSpreadPips": 2.2,
        "reasonZh": "2.2 pips 档只增加通过完整晋级链的高质量机会，可进入 micro-live patch 审查。"
        if eligible
        else "暂不把 live cap 升到 2.2 pips；新增机会还没有通过完整质量链。",
        "blockersZh": reasons,
        "orderSendAllowed": False,
        "livePresetMutationAllowed": False,
    }


def _promotion_row(
    family: str,
    direction: str,
    replay: Dict[str, Any],
    wf: Dict[str, Any],
    shadow_strategy_rows: Dict[Tuple[str, str], Dict[str, Any]],
    candidate_rows: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    metrics = replay.get("metrics") if isinstance(replay.get("metrics"), dict) else {}
    wf_summary = wf.get("summary") if isinstance(wf.get("summary"), dict) else {}
    shadow = shadow_strategy_rows.get((family, direction), {})
    route_candidates = [
        row
        for row in candidate_rows
        if str(row.get("CandidateRoute")) == family and _direction_from_candidate(row.get("CandidateDirection")) == direction
    ]
    route_opps = [row for row in opportunities if row.get("family") == family and row.get("direction") == direction]
    replay_trades = int(_num(metrics.get("tradeCount")))
    replay_net = _round(_num(metrics.get("netR")))
    replay_pf = _round(_num(metrics.get("profitFactor")))
    replay_dd = _round(_num(metrics.get("maxDrawdownR")))
    shadow_samples = int(_num(shadow.get("sampleCount")))
    blockers = []
    if shadow_samples < 5 and len(route_candidates) < 5:
        blockers.append("SHADOW_EVIDENCE_INSUFFICIENT")
    if replay_trades < 5:
        blockers.append("REPLAY_SAMPLE_INSUFFICIENT")
    if replay_net <= 0:
        blockers.append("REPLAY_NET_R_NON_POSITIVE")
    if replay_pf < 1.10:
        blockers.append("REPLAY_PROFIT_FACTOR_LT_1_10")
    if replay_dd > 8.0:
        blockers.append("REPLAY_DRAWDOWN_GT_8R")
    if wf_summary.get("promotionGateStatus") != "PASS":
        blockers.append(str(wf_summary.get("blockerCode") or "WALK_FORWARD_NOT_PASS"))
    blockers.append("EA_LIVE_ROUTE_NOT_IMPLEMENTED_FOR_FAMILY")
    blockers = sorted({item for item in blockers if item})
    recommended = "REMAIN_SHADOW" if blockers else "PAPER_LIVE_SIM"
    return {
        "family": family,
        "direction": direction,
        "shadowPassed": not any(item.startswith("SHADOW_") for item in blockers),
        "shadowSamples": shadow_samples,
        "shadowStage": shadow.get("promotionStage", ""),
        "candidateLedgerCount": len(route_candidates),
        "shadowJsonOpportunityCount": len(route_opps),
        "replayTrades": replay_trades,
        "replayNetR": replay_net,
        "replayPF": replay_pf,
        "replayMaxDD": replay_dd,
        "wfStatus": wf_summary.get("promotionGateStatus", ""),
        "wfBlocker": wf_summary.get("blockerCode", ""),
        "wfSampleCount": int(_num(wf_summary.get("sampleCount"))),
        "wfValidationNetR": _round(_num(wf_summary.get("validationNetR"))),
        "wfForwardNetR": _round(_num(wf_summary.get("forwardNetR"))),
        "wfStabilityScore": _round(_num(wf_summary.get("stabilityScore"))),
        "liveRoutePassed": False,
        "recommendedStage": recommended,
        "blockers": "|".join(blockers),
    }


def _review_seed(family: str, direction: str, contract_params: Dict[str, Any]) -> Dict[str, Any]:
    seed = base_strategy_seed(f"SPREAD-GATE-REVIEW-{family}-{direction}", family=family, direction=direction)
    family_params = contract_params.get(family)
    if isinstance(family_params, dict):
        key = "tokyoRange" if family == TOKYO_FAMILY else "h4Pullback"
        seed["indicators"][key].update(family_params)
    exit_params = contract_params.get("exit")
    if isinstance(exit_params, dict):
        seed["exit"].update(exit_params)
    seed.setdefault("risk", {})["stage"] = "SHADOW"
    return seed


def _contract_family_parameters(runtime_dir: Path) -> Dict[str, Any]:
    contract = _load_json(runtime_dir / "QuantGod_StrategyJsonEAContract.json")
    strategy = contract.get("strategy") if isinstance(contract.get("strategy"), dict) else {}
    params = contract.get("familyParameters")
    if not isinstance(params, dict):
        params = strategy.get("familyParameters") if isinstance(strategy.get("familyParameters"), dict) else {}
    if not params:
        params = _parse_contract_txt_family_params(runtime_dir / "QuantGod_StrategyJsonEAContract_EA.txt")
    exit_params = {}
    for key in ("breakevenDelayR", "trailStartR", "mfeGivebackPct"):
        value = strategy.get(key, contract.get(key))
        if value is not None:
            exit_params[key] = value
    out: Dict[str, Any] = {
        TOKYO_FAMILY: params.get("tokyoRange") if isinstance(params.get("tokyoRange"), dict) else {},
        H4_FAMILY: params.get("h4Pullback") if isinstance(params.get("h4Pullback"), dict) else {},
    }
    if exit_params:
        out["exit"] = exit_params
    return out


def _parse_contract_txt_family_params(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    try:
        params = json.loads(values.get("familyParameters", "{}"))
    except json.JSONDecodeError:
        params = {}
    return params if isinstance(params, dict) else {}


def _load_latest_shadow_strategy_rows(runtime_dir: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = runtime_dir / "agent" / "QuantGod_MT5ShadowStrategyLedger.csv"
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            key = (str(row.get("strategy") or ""), str(row.get("direction") or "").upper())
            if key[0] and key[1]:
                rows[key] = row
    return rows


def _load_shadow_candidate_rows(runtime_dir: Path, start: str, end: str) -> List[Dict[str, Any]]:
    path = runtime_dir / "QuantGod_ShadowCandidateLedger.csv"
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            date = _date_from_local(row.get("LabelTimeLocal"))
            if start <= date <= end:
                rows.append(row)
    return rows


def _direction_from_candidate(value: Any) -> str:
    text = str(value or "").upper()
    if text in {"BUY", "LONG", "1"}:
        return "LONG"
    if text in {"SELL", "SHORT", "-1"}:
        return "SHORT"
    return text


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_audit_csv(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in payload.get("shadowEvaluationImpact", {}).get("byThreshold", []):
        rows.append(
            {
                "generatedAtIso": payload.get("generatedAtIso"),
                "startDateJst": payload.get("window", {}).get("startDateJst"),
                "endDateJst": payload.get("window", {}).get("endDateJst"),
                "thresholdPips": item.get("thresholdPips"),
                "m1Rows": item.get("m1Rows"),
                "m1PassRows": item.get("m1PassRows"),
                "m1PassRate": item.get("m1PassRate"),
                "shadowEvaluationRows": item.get("shadowEvaluationRows"),
                "shadowEvaluationPassRows": item.get("shadowEvaluationPassRows"),
                "uniqueOpportunityCount": item.get("uniqueOpportunityCount"),
                "highScoreOpportunityCount": item.get("highScoreOpportunityCount"),
                "recommendation": payload.get("microLiveDecision", {}).get("recommendation"),
            }
        )
    _write_csv(path, rows)


def _write_promotion_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    _write_csv(path, rows)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["generatedAtIso"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _round(value: float, digits: int = 4) -> float:
    return round(float(value or 0.0), digits)


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
    return ordered[index]
