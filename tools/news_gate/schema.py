from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

NEWS_GATE_OFF = "OFF"
NEWS_GATE_SOFT = "SOFT"
NEWS_GATE_HARD_ONLY = "HARD_ONLY"
NEWS_GATE_HARD = "HARD"

NEWS_RISK_NONE = "NONE"
NEWS_RISK_SOFT = "SOFT"
NEWS_RISK_HARD = "HARD"
NEWS_RISK_UNKNOWN = "UNKNOWN"

ENTRY_STANDARD = "STANDARD_ENTRY"
ENTRY_OPPORTUNITY = "OPPORTUNITY_ENTRY"
ENTRY_BLOCKED = "BLOCKED"

SCHEMA_NEWS_GATE = "quantgod.news_gate.v2_5_1"
SCHEMA_NEWS_REPLAY = "quantgod.usdjpy_news_gate_replay.v2_5_1"

HIGH_IMPACT_KEYWORDS = (
    "BOJ",
    "BANK OF JAPAN",
    "FOMC",
    "FED",
    "FEDERAL RESERVE",
    "CPI",
    "NFP",
    "NONFARM",
    "PAYROLL",
    "PCE",
    "RATE DECISION",
    "INTEREST RATE",
    "POWELL",
    "UEDA",
    "INFLATION",
)

SOFT_RISK_KEYWORDS = (
    "NEWS",
    "MEDIUM",
    "LOW",
    "SPEECH",
    "RETAIL",
    "PMI",
    "GDP",
    "CLAIMS",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class NewsGateDecision:
    mode: str
    riskLevel: str
    hardBlock: bool
    lotMultiplier: float
    stageDowngrade: bool
    reasonZh: str
    highImpactEvent: Optional[Dict[str, Any]] = None
    sourceAvailable: bool = True
    blockedBySource: bool = False
    wouldHaveBlockedBeforeV251: bool = False
    generatedAtIso: str = ""
    schema: str = SCHEMA_NEWS_GATE

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["generatedAtIso"] = payload["generatedAtIso"] or utc_now_iso()
        return payload

