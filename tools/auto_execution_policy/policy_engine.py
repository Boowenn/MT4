from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from .data_loader import EvidenceLoader, write_csv_rows, write_json
from .exit_tuner import tune_exit
from .lot_sizer import LotSizingConfig, size_lot
from .schema import AutoPolicyRow, build_policy_document, normalize_direction, validate_safe_payload
from .strictness_tuner import tune_entry_strictness


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def load_lot_config() -> LotSizingConfig:
    return LotSizingConfig(
        max_lot=_env_float("QG_AUTO_MAX_LOT", 2.0),
        risk_per_trade_pct=_env_float("QG_AUTO_RISK_PER_TRADE_PCT", 0.5),
        opportunity_multiplier=_env_float("QG_AUTO_OPPORTUNITY_LOT_MULTIPLIER", 0.35),
        standard_multiplier=_env_float("QG_AUTO_STANDARD_LOT_MULTIPLIER", 1.0),
        minimum_lot=_env_float("QG_AUTO_MIN_LOT", 0.01),
        lot_step=_env_float("QG_AUTO_LOT_STEP", 0.01),
        account_equity=_env_float("QG_AUTO_ACCOUNT_EQUITY", 1000.0),
    )


class AutoExecutionPolicyEngine:
    def __init__(self, runtime_dir: str | Path, max_age_seconds: int = 180):
        self.runtime_dir = Path(runtime_dir)
        self.loader = EvidenceLoader(self.runtime_dir, max_age_seconds=max_age_seconds)
        self.max_age_seconds = max_age_seconds

    def build_row(self, symbol: str, direction: str, strategy: str = "AUTO_POLICY", regime: str = "UNKNOWN") -> AutoPolicyRow:
        direction = normalize_direction(direction)
        runtime = self.loader.snapshot_for(symbol)
        fastlane = self.loader.fastlane_quality(symbol)
        gate = self.loader.entry_gate(symbol, direction)
        sltp = self.loader.sltp_plan(symbol, direction)
        shadow = self.loader.shadow_stats(symbol, direction)
        decision = tune_entry_strictness(runtime, fastlane, gate, sltp, shadow)
        exit_tuning = tune_exit(decision.entry_mode, sltp, shadow)
        lot_config = load_lot_config()
        lot = size_lot(decision.entry_mode, decision.score, lot_config)
        allowed = lot > 0 and decision.entry_mode != "BLOCKED"
        if decision.entry_mode == "OPPORTUNITY_ENTRY" and lot > lot_config.max_lot * lot_config.opportunity_multiplier:
            lot = round(lot_config.max_lot * lot_config.opportunity_multiplier, 2)
        row = AutoPolicyRow(
            symbol=symbol,
            direction=direction,
            strategy=strategy,
            regime=regime,
            entryMode=decision.entry_mode,
            allowed=allowed,
            score=round(decision.score, 2),
            maxLot=lot_config.max_lot,
            recommendedLot=lot,
            riskPerTradePct=lot_config.risk_per_trade_pct,
            entryStrictness=decision.strictness,
            exitMode=exit_tuning.exit_mode,
            breakevenDelayR=exit_tuning.breakeven_delay_r,
            trailStartR=exit_tuning.trail_start_r,
            timeStopBars=exit_tuning.time_stop_bars,
            initialStopReference=sltp.initial_stop,
            targetReference=sltp.targets,
            reason=f"{decision.reason}；{exit_tuning.reason}",
            blockers=decision.blockers,
            warnings=decision.warnings,
        )
        return row

    def build(self, symbols: List[str], directions: List[str] | None = None, write: bool = False) -> Dict:
        directions = directions or ["LONG", "SHORT"]
        rows: List[AutoPolicyRow] = []
        for symbol in symbols:
            clean_symbol = symbol.strip()
            if not clean_symbol:
                continue
            for direction in directions:
                rows.append(self.build_row(clean_symbol, direction))
        document = build_policy_document(rows, str(self.runtime_dir))
        validate_safe_payload(document)
        if write:
            self.write_outputs(document)
        return document

    def write_outputs(self, document: Dict) -> None:
        target = self.runtime_dir / "adaptive" / "QuantGod_AutoExecutionPolicy.json"
        write_json(target, document)
        ledger_rows: List[Dict] = []
        for row in document.get("policies", []):
            ledger_rows.append({
                "generatedAt": document.get("generatedAt"),
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "entryMode": row.get("entryMode"),
                "allowed": row.get("allowed"),
                "score": row.get("score"),
                "recommendedLot": row.get("recommendedLot"),
                "maxLot": row.get("maxLot"),
                "entryStrictness": row.get("entryStrictness"),
                "exitMode": row.get("exitMode"),
                "reason": row.get("reason"),
            })
        write_csv_rows(self.runtime_dir / "adaptive" / "QuantGod_AutoExecutionPolicyLedger.csv", ledger_rows)
