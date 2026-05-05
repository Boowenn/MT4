from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .data_loader import EntryGateEvidence, FastLaneQuality, RuntimeEvidence, ShadowStats, DynamicSLTPPlan
from .schema import ENTRY_BLOCKED, ENTRY_OPPORTUNITY, ENTRY_STANDARD

TACTICAL_KEYWORDS = ["二次确认", "回踩", "bar close", "BAR_CLOSE", "M1", "M5", "点位确认", "等待确认"]
CORE_BLOCK_KEYWORDS = ["陈旧", "fallback", "回退", "快通道", "点差", "spread", "ATR", "ADX", "BBWidth", "暂停", "PAUSED", "负期望", "缺少", "MISSING"]


@dataclass
class StrictnessDecision:
    entry_mode: str
    score: float
    strictness: str
    reason: str
    blockers: List[str]
    warnings: List[str]


def _looks_tactical(reason: str) -> bool:
    return any(keyword.lower() in reason.lower() for keyword in TACTICAL_KEYWORDS)


def _looks_core_block(reason: str) -> bool:
    return any(keyword.lower() in reason.lower() for keyword in CORE_BLOCK_KEYWORDS)


def tune_entry_strictness(
    runtime: RuntimeEvidence,
    fastlane: FastLaneQuality,
    entry_gate: EntryGateEvidence,
    sltp: DynamicSLTPPlan,
    shadow: ShadowStats,
    min_samples: int = 5,
) -> StrictnessDecision:
    blockers: List[str] = []
    warnings: List[str] = []
    score = 0.0

    if not runtime.snapshot:
        blockers.append("缺少运行快照")
    elif not runtime.runtime_fresh:
        blockers.append("运行快照不新鲜")
    else:
        score += 25

    if runtime.fallback:
        blockers.append("运行快照为回退数据")

    if not fastlane.ok:
        blockers.append(fastlane.reason or "快通道质量未通过")
    else:
        score += 20

    if not sltp.available:
        blockers.append("缺少动态止盈止损计划")
    else:
        score += 15

    if shadow.samples >= min_samples:
        if shadow.avg_r < -0.05 or shadow.win_rate < 0.38:
            blockers.append(f"影子样本表现为负：样本={shadow.samples}，胜率={shadow.win_rate:.1%}，平均R={shadow.avg_r:.2f}")
        else:
            score += 15
    else:
        warnings.append(f"影子样本不足：{shadow.samples}/{min_samples}")
        score += 5

    if blockers:
        return StrictnessDecision(
            entry_mode=ENTRY_BLOCKED,
            score=min(score, 49.0),
            strictness="CORE_BLOCKED",
            reason="核心安全证据未通过，阻断自动入场",
            blockers=blockers,
            warnings=warnings,
        )

    if entry_gate.passed:
        score += 25
        return StrictnessDecision(
            entry_mode=ENTRY_STANDARD if score >= 85 else ENTRY_OPPORTUNITY,
            score=min(100.0, score),
            strictness="STANDARD_ALL_CONFIRMED" if score >= 85 else "OPPORTUNITY_SCORE_MEDIUM",
            reason="核心安全与入场闸门均通过" if score >= 85 else "核心安全通过，但综合分不足标准入场，仅允许机会入场",
            blockers=[],
            warnings=warnings,
        )

    reason = entry_gate.reason or entry_gate.status
    if _looks_core_block(reason) and not _looks_tactical(reason):
        return StrictnessDecision(
            entry_mode=ENTRY_BLOCKED,
            score=min(score, 64.0),
            strictness="ENTRY_GATE_CORE_BLOCK",
            reason="自适应入场闸门包含核心阻断原因，禁止自动入场",
            blockers=[reason],
            warnings=warnings,
        )

    if _looks_tactical(reason) or entry_gate.status in {"WAIT", "WAITING", "WATCH_ONLY", "BLOCKED"}:
        score += 10
        if score >= 65:
            warnings.append(f"战术确认未完全通过：{reason}")
            return StrictnessDecision(
                entry_mode=ENTRY_OPPORTUNITY,
                score=min(84.0, score),
                strictness="RELAXED_ONE_MISSING_CONFIRMATION",
                reason="核心安全通过，战术确认缺一项，仅允许小仓试探",
                blockers=[],
                warnings=warnings,
            )

    return StrictnessDecision(
        entry_mode=ENTRY_BLOCKED,
        score=min(score, 64.0),
        strictness="ENTRY_GATE_NOT_CONFIRMED",
        reason="入场触发证据不足，暂停自动入场",
        blockers=[reason],
        warnings=warnings,
    )
