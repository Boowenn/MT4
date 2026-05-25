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
SCHEMA_CANDIDATE_BACKFILL = "quantgod.tokyo_h4_shadow_candidate_backfill.v1"
SCHEMA_OUTCOME_BACKFILL = "quantgod.tokyo_h4_shadow_candidate_outcome_backfill.v1"
FOCUS_SYMBOL = "USDJPYc"
TOKYO_FAMILY = "USDJPY_TOKYO_RANGE_BREAKOUT"
H4_FAMILY = "USDJPY_H4_TREND_PULLBACK"
FAMILY_DIRECTIONS: Tuple[Tuple[str, str], ...] = (
    (TOKYO_FAMILY, "LONG"),
    (TOKYO_FAMILY, "SHORT"),
    (H4_FAMILY, "LONG"),
    (H4_FAMILY, "SHORT"),
)
DEFAULT_THRESHOLDS = (2.0, 2.2, 2.3, 2.4, 2.5)
CANDIDATE_LEDGER_FIELDS = [
    "EventId",
    "LabelTimeLocal",
    "LabelTimeServer",
    "EventBarTime",
    "Symbol",
    "CandidateRoute",
    "Timeframe",
    "CandidateDirection",
    "CandidateScore",
    "Regime",
    "ReferencePrice",
    "SpreadPips",
    "NewsStatus",
    "Trigger",
    "Reason",
]
OUTCOME_LEDGER_FIELDS = [
    "EventId",
    "OutcomeLabelTimeLocal",
    "OutcomeLabelTimeServer",
    "EventBarTime",
    "Symbol",
    "CandidateRoute",
    "Timeframe",
    "CandidateDirection",
    "CandidateScore",
    "Regime",
    "ReferencePrice",
    "HorizonBars",
    "HorizonMinutes",
    "FutureClose",
    "LongClosePips",
    "ShortClosePips",
    "LongMFEPips",
    "LongMAEPips",
    "ShortMFEPips",
    "ShortMAEPips",
    "DirectionalOutcome",
    "BestOpportunity",
    "OutcomeReason",
]


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
    current_live_max_spread_pips = _current_live_max_spread_pips(runtime_dir)
    probe_max_spread_pips = _next_probe_threshold(thresholds, current_live_max_spread_pips)
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
    decision = _micro_live_decision(
        threshold_rows,
        promotion,
        current_live_max_spread_pips=current_live_max_spread_pips,
        probe_max_spread_pips=probe_max_spread_pips,
    )
    rsi_long_probe = _rsi_long_micro_live_probe_review(
        eval_rows,
        threshold_rows,
        current_live_max_spread_pips=current_live_max_spread_pips,
        thresholds=thresholds,
    )
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
        "currentLiveMaxSpreadPips": current_live_max_spread_pips,
        "probeMaxSpreadPips": probe_max_spread_pips,
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
        "rsiLongMicroLiveProbeReview": rsi_long_probe,
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
    outcome_counts = _tokyo_h4_candidate_outcome_counts(runtime_dir, candidate_rows)
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
            outcome_counts,
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


