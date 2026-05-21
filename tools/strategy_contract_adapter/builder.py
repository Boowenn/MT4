from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from strategy_ga.schema import CANDIDATE_RUNS_FILE, ELITE_FILE, ga_dir
    from strategy_json.fingerprint import strategy_fingerprint
    from strategy_json.normalizer import normalize_strategy_json
    from strategy_json.schema import ALLOWED_STRATEGY_FAMILIES, FOCUS_SYMBOL, base_strategy_seed
    from strategy_json.validator import validate_strategy_json
except ModuleNotFoundError:  # pragma: no cover - package import path for unittest
    from tools.strategy_ga.schema import CANDIDATE_RUNS_FILE, ELITE_FILE, ga_dir
    from tools.strategy_json.fingerprint import strategy_fingerprint
    from tools.strategy_json.normalizer import normalize_strategy_json
    from tools.strategy_json.schema import ALLOWED_STRATEGY_FAMILIES, FOCUS_SYMBOL, base_strategy_seed
    from tools.strategy_json.validator import validate_strategy_json

from .schema import (
    AGENT_VERSION,
    ALLOWED_CONTRACT_MODES,
    CONTRACT_EA_FILE,
    CONTRACT_JSON_FILE,
    CONTRACT_MODE,
    CONTRACT_SCHEMA,
    CONTRACT_STATUS_FILE,
    EA_STATUS_FILE,
    EA_SHADOW_EVALUATION_LEDGER_FILE,
    EA_SHADOW_EVALUATION_STATUS_FILE,
    FROZEN_RSI_LINEAGE_FILE,
    RSI_OPPORTUNITY_LAYER_AUDIT_REPORT_FILE,
    RSI_SHADOW_OBSERVATION_REPORT_FILE,
    RSI_TRIGGER_ALIGNMENT_AUDIT_REPORT_FILE,
    SAFETY_BOUNDARY,
    contract_dir,
    utc_now_iso,
)

MT5_FILES_ENV_KEYS = (
    "QG_MT5_FILES_DIR",
    "QG_MT5_FILES",
    "QG_HFM_FILES_DIR",
    "QG_HFM_FILES",
)

