from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import DecisionAgent, RiskAgent, TechnicalAgent
from .agents.base_agent import utc_now_iso
from .config import AIAnalysisConfig, load_config
from .llm_client import LLMClient
from .market_data_collector import MarketDataCollector, READ_ONLY_SAFETY

EVIDENCE_FILE_NAME = "QuantGod_AIAnalysisEvidence.json"
LATEST_FILE_NAME = "latest.json"
HISTORY_DIR_NAME = "history"


class AnalysisService:
    """Orchestrates QuantGod's advisory 3-Agent analysis pipeline."""

    def __init__(
        self,
        config: AIAnalysisConfig | None = None,
        collector: MarketDataCollector | None = None,
        llm: LLMClient | None = None,
        technical_agent: TechnicalAgent | None = None,
        risk_agent: RiskAgent | None = None,
        decision_agent: DecisionAgent | None = None,
    ) -> None:
        self.config = config or load_config()
        self.collector = collector or MarketDataCollector(self.config)
        shared_llm = llm or LLMClient(
            api_key=self.config.openrouter_api_key,
            default_model=self.config.model_decision,
            timeout=self.config.request_timeout,
            max_retries=self.config.max_retries,
            base_url=self.config.openrouter_base_url,
        )
        self.technical_agent = technical_agent or TechnicalAgent(shared_llm, model=self.config.model_technical)
        self.risk_agent = risk_agent or RiskAgent(shared_llm, model=self.config.model_risk)
        self.decision_agent = decision_agent or DecisionAgent(shared_llm, model=self.config.model_decision)

    async def run_analysis(self, symbol: str, timeframes: list[str] | None = None) -> dict[str, Any]:
        clean_symbol = (symbol or "").strip()
        if not clean_symbol:
            raise ValueError("symbol is required")

        snapshot = await self.collector.collect(clean_symbol, timeframes)
        technical, risk = await asyncio.gather(
            self.technical_agent.analyze(snapshot),
            self.risk_agent.analyze(snapshot),
        )
        decision = await self.decision_agent.analyze(
            {"technical": technical, "risk": risk, "snapshot": snapshot}
        )
        report = self._full_report(clean_symbol, snapshot, technical, risk, decision)
        self.save_report(report)
        self.feed_governance(report)
        return report

    def _full_report(
        self,
        symbol: str,
        snapshot: dict[str, Any],
        technical: dict[str, Any],
        risk: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mode": "QUANTGOD_AI_ANALYSIS_FULL_REPORT_V1",
            "id": _report_id(symbol),
            "symbol": symbol,
            "generatedAtIso": utc_now_iso(),
            "safety": {
                **READ_ONLY_SAFETY,
                "advisoryOnly": True,
                "canExecuteTrade": False,
                "canOverrideKillSwitch": False,
                "canMutateGovernanceDecision": False,
            },
            "models": {
                "technical": technical.get("model", self.config.model_technical),
                "risk": risk.get("model", self.config.model_risk),
                "decision": decision.get("model", self.config.model_decision),
            },
            "snapshot": snapshot,
            "technical": technical,
            "risk": risk,
            "decision": decision,
            "total_cost_usd": round(
                float(technical.get("cost_usd", 0.0) or 0.0)
                + float(risk.get("cost_usd", 0.0) or 0.0)
                + float(decision.get("total_cost_usd", decision.get("cost_usd", 0.0)) or 0.0),
                6,
            ),
        }

    def save_report(self, report: dict[str, Any]) -> dict[str, str]:
        history_dir = self.config.safe_history_dir
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / HISTORY_DIR_NAME).mkdir(parents=True, exist_ok=True)
        latest_path = history_dir / LATEST_FILE_NAME
        history_path = history_dir / HISTORY_DIR_NAME / f"{report['id']}.json"
        _write_json(latest_path, report)
        _write_json(history_path, report)
        return {"latest": str(latest_path), "history": str(history_path)}

    def feed_governance(self, report: dict[str, Any]) -> Path:
        runtime_dir = self.config.safe_runtime_dir
        runtime_dir.mkdir(parents=True, exist_ok=True)
        decision = report.get("decision") or {}
        technical = report.get("technical") or {}
        risk = report.get("risk") or {}
        evidence = {
            "mode": "QUANTGOD_AI_ANALYSIS_EVIDENCE_V1",
            "generatedAtIso": utc_now_iso(),
            "sourceReportId": report.get("id"),
            "symbol": report.get("symbol"),
            "advisoryOnly": True,
            "safety": {
                **READ_ONLY_SAFETY,
                "canExecuteTrade": False,
                "canOverrideKillSwitch": False,
                "canMutateLivePreset": False,
                "canPromoteOrDemoteRoute": False,
            },
            "decision": {
                "action": decision.get("action"),
                "confidence": decision.get("confidence"),
                "entry_price": decision.get("entry_price"),
                "stop_loss": decision.get("stop_loss"),
                "take_profit": decision.get("take_profit"),
                "risk_reward_ratio": decision.get("risk_reward_ratio"),
                "reasoning": decision.get("reasoning"),
                "key_factors": decision.get("key_factors", []),
                "governance_evidence": decision.get("governance_evidence", {}),
            },
            "technicalSummary": {
                "direction": technical.get("direction"),
                "signal_strength": technical.get("signal_strength"),
                "trend": technical.get("trend"),
                "key_levels": technical.get("key_levels"),
            },
            "riskSummary": {
                "risk_score": risk.get("risk_score"),
                "risk_level": risk.get("risk_level"),
                "kill_switch_active": risk.get("kill_switch_active"),
                "tradeable": risk.get("tradeable"),
                "factors": risk.get("factors", []),
            },
            "total_cost_usd": report.get("total_cost_usd", decision.get("total_cost_usd", 0.0)),
        }
        target = runtime_dir / EVIDENCE_FILE_NAME
        _write_json(target, evidence)
        return target

    def latest(self) -> dict[str, Any] | None:
        return _read_json(self.config.safe_history_dir / LATEST_FILE_NAME)

    def history(self, symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        history_root = self.config.safe_history_dir / HISTORY_DIR_NAME
        if not history_root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(history_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            payload = _read_json(path)
            if not isinstance(payload, dict):
                continue
            if symbol and str(payload.get("symbol", "")).upper() != symbol.upper():
                continue
            rows.append(
                {
                    "id": payload.get("id") or path.stem,
                    "symbol": payload.get("symbol"),
                    "generatedAtIso": payload.get("generatedAtIso"),
                    "action": (payload.get("decision") or {}).get("action"),
                    "confidence": (payload.get("decision") or {}).get("confidence"),
                    "risk_level": (payload.get("risk") or {}).get("risk_level"),
                    "path": str(path),
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def history_item(self, report_id: str) -> dict[str, Any] | None:
        clean = _safe_report_id(report_id)
        if not clean:
            return None
        return _read_json(self.config.safe_history_dir / HISTORY_DIR_NAME / f"{clean}.json")

    def config_status(self) -> dict[str, Any]:
        return {
            "mode": "QUANTGOD_AI_ANALYSIS_CONFIG_V1",
            "generatedAtIso": utc_now_iso(),
            "configured": bool(self.config.openrouter_api_key) or self.config.mock_mode,
            "mockMode": self.config.mock_mode,
            "models": {
                "technical": self.config.model_technical,
                "risk": self.config.model_risk,
                "decision": self.config.model_decision,
            },
            "runtimeDir": str(self.config.safe_runtime_dir),
            "historyDir": str(self.config.safe_history_dir),
            "safety": {
                **READ_ONLY_SAFETY,
                "advisoryOnly": True,
                "canExecuteTrade": False,
                "canMutateLivePreset": False,
            },
        }


def _report_id(symbol: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    clean_symbol = re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol).strip("_") or "UNKNOWN"
    return f"{stamp}_{clean_symbol}"


def _safe_report_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "", value or "")[:160]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
