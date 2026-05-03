"""QuantGod AI Analysis V2 orchestration: evidence → debate → decision + memory."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from typing import Any

from .agents.bear_agent import BearAgent
from .agents.bull_agent import BullAgent
from .agents.news_agent import NewsAgent
from .agents.sentiment_agent import SentimentAgent
from .decision_agent_v2 import DecisionAgentV2
from .memory.vector_store import LocalVectorMemory

try:  # Keep compatibility with Phase 1 modules when present.
    from .agents.technical_agent import TechnicalAgent  # type: ignore
except Exception:  # pragma: no cover - fallback for isolated tests.
    TechnicalAgent = None
try:
    from .agents.risk_agent import RiskAgent  # type: ignore
except Exception:  # pragma: no cover
    RiskAgent = None
try:
    from .market_data_collector import MarketDataCollector  # type: ignore
except Exception:  # pragma: no cover
    MarketDataCollector = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase3_ai_safety() -> dict[str, Any]:
    return {
        "mode": "QUANTGOD_AI_ANALYSIS_V2",
        "localOnly": True,
        "advisoryOnly": True,
        "orderSendAllowed": False,
        "closeAllowed": False,
        "cancelAllowed": False,
        "credentialStorageAllowed": False,
        "livePresetMutationAllowed": False,
        "canOverrideKillSwitch": False,
        "canMutateGovernanceDecision": False,
        "canPromoteOrDemoteRoute": False,
        "debateCanTriggerTrade": False,
        "ragStoresAccountInfo": False,
        "ragStoresApiKeys": False,
    }


class FallbackTechnicalAgent:
    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": "technical",
            "timestamp": utc_now(),
            "trend": {"m15": "neutral", "h1": "neutral", "h4": "neutral", "d1": "neutral", "consensus": "neutral"},
            "indicators": {},
            "key_levels": {"resistance": [], "support": []},
            "signal_strength": 0.25,
            "direction": "neutral",
            "reasoning": "Fallback technical report because Phase 1 TechnicalAgent was not available.",
            "cost_usd": 0.0,
        }


class FallbackRiskAgent:
    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": "risk",
            "timestamp": utc_now(),
            "risk_score": 0.5,
            "risk_level": "medium",
            "factors": [],
            "kill_switch_active": False,
            "position_exposure": "unknown",
            "tradeable": True,
            "reasoning": "Fallback risk report because Phase 1 RiskAgent was not available.",
            "cost_usd": 0.0,
        }


class AnalysisServiceV2:
    def __init__(self, runtime_dir: str | Path | None = None):
        self.runtime_dir = Path(runtime_dir or os.environ.get("QG_RUNTIME_DIR") or Path.cwd() / "runtime" / "ai_analysis").resolve()
        self.history_dir = Path(os.environ.get("AI_ANALYSIS_HISTORY_DIR") or self.runtime_dir / "ai_analysis").resolve()
        self.history_dir.mkdir(parents=True, exist_ok=True)
        (self.history_dir / "history").mkdir(parents=True, exist_ok=True)
        self.memory = LocalVectorMemory(self.history_dir / "memory" / "vector_cases.jsonl")
        self.technical_agent = self._init_agent(TechnicalAgent, FallbackTechnicalAgent())
        self.risk_agent = self._init_agent(RiskAgent, FallbackRiskAgent())
        self.news_agent = NewsAgent()
        self.sentiment_agent = SentimentAgent()
        self.bull_agent = BullAgent()
        self.bear_agent = BearAgent()
        self.decision_agent = DecisionAgentV2()

    def _init_agent(self, cls, fallback):
        if cls is None:
            return fallback
        try:
            return cls()
        except Exception:
            return fallback

    async def collect_snapshot(self, symbol: str, timeframes: list[str] | None = None) -> dict[str, Any]:
        if MarketDataCollector is not None:
            try:
                collector = MarketDataCollector(runtime_dir=self.runtime_dir)
                if hasattr(collector, "collect"):
                    result = collector.collect(symbol, timeframes or ["M15", "H1", "H4", "D1"])
                    if asyncio.iscoroutine(result):
                        result = await result
                    if isinstance(result, dict):
                        return result
            except Exception:
                pass
        return {
            "symbol": symbol,
            "timeframes": timeframes or ["M15", "H1", "H4", "D1"],
            "current_price": None,
            "news": {"events": [], "active": False},
            "sentiment": {"score": 0.0},
            "source": "phase3_v2_fallback_snapshot",
        }

    async def run_analysis(self, symbol: str, timeframes: list[str] | None = None) -> dict[str, Any]:
        snapshot = await self.collect_snapshot(symbol, timeframes)
        similar_cases = self.memory.query(symbol=symbol, conditions=["ai_v2", "debate"], text=json.dumps(snapshot, ensure_ascii=False)[:1000], top_k=3)
        snapshot["similar_cases"] = similar_cases

        technical, risk, news, sentiment = await asyncio.gather(
            self.technical_agent.analyze(snapshot),
            self.risk_agent.analyze(snapshot),
            self.news_agent.analyze(snapshot),
            self.sentiment_agent.analyze(snapshot),
        )
        evidence = {"technical": technical, "risk": risk, "news": news, "sentiment": sentiment, "snapshot": snapshot}
        bull_case, bear_case = await asyncio.gather(self.bull_agent.argue(evidence), self.bear_agent.argue(evidence))
        decision = await self.decision_agent.analyze({**evidence, "bull_case": bull_case, "bear_case": bear_case})
        report = {
            "ok": True,
            "schema": "quantgod.ai_analysis.v2",
            "generatedAt": utc_now(),
            "symbol": symbol,
            "timeframes": timeframes or ["M15", "H1", "H4", "D1"],
            "snapshot": snapshot,
            "technical": technical,
            "risk": risk,
            "news": news,
            "sentiment": sentiment,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "decision": decision,
            "memory": {"similar_cases": similar_cases, "status": self.memory.status()},
            "safety": phase3_ai_safety(),
        }
        self.save_report(report)
        self.feed_governance(report)
        self.memory.store_case(symbol=symbol, report=report, tags=["ai_v2", decision.get("action", "HOLD")])
        return report

    def save_report(self, report: dict[str, Any]) -> None:
        latest = self.history_dir / "latest_v2.json"
        latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        ts = str(report.get("generatedAt", utc_now())).replace(":", "").replace("-", "")
        symbol = str(report.get("symbol", "symbol")).replace("/", "_")
        history_path = self.history_dir / "history" / f"{ts}_{symbol}_v2.json"
        history_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def feed_governance(self, report: dict[str, Any]) -> None:
        evidence = {
            "schema": "quantgod.ai_governance_evidence.v2",
            "generatedAt": utc_now(),
            "symbol": report.get("symbol"),
            "decision": report.get("decision"),
            "bull_case": report.get("bull_case"),
            "bear_case": report.get("bear_case"),
            "memory": report.get("memory"),
            "safety": phase3_ai_safety(),
        }
        target = self.runtime_dir / "QuantGod_AIAnalysisEvidenceV2.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    def latest(self, allow_empty: bool = False) -> dict[str, Any]:
        path = self.history_dir / "latest_v2.json"
        if not path.exists():
            return {"ok": False, "error": "latest_v2_not_found", "safety": phase3_ai_safety()} if allow_empty else {}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def history(self, symbol: str | None = None, limit: int = 20) -> dict[str, Any]:
        rows = []
        for path in sorted((self.history_dir / "history").glob("*_v2.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if symbol and str(data.get("symbol", "")).lower() != symbol.lower():
                continue
            rows.append({"id": path.name, "path": str(path), "symbol": data.get("symbol"), "generatedAt": data.get("generatedAt"), "decision": data.get("decision", {})})
            if len(rows) >= limit:
                break
        return {"ok": True, "schema": "quantgod.ai_analysis.history.v2", "items": rows, "safety": phase3_ai_safety()}

    def history_item(self, item_id: str) -> dict[str, Any]:
        safe_name = Path(item_id).name
        path = self.history_dir / "history" / safe_name
        if not path.exists():
            return {"ok": False, "error": "history_item_not_found", "id": safe_name, "safety": phase3_ai_safety()}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def config(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": "quantgod.ai_analysis.config.v2",
            "agents": ["technical", "risk", "news", "sentiment", "bull", "bear", "decision_v2"],
            "orchestration": ["evidence_collection", "bull_bear_debate", "decision_v2", "rag_memory_store"],
            "history_dir": str(self.history_dir),
            "memory": self.memory.status(),
            "safety": phase3_ai_safety(),
        }