DEFAULT_MT5_FILES_PATH = (
    Path.home()
    / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path, limit: int = 512) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except Exception:
        return rows
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _candidate_runtime_dirs(runtime_dir: Path) -> List[Path]:
    candidates: List[Path] = [runtime_dir, contract_dir(runtime_dir)]
    for key in MT5_FILES_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value).expanduser())
    candidates.append(DEFAULT_MT5_FILES_PATH)
    seen: set[str] = set()
    dirs: List[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        dirs.append(resolved)
    return dirs


def _safe_str(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback)
    return text.replace("\r", " ").replace("\n", " ").strip()


def _flatten_contract_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "|".join(_safe_str(item).replace(" ", "_") for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(" ", "_")
    return _safe_str(value).replace(" ", "_")


def _candidate_priority(row: Dict[str, Any]) -> Tuple[int, float, str]:
    status = str(row.get("status") or "")
    stage = str(row.get("promotionStage") or "")
    source = str(row.get("source") or "")
    fitness = float(row.get("fitness") or 0.0)
    if status == "ELITE_SELECTED":
        bucket = 0
    elif stage in {"TESTER_ONLY", "PAPER_LIVE_SIM", "FAST_SHADOW"}:
        bucket = 1
    elif status in {"PROMOTED_TO_SHADOW", "NEEDS_MORE_DATA"}:
        bucket = 2
    elif source in {"MUTATION", "CROSSOVER", "CASE_MEMORY"}:
        bucket = 3
    else:
        bucket = 4
    return (bucket, -fitness, str(row.get("seedId") or ""))


def _candidate_strategy(row: Dict[str, Any]) -> Dict[str, Any] | None:
    seed = row.get("strategyJson")
    return seed if isinstance(seed, dict) else None


def _load_frozen_rsi_lineage(runtime_dir: Path) -> Dict[str, Any]:
    return _load_json(ga_dir(runtime_dir) / FROZEN_RSI_LINEAGE_FILE)


def _frozen_lineage_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    criteria = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    lineage = payload.get("lineagePath") if isinstance(payload.get("lineagePath"), dict) else {}
    production = (
        payload.get("productionEvidenceAlignment")
        if isinstance(payload.get("productionEvidenceAlignment"), dict)
        else {}
    )
    replay = payload.get("replayAlignment") if isinstance(payload.get("replayAlignment"), dict) else {}
    return {
        "sourceFile": FROZEN_RSI_LINEAGE_FILE,
        "frozenAt": payload.get("frozenAt"),
        "selectedSeedId": payload.get("selectedSeedId"),
        "selectedGeneration": payload.get("selectedGeneration"),
        "selectedProfile": payload.get("selectedProfile"),
        "selectedFingerprint": payload.get("selectedFingerprint"),
        "lineageDepth": lineage.get("lineageDepth"),
        "criteria": {
            "allPass": bool(criteria.get("allPass")),
            "sampleCount": criteria.get("sampleCount"),
            "tradeCount": criteria.get("tradeCount"),
            "netR": criteria.get("netR"),
            "validationNetR": criteria.get("validationNetR"),
            "forwardNetR": criteria.get("forwardNetR"),
            "maxAdverseR": criteria.get("maxAdverseR"),
            "walkForwardStatus": criteria.get("walkForwardStatus"),
        },
        "productionEvidenceAllPass": bool(production.get("allPass")),
        "replayAllPass": bool(replay.get("allPass")),
    }


def _frozen_rsi_selection(runtime_dir: Path) -> Dict[str, Any] | None:
    frozen = _load_frozen_rsi_lineage(runtime_dir)
    seed = frozen.get("strategyJson") if isinstance(frozen.get("strategyJson"), dict) else {}
    if not seed:
        return None
    validation = validate_strategy_json(seed)
    if not validation.get("valid"):
        return None
    criteria = frozen.get("criteria") if isinstance(frozen.get("criteria"), dict) else {}
    production = (
        frozen.get("productionEvidenceAlignment")
        if isinstance(frozen.get("productionEvidenceAlignment"), dict)
        else {}
    )
    replay = frozen.get("replayAlignment") if isinstance(frozen.get("replayAlignment"), dict) else {}
    normalized = validation.get("normalized") or normalize_strategy_json(seed)
    if (
        normalized.get("strategyFamily") != "RSI_Reversal"
        or normalized.get("direction") != "LONG"
        or not criteria.get("allPass")
        or not production.get("allPass")
        or not replay.get("allPass")
    ):
        return None
    row = {
        "seedId": normalized.get("seedId"),
        "strategyId": normalized.get("strategyId"),
        "strategyFamily": normalized.get("strategyFamily"),
        "direction": normalized.get("direction"),
        "source": "P4_10I_FROZEN_RSI_LINEAGE",
        "fingerprint": frozen.get("selectedFingerprint") or strategy_fingerprint(normalized),
        "status": "ELITE_SELECTED",
        "promotionStage": "TESTER_ONLY",
        "fitness": criteria.get("fitness"),
        "rank": criteria.get("rank"),
        "strategyJson": normalized,
    }
    selection = _selection_from_row(
        row,
        validation,
        source="P4_10J_FROZEN_RSI_SEED",
        reason_zh="按 P4-10I 冻结的 guarded RSI elite lineage 强制轮换到 EA 只读 shadow contract。",
    )
    selection["frozenLineage"] = _frozen_lineage_summary(frozen)
    return selection


def _valid_candidate_rows(runtime_dir: Path) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    elites = _load_json(ga_dir(runtime_dir) / ELITE_FILE).get("elites")
    rows: List[Dict[str, Any]] = [row for row in elites if isinstance(row, dict)] if isinstance(elites, list) else []
    rows.extend(_read_jsonl(ga_dir(runtime_dir) / CANDIDATE_RUNS_FILE))
    rows = sorted(rows, key=_candidate_priority)
    seen: set[str] = set()
    for row in rows:
        seed_id = str(row.get("seedId") or "")
        if seed_id in seen:
            continue
        seen.add(seed_id)
        seed = _candidate_strategy(row)
        if not seed:
            continue
        validation = validate_strategy_json(seed)
        if validation.get("valid"):
            yield row, validation


def _selection_from_row(
    row: Dict[str, Any],
    validation: Dict[str, Any],
    *,
    source: str,
    reason_zh: str,
) -> Dict[str, Any]:
    return {
        "source": source,
        "reasonZh": reason_zh,
        "row": row,
        "validation": validation,
        "strategyJson": validation.get("normalized") or normalize_strategy_json(row.get("strategyJson") or {}),
    }


def select_strategy_candidate(
    runtime_dir: Path,
    *,
    forced_seed_id: str | None = None,
    forced_family: str | None = None,
    force_frozen_rsi: bool = False,
) -> Dict[str, Any]:
    forced_seed_id = _safe_str(forced_seed_id)
    forced_family = _safe_str(forced_family)
    candidates = list(_valid_candidate_rows(runtime_dir))
    if forced_seed_id:
        for row, validation in candidates:
            strategy_json = validation.get("normalized") or normalize_strategy_json(row.get("strategyJson") or {})
            if str(strategy_json.get("seedId") or row.get("seedId") or "") == forced_seed_id:
                return _selection_from_row(
                    row,
                    validation,
                    source="GA_CANDIDATE_FORCED_SEED",
                    reason_zh="按 seedId 轮换 Strategy JSON → EA 只读影子评估契约；不代表晋级或实盘授权。",
                )
        raise ValueError(f"Strategy JSON seed not found or invalid for shadow contract rotation: {forced_seed_id}")
    if force_frozen_rsi:
        selection = _frozen_rsi_selection(runtime_dir)
        if selection:
            return selection
        raise ValueError("Frozen RSI lineage is missing, invalid, or not closed for shadow contract rotation")
    if forced_family:
        if forced_family not in ALLOWED_STRATEGY_FAMILIES:
            raise ValueError(f"Strategy JSON family is not allowed for shadow contract rotation: {forced_family}")
        for row, validation in candidates:
            strategy_json = validation.get("normalized") or normalize_strategy_json(row.get("strategyJson") or {})
            if str(strategy_json.get("strategyFamily") or "") == forced_family:
                return _selection_from_row(
                    row,
                    validation,
                    source="GA_CANDIDATE_FORCED_FAMILY",
                    reason_zh=f"按策略族 {forced_family} 轮换 Strategy JSON → EA 只读影子评估契约；不代表晋级或实盘授权。",
                )
        raise ValueError(f"Strategy JSON family has no valid GA candidate for shadow contract rotation: {forced_family}")
    for row, validation in candidates:
        return _selection_from_row(
            row,
            validation,
            source="GA_CANDIDATE",
            reason_zh="选择最新 GA elite / shadow 候选作为 EA 只读评估契约。",
        )
    seed = base_strategy_seed("SAFE_BASE_USDJPY_RSI_LONG")
    validation = validate_strategy_json(seed)
    return {
        "source": "SAFE_BASE_SEED",
        "reasonZh": "未找到可用 GA 候选，生成安全 USDJPY RSI_Reversal LONG shadow 基准契约。",
        "row": {"seedId": seed.get("seedId"), "status": "SAFE_BASE_SEED", "promotionStage": "SHADOW"},
        "validation": validation,
        "strategyJson": validation.get("normalized") or normalize_strategy_json(seed),
    }


def _strategy_summary(strategy_json: Dict[str, Any]) -> Dict[str, Any]:
    indicators = strategy_json.get("indicators") if isinstance(strategy_json.get("indicators"), dict) else {}
    rsi = indicators.get("rsi") if isinstance(indicators.get("rsi"), dict) else {}
    exit_plan = strategy_json.get("exit") if isinstance(strategy_json.get("exit"), dict) else {}
    risk = strategy_json.get("risk") if isinstance(strategy_json.get("risk"), dict) else {}
    entry = strategy_json.get("entry") if isinstance(strategy_json.get("entry"), dict) else {}
    family_parameters = {
        "ma": indicators.get("ma") if isinstance(indicators.get("ma"), dict) else {},
        "bollinger": indicators.get("bollinger") if isinstance(indicators.get("bollinger"), dict) else {},
        "macd": indicators.get("macd") if isinstance(indicators.get("macd"), dict) else {},
        "supportResistance": indicators.get("supportResistance") if isinstance(indicators.get("supportResistance"), dict) else {},
        "tokyoRange": indicators.get("tokyoRange") if isinstance(indicators.get("tokyoRange"), dict) else {},
        "nightReversion": indicators.get("nightReversion") if isinstance(indicators.get("nightReversion"), dict) else {},
        "h4Pullback": indicators.get("h4Pullback") if isinstance(indicators.get("h4Pullback"), dict) else {},
    }
    return {
        "seedId": strategy_json.get("seedId"),
        "strategyId": strategy_json.get("strategyId"),
        "symbol": strategy_json.get("symbol"),
        "lane": strategy_json.get("lane"),
        "strategyFamily": strategy_json.get("strategyFamily"),
        "direction": strategy_json.get("direction"),
        "qualityProfile": strategy_json.get("qualityProfile"),
        "timeframes": strategy_json.get("timeframes") if isinstance(strategy_json.get("timeframes"), list) else [],
        "entryMode": entry.get("mode") or "OPPORTUNITY_ENTRY",
        "entryConditions": entry.get("conditions") if isinstance(entry.get("conditions"), list) else [],
        "rsi": {
            "period": int(float(rsi.get("period", 14))),
            "timeframe": rsi.get("timeframe") or "H1",
            "buyBand": float(rsi.get("buyBand", 34)),
            "crossbackThreshold": float(rsi.get("crossbackThreshold", 0.8)),
            "adverseExcursionGuard": (
                rsi.get("adverseExcursionGuard")
                if isinstance(rsi.get("adverseExcursionGuard"), dict)
                else {}
            ),
        },
        "familyParameters": family_parameters,
        "exit": {
            "breakevenDelayR": float(exit_plan.get("breakevenDelayR", 1.0)),
            "trailStartR": float(exit_plan.get("trailStartR", 1.5)),
            "mfeGivebackPct": float(exit_plan.get("mfeGivebackPct", 0.6)),
            "timeStopBars": exit_plan.get("timeStopBars") if isinstance(exit_plan.get("timeStopBars"), dict) else {},
        },
        "risk": {
            "stage": risk.get("stage") or "SHADOW",
            "maxLot": float(risk.get("maxLot", 2.0)),
            "opportunityLotMultiplier": float(risk.get("opportunityLotMultiplier", 0.35)),
        },
    }


def _build_ea_text(contract: Dict[str, Any]) -> str:
    strategy = contract["strategy"]
    rsi = strategy["rsi"]
    adverse_guard = rsi.get("adverseExcursionGuard") if isinstance(rsi.get("adverseExcursionGuard"), dict) else {}
    family_params = strategy.get("familyParameters") if isinstance(strategy.get("familyParameters"), dict) else {}
    ma = family_params.get("ma") if isinstance(family_params.get("ma"), dict) else {}
    bollinger = family_params.get("bollinger") if isinstance(family_params.get("bollinger"), dict) else {}
    macd = family_params.get("macd") if isinstance(family_params.get("macd"), dict) else {}
    support_resistance = (
        family_params.get("supportResistance") if isinstance(family_params.get("supportResistance"), dict) else {}
    )
    tokyo_range = family_params.get("tokyoRange") if isinstance(family_params.get("tokyoRange"), dict) else {}
    night_reversion = family_params.get("nightReversion") if isinstance(family_params.get("nightReversion"), dict) else {}
    h4_pullback = family_params.get("h4Pullback") if isinstance(family_params.get("h4Pullback"), dict) else {}
    exit_plan = strategy["exit"]
    risk = strategy["risk"]
    values = {
        "schema": contract["schema"],
        "agentVersion": contract["agentVersion"],
        "generatedAt": contract["generatedAt"],
        "contractMode": contract["contractMode"],
        "focusSymbol": contract["focusSymbol"],
        "fingerprint": contract["fingerprint"],
        "selectedSeedId": contract["selectedSeedId"],
        "strategyId": strategy.get("strategyId"),
        "strategyFamily": strategy.get("strategyFamily"),
        "direction": strategy.get("direction"),
        "qualityProfile": strategy.get("qualityProfile"),
        "lane": strategy.get("lane"),
        "entryMode": strategy.get("entryMode"),
        "timeframes": strategy.get("timeframes"),
        "rsiPeriod": rsi.get("period"),
        "rsiTimeframe": rsi.get("timeframe"),
        "rsiBuyBand": rsi.get("buyBand"),
        "rsiCrossbackThreshold": rsi.get("crossbackThreshold"),
        "rsiAdverseGuardMode": adverse_guard.get("mode"),
        "rsiAdverseGuardMaxEarlyAdverseR": adverse_guard.get("maxEarlyAdverseR"),
        "rsiAdverseGuardMaxEntryRangePips": adverse_guard.get("maxEntryRangePips"),
        "rsiAdverseGuardConfirmationBars": adverse_guard.get("confirmationBars"),
        "rsiAdverseGuardLookaheadBars": adverse_guard.get("lookaheadBars"),
        "rsiAdverseGuardMinConfirmR": adverse_guard.get("minConfirmR"),
        "rsiAdverseGuardRangeLookbackBars": adverse_guard.get("rangeLookbackBars"),
        "familyParameters": family_params,
        "maTimeframe": ma.get("timeframe"),
        "maFastPeriod": ma.get("fastPeriod"),
        "maSlowPeriod": ma.get("slowPeriod"),
        "bbTimeframe": bollinger.get("timeframe"),
        "bbPeriod": bollinger.get("period"),
        "bbDeviations": bollinger.get("deviations"),
        "bbReclaimBufferPips": bollinger.get("reclaimBufferPips"),
        "macdTimeframe": macd.get("timeframe"),
        "macdFastPeriod": macd.get("fastPeriod"),
        "macdSlowPeriod": macd.get("slowPeriod"),
        "macdSignalPeriod": macd.get("signalPeriod"),
        "macdMinHistogramAbs": macd.get("minHistogramAbs"),
        "srTimeframe": support_resistance.get("timeframe"),
        "srLookbackBars": support_resistance.get("lookbackBars"),
        "srBreakoutBufferPips": support_resistance.get("breakoutBufferPips"),
        "tokyoTimeframe": tokyo_range.get("timeframe"),
        "tokyoRangeStartHourUtc": tokyo_range.get("rangeStartHourUtc"),
        "tokyoRangeEndHourUtc": tokyo_range.get("rangeEndHourUtc"),
        "tokyoTradeStartHourUtc": tokyo_range.get("tradeStartHourUtc"),
        "tokyoTradeEndHourUtc": tokyo_range.get("tradeEndHourUtc"),
        "tokyoLookbackBars": tokyo_range.get("lookbackBars"),
        "tokyoBufferPips": tokyo_range.get("bufferPips"),
        "nightTimeframe": night_reversion.get("timeframe"),
        "nightStartHourUtc": night_reversion.get("startHourUtc"),
        "nightEndHourUtc": night_reversion.get("endHourUtc"),
        "nightBollingerPeriod": night_reversion.get("bollingerPeriod"),
        "nightDeviations": night_reversion.get("deviations"),
        "nightEntryBufferPips": night_reversion.get("entryBufferPips"),
        "h4Timeframe": h4_pullback.get("timeframe"),
        "h4FastEmaPeriod": h4_pullback.get("fastEmaPeriod"),
        "h4SlowEmaPeriod": h4_pullback.get("slowEmaPeriod"),
        "h4PullbackEmaPeriod": h4_pullback.get("pullbackEmaPeriod"),
        "h4RsiPeriod": h4_pullback.get("rsiPeriod"),
        "h4LongRsiMin": h4_pullback.get("longRsiMin"),
        "h4ShortRsiMax": h4_pullback.get("shortRsiMax"),
        "breakevenDelayR": exit_plan.get("breakevenDelayR"),
        "trailStartR": exit_plan.get("trailStartR"),
        "mfeGivebackPct": exit_plan.get("mfeGivebackPct"),
        "riskStage": risk.get("stage"),
        "maxLot": risk.get("maxLot"),
        "opportunityLotMultiplier": risk.get("opportunityLotMultiplier"),
        "orderSendAllowed": False,
        "livePresetMutationAllowed": False,
        "gaDirectLiveAllowed": False,
        "shadowOnly": True,
        "wouldAffectLive": False,
    }
    return "".join(f"{key}={_flatten_contract_value(value)}\n" for key, value in values.items())


def _read_ea_status(runtime_dir: Path) -> Dict[str, Any]:
    for directory in _candidate_runtime_dirs(runtime_dir):
        payload = _load_json(directory / EA_STATUS_FILE)
        if payload:
            return {**payload, "sourcePath": str(directory / EA_STATUS_FILE)}
    return {}


def _read_shadow_evaluation_status(runtime_dir: Path) -> Dict[str, Any]:
    primary_paths = [
        runtime_dir / EA_SHADOW_EVALUATION_STATUS_FILE,
        contract_dir(runtime_dir) / EA_SHADOW_EVALUATION_STATUS_FILE,
    ]
    for path in primary_paths:
        payload = _load_json(path)
        if payload:
            return {**payload, "sourcePath": str(path)}
    for directory in _candidate_runtime_dirs(runtime_dir):
        payload = _load_json(directory / EA_SHADOW_EVALUATION_STATUS_FILE)
        if payload:
            return {**payload, "sourcePath": str(directory / EA_SHADOW_EVALUATION_STATUS_FILE)}
    return {}


def _read_shadow_evaluation_ledger(runtime_dir: Path, limit: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    primary_dirs = [runtime_dir, contract_dir(runtime_dir)]
    for directory in primary_dirs:
        path = directory / EA_SHADOW_EVALUATION_LEDGER_FILE
        for row in _read_jsonl(path, limit=limit):
            rows.append({**row, "sourcePath": str(path)})
    if rows:
        rows.sort(key=lambda item: str(item.get("generatedAtServer") or item.get("generatedAtLocal") or ""))
        return rows[-limit:]
    for directory in _candidate_runtime_dirs(runtime_dir):
        path = directory / EA_SHADOW_EVALUATION_LEDGER_FILE
        for row in _read_jsonl(path, limit=limit):
            rows.append({**row, "sourcePath": str(path)})
    rows.sort(key=lambda item: str(item.get("generatedAtServer") or item.get("generatedAtLocal") or ""))
    return rows[-limit:]


def build_strategy_contract(
    runtime_dir: Path,
    write: bool = True,
    *,
    forced_seed_id: str | None = None,
    forced_family: str | None = None,
    force_frozen_rsi: bool = False,
) -> Dict[str, Any]:
    selection = select_strategy_candidate(
        runtime_dir,
        forced_seed_id=forced_seed_id,
        forced_family=forced_family,
        force_frozen_rsi=force_frozen_rsi,
    )
    strategy_json = selection["strategyJson"]
    strategy = _strategy_summary(strategy_json)
    fingerprint = strategy_fingerprint(strategy_json)
    now = utc_now_iso()
    contract = {
        "ok": True,
        "schema": CONTRACT_SCHEMA,
        "agentVersion": AGENT_VERSION,
        "generatedAt": now,
        "singleSourceOfTruth": "STRATEGY_JSON_EA_CONTRACT_ADAPTER",
        "contractMode": CONTRACT_MODE,
        "allowedContractModes": sorted(ALLOWED_CONTRACT_MODES),
        "focusSymbol": FOCUS_SYMBOL,
        "selectedSeedId": strategy_json.get("seedId"),
        "selectionSource": selection["source"],
        "selectionReasonZh": selection["reasonZh"],
        "forcedSeedId": forced_seed_id or None,
        "forcedFamily": forced_family or None,
        "forceFrozenRsi": bool(force_frozen_rsi),
        "frozenRsiLineage": selection.get("frozenLineage") or {},
        "fingerprint": fingerprint,
        "strategy": strategy,
        "strategyJson": strategy_json,
        "validation": selection["validation"],
        "safety": dict(SAFETY_BOUNDARY),
        "ea": {
            "inputFile": CONTRACT_EA_FILE,
            "statusFile": EA_STATUS_FILE,
            "readOnlyAdapter": True,
            "shadowOnly": True,
            "reasonZh": "EA 只读 Strategy JSON contract，用于 shadow/tester/paper lane 评估；不会影响实盘下单权限。",
        },
    }
    status = {
        "ok": True,
        "schema": "quantgod.strategy_json_ea_contract_status.v1",
        "agentVersion": AGENT_VERSION,
        "updatedAt": now,
        "status": "CONTRACT_WRITTEN" if write else "CONTRACT_PREVIEW",
        "contract": contract,
        "eaStatus": _read_ea_status(runtime_dir),
        "eaShadowEvaluation": _read_shadow_evaluation_status(runtime_dir),
        "eaShadowEvaluationRecent": _read_shadow_evaluation_ledger(runtime_dir, limit=20),
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        contract_dir(runtime_dir).mkdir(parents=True, exist_ok=True)
        ea_text = _build_ea_text(contract)
        for base in (runtime_dir, contract_dir(runtime_dir)):
            _write_json(base / CONTRACT_JSON_FILE, contract)
            _write_json(base / CONTRACT_STATUS_FILE, status)
            (base / CONTRACT_EA_FILE).write_text(ea_text, encoding="utf-8")
    return status


def build_rsi_shadow_contract_observation(runtime_dir: Path, *, write: bool = True) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    lineage_file = _load_frozen_rsi_lineage(runtime_dir)
    contract_status = _load_json(runtime_dir / CONTRACT_STATUS_FILE) or _load_json(
        contract_dir(runtime_dir) / CONTRACT_STATUS_FILE
    )
    contract = contract_status.get("contract") if isinstance(contract_status.get("contract"), dict) else {}
    if not contract:
        contract = _load_json(runtime_dir / CONTRACT_JSON_FILE) or _load_json(contract_dir(runtime_dir) / CONTRACT_JSON_FILE)
    frozen, lineage_source = _rsi_observation_lineage_snapshot(contract, lineage_file)
    frozen_seed_id = str(frozen.get("selectedSeedId") or "")
    frozen_fingerprint = str(frozen.get("selectedFingerprint") or "")
    lineage_file_state = _lineage_file_state(lineage_file, frozen)
    shadow_status = _read_shadow_evaluation_status(runtime_dir)
    rows = _read_shadow_evaluation_ledger(runtime_dir, limit=512)
    if shadow_status:
        rows.append(shadow_status)
    matching = [
        row
        for row in rows
        if _row_matches_frozen_seed(row, frozen_seed_id, frozen_fingerprint)
    ]
    latest = _latest_shadow_row(matching)
    contract_rotated = bool(frozen_seed_id) and str(contract.get("selectedSeedId") or "") == frozen_seed_id
    entry_quality = _entry_quality_summary(matching)
    adverse = _adverse_quality_summary(matching, frozen)
    blockers: List[Dict[str, Any]] = []
    if not frozen_seed_id:
        blockers.append({"code": "NO_FROZEN_RSI_LINEAGE", "reasonZh": "缺少 P4-10I frozen RSI lineage。"})
    if not contract_rotated:
        blockers.append({"code": "FROZEN_RSI_CONTRACT_NOT_ROTATED", "reasonZh": "EA contract 尚未轮换到 frozen RSI seed。"})
    if not matching:
        blockers.append({"code": "WAITING_FROZEN_RSI_SHADOW_LEDGER", "reasonZh": "等待 EA 写入 frozen RSI seed 的 shadow evaluation ledger。"})
    if entry_quality.get("status") == "FAIL":
        blockers.append({"code": "RSI_SHADOW_ENTRY_QUALITY_FAIL", "reasonZh": entry_quality.get("reasonZh")})
    if adverse.get("status") == "FAIL":
        blockers.append({"code": "RSI_SHADOW_ADVERSE_DEGRADED", "reasonZh": adverse.get("reasonZh")})
    status = "PASS"
    if blockers:
        hard_blockers = {"NO_FROZEN_RSI_LINEAGE", "FROZEN_RSI_CONTRACT_NOT_ROTATED", "RSI_SHADOW_ADVERSE_DEGRADED"}
        status = "WARN"
        if any(blocker.get("code") in hard_blockers for blocker in blockers):
            status = "WARN"
    elif entry_quality.get("status") == "WATCH" or adverse.get("status") == "WATCH":
        status = "WATCH"
    report = {
        "ok": True,
        "schema": "quantgod.rsi_shadow_contract_observation.v1",
        "generatedAt": utc_now_iso(),
        "status": status,
        "phase": "P4_10J_RSI_SHADOW_CONTRACT_OBSERVATION",
        "lineageSource": lineage_source,
        "frozenSeedId": frozen_seed_id or None,
        "frozenFingerprint": frozen_fingerprint or None,
        "lineageFile": lineage_file_state,
        "contractRotation": {
            "selectedSeedId": contract.get("selectedSeedId"),
            "selectionSource": contract.get("selectionSource"),
            "forceFrozenRsi": bool(contract.get("forceFrozenRsi")),
            "matchesFrozenSeed": contract_rotated,
            "contractMode": contract.get("contractMode"),
        },
        "shadowEvaluation": {
            "matchingRowCount": len(matching),
            "latest": _shadow_row_summary(latest),
            "statusCounts": dict(_status_counts(matching)),
            "sourceRowsInspected": len(rows),
        },
        "entryQuality": entry_quality,
        "adverseExcursion": adverse,
        "blockers": blockers,
        "recommendationsZh": _rsi_shadow_observation_recommendations(status, blockers),
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        _write_json(contract_dir(runtime_dir) / RSI_SHADOW_OBSERVATION_REPORT_FILE, report)
    return report


def build_rsi_opportunity_layer_audit(runtime_dir: Path, *, write: bool = True) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    lineage_file = _load_frozen_rsi_lineage(runtime_dir)
    contract_status = _load_json(runtime_dir / CONTRACT_STATUS_FILE) or _load_json(
        contract_dir(runtime_dir) / CONTRACT_STATUS_FILE
    )
    contract = contract_status.get("contract") if isinstance(contract_status.get("contract"), dict) else {}
    if not contract:
        contract = _load_json(runtime_dir / CONTRACT_JSON_FILE) or _load_json(contract_dir(runtime_dir) / CONTRACT_JSON_FILE)
    frozen, lineage_source = _rsi_observation_lineage_snapshot(contract, lineage_file)
    frozen_seed_id = str(frozen.get("selectedSeedId") or "")
    frozen_fingerprint = str(frozen.get("selectedFingerprint") or "")
    lineage_file_state = _lineage_file_state(lineage_file, frozen)
    shadow_status = _read_shadow_evaluation_status(runtime_dir)
    rows = _read_shadow_evaluation_ledger(runtime_dir, limit=2048)
    if shadow_status:
        rows.append(shadow_status)
    matching = _dedupe_shadow_rows(
        [row for row in rows if _row_matches_frozen_seed(row, frozen_seed_id, frozen_fingerprint)]
    )
    contract_rotated = bool(frozen_seed_id) and str(contract.get("selectedSeedId") or "") == frozen_seed_id
    classification = _rsi_opportunity_layer_classification(matching)
    latest = _latest_shadow_row(matching)
    blockers: List[Dict[str, Any]] = []
    if not frozen_seed_id:
        blockers.append({"code": "NO_FROZEN_RSI_LINEAGE", "reasonZh": "缺少 P4-10I/P4-10J frozen RSI lineage 快照。"})
    if not contract_rotated:
        blockers.append({"code": "FROZEN_RSI_CONTRACT_NOT_ROTATED", "reasonZh": "EA contract 尚未轮换到 frozen RSI seed。"})
    if not matching:
        blockers.append({"code": "WAITING_FROZEN_RSI_SHADOW_LEDGER", "reasonZh": "等待 frozen RSI seed 的 EA shadow ledger 后再审计机会层。"})
    if classification["safetyFlags"]["unsafeRowCount"]:
        blockers.append({"code": "SHADOW_ONLY_SAFETY_BROKEN", "reasonZh": "ledger 出现非 shadow-only 安全旗标，需先停止晋级判断。"})
    if classification["rsiAdverseGuard"]["missingLoadedCount"] and not classification["rsiAdverseGuard"]["loadedCount"]:
        blockers.append({"code": "RSI_ADVERSE_GUARD_NOT_LOADED", "reasonZh": "当前样本未看到 rsiAdverseGuard.loaded=true，low-adverse 复核证据不完整。"})
    status = _rsi_opportunity_layer_status(blockers, classification)
    report = {
        "ok": True,
        "schema": "quantgod.rsi_opportunity_layer_audit.v1",
        "generatedAt": utc_now_iso(),
        "status": status,
        "phase": "P4_10K_RSI_SHADOW_ONLY_OPPORTUNITY_LAYER_AUDIT",
        "lineageSource": lineage_source,
        "frozenSeedId": frozen_seed_id or None,
        "frozenFingerprint": frozen_fingerprint or None,
        "lineageFile": lineage_file_state,
        "contractRotation": {
            "selectedSeedId": contract.get("selectedSeedId"),
            "selectionSource": contract.get("selectionSource"),
            "forceFrozenRsi": bool(contract.get("forceFrozenRsi")),
            "matchesFrozenSeed": contract_rotated,
            "contractMode": contract.get("contractMode"),
        },
        "sampleWindow": {
            "matchingRowCount": len(matching),
            "sourceRowsInspected": len(rows),
            "first": _shadow_row_summary(matching[0]) if matching else {},
            "latest": _shadow_row_summary(latest),
            "statusCounts": dict(_status_counts(matching)),
            "blockerCounts": _field_counts(matching, "blocker"),
        },
        "classification": classification,
        "blockers": blockers,
        "recommendationsZh": _rsi_opportunity_layer_recommendations(status, classification, blockers),
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        _write_json(contract_dir(runtime_dir) / RSI_OPPORTUNITY_LAYER_AUDIT_REPORT_FILE, report)
    return report


def build_rsi_trigger_alignment_audit(runtime_dir: Path, *, write: bool = True) -> Dict[str, Any]:
    runtime_dir = Path(runtime_dir)
    lineage_file = _load_frozen_rsi_lineage(runtime_dir)
    contract_status = _load_json(runtime_dir / CONTRACT_STATUS_FILE) or _load_json(
        contract_dir(runtime_dir) / CONTRACT_STATUS_FILE
    )
    contract = contract_status.get("contract") if isinstance(contract_status.get("contract"), dict) else {}
    if not contract:
        contract = _load_json(runtime_dir / CONTRACT_JSON_FILE) or _load_json(contract_dir(runtime_dir) / CONTRACT_JSON_FILE)
    frozen, lineage_source = _rsi_observation_lineage_snapshot(contract, lineage_file)
    frozen_seed_id = str(frozen.get("selectedSeedId") or "")
    frozen_fingerprint = str(frozen.get("selectedFingerprint") or "")
    lineage_file_state = _lineage_file_state(lineage_file, frozen)
    shadow_status = _read_shadow_evaluation_status(runtime_dir)
    rows = _read_shadow_evaluation_ledger(runtime_dir, limit=4096)
    if shadow_status:
        rows.append(shadow_status)
    matching = _dedupe_shadow_rows(
        [row for row in rows if _row_matches_frozen_seed(row, frozen_seed_id, frozen_fingerprint)]
    )
    contract_rotated = bool(frozen_seed_id) and str(contract.get("selectedSeedId") or "") == frozen_seed_id
    contract_strategy = contract.get("strategy") if isinstance(contract.get("strategy"), dict) else {}
    contract_rsi = contract_strategy.get("rsi") if isinstance(contract_strategy.get("rsi"), dict) else {}
    strategy_json = contract.get("strategyJson") if isinstance(contract.get("strategyJson"), dict) else {}
    strategy_json_rsi = (
        ((strategy_json.get("indicators") or {}).get("rsi") or {})
        if isinstance(strategy_json.get("indicators"), dict)
        else {}
    )
    rsi_source = strategy_json_rsi if strategy_json_rsi else contract_rsi
    parameter_parity = _rsi_trigger_parameter_parity(matching, contract_rsi, strategy_json_rsi)
    trigger_telemetry = _rsi_trigger_telemetry(matching, rsi_source)
    adapter_coverage = _rsi_trigger_adapter_coverage(contract_rsi, strategy_json_rsi, trigger_telemetry)
    reference_alignment = _rsi_trigger_reference_alignment(runtime_dir, frozen, lineage_file_state)
    legacy_diagnostics = _rsi_legacy_diagnostics_summary(runtime_dir, rsi_source)
    blockers: List[Dict[str, Any]] = []
    if not frozen_seed_id:
        blockers.append({"code": "NO_FROZEN_RSI_LINEAGE", "reasonZh": "缺少 P4-10I/P4-10J frozen RSI lineage 快照。"})
    if not contract_rotated:
        blockers.append({"code": "FROZEN_RSI_CONTRACT_NOT_ROTATED", "reasonZh": "EA contract 尚未轮换到 frozen RSI seed。"})
    if not matching:
        blockers.append({"code": "WAITING_FROZEN_RSI_SHADOW_LEDGER", "reasonZh": "等待 frozen RSI seed 的 EA shadow ledger 后再复核 RSI trigger。"})
    if not parameter_parity.get("contractToLedgerAllPass"):
        blockers.append({"code": "RSI_CONTRACT_LEDGER_PARAMETER_MISMATCH", "reasonZh": "EA ledger 的 RSI period/timeframe/buyBand/crossback 与 active contract 不一致。"})
    if not parameter_parity.get("strategyJsonToContractAllPass"):
        blockers.append({"code": "RSI_STRATEGY_JSON_CONTRACT_PARAMETER_MISMATCH", "reasonZh": "Strategy JSON 与 EA contract 的核心 RSI 参数不一致。"})
    if adapter_coverage.get("materialCoverageGap"):
        blockers.append({"code": "RSI_TRIGGER_ADAPTER_COVERAGE_GAP", "reasonZh": adapter_coverage.get("reasonZh")})
    if trigger_telemetry.get("ledgerSignalMismatchCount"):
        blockers.append({"code": "RSI_TRIGGER_RECOMPUTE_MISMATCH", "reasonZh": "按 ledger RSI 值重算的 EA trigger 与 rsiLongSignal 字段不一致。"})
    status = _rsi_trigger_alignment_status(blockers, trigger_telemetry)
    decision = _rsi_trigger_alignment_decision(parameter_parity, trigger_telemetry, adapter_coverage)
    report = {
        "ok": True,
        "schema": "quantgod.rsi_trigger_alignment_audit.v1",
        "generatedAt": utc_now_iso(),
        "status": status,
        "phase": "P4_10L_RSI_TRIGGER_ALIGNMENT_AUDIT",
        "lineageSource": lineage_source,
        "frozenSeedId": frozen_seed_id or None,
        "frozenFingerprint": frozen_fingerprint or None,
        "lineageFile": lineage_file_state,
        "contractRotation": {
            "selectedSeedId": contract.get("selectedSeedId"),
            "selectionSource": contract.get("selectionSource"),
            "forceFrozenRsi": bool(contract.get("forceFrozenRsi")),
            "matchesFrozenSeed": contract_rotated,
            "contractMode": contract.get("contractMode"),
        },
        "rsiParameters": {
            "contract": _rsi_parameter_snapshot(contract_rsi),
            "strategyJson": _rsi_parameter_snapshot(strategy_json_rsi),
            "ledger": parameter_parity.get("ledgerObserved"),
        },
        "parameterParity": parameter_parity,
        "triggerTelemetry": trigger_telemetry,
        "adapterCoverage": adapter_coverage,
        "referenceAlignment": reference_alignment,
        "legacyDiagnostics": legacy_diagnostics,
        "sampleWindow": {
            "matchingRowCount": len(matching),
            "sourceRowsInspected": len(rows),
            "latest": _shadow_row_summary(_latest_shadow_row(matching)),
            "statusCounts": dict(_status_counts(matching)),
            "blockerCounts": _field_counts(matching, "blocker"),
        },
        "decision": decision,
        "blockers": blockers,
        "recommendationsZh": _rsi_trigger_alignment_recommendations(status, decision, blockers),
        "safety": dict(SAFETY_BOUNDARY),
    }
    if write:
        _write_json(contract_dir(runtime_dir) / RSI_TRIGGER_ALIGNMENT_AUDIT_REPORT_FILE, report)
    return report


def _rsi_observation_lineage_snapshot(contract: Dict[str, Any], lineage_file: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    contract_lineage = (
        contract.get("frozenRsiLineage")
        if isinstance(contract.get("frozenRsiLineage"), dict)
        else {}
    )
    contract_seed_id = str(contract.get("selectedSeedId") or "")
    contract_fingerprint = str(contract.get("fingerprint") or contract_lineage.get("selectedFingerprint") or "")
    is_p4_10j_contract = (
        bool(contract.get("forceFrozenRsi"))
        and str(contract.get("selectionSource") or "") == "P4_10J_FROZEN_RSI_SEED"
        and bool(contract_seed_id)
    )
    if is_p4_10j_contract:
        snapshot = {
            "sourceFile": contract_lineage.get("sourceFile") or FROZEN_RSI_LINEAGE_FILE,
            "frozenAt": contract_lineage.get("frozenAt") or contract.get("generatedAt"),
            "selectedSeedId": contract_seed_id,
            "selectedGeneration": contract_lineage.get("selectedGeneration"),
            "selectedProfile": contract_lineage.get("selectedProfile"),
            "selectedFingerprint": contract_fingerprint,
            "lineageDepth": contract_lineage.get("lineageDepth"),
            "criteria": contract_lineage.get("criteria") if isinstance(contract_lineage.get("criteria"), dict) else {},
            "productionEvidenceAllPass": contract_lineage.get("productionEvidenceAllPass"),
            "replayAllPass": contract_lineage.get("replayAllPass"),
        }
        return snapshot, "EA_CONTRACT_FROZEN_RSI_SNAPSHOT"
    return lineage_file, "GA_FROZEN_RSI_LINEAGE_FILE"


def _lineage_file_state(lineage_file: Dict[str, Any], active_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    file_seed_id = str(lineage_file.get("selectedSeedId") or "")
    file_fingerprint = str(lineage_file.get("selectedFingerprint") or "")
    active_seed_id = str(active_snapshot.get("selectedSeedId") or "")
    active_fingerprint = str(active_snapshot.get("selectedFingerprint") or "")
    drifted = bool(file_seed_id and active_seed_id and file_seed_id != active_seed_id) or bool(
        file_fingerprint and active_fingerprint and file_fingerprint != active_fingerprint
    )
    return {
        "sourceFile": FROZEN_RSI_LINEAGE_FILE,
        "selectedSeedId": file_seed_id or None,
        "selectedFingerprint": file_fingerprint or None,
        "selectedGeneration": lineage_file.get("selectedGeneration"),
        "driftedFromActiveContract": drifted,
    }


def _row_matches_frozen_seed(row: Dict[str, Any], seed_id: str, fingerprint: str) -> bool:
    if not isinstance(row, dict):
        return False
    if seed_id and str(row.get("selectedSeedId") or "") == seed_id:
        return True
    return bool(fingerprint and str(row.get("fingerprint") or "") == fingerprint)


def _latest_shadow_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    return sorted(rows, key=lambda item: str(item.get("generatedAtServer") or item.get("generatedAtLocal") or ""))[-1]


def _dedupe_shadow_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = str(row.get("evaluationId") or "")
        if not key:
            key = "|".join(
                [
                    str(row.get("generatedAtServer") or row.get("generatedAtLocal") or index),
                    str(row.get("selectedSeedId") or ""),
                    str(row.get("fingerprint") or ""),
                    str(row.get("status") or ""),
                    str(row.get("blocker") or ""),
                ]
            )
        deduped[key] = row
    return sorted(deduped.values(), key=lambda item: str(item.get("generatedAtServer") or item.get("generatedAtLocal") or ""))


def _status_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _field_counts(rows: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "UNKNOWN")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _shadow_row_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    adverse_guard = row.get("rsiAdverseGuard") if isinstance(row.get("rsiAdverseGuard"), dict) else {}
    return {
        "evaluationId": row.get("evaluationId"),
        "generatedAtLocal": row.get("generatedAtLocal"),
        "generatedAtServer": row.get("generatedAtServer"),
        "status": row.get("status"),
        "blocker": row.get("blocker"),
        "selectedSeedId": row.get("selectedSeedId"),
        "strategyFamily": row.get("strategyFamily"),
        "direction": row.get("direction"),
        "wouldEnter": bool(row.get("wouldEnter")),
        "hardGuardsPass": bool(row.get("hardGuardsPass")),
        "indicatorReady": bool(row.get("indicatorReady")),
        "rsiLongSignal": bool(row.get("rsiLongSignal")),
        "spreadPips": row.get("spreadPips"),
        "rsiClosed1": row.get("rsiClosed1"),
        "rsiClosed2": row.get("rsiClosed2"),
        "rsiAdverseGuard": adverse_guard,
        "reasonZh": row.get("reasonZh"),
    }


def _rsi_opportunity_layer_classification(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    research_observable_live_blocked: List[Dict[str, Any]] = []
    research_observable_live_blocked_rsi: List[Dict[str, Any]] = []
    true_no_rsi_opportunity: List[Dict[str, Any]] = []
    not_research_observable_spread_blocked: List[Dict[str, Any]] = []
    would_enter = [row for row in rows if bool(row.get("wouldEnter")) or row.get("status") == "SHADOW_WOULD_ENTER"]
    adverse_values = [_adverse_value(row) for row in rows]
    adverse_values = [value for value in adverse_values if value is not None]
    indicator_ready_count = sum(1 for row in rows if bool(row.get("indicatorReady")))
    hard_guards_pass_count = sum(1 for row in rows if bool(row.get("hardGuardsPass")))
    rsi_signal_count = sum(1 for row in rows if bool(row.get("rsiLongSignal")))
    live_spread_allowed_count = sum(1 for row in rows if bool(row.get("liveSpreadAllowed")))
    shadow_research_spread_allowed_count = sum(1 for row in rows if bool(row.get("shadowResearchSpreadAllowed")))
    spread_block_count = sum(1 for row in rows if str(row.get("blocker") or "") == "SPREAD_BLOCK")
    guard_loaded_count = sum(1 for row in rows if _rsi_adverse_guard_loaded(row))
    guard_range_pass_count = sum(1 for row in rows if _rsi_guard_range_pass(row))
    unsafe_rows = [
        row
        for row in rows
        if bool(row.get("orderSendAllowed"))
        or bool(row.get("livePresetMutationAllowed"))
        or bool(row.get("gaDirectLiveAllowed"))
    ]
    for row in rows:
        live_spread_blocked = not bool(row.get("liveSpreadAllowed"))
        research_spread_allowed = bool(row.get("shadowResearchSpreadAllowed"))
        spread_blocked = str(row.get("blocker") or "") == "SPREAD_BLOCK"
        research_observable = research_spread_allowed and live_spread_blocked
        guard_ready = _rsi_guard_range_pass(row)
        if spread_blocked and research_observable:
            research_observable_live_blocked.append(row)
            if bool(row.get("rsiLongSignal")) and guard_ready:
                research_observable_live_blocked_rsi.append(row)
            elif bool(row.get("indicatorReady")) and guard_ready and not bool(row.get("rsiLongSignal")):
                true_no_rsi_opportunity.append(row)
        elif spread_blocked and not research_observable:
            not_research_observable_spread_blocked.append(row)
        elif bool(row.get("indicatorReady")) and guard_ready and not bool(row.get("rsiLongSignal")):
            true_no_rsi_opportunity.append(row)
    latest_hidden = _latest_shadow_row(research_observable_live_blocked_rsi)
    latest_true_no_rsi = _latest_shadow_row(true_no_rsi_opportunity)
    return {
        "rowCount": len(rows),
        "wouldEnterCount": len(would_enter),
        "rsiSignalCount": rsi_signal_count,
        "indicatorReadyCount": indicator_ready_count,
        "hardGuardsPassCount": hard_guards_pass_count,
        "spreadBlockCount": spread_block_count,
        "liveSpreadAllowedCount": live_spread_allowed_count,
        "shadowResearchSpreadAllowedCount": shadow_research_spread_allowed_count,
        "researchObservableLiveBlockedCount": len(research_observable_live_blocked),
        "researchObservableLiveBlockedWithRsiSignalCount": len(research_observable_live_blocked_rsi),
        "trueNoRsiOpportunityCount": len(true_no_rsi_opportunity),
        "notResearchObservableSpreadBlockedCount": len(not_research_observable_spread_blocked),
        "latestResearchObservableLiveBlockedWithRsiSignal": _shadow_row_summary(latest_hidden),
        "latestTrueNoRsiOpportunity": _shadow_row_summary(latest_true_no_rsi),
        "spreadDistribution": _numeric_distribution(rows, "spreadPips"),
        "liveMaxSpreadDistribution": _numeric_distribution(rows, "liveMaxSpreadPips"),
        "shadowResearchMaxSpreadDistribution": _numeric_distribution(rows, "shadowResearchMaxSpreadPips"),
        "rsiClosed1Distribution": _numeric_distribution(rows, "rsiClosed1"),
        "rsiBuyBandDistribution": _numeric_distribution(rows, "rsiBuyBand"),
        "rsiAdverseGuard": {
            "loadedCount": guard_loaded_count,
            "rangePassCount": guard_range_pass_count,
            "missingLoadedCount": max(0, len(rows) - guard_loaded_count),
            "entryRangePipsDistribution": _nested_numeric_distribution(rows, ("rsiAdverseGuard", "entryRangePips")),
            "maxEntryRangePipsDistribution": _nested_numeric_distribution(rows, ("rsiAdverseGuard", "maxEntryRangePips")),
        },
        "adverseSamples": {
            "count": len(adverse_values),
            "worstObservedAdverseR": min(adverse_values) if adverse_values else None,
            "bestObservedAdverseR": max(adverse_values) if adverse_values else None,
        },
        "safetyFlags": {
            "unsafeRowCount": len(unsafe_rows),
            "orderSendAllowedCount": sum(1 for row in rows if bool(row.get("orderSendAllowed"))),
            "livePresetMutationAllowedCount": sum(1 for row in rows if bool(row.get("livePresetMutationAllowed"))),
            "gaDirectLiveAllowedCount": sum(1 for row in rows if bool(row.get("gaDirectLiveAllowed"))),
        },
        "decision": _rsi_opportunity_layer_decision(
            len(rows),
            len(research_observable_live_blocked),
            len(research_observable_live_blocked_rsi),
            len(true_no_rsi_opportunity),
            len(not_research_observable_spread_blocked),
        ),
    }


def _rsi_guard_range_pass(row: Dict[str, Any]) -> bool:
    guard = row.get("rsiAdverseGuard") if isinstance(row.get("rsiAdverseGuard"), dict) else {}
    if "rangePass" in guard:
        return bool(guard.get("rangePass"))
    return True


def _numeric_distribution(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    values = [_safe_float(row.get(key), None) for row in rows]
    values = [value for value in values if value is not None]
    return _distribution(values)


def _nested_numeric_distribution(rows: List[Dict[str, Any]], path: Tuple[str, ...]) -> Dict[str, Any]:
    values: List[float] = []
    for row in rows:
        current: Any = row
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        value = _safe_float(current, None)
        if value is not None:
            values.append(value)
    return _distribution(values)


def _distribution(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        median = ordered[midpoint]
    else:
        median = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    return {"count": len(ordered), "min": ordered[0], "median": median, "max": ordered[-1]}


def _rsi_opportunity_layer_decision(
    row_count: int,
    research_observable_live_blocked_count: int,
    hidden_rsi_count: int,
    true_no_rsi_count: int,
    not_research_observable_spread_blocked_count: int,
) -> Dict[str, Any]:
    if row_count <= 0:
        return {
            "label": "WAITING_LEDGER",
            "reasonZh": "还没有 frozen RSI seed 的 shadow ledger，暂时不能区分 spread 阻断与无机会。",
        }
    if hidden_rsi_count > 0:
        return {
            "label": "RESEARCH_SPREAD_PASS_LIVE_SPREAD_BLOCKED_RSI_SIGNAL",
            "reasonZh": "已出现 RSI 入场信号：研究点差口径可观察，但 live 点差口径阻断；这不是“没有机会”。",
        }
    if research_observable_live_blocked_count > 0 and true_no_rsi_count >= research_observable_live_blocked_count:
        return {
            "label": "TRUE_NO_RSI_OPPORTUNITY_UNDER_RESEARCH_SPREAD",
            "reasonZh": "研究点差口径可观察的样本里 RSI 未触发，当前更像是真的没有 RSI 入场机会。",
        }
    if not_research_observable_spread_blocked_count > 0 and research_observable_live_blocked_count <= 0:
        return {
            "label": "SPREAD_TOO_WIDE_FOR_RESEARCH_LAYER",
            "reasonZh": "点差连 research shadow 口径都未通过，不能把这些样本解释成可观察机会。",
        }
    return {
        "label": "MIXED_OR_INCOMPLETE_OPPORTUNITY_LAYER",
        "reasonZh": "样本同时包含不同阻断路径或字段不完整，需要继续观察更多 shadow ledger。",
    }


def _rsi_opportunity_layer_status(blockers: List[Dict[str, Any]], classification: Dict[str, Any]) -> str:
    hard_blockers = {"NO_FROZEN_RSI_LINEAGE", "FROZEN_RSI_CONTRACT_NOT_ROTATED", "SHADOW_ONLY_SAFETY_BROKEN"}
    if any(blocker.get("code") in hard_blockers for blocker in blockers):
        return "WARN"
    if classification.get("researchObservableLiveBlockedWithRsiSignalCount", 0) > 0:
        return "PASS"
    return "WATCH"


def _rsi_opportunity_layer_recommendations(
    status: str, classification: Dict[str, Any], blockers: List[Dict[str, Any]]
) -> List[str]:
    if status == "WARN" and blockers:
        return [str(blocker.get("reasonZh") or blocker.get("code")) for blocker in blockers]
    decision = classification.get("decision") if isinstance(classification.get("decision"), dict) else {}
    label = str(decision.get("label") or "")
    if label == "RESEARCH_SPREAD_PASS_LIVE_SPREAD_BLOCKED_RSI_SIGNAL":
        return [
            "保留 frozen seed，不扩搜索；下一步复核 live spread gate 是否应记录 opportunity-layer shadow 样本，而不是立刻放宽实盘点差。",
            "继续等待 post-entry adverse/MAE/maxAdverseR，确认 low-adverse guard 在 MT5 shadow 里复现。",
        ]
    if label == "TRUE_NO_RSI_OPPORTUNITY_UNDER_RESEARCH_SPREAD":
        return ["继续观察同一颗 seed；当前证据指向 RSI 未触发，而不是 live spread 掩盖了入场机会。"]
    if label == "SPREAD_TOO_WIDE_FOR_RESEARCH_LAYER":
        return ["继续等正常流动性窗口；这些样本连 research spread 口径都不可观察，不应用来否定 RSI seed。"]
    return ["继续收集 frozen RSI shadow ledger，直到能分清 research-spread-pass/live-blocked 与 no-signal。"]


def _rsi_parameter_snapshot(rsi: Dict[str, Any]) -> Dict[str, Any]:
    regime = rsi.get("regimeFilter") if isinstance(rsi.get("regimeFilter"), dict) else {}
    return {
        "period": rsi.get("period"),
        "timeframe": rsi.get("timeframe"),
        "buyBand": rsi.get("buyBand"),
        "crossbackThreshold": rsi.get("crossbackThreshold"),
        "maxCrossbackRsi": rsi.get("maxCrossbackRsi"),
        "regimeFilterMode": regime.get("mode"),
        "regimeFilterEnabled": _rsi_regime_filter_enabled(regime),
        "adverseExcursionGuard": (
            rsi.get("adverseExcursionGuard") if isinstance(rsi.get("adverseExcursionGuard"), dict) else {}
        ),
    }


def _rsi_trigger_parameter_parity(
    rows: List[Dict[str, Any]], contract_rsi: Dict[str, Any], strategy_json_rsi: Dict[str, Any]
) -> Dict[str, Any]:
    ledger_observed = {
        "periodValues": _unique_row_values(rows, "rsiPeriod"),
        "timeframeValues": _unique_row_values(rows, "timeframe"),
        "buyBandValues": _unique_row_values(rows, "rsiBuyBand"),
        "crossbackThresholdValues": _unique_row_values(rows, "rsiCrossbackThreshold"),
    }
    contract_checks = {
        "period": _all_values_match(ledger_observed["periodValues"], contract_rsi.get("period")),
        "timeframe": _all_values_match(ledger_observed["timeframeValues"], contract_rsi.get("timeframe")),
        "buyBand": _all_values_match(ledger_observed["buyBandValues"], contract_rsi.get("buyBand")),
        "crossbackThreshold": _all_values_match(
            ledger_observed["crossbackThresholdValues"], contract_rsi.get("crossbackThreshold")
        ),
    }
    strategy_contract_checks = {
        "period": _values_match(contract_rsi.get("period"), strategy_json_rsi.get("period")),
        "timeframe": _values_match(contract_rsi.get("timeframe"), strategy_json_rsi.get("timeframe")),
        "buyBand": _values_match(contract_rsi.get("buyBand"), strategy_json_rsi.get("buyBand")),
        "crossbackThreshold": _values_match(
            contract_rsi.get("crossbackThreshold"), strategy_json_rsi.get("crossbackThreshold")
        ),
    }
    return {
        "ledgerObserved": ledger_observed,
        "contractToLedgerChecks": contract_checks,
        "contractToLedgerAllPass": bool(rows) and all(contract_checks.values()),
        "strategyJsonToContractChecks": strategy_contract_checks,
        "strategyJsonToContractAllPass": bool(strategy_json_rsi) and all(strategy_contract_checks.values()),
        "reasonZh": (
            "EA shadow ledger 的核心 RSI 参数与 active contract 一致。"
            if bool(rows) and all(contract_checks.values())
            else "EA shadow ledger 的核心 RSI 参数与 active contract 存在不一致或样本不足。"
        ),
    }


def _unique_row_values(rows: List[Dict[str, Any]], key: str, limit: int = 10) -> List[Any]:
    values: List[Any] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get(key)
        marker = str(value)
        if marker in seen:
            continue
        seen.add(marker)
        values.append(value)
        if len(values) >= limit:
            break
    return values


def _all_values_match(values: List[Any], expected: Any) -> bool:
    if not values:
        return False
    return all(_values_match(value, expected) for value in values)


def _values_match(left: Any, right: Any, *, tolerance: float = 0.0001) -> bool:
    if left is None or right is None:
        return left is None and right is None
    left_number = _safe_float(left, None)
    right_number = _safe_float(right, None)
    if left_number is not None and right_number is not None:
        return abs(left_number - right_number) <= tolerance
    return str(left) == str(right)


def _rsi_trigger_telemetry(rows: List[Dict[str, Any]], rsi: Dict[str, Any]) -> Dict[str, Any]:
    buy_band = _safe_float(rsi.get("buyBand"), 34.0) or 34.0
    threshold = _safe_float(rsi.get("crossbackThreshold"), 0.8) or 0.0
    max_crossback = _safe_float(rsi.get("maxCrossbackRsi"), 100.0)
    if max_crossback is None:
        max_crossback = 100.0
    eligible_rows = [row for row in rows if _safe_float(row.get("rsiClosed1"), None) is not None and _safe_float(row.get("rsiClosed2"), None) is not None]
    rsi1_values = [_safe_float(row.get("rsiClosed1"), None) for row in eligible_rows]
    rsi2_values = [_safe_float(row.get("rsiClosed2"), None) for row in eligible_rows]
    rsi1_values = [value for value in rsi1_values if value is not None]
    rsi2_values = [value for value in rsi2_values if value is not None]
    distances = [value - buy_band for value in rsi1_values]
    current_at_or_below = 0
    previous_at_or_below = 0
    backtest_crossback = 0
    ea_adapter_signal = 0
    ea_direct_oversold_only = 0
    ledger_signal = 0
    mismatch = 0
    max_crossback_rejected = 0
    near_counts = {"within1": 0, "within3": 0, "within5": 0, "within10": 0}
    for row in eligible_rows:
        rsi1 = _safe_float(row.get("rsiClosed1"), None)
        rsi2 = _safe_float(row.get("rsiClosed2"), None)
        if rsi1 is None or rsi2 is None:
            continue
        direct_oversold = rsi1 <= buy_band
        backtest_cross = rsi2 <= buy_band and rsi1 >= buy_band + threshold
        capped_backtest_cross = backtest_cross and rsi1 <= max_crossback
        if backtest_cross and rsi1 > max_crossback:
            max_crossback_rejected += 1
        ea_signal = direct_oversold or (rsi2 < buy_band and rsi1 > buy_band + threshold)
        ledger = bool(row.get("rsiLongSignal"))
        current_at_or_below += int(direct_oversold)
        previous_at_or_below += int(rsi2 <= buy_band)
        backtest_crossback += int(capped_backtest_cross)
        ea_adapter_signal += int(ea_signal)
        ea_direct_oversold_only += int(direct_oversold and not capped_backtest_cross)
        ledger_signal += int(ledger)
        mismatch += int(ledger != ea_signal)
        distance = rsi1 - buy_band
        if 0 <= distance <= 1:
            near_counts["within1"] += 1
        if 0 <= distance <= 3:
            near_counts["within3"] += 1
        if 0 <= distance <= 5:
            near_counts["within5"] += 1
        if 0 <= distance <= 10:
            near_counts["within10"] += 1
    return {
        "rowCount": len(rows),
        "rsiValueRowCount": len(eligible_rows),
        "buyBand": buy_band,
        "crossbackThreshold": threshold,
        "maxCrossbackRsi": max_crossback,
        "rsiClosed1Distribution": _distribution(rsi1_values),
        "rsiClosed2Distribution": _distribution(rsi2_values),
        "rsiClosed1MinusBuyBandDistribution": _distribution(distances),
        "currentAtOrBelowBuyBandCount": current_at_or_below,
        "previousAtOrBelowBuyBandCount": previous_at_or_below,
        "backtestCrossbackCount": backtest_crossback,
        "maxCrossbackRejectedCount": max_crossback_rejected,
        "eaAdapterSignalRecomputedCount": ea_adapter_signal,
        "eaDirectOversoldOnlyCount": ea_direct_oversold_only,
        "ledgerRsiSignalCount": ledger_signal,
        "ledgerSignalMismatchCount": mismatch,
        "nearBuyBandCounts": near_counts,
        "reasonZh": _rsi_trigger_telemetry_reason(len(eligible_rows), current_at_or_below, backtest_crossback, distances),
    }


def _rsi_trigger_telemetry_reason(
    row_count: int, current_at_or_below_count: int, backtest_crossback_count: int, distances: List[float]
) -> str:
    if row_count <= 0:
        return "没有可用 RSI telemetry 样本。"
    if backtest_crossback_count > 0:
        return "当前 MT5 RSI telemetry 已出现按 backtest/replay 规则可触发的 crossback。"
    if current_at_or_below_count > 0:
        return "当前 MT5 RSI telemetry 有 RSI 低于 buyBand，但尚未形成 backtest/replay crossback。"
    min_distance = min(distances) if distances else None
    if min_distance is not None and min_distance > 5:
        return "当前 MT5 RSI telemetry 距 buyBand 仍较远，未触发更像行情状态而非点差掩盖。"
    return "当前 MT5 RSI telemetry 接近 buyBand，但尚未形成 crossback。"


def _rsi_trigger_adapter_coverage(
    contract_rsi: Dict[str, Any], strategy_json_rsi: Dict[str, Any], trigger_telemetry: Dict[str, Any]
) -> Dict[str, Any]:
    strategy_max_crossback = _safe_float(strategy_json_rsi.get("maxCrossbackRsi"), None)
    contract_max_crossback = _safe_float(contract_rsi.get("maxCrossbackRsi"), None)
    regime = strategy_json_rsi.get("regimeFilter") if isinstance(strategy_json_rsi.get("regimeFilter"), dict) else {}
    contract_regime = contract_rsi.get("regimeFilter") if isinstance(contract_rsi.get("regimeFilter"), dict) else {}
    strategy_has_non_default_max_crossback = strategy_max_crossback is not None and abs(strategy_max_crossback - 100.0) > 0.0001
    max_crossback_propagated = (not strategy_has_non_default_max_crossback) or _values_match(
        strategy_max_crossback, contract_max_crossback
    )
    regime_enabled = _rsi_regime_filter_enabled(regime)
    regime_propagated = (not regime_enabled) or bool(contract_regime)
    rule_gap = True
    material_gap = (not max_crossback_propagated) or (not regime_propagated) or bool(
        rule_gap
    )
    gaps: List[str] = []
    if rule_gap:
        gaps.append("EA adapter trigger rule 不是 backtest/replay 的 crossback-only 口径")
    if not max_crossback_propagated:
        gaps.append("maxCrossbackRsi 未进入 EA contract/ledger")
    if not regime_propagated:
        gaps.append("regimeFilter 未进入 EA contract/ledger")
    if trigger_telemetry.get("eaDirectOversoldOnlyCount", 0):
        gaps.append("EA adapter 的 direct oversold 分支会产生 backtest crossback 之外的信号")
    return {
        "backtestRule": "previous_rsi <= buyBand && current_rsi >= buyBand + crossbackThreshold && current_rsi <= maxCrossbackRsi，再经过 regime/adverse guard。",
        "eaAdapterRuleObserved": "rsiClosed1 <= buyBand OR (rsiClosed2 < buyBand && rsiClosed1 > buyBand + crossbackThreshold)，再经过 adverse range guard。",
        "ruleShapeGapKnown": rule_gap,
        "strategyJsonHasNonDefaultMaxCrossbackRsi": strategy_has_non_default_max_crossback,
        "maxCrossbackRsiPropagated": max_crossback_propagated,
        "strategyJsonRegimeFilterEnabled": regime_enabled,
        "regimeFilterPropagated": regime_propagated,
        "materialCoverageGap": material_gap,
        "gaps": gaps,
        "reasonZh": "；".join(gaps) if gaps else "当前样本未发现会改变本窗口结论的 adapter 覆盖缺口。",
    }


def _rsi_regime_filter_enabled(regime: Dict[str, Any]) -> bool:
    return bool(regime) and str(regime.get("mode") or "OFF").upper() not in {"", "OFF", "NONE"}


def _rsi_trigger_reference_alignment(
    runtime_dir: Path, active_snapshot: Dict[str, Any], lineage_file_state: Dict[str, Any]
) -> Dict[str, Any]:
    closure = _load_json(runtime_dir / "production_validation" / "QuantGod_RSILineageClosureReport.json")
    replay = _load_json(runtime_dir / "replay" / "usdjpy" / "QuantGod_USDJPYBarReplayReport.json")
    backtest = _load_json(runtime_dir / "backtest" / "QuantGod_StrategyBacktestReport.json")
    contract_replay = active_snapshot.get("replayAllPass")
    contract_production = active_snapshot.get("productionEvidenceAllPass")
    criteria = active_snapshot.get("criteria") if isinstance(active_snapshot.get("criteria"), dict) else {}
    closure_criteria = closure.get("criteria") if isinstance(closure.get("criteria"), dict) else {}
    replay_alignment = closure.get("replayAlignment") if isinstance(closure.get("replayAlignment"), dict) else {}
    return {
        "activeContractSnapshot": {
            "selectedSeedId": active_snapshot.get("selectedSeedId"),
            "selectedGeneration": active_snapshot.get("selectedGeneration"),
            "criteria": criteria,
            "replayAllPass": contract_replay,
            "productionEvidenceAllPass": contract_production,
        },
        "rollingLineageFile": lineage_file_state,
        "closureReport": {
            "present": bool(closure),
            "seedId": closure_criteria.get("seedId"),
            "closureStage": closure.get("closureStage"),
            "allPass": closure_criteria.get("allPass"),
            "replayAlignment": replay_alignment,
            "driftedFromActiveContract": bool(lineage_file_state.get("driftedFromActiveContract")),
        },
        "barReplayReport": {
            "present": bool(replay),
            "status": replay.get("status"),
            "sampleCount": ((replay.get("summary") or {}).get("sampleCount") if isinstance(replay.get("summary"), dict) else None),
            "currentEntryCount": (
                (replay.get("summary") or {}).get("currentEntryCount") if isinstance(replay.get("summary"), dict) else None
            ),
            "generatedAtIso": replay.get("generatedAtIso"),
        },
        "strategyBacktestReport": {
            "present": bool(backtest),
            "seedId": backtest.get("seedId"),
            "strategyId": backtest.get("strategyId"),
            "timeframe": backtest.get("timeframe"),
            "tradeCount": backtest.get("tradeCount"),
            "signalCount": ((backtest.get("engine") or {}).get("signalCount") if isinstance(backtest.get("engine"), dict) else None),
            "parityVectorRsi": (
                (((backtest.get("engine") or {}).get("parityVector") or {}).get("rsi") or {})
                if isinstance((backtest.get("engine") or {}).get("parityVector"), dict)
                else {}
            ),
        },
        "reasonZh": (
            "当前 runtime closure/lineage 文件已滚动到新 seed；P4-10L 仍以 EA contract frozen snapshot 为 active seed 证据源。"
            if lineage_file_state.get("driftedFromActiveContract")
            else "当前 lineage 文件与 EA contract active seed 一致。"
        ),
    }


def _rsi_legacy_diagnostics_summary(runtime_dir: Path, rsi_source: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = _load_json(runtime_dir / "QuantGod_USDJPYRsiEntryDiagnostics.json")
    inputs = diagnostics.get("inputs") if isinstance(diagnostics.get("inputs"), dict) else {}
    rsi = diagnostics.get("rsi") if isinstance(diagnostics.get("rsi"), dict) else {}
    if not diagnostics:
        return {"present": False, "reasonZh": "未找到 legacy RSI diagnostics；P4-10L 主要使用 Strategy JSON shadow ledger。"}
    comparisons = {
        "periodMatchesContract": _values_match(rsi.get("period") or inputs.get("PilotRsiPeriod"), rsi_source.get("period")),
        "timeframeMatchesContract": _values_match(
            rsi.get("timeframe") or inputs.get("PilotRsiTimeframe"), rsi_source.get("timeframe")
        ),
        "buyBandMatchesContract": _values_match(
            rsi.get("buyBandLevel") or rsi.get("oversold") or inputs.get("PilotRsiOversold"), rsi_source.get("buyBand")
        ),
        "crossbackMatchesContract": _values_match(
            rsi.get("crossbackThreshold") or inputs.get("PilotRsiCrossbackThreshold"),
            rsi_source.get("crossbackThreshold"),
        ),
    }
    return {
        "present": True,
        "state": diagnostics.get("state"),
        "generatedAtLocal": diagnostics.get("generatedAtLocal"),
        "generatedAtServer": diagnostics.get("generatedAtServer"),
        "diagnosticRoute": "LEGACY_PILOT_RSI",
        "contractRoute": "STRATEGY_JSON_EA_SHADOW_CONTRACT",
        "inputs": {
            "period": rsi.get("period") or inputs.get("PilotRsiPeriod"),
            "timeframe": rsi.get("timeframe") or inputs.get("PilotRsiTimeframe"),
            "buyBandLevel": rsi.get("buyBandLevel") or rsi.get("oversold") or inputs.get("PilotRsiOversold"),
            "crossbackThreshold": rsi.get("crossbackThreshold") or inputs.get("PilotRsiCrossbackThreshold"),
            "rsiClosed1": rsi.get("rsiClosed1"),
            "rsiClosed2": rsi.get("rsiClosed2"),
        },
        "matchesStrategyJsonContract": comparisons,
        "allMatch": all(comparisons.values()),
        "reasonZh": "legacy diagnostics 是 Pilot RSI 路线，不是 frozen Strategy JSON contract 的唯一证据源；若参数不同，不应直接用它否定 P4-10J/P4-10K。",
    }


def _rsi_trigger_alignment_status(blockers: List[Dict[str, Any]], telemetry: Dict[str, Any]) -> str:
    hard = {
        "NO_FROZEN_RSI_LINEAGE",
        "FROZEN_RSI_CONTRACT_NOT_ROTATED",
        "RSI_CONTRACT_LEDGER_PARAMETER_MISMATCH",
        "RSI_STRATEGY_JSON_CONTRACT_PARAMETER_MISMATCH",
        "RSI_TRIGGER_ADAPTER_COVERAGE_GAP",
        "RSI_TRIGGER_RECOMPUTE_MISMATCH",
    }
    if any(blocker.get("code") in hard for blocker in blockers):
        return "WARN"
    if telemetry.get("ledgerRsiSignalCount", 0) > 0 or telemetry.get("backtestCrossbackCount", 0) > 0:
        return "PASS"
    return "WATCH"


def _rsi_trigger_alignment_decision(
    parameter_parity: Dict[str, Any], telemetry: Dict[str, Any], adapter_coverage: Dict[str, Any]
) -> Dict[str, Any]:
    if not parameter_parity.get("contractToLedgerAllPass"):
        return {
            "label": "RSI_PARAMETER_PARITY_FAIL",
            "reasonZh": "EA ledger 里的 RSI period/timeframe/buyBand/crossback 与 active contract 不一致。",
        }
    if telemetry.get("ledgerSignalMismatchCount"):
        return {
            "label": "RSI_LEDGER_SIGNAL_RECOMPUTE_MISMATCH",
            "reasonZh": "按 RSI telemetry 重算的 EA trigger 与 ledger rsiLongSignal 不一致。",
        }
    if telemetry.get("ledgerRsiSignalCount", 0) > 0:
        return {"label": "RSI_SIGNAL_PRESENT", "reasonZh": "MT5 shadow ledger 已出现 RSI trigger。"}
    if telemetry.get("backtestCrossbackCount", 0) > 0:
        return {
            "label": "BACKTEST_RULE_SIGNAL_PRESENT_BUT_LEDGER_BLOCKED",
            "reasonZh": "按 backtest/replay crossback 规则已可触发，但 ledger 尚未出现 rsiLongSignal。",
        }
    distance = telemetry.get("rsiClosed1MinusBuyBandDistribution") if isinstance(telemetry.get("rsiClosed1MinusBuyBandDistribution"), dict) else {}
    min_distance = _safe_float(distance.get("min"), None)
    if min_distance is not None and min_distance > 5:
        label = "RSI_FAR_FROM_BUY_BAND"
        reason = "当前 MT5 H1 RSI 距 buyBand 至少超过 5 点，没触发主要是行情尚未到 frozen seed 的触发区。"
        if adapter_coverage.get("materialCoverageGap"):
            label = "RSI_FAR_FROM_BUY_BAND_WITH_ADAPTER_COVERAGE_GAP"
            reason += " 但 EA adapter 仍有 maxCrossback/regime/trigger-rule 覆盖缺口，晋级前应修。"
        return {"label": label, "reasonZh": reason}
    if telemetry.get("nearBuyBandCounts", {}).get("within5", 0) > 0:
        return {
            "label": "RSI_NEAR_BAND_NO_CROSSBACK",
            "reasonZh": "当前 RSI 已接近 buyBand，但尚未形成 backtest/replay crossback。",
        }
    return {"label": "RSI_TRIGGER_STILL_WAITING", "reasonZh": "当前样本未出现 RSI trigger，继续观察。"}


def _rsi_trigger_alignment_recommendations(
    status: str, decision: Dict[str, Any], blockers: List[Dict[str, Any]]
) -> List[str]:
    codes = {str(blocker.get("code") or "") for blocker in blockers}
    if "RSI_CONTRACT_LEDGER_PARAMETER_MISMATCH" in codes or "RSI_STRATEGY_JSON_CONTRACT_PARAMETER_MISMATCH" in codes:
        return ["先修 Strategy JSON → EA contract 参数 parity，再继续判断 frozen RSI 是否有效。"]
    if "RSI_TRIGGER_ADAPTER_COVERAGE_GAP" in codes:
        return [
            "进入下一步 parity fix：让 Strategy JSON EA adapter 覆盖 maxCrossbackRsi / regimeFilter，并把 RSI trigger 规则收敛到 backtest/replay 的 crossback-only 口径。",
            "在修复前继续观察可以证明行情是否到达 buyBand，但不能作为 shadow promotion 的完整 parity 证据。",
        ]
    label = str(decision.get("label") or "")
    if label == "RSI_FAR_FROM_BUY_BAND":
        return ["继续观察同一颗 seed；当前不是 trigger 参数过窄或点差掩盖，而是 H1 RSI 还没有接近 buyBand。"]
    if label == "RSI_NEAR_BAND_NO_CROSSBACK":
        return ["继续观察同一颗 seed，重点等 previous_rsi <= buyBand 且 current_rsi >= buyBand + crossbackThreshold。"]
    if status == "PASS":
        return ["保留 frozen seed，转回 P4-10K/P4-10J 观察 entry quality 与 adverse 样本。"]
    return [str(blocker.get("reasonZh") or blocker.get("code")) for blocker in blockers] or ["继续观察同一颗 frozen RSI seed。"]


def _entry_quality_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"status": "WATCH", "reasonZh": "等待 frozen RSI seed 的 EA shadow evaluation 样本。"}
    would_enter = [row for row in rows if bool(row.get("wouldEnter")) or row.get("status") == "SHADOW_WOULD_ENTER"]
    hard_pass = sum(1 for row in rows if bool(row.get("hardGuardsPass")))
    indicator_ready = sum(1 for row in rows if bool(row.get("indicatorReady")))
    guard_blocked = sum(1 for row in rows if str(row.get("status") or "") == "SHADOW_GUARD_BLOCKED")
    if any(str(row.get("status") or "") in {"SAFETY_REJECTED", "MODE_REJECTED", "SYMBOL_REJECTED"} for row in rows):
        status = "FAIL"
        reason = "EA shadow evaluation 拒绝了 contract 安全边界。"
    elif would_enter and all(bool(row.get("hardGuardsPass")) for row in would_enter):
        status = "PASS"
        reason = "frozen RSI seed 已在 EA shadow ledger 里复现 would-enter，且硬守门通过。"
    elif guard_blocked:
        status = "WATCH"
        reason = "EA 已读取 frozen RSI seed，但当前 tick/spread/session/news 守门阻断。"
    else:
        status = "WATCH"
        reason = "EA 已读取 frozen RSI seed，当前 RSI 入场条件尚未触发；继续观察。"
    return {
        "status": status,
        "rowCount": len(rows),
        "wouldEnterCount": len(would_enter),
        "hardGuardsPassCount": hard_pass,
        "indicatorReadyCount": indicator_ready,
        "guardBlockedCount": guard_blocked,
        "reasonZh": reason,
    }


def _adverse_quality_summary(rows: List[Dict[str, Any]], frozen: Dict[str, Any]) -> Dict[str, Any]:
    criteria = frozen.get("criteria") if isinstance(frozen.get("criteria"), dict) else {}
    baseline_max_adverse = _safe_float(criteria.get("maxAdverseR"), None)
    observed_values = [_adverse_value(row) for row in rows]
    observed_values = [value for value in observed_values if value is not None]
    guard_loaded_count = sum(1 for row in rows if _rsi_adverse_guard_loaded(row))
    if observed_values:
        worst = min(observed_values)
        status = "PASS" if worst >= -1.15 else "FAIL"
        reason = "EA shadow adverse 样本仍在 P4-10H/P4-10I 低回撤阈值内。" if status == "PASS" else "EA shadow adverse 样本重新劣化。"
    elif rows and guard_loaded_count:
        worst = None
        status = "WATCH"
        reason = "EA 已加载 RSI adverse guard；等待 post-entry adverse/MAE 样本。"
    elif rows:
        worst = None
        status = "WATCH"
        reason = "EA 已写入 frozen seed ledger，但当前 EA build 尚未输出 adverse guard 字段。"
    else:
        worst = None
        status = "WATCH"
        reason = "等待 frozen RSI seed 的 shadow ledger 后再判断 adverse excursion。"
    return {
        "status": status,
        "baselineMaxAdverseR": baseline_max_adverse,
        "observedAdverseSampleCount": len(observed_values),
        "worstObservedAdverseR": worst,
        "guardLoadedCount": guard_loaded_count,
        "reasonZh": reason,
    }


def _adverse_value(row: Dict[str, Any]) -> float | None:
    for key in ("maxAdverseR", "maeR", "adverseR", "earlyAdverseR", "rsiAdverseR"):
        value = _safe_float(row.get(key), None)
        if value is not None:
            return value
    return None


def _rsi_adverse_guard_loaded(row: Dict[str, Any]) -> bool:
    guard = row.get("rsiAdverseGuard") if isinstance(row.get("rsiAdverseGuard"), dict) else {}
    return bool(guard.get("mode") or row.get("rsiAdverseGuardMode"))


def _safe_float(value: Any, fallback: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _rsi_shadow_observation_recommendations(status: str, blockers: List[Dict[str, Any]]) -> List[str]:
    if status == "PASS":
        return ["继续让 EA shadow contract 收集 frozen RSI 入场/结果样本，暂不扩大 live scope。"]
    if blockers:
        return [str(blocker.get("reasonZh") or blocker.get("code")) for blocker in blockers]
    return ["继续观察 frozen RSI seed 的 EA shadow ledger。"]


def read_strategy_contract_status(runtime_dir: Path) -> Dict[str, Any]:
    status = _load_json(runtime_dir / CONTRACT_STATUS_FILE) or _load_json(contract_dir(runtime_dir) / CONTRACT_STATUS_FILE)
    contract = _load_json(runtime_dir / CONTRACT_JSON_FILE) or _load_json(contract_dir(runtime_dir) / CONTRACT_JSON_FILE)
    ea_status = _read_ea_status(runtime_dir)
    shadow_evaluation = _read_shadow_evaluation_status(runtime_dir)
    shadow_evaluation_recent = _read_shadow_evaluation_ledger(runtime_dir, limit=20)
    if not status:
        return {
            "ok": True,
            "schema": "quantgod.strategy_json_ea_contract_status.v1",
            "agentVersion": AGENT_VERSION,
            "updatedAt": utc_now_iso(),
            "status": "WAITING_CONTRACT_BUILD",
            "contract": contract,
            "eaStatus": ea_status,
            "eaShadowEvaluation": shadow_evaluation,
            "eaShadowEvaluationRecent": shadow_evaluation_recent,
            "reasonZh": "等待 Agent 生成 Strategy JSON → EA 只读评估契约。",
            "safety": dict(SAFETY_BOUNDARY),
        }
    status = dict(status)
    status["contract"] = status.get("contract") or contract
    status["eaStatus"] = ea_status
    status["eaShadowEvaluation"] = shadow_evaluation
    status["eaShadowEvaluationRecent"] = shadow_evaluation_recent
    status["safety"] = dict(SAFETY_BOUNDARY)
    if ea_status:
        status["eaAck"] = {
            "status": ea_status.get("status"),
            "loaded": ea_status.get("loaded"),
            "selectedSeedId": ea_status.get("selectedSeedId"),
            "fingerprint": ea_status.get("fingerprint"),
            "reasonZh": ea_status.get("reasonZh"),
        }
    return status
