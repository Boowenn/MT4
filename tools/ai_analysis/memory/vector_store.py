"""A tiny local vector-like store for AI Analysis V2.

This avoids server dependencies. It stores only analysis summaries and outcomes;
no account credentials, API keys, or broker secrets are persisted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import re
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def tokenize(value: str) -> Counter:
    words = re.findall(r"[A-Za-z0-9_]+", str(value or "").lower())
    return Counter(word for word in words if len(word) > 2)


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class MemoryCase:
    id: str
    symbol: str
    text: str
    tags: list[str]
    report: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "text": self.text[:4000],
            "tags": self.tags[:32],
            "report": self.report,
            "created_at": self.created_at,
        }


class LocalVectorMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_cases(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def store_case(self, *, symbol: str, report: dict[str, Any], tags: list[str] | None = None) -> dict[str, Any]:
        decision = report.get("decision") or report.get("decision_v2") or {}
        text_parts = [
            symbol,
            str(decision.get("action") or ""),
            str(decision.get("reasoning") or ""),
            json.dumps(report.get("technical") or {}, ensure_ascii=False)[:1200],
            json.dumps(report.get("risk") or {}, ensure_ascii=False)[:1200],
            json.dumps(report.get("news") or {}, ensure_ascii=False)[:800],
            json.dumps(report.get("sentiment") or {}, ensure_ascii=False)[:800],
        ]
        text = "\n".join(text_parts)
        case_id = f"case-{abs(hash((symbol, text[:500], utc_now()))):x}"
        case = MemoryCase(case_id, symbol, text, tags or [], {"summary": decision, "schema": report.get("schema")}, utc_now())
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
        return case.to_dict()

    def query(self, *, symbol: str, conditions: list[str] | None = None, text: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
        query_text = " ".join([symbol, *(conditions or []), text or ""])
        q = tokenize(query_text)
        scored = []
        for case in self._read_cases():
            if symbol and case.get("symbol") and str(case.get("symbol")).lower() != symbol.lower():
                # Still allow cross-symbol recall if exact symbol has no match by assigning low score.
                penalty = 0.2
            else:
                penalty = 1.0
            score = cosine(q, tokenize(case.get("text") or "")) * penalty
            if score > 0:
                scored.append({**case, "similarity": round(score, 4)})
        scored.sort(key=lambda row: row.get("similarity", 0), reverse=True)
        return scored[: max(1, min(top_k, 10))]

    def status(self) -> dict[str, Any]:
        cases = self._read_cases()
        return {
            "ok": True,
            "schema": "quantgod.ai_memory.v1",
            "path": str(self.path),
            "case_count": len(cases),
            "safety": {
                "storesAccountInfo": False,
                "storesApiKeys": False,
                "storesAnalysisReportsOnly": True,
                "orderSendAllowed": False,
            },
        }