def backfill_tokyo_h4_shadow_candidate_ledger(
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
    ledger_path = runtime_dir / "QuantGod_ShadowCandidateLedger.csv"
    existing_count, existing_event_ids, existing_keys = _candidate_ledger_identity(ledger_path)
    appended_rows: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = defaultdict(int)

    for item in opportunities:
        family = str(item.get("family") or "")
        direction = str(item.get("direction") or "").upper()
        if family not in {TOKYO_FAMILY, H4_FAMILY}:
            skipped["unsupportedFamily"] += 1
            continue
        if not item.get("sessionOpen"):
            skipped["sessionClosed"] += 1
            continue
        if item.get("newsBlocked"):
            skipped["newsBlocked"] += 1
            continue
        if not _shadow_research_spread_allowed(item):
            skipped["spreadAboveShadowResearchCap"] += 1
            continue

        event_bar_time = _mt5_datetime_text(item.get("eventBarTime"))
        label_time_local = _mt5_datetime_text(item.get("generatedAtLocal"))
        label_time_server = _mt5_datetime_text(item.get("generatedAtServer") or item.get("generatedAtLocal"))
        timeframe = str(item.get("timeframe") or "M15").upper()
        symbol = str(item.get("symbol") or FOCUS_SYMBOL)
        direction_label = "BUY" if direction == "LONG" else "SELL"
        reference_price = _num(item.get("ask") if direction == "LONG" else item.get("bid"))
        if not event_bar_time or reference_price <= 0.0:
            skipped["missingEventOrReference"] += 1
            continue

        event_id = _candidate_event_id(symbol, timeframe, event_bar_time, family, direction_label)
        identity = (family, direction, event_bar_time)
        if event_id in existing_event_ids or identity in existing_keys:
            skipped["alreadyPresent"] += 1
            continue

        row = {
            "EventId": event_id,
            "LabelTimeLocal": label_time_local,
            "LabelTimeServer": label_time_server,
            "EventBarTime": event_bar_time,
            "Symbol": symbol,
            "CandidateRoute": family,
            "Timeframe": timeframe,
            "CandidateDirection": direction_label,
            "CandidateScore": f"{_num(item.get('score')):.1f}",
            "Regime": "STRATEGY_JSON_SHADOW",
            "ReferencePrice": f"{reference_price:.3f}",
            "SpreadPips": f"{_num(item.get('spreadPips')):.1f}",
            "NewsStatus": "CLEAR",
            "Trigger": _candidate_trigger(family),
            "Reason": "Strategy JSON shadow candidate backfill; outcome-only and never sends live orders",
        }
        appended_rows.append(row)
        existing_event_ids.add(event_id)
        existing_keys.add(identity)

    if write and appended_rows:
        _append_candidate_rows(ledger_path, appended_rows)

    return {
        "ok": True,
        "schema": SCHEMA_CANDIDATE_BACKFILL,
        "generatedAtIso": _utc_now(),
        "symbol": FOCUS_SYMBOL,
        "window": {
            "startDateJst": start_date_jst,
            "endDateJst": end_date_jst,
            "inclusive": True,
        },
        "sourceFile": "QuantGod_StrategyJsonEAShadowEvaluationLedger.jsonl",
        "targetFile": "QuantGod_ShadowCandidateLedger.csv",
        "write": bool(write),
        "shadowEvaluationRows": len(eval_rows),
        "dedupedOpportunityCount": len(opportunities),
        "existingCandidateRows": existing_count,
        "appendedCandidateRows": len(appended_rows),
        "skipped": dict(sorted(skipped.items())),
        "safety": {
            **dict(SAFETY_BOUNDARY),
            "readOnlyAudit": not write,
            "writesLivePreset": False,
            "orderSendAllowed": False,
            "livePresetMutationAllowed": False,
        },
    }


def backfill_tokyo_h4_shadow_candidate_outcome_ledger(
    runtime_dir: Path,
    *,
    start_date_jst: str | None = None,
    end_date_jst: str | None = None,
    write: bool = False,
) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    start_date_jst, end_date_jst = _window(start_date_jst, end_date_jst)
    candidate_rows = [
        row
        for row in _load_shadow_candidate_rows(runtime_dir, start_date_jst, end_date_jst)
        if str(row.get("CandidateRoute") or "") in {TOKYO_FAMILY, H4_FAMILY}
    ]
    bars = _load_m15_outcome_bars(runtime_dir)
    bar_index = {row["timestamp"]: index for index, row in enumerate(bars)}
    outcome_path = runtime_dir / "QuantGod_ShadowCandidateOutcomeLedger.csv"
    existing = _outcome_ledger_identity(outcome_path)
    appended_rows: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = defaultdict(int)

    for candidate in candidate_rows:
        event_id = str(candidate.get("EventId") or "")
        event_time = _mt5_datetime_text(candidate.get("EventBarTime"))
        event_index = bar_index.get(event_time)
        if not event_id or event_index is None:
            skipped["missingEventBar"] += 1
            continue
        reference_price = _num(candidate.get("ReferencePrice"))
        if reference_price <= 0:
            skipped["missingReferencePrice"] += 1
            continue
        for horizon in (1, 2, 4):
            key = (event_id, str(horizon))
            if key in existing:
                skipped["alreadyPresent"] += 1
                continue
            row = _candidate_outcome_row(candidate, bars, event_index, horizon, reference_price)
            if row:
                appended_rows.append(row)
                existing.add(key)
            else:
                skipped["futureBarsUnavailable"] += 1

    if write and appended_rows:
        _append_outcome_rows(outcome_path, appended_rows)

    return {
        "ok": True,
        "schema": SCHEMA_OUTCOME_BACKFILL,
        "generatedAtIso": _utc_now(),
        "symbol": FOCUS_SYMBOL,
        "window": {
            "startDateJst": start_date_jst,
            "endDateJst": end_date_jst,
            "inclusive": True,
        },
        "sourceFiles": [
            "QuantGod_ShadowCandidateLedger.csv",
            "backtest/exported_klines/QuantGod_USDJPYc_M15_rates.csv",
        ],
        "targetFile": "QuantGod_ShadowCandidateOutcomeLedger.csv",
        "write": bool(write),
        "candidateRows": len(candidate_rows),
        "m15Bars": len(bars),
        "appendedOutcomeRows": len(appended_rows),
        "skipped": dict(sorted(skipped.items())),
        "safety": {
            **dict(SAFETY_BOUNDARY),
            "readOnlyAudit": not write,
            "writesLivePreset": False,
            "orderSendAllowed": False,
            "livePresetMutationAllowed": False,
        },
    }


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


def _current_live_max_spread_pips(runtime_dir: Path, default: float = 2.0) -> float:
    for path in (
        runtime_dir / "QuantGod_USDJPYRsiEntryDiagnostics.json",
        runtime_dir / "QuantGod_StrategyJsonEAShadowEvaluationStatus.json",
    ):
        data = _load_json(path)
        if not data:
            continue
        candidates = []
        inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
        guards = data.get("guards") if isinstance(data.get("guards"), dict) else {}
        candidates.extend(
            [
                inputs.get("PilotMaxSpreadPips"),
                data.get("liveMaxSpreadPips"),
                guards.get("maxSpreadPips"),
                data.get("maxSpreadPips"),
            ]
        )
        for value in candidates:
            spread = _num(value, default=0.0)
            if spread > 0:
                return _round(spread)

    preset = runtime_dir.parent / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
    if preset.exists():
        for raw in preset.read_text(encoding="utf-8", errors="ignore").splitlines():
            if raw.strip().startswith("PilotMaxSpreadPips="):
                spread = _num(raw.split("=", 1)[1], default=0.0)
                if spread > 0:
                    return _round(spread)
    return _round(default)


def _next_probe_threshold(thresholds: Sequence[float], current: float) -> float:
    ordered = sorted(round(float(item), 4) for item in thresholds)
    for threshold in ordered:
        if threshold > current and not math.isclose(threshold, current):
            return _round(threshold)
    return _round(ordered[-1] if ordered else current)


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
    generated_server = row.get("generatedAtServer") or generated
    symbol = row.get("symbol") or FOCUS_SYMBOL
    shared = {
        "symbol": symbol,
        "generatedAtServer": generated_server,
        "shadowResearchSpreadAllowed": row.get("shadowResearchSpreadAllowed"),
        "shadowResearchMaxSpreadPips": row.get("shadowResearchMaxSpreadPips"),
        "bid": _num(row.get("bid")),
        "ask": _num(row.get("ask")),
    }
    h4 = row.get("h4Pullback") if isinstance(row.get("h4Pullback"), dict) else {}
    h4_dir = int(_num(h4.get("signalDirection")))
    if h4_dir:
        items.append(
            {
                **shared,
                "family": H4_FAMILY,
                "direction": "LONG" if h4_dir > 0 else "SHORT",
                "eventBarTime": str(h4.get("eventBarTime") or generated),
                "generatedAtLocal": generated,
                "timeframe": str(h4.get("signalTimeframe") or h4.get("timeframe") or "M15"),
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
                **shared,
                "family": TOKYO_FAMILY,
                "direction": "LONG" if tokyo_dir > 0 else "SHORT",
                "eventBarTime": str(tokyo.get("eventBarTime") or generated),
                "generatedAtLocal": generated,
                "timeframe": str(tokyo.get("timeframe") or "M15"),
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
                **shared,
                "family": "RSI_Reversal",
                "direction": direction,
                "eventBarTime": str(row.get("generatedAtServer") or generated),
                "generatedAtLocal": generated,
                "timeframe": str(row.get("timeframe") or "H1"),
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


def _spread_cap_token(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text.replace(".", "_")


def _micro_live_decision(
    threshold_rows: List[Dict[str, Any]],
    promotion: Dict[str, Any],
    *,
    current_live_max_spread_pips: float = 2.0,
    probe_max_spread_pips: float = 2.2,
) -> Dict[str, Any]:
    probe = next(
        (row for row in threshold_rows if math.isclose(float(row["thresholdPips"]), probe_max_spread_pips)),
        None,
    )
    current = next(
        (row for row in threshold_rows if math.isclose(float(row["thresholdPips"]), current_live_max_spread_pips)),
        None,
    )
    promotion_rows = promotion.get("summary") if isinstance(promotion.get("summary"), list) else []
    promoted = [row for row in promotion_rows if row.get("recommendedStage") != "REMAIN_SHADOW"]
    reasons = []
    if not probe:
        reasons.append(f"本轮没有 {probe_max_spread_pips:g} pips probe 档，不能评估 micro-live 扩门。")
    elif current and probe.get("uniqueOpportunityCount", 0) <= current.get("uniqueOpportunityCount", 0):
        reasons.append(
            f"{probe_max_spread_pips:g} pips 相比 {current_live_max_spread_pips:g} pips 没有增加可去重机会。"
        )
    if not promoted:
        reasons.append("Tokyo/H4 没有路线通过 shadow→replay→walk-forward 晋级审查。")
    if probe and int(probe.get("highScoreOpportunityCount") or 0) <= 0:
        reasons.append(f"{probe_max_spread_pips:g} pips 档没有新增高分且 session/news 可用的去重机会。")
    eligible = bool(probe and promoted and not reasons)
    current_token = _spread_cap_token(current_live_max_spread_pips)
    probe_token = _spread_cap_token(probe_max_spread_pips)
    return {
        "eligible": eligible,
        "recommendation": f"STAGE_LIVE_CAP_{probe_token}_MICRO_LIVE" if eligible else f"KEEP_LIVE_CAP_{current_token}",
        "currentLiveMaxSpreadPips": current_live_max_spread_pips,
        "reviewedProbeMaxSpreadPips": probe_max_spread_pips,
        "reasonZh": f"{probe_max_spread_pips:g} pips 档只增加通过完整晋级链的高质量机会，可进入 micro-live patch 审查。"
        if eligible
        else f"暂不把 live cap 继续升到 {probe_max_spread_pips:g} pips；新增机会还没有通过完整质量链。",
        "blockersZh": reasons,
        "orderSendAllowed": False,
        "livePresetMutationAllowed": False,
    }


def _rsi_long_candidate(row: Dict[str, Any]) -> bool:
    if str(row.get("strategyFamily") or "").upper() not in {"", "RSI_REVERSAL", "RSI_REVERSAL_LONG"}:
        return False
    direction = str(row.get("direction") or "LONG").upper()
    if direction != "LONG":
        return False
    if not bool(row.get("rsiLongSignal") or row.get("rsiCrossbackSignal")):
        return False
    if not bool(row.get("sessionOpen", True)):
        return False
    if bool(row.get("newsBlocked", False)):
        return False
    return True


def _rsi_long_micro_live_probe_review(
    eval_rows: List[Dict[str, Any]],
    threshold_rows: List[Dict[str, Any]],
    *,
    current_live_max_spread_pips: float,
    thresholds: Sequence[float],
) -> Dict[str, Any]:
    probe_thresholds = [
        _round(item)
        for item in sorted({float(value) for value in thresholds})
        if item > current_live_max_spread_pips and item <= 2.4 and not math.isclose(item, current_live_max_spread_pips)
    ]
    candidates = [row for row in eval_rows if _rsi_long_candidate(row)]
    rows_by_threshold = []
    for threshold in probe_thresholds:
        all_pass = [row for row in candidates if _num(row.get("spreadPips")) <= threshold]
        incremental = [
            row
            for row in all_pass
            if _num(row.get("spreadPips")) > current_live_max_spread_pips
        ]
        threshold_impact = next(
            (row for row in threshold_rows if math.isclose(float(row.get("thresholdPips", 0.0)), threshold)),
            {},
        )
        rows_by_threshold.append(
            {
                "thresholdPips": threshold,
                "candidateRows": len(all_pass),
                "incrementalRowsVsCurrentCap": len(incremental),
                "shadowEvaluationPassRows": int(threshold_impact.get("shadowEvaluationPassRows") or 0),
                "shadowEvaluationPassRate": threshold_impact.get("shadowEvaluationPassRate", 0.0),
                "exampleRows": [
                    {
                        "generatedAtLocal": row.get("generatedAtLocal"),
                        "generatedAtServer": row.get("generatedAtServer"),
                        "spreadPips": _round(_num(row.get("spreadPips"))),
                        "rsiClosed1": _round(_num(row.get("rsiClosed1"))),
                        "rsiClosed2": _round(_num(row.get("rsiClosed2"))),
                        "rsiRegimeReason": (
                            row.get("rsiRegimeFilter", {}).get("reason")
                            if isinstance(row.get("rsiRegimeFilter"), dict)
                            else ""
                        ),
                    }
                    for row in incremental[:8]
                ],
            }
        )
    max_probe = max(probe_thresholds) if probe_thresholds else current_live_max_spread_pips
    incremental_total = sum(
        1
        for row in candidates
        if current_live_max_spread_pips < _num(row.get("spreadPips")) <= max_probe
    )
    return {
        "active": True,
        "route": "RSI_Reversal",
        "direction": "LONG",
        "mode": "SPREAD_PROBE_REVIEW_ONLY",
        "currentLiveMaxSpreadPips": current_live_max_spread_pips,
        "probeThresholdsPips": probe_thresholds,
        "candidateRowsAtCurrentCap": sum(
            1 for row in candidates if _num(row.get("spreadPips")) <= current_live_max_spread_pips
        ),
        "totalCandidateRows": len(candidates),
        "incrementalRowsAtMaxProbe": incremental_total,
        "byThreshold": rows_by_threshold,
        "recommendation": "RUN_REPLAY_BEFORE_ANY_LIVE_CAP_CHANGE"
        if incremental_total
        else "NO_RSI_LONG_PROBE_CANDIDATES",
        "reasonZh": "2.3/2.4 pips probe 档出现 RSI LONG 新候选；必须先回放/复盘，不自动修改 live cap。"
        if incremental_total
        else "2.3/2.4 pips probe 档没有新增 RSI LONG 真实候选；维持 2.2 live cap。",
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
    outcome_counts: Dict[Tuple[str, str], int],
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
    computed_outcome_samples = int(outcome_counts.get((family, direction), 0))
    shadow_samples = max(int(_num(shadow.get("sampleCount"))), computed_outcome_samples)
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
        "computedOutcomeSamples": computed_outcome_samples,
        "shadowStage": shadow.get("promotionStage", "") or ("BACKFILLED_OUTCOME" if computed_outcome_samples else ""),
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


def _candidate_ledger_identity(path: Path) -> Tuple[int, set[str], set[Tuple[str, str, str]]]:
    if not path.exists():
        return 0, set(), set()
    event_ids: set[str] = set()
    keys: set[Tuple[str, str, str]] = set()
    rows = 0
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            event_id = str(row.get("EventId") or "")
            if event_id:
                event_ids.add(event_id)
            family = str(row.get("CandidateRoute") or "")
            direction = _direction_from_candidate(row.get("CandidateDirection"))
            event_bar_time = _mt5_datetime_text(row.get("EventBarTime"))
            if family and direction and event_bar_time:
                keys.add((family, direction, event_bar_time))
    return rows, event_ids, keys


def _shadow_research_spread_allowed(item: Dict[str, Any]) -> bool:
    flag = item.get("shadowResearchSpreadAllowed")
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, str) and flag.strip():
        return flag.strip().lower() in {"true", "1", "yes", "y"}
    max_spread = _num(item.get("shadowResearchMaxSpreadPips"), 3.0)
    if max_spread <= 0:
        max_spread = 3.0
    return _num(item.get("spreadPips")) <= max_spread


def _mt5_datetime_text(value: Any) -> str:
    text = str(value or "").strip().replace("T", " ").replace("-", ".")
    if not text:
        return ""
    return text[:19]


def _candidate_event_id(symbol: str, timeframe: str, event_bar_time: str, family: str, direction_label: str) -> str:
    epoch = _mt5_datetime_epoch(event_bar_time)
    event_key = str(epoch) if epoch > 0 else event_bar_time.replace(".", "").replace(" ", "").replace(":", "")
    return f"{symbol}-{timeframe}-{event_key}-{family}-{direction_label}"


def _mt5_datetime_epoch(value: str) -> int:
    text = _mt5_datetime_text(value)
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0


def _candidate_trigger(family: str) -> str:
    if family == TOKYO_FAMILY:
        return "Strategy JSON Tokyo Range shadow signal"
    if family == H4_FAMILY:
        return "Strategy JSON H4 Pullback shadow signal"
    return "Strategy JSON shadow signal"


def _append_candidate_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size <= 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_LEDGER_FIELDS, lineterminator="\r\n")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def _load_m15_outcome_bars(runtime_dir: Path) -> List[Dict[str, Any]]:
    path = runtime_dir / "backtest" / "exported_klines" / "QuantGod_USDJPYc_M15_rates.csv"
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            timestamp = _mt5_datetime_text(row.get("timestamp"))
            if not timestamp:
                continue
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": _num(row.get("open")),
                    "high": _num(row.get("high")),
                    "low": _num(row.get("low")),
                    "close": _num(row.get("close")),
                }
            )
    return rows


def _tokyo_h4_candidate_outcome_counts(
    runtime_dir: Path,
    candidate_rows: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], int]:
    bars = _load_m15_outcome_bars(runtime_dir)
    if not bars:
        return {}
    bar_index = {row["timestamp"]: index for index, row in enumerate(bars)}
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for candidate in candidate_rows:
        family = str(candidate.get("CandidateRoute") or "")
        if family not in {TOKYO_FAMILY, H4_FAMILY}:
            continue
        direction = _direction_from_candidate(candidate.get("CandidateDirection"))
        event_index = bar_index.get(_mt5_datetime_text(candidate.get("EventBarTime")))
        reference_price = _num(candidate.get("ReferencePrice"))
        if not direction or event_index is None or reference_price <= 0:
            continue
        for horizon in (1, 2, 4):
            if _candidate_outcome_row(candidate, bars, event_index, horizon, reference_price):
                counts[(family, direction)] += 1
    return dict(counts)


