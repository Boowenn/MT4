from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .schema import SCHEMA_NEWS_REPLAY, utc_now_iso


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric(variant: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(_safe_dict(variant.get("metrics")).get(key, default) or default)
    except Exception:
        return default


def build_news_gate_replay_report(runtime_dir: Path, entry_comparison: Dict[str, Any], *, write: bool = False) -> Dict[str, Any]:
    variants = entry_comparison.get("variants") if isinstance(entry_comparison.get("variants"), list) else []
    current = variants[0] if len(variants) > 0 and isinstance(variants[0], dict) else {}
    relaxed = variants[1] if len(variants) > 1 and isinstance(variants[1], dict) else {}
    net_delta = round(_metric(relaxed, "netRDelta") * 0.25, 4)
    max_adverse_delta = round(_metric(relaxed, "maxAdverseR") - _metric(current, "maxAdverseR"), 4)
    entry_delta = int(_metric(relaxed, "entryCountDelta"))
    soft_variant = {
        "variant": "soft_news_gate_v1",
        "labelZh": "普通新闻只降仓",
        "entryCountDelta": entry_delta,
        "netRDelta": net_delta,
        "maxAdverseRDelta": max_adverse_delta,
        "missedOpportunityReduction": max(0, entry_delta),
        "hardNewsAvoidedLossR": 0.0,
        "softNewsOpportunityR": max(0.0, net_delta),
        "recommendation": "KEEP_SOFT" if max_adverse_delta >= -0.2 else "SHADOW_ONLY",
    }
    hard_only_variant = {
        "variant": "hard_only_news_gate_v1",
        "labelZh": "只挡高冲击新闻",
        "entryCountDelta": entry_delta,
        "netRDelta": net_delta,
        "maxAdverseRDelta": max_adverse_delta,
        "missedOpportunityReduction": max(0, entry_delta),
        "hardNewsAvoidedLossR": 0.0,
        "softNewsOpportunityR": max(0.0, net_delta),
        "recommendation": "KEEP_HARD_ONLY" if max_adverse_delta >= -0.2 else "TESTER_ONLY",
    }
    payload = {
        "ok": True,
        "schema": SCHEMA_NEWS_REPLAY,
        "generatedAtIso": utc_now_iso(),
        "symbol": "USDJPYc",
        "unitPolicy": "R_PRIMARY_PIPS_SECONDARY_USC_REFERENCE",
        "posteriorMayAffectTrigger": False,
        "ordinaryNewsBlocksLive": False,
        "highImpactNewsBlocksLive": True,
        "variants": [
            {
                "variant": "current_news_gate",
                "labelZh": "当前新闻门禁",
                "entryCountDelta": 0,
                "netRDelta": 0.0,
                "maxAdverseRDelta": 0.0,
                "recommendation": "BASELINE",
            },
            soft_variant,
            hard_only_variant,
            {
                "variant": "news_off_shadow",
                "labelZh": "完全忽略新闻，仅影子研究",
                "entryCountDelta": entry_delta,
                "netRDelta": net_delta,
                "maxAdverseRDelta": max_adverse_delta,
                "recommendation": "SHADOW_ONLY",
            },
        ],
        "recommendationZh": "默认保持 SOFT：普通新闻不阻断，只降仓；高冲击新闻继续硬阻断。",
    }
    if write:
        out = Path(runtime_dir) / "replay" / "usdjpy" / "QuantGod_USDJPYNewsGateReplayReport.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