def _outcome_ledger_identity(path: Path) -> set[Tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[Tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            event_id = str(row.get("EventId") or "")
            horizon = str(row.get("HorizonBars") or "")
            if event_id and horizon:
                keys.add((event_id, horizon))
    return keys


def _candidate_outcome_row(
    candidate: Dict[str, Any],
    bars: List[Dict[str, Any]],
    event_index: int,
    horizon: int,
    reference_price: float,
) -> Dict[str, Any] | None:
    future_index = event_index + horizon - 1
    if future_index >= len(bars):
        return None
    window = bars[event_index : future_index + 1]
    future_close = _num(bars[future_index].get("close"))
    if future_close <= 0:
        return None
    pip = 0.01
    max_high = max([reference_price] + [_num(row.get("high")) for row in window])
    min_low = min([reference_price] + [_num(row.get("low")) for row in window if _num(row.get("low")) > 0])
    long_close = (future_close - reference_price) / pip
    short_close = (reference_price - future_close) / pip
    long_mfe = (max_high - reference_price) / pip
    long_mae = (reference_price - min_low) / pip
    short_mfe = (reference_price - min_low) / pip
    short_mae = (max_high - reference_price) / pip
    direction = str(candidate.get("CandidateDirection") or "").upper()
    now_local = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y.%m.%d %H:%M:%S")
    now_server = datetime.now(timezone.utc).strftime("%Y.%m.%d %H:%M:%S")
    return {
        "EventId": candidate.get("EventId"),
        "OutcomeLabelTimeLocal": now_local,
        "OutcomeLabelTimeServer": now_server,
        "EventBarTime": _mt5_datetime_text(candidate.get("EventBarTime")),
        "Symbol": candidate.get("Symbol") or FOCUS_SYMBOL,
        "CandidateRoute": candidate.get("CandidateRoute"),
        "Timeframe": candidate.get("Timeframe") or "M15",
        "CandidateDirection": direction,
        "CandidateScore": candidate.get("CandidateScore") or "",
        "Regime": candidate.get("Regime") or "",
        "ReferencePrice": f"{reference_price:.3f}",
        "HorizonBars": horizon,
        "HorizonMinutes": horizon * 15,
        "FutureClose": f"{future_close:.3f}",
        "LongClosePips": f"{long_close:.1f}",
        "ShortClosePips": f"{short_close:.1f}",
        "LongMFEPips": f"{long_mfe:.1f}",
        "LongMAEPips": f"{long_mae:.1f}",
        "ShortMFEPips": f"{short_mfe:.1f}",
        "ShortMAEPips": f"{short_mae:.1f}",
        "DirectionalOutcome": _candidate_directional_outcome(direction, long_close, short_close),
        "BestOpportunity": _candidate_best_opportunity(long_close, short_close),
        "OutcomeReason": "Tokyo/H4 shadow candidate outcome backfill from exported M15 bars; does not alter live order gating",
    }


def _candidate_directional_outcome(direction: str, long_close: float, short_close: float) -> str:
    neutral = 2.0
    if direction == "BUY":
        if long_close >= neutral:
            return "WIN"
        if long_close <= -neutral:
            return "LOSS"
        return "FLAT"
    if direction == "SELL":
        if short_close >= neutral:
            return "WIN"
        if short_close <= -neutral:
            return "LOSS"
        return "FLAT"
    if long_close >= neutral and long_close >= short_close:
        return "LONG_OPPORTUNITY"
    if short_close >= neutral and short_close > long_close:
        return "SHORT_OPPORTUNITY"
    return "NEUTRAL_OPPORTUNITY"


def _candidate_best_opportunity(long_close: float, short_close: float) -> str:
    neutral = 2.0
    if long_close >= neutral and long_close >= short_close:
        return "LONG"
    if short_close >= neutral and short_close > long_close:
        return "SHORT"
    return "NEUTRAL"


def _append_outcome_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size <= 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTCOME_LEDGER_FIELDS, lineterminator="\r\n")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


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
