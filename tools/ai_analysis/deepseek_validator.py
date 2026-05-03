"""Code-level DeepSeek advisory validator for QuantGod MT5 Telegram reports.

The validator is intentionally stricter than the model prompt.  DeepSeek may
produce useful Chinese trading research, but QuantGod must never trust raw LLM
text as an executable trading instruction.  This module turns raw advice into a
safe effective advice payload before the Telegram formatter sees it.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

SCHEMA = "quantgod.deepseek_advice.validation.v1"

OBSERVATION_VERDICT = "观望，不开新仓"
OBSERVATION_PLAN_STATUS = "暂停，仅允许观察复核"
OBSERVATION_ENTRY = "不生成，等待新鲜运行快照与程序风控确认"
OBSERVATION_TARGET = "不生成"
OBSERVATION_DEFENSE = "不生成"
OBSERVATION_RISK_REWARD = "未评估"
OBSERVATION_POSITION = "不构成下单建议；仅允许人工观察复核"
OBSERVATION_INVALIDATION = "证据不足、风险升高、熔断触发或 DeepSeek 输出未通过校验时保持观望"

# Phrases that are acceptable because they explicitly deny execution.  These are
# checked before the unsafe phrase scan so common safety wording such as
# "不下单" does not become a false positive.
SAFE_NEGATED_EXECUTION_PHRASES = (
    "不下单",
    "不执行",
    "不会下单",
    "不得下单",
    "禁止下单",
    "不平仓",
    "不撤单",
    "不修改",
    "不得修改",
    "不会平仓",
    "不会撤单",
    "no order",
    "do not order",
    "do not execute",
    "not execute",
    "execution disabled",
    "advisory only",
)

UNSAFE_EXECUTION_PATTERNS = (
    r"市价\s*(买入|卖出)",
    r"立即\s*(买入|卖出|开仓|平仓|下单)",
    r"直接\s*(买入|卖出|开仓|平仓|下单)",
    r"执行\s*(买入|卖出|开仓|平仓|下单)",
    r"发送\s*(订单|下单|买入|卖出)",
    r"自动\s*(下单|开仓|平仓|撤单|执行)",
    r"解除\s*熔断",
    r"绕过\s*风控",
    r"修改\s*实盘",
    r"放宽\s*风控",
    r"加\s*杠杆",
    r"满仓",
    r"重仓",
    r"\bmarket\s+(buy|sell)\b",
    r"\bsend\s+order\b",
    r"\border[_\s-]?send\b",
    r"\bclose\s+position\b",
    r"\bcancel\s+order\b",
    r"\boverride\s+kill\s*switch\b",
)

LONG_DIRECTION_TERMS = ("做多", "偏多", "看多", "买入", "long", "bullish")
SHORT_DIRECTION_TERMS = ("做空", "偏空", "看空", "卖出", "short", "bearish")
HOLD_TERMS = ("观望", "暂停", "等待", "不开新仓", "hold", "wait", "neutral")

REQUIRED_ADVICE_KEYS = (
    "headline",
    "verdict",
    "signalGrade",
    "confidencePct",
    "marketSummary",
    "technicalSummary",
    "bullCase",
    "bearCase",
    "newsRisk",
    "sentimentPositioning",
    "planStatus",
    "entryZone",
    "targets",
    "defense",
    "riskReward",
    "positionAdvice",
    "invalidation",
    "watchPoints",
    "riskNotes",
    "executionBoundary",
)


@dataclass(frozen=True)
class EvidenceQuality:
    source: str
    fallback: bool
    runtime_fresh: bool
    runtime_age_seconds: Any
    kill_switch_active: bool
    risk_level: str

    @property
    def blocks_directional_advice(self) -> bool:
        return self.fallback or not self.runtime_fresh or self.kill_switch_active

    @property
    def reason(self) -> str:
        if self.kill_switch_active:
            return "kill_switch_active"
        if self.fallback:
            return "fallback_snapshot"
        if not self.runtime_fresh:
            return "runtime_not_fresh"
        return "fresh_runtime"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _lower(value: Any) -> str:
    return _text(value).lower()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_sentence(value: Any, fallback: str) -> str:
    text = _text(value).strip()
    return text if text else fallback


def _clean_targets(value: Any) -> list[str]:
    raw = _as_list(value)
    items = [_clean_sentence(item, OBSERVATION_TARGET) for item in raw]
    while len(items) < 3:
        items.append(OBSERVATION_TARGET)
    return items[:3]


def advice_text_blob(advice: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in REQUIRED_ADVICE_KEYS:
        value = advice.get(key)
        if isinstance(value, list):
            parts.extend(_text(item) for item in value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def _remove_safe_negated_phrases(text: str) -> str:
    out = text
    for phrase in SAFE_NEGATED_EXECUTION_PHRASES:
        out = out.replace(phrase, " ")
        out = out.replace(phrase.upper(), " ")
        out = out.replace(phrase.title(), " ")
    return out


def find_unsafe_execution_terms(advice: dict[str, Any]) -> list[str]:
    """Return execution-like phrases not protected by explicit negation."""
    searchable = _remove_safe_negated_phrases(advice_text_blob(advice))
    findings: list[str] = []
    for pattern in UNSAFE_EXECUTION_PATTERNS:
        if re.search(pattern, searchable, flags=re.IGNORECASE):
            findings.append(pattern)
    return findings


def evidence_quality(report: dict[str, Any]) -> EvidenceQuality:
    snapshot = _as_dict(report.get("snapshot"))
    risk = _as_dict(report.get("risk"))
    return EvidenceQuality(
        source=str(snapshot.get("source") or "unknown"),
        fallback=bool(snapshot.get("fallback", False)),
        runtime_fresh=bool(snapshot.get("runtimeFresh", False)),
        runtime_age_seconds=snapshot.get("runtimeAgeSeconds"),
        kill_switch_active=bool(risk.get("kill_switch_active", False)),
        risk_level=str(risk.get("risk_level") or "unknown"),
    )


def local_action(report: dict[str, Any]) -> str:
    decision = _as_dict(report.get("decision"))
    action = str(decision.get("action") or "HOLD").upper().strip()
    return action if action in {"BUY", "SELL", "HOLD"} else "HOLD"


def local_confidence(report: dict[str, Any]) -> float:
    decision = _as_dict(report.get("decision"))
    raw = _to_float(decision.get("confidence"), 0.0)
    return raw * 100 if raw <= 1.0 else raw


def _direction_score(blob: str) -> tuple[int, int]:
    long_score = sum(1 for term in LONG_DIRECTION_TERMS if term in blob)
    short_score = sum(1 for term in SHORT_DIRECTION_TERMS if term in blob)
    return long_score, short_score


def infer_deepseek_bias(advice: dict[str, Any]) -> str:
    # Prioritize direct recommendation fields. Bull/bear explanatory sections can
    # mention both directions and should not cancel the actual verdict.
    priority_blob = _lower(
        "\n".join(
            [
                _text(advice.get("verdict")),
                _text(advice.get("headline")),
                _text(advice.get("planStatus")),
                _text(advice.get("entryZone")),
                _text(advice.get("positionAdvice")),
            ]
        )
    )
    long_score, short_score = _direction_score(priority_blob)
    if long_score > short_score:
        return "BUY"
    if short_score > long_score:
        return "SELL"

    blob = _lower(advice_text_blob(advice))
    if any(term in blob for term in HOLD_TERMS):
        if not any(term in blob for term in LONG_DIRECTION_TERMS + SHORT_DIRECTION_TERMS):
            return "HOLD"
    long_score, short_score = _direction_score(blob)
    if long_score > short_score:
        return "BUY"
    if short_score > long_score:
        return "SELL"
    return "HOLD"


def has_directional_conflict(report: dict[str, Any], advice: dict[str, Any]) -> bool:
    local = local_action(report)
    deepseek = infer_deepseek_bias(advice)
    return (local == "BUY" and deepseek == "SELL") or (local == "SELL" and deepseek == "BUY")


def normalize_raw_advice(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    advice = {
        "headline": _clean_sentence(source.get("headline"), "DeepSeek 输出已进入安全复核。"),
        "verdict": _clean_sentence(source.get("verdict"), OBSERVATION_VERDICT),
        "signalGrade": _clean_sentence(source.get("signalGrade"), "观察级"),
        "confidencePct": _clean_sentence(source.get("confidencePct"), "--"),
        "marketSummary": _clean_sentence(source.get("marketSummary"), "暂无市场摘要"),
        "technicalSummary": _clean_sentence(source.get("technicalSummary"), "暂无技术摘要"),
        "bullCase": _clean_sentence(source.get("bullCase"), "多头证据不足"),
        "bearCase": _clean_sentence(source.get("bearCase"), "空头证据不足"),
        "newsRisk": _clean_sentence(source.get("newsRisk"), "暂无新闻风险证据"),
        "sentimentPositioning": _clean_sentence(source.get("sentimentPositioning"), "情绪中性或证据不足"),
        "planStatus": _clean_sentence(source.get("planStatus"), OBSERVATION_PLAN_STATUS),
        "entryZone": _clean_sentence(source.get("entryZone"), OBSERVATION_ENTRY),
        "targets": _clean_targets(source.get("targets")),
        "defense": _clean_sentence(source.get("defense"), OBSERVATION_DEFENSE),
        "riskReward": _clean_sentence(source.get("riskReward"), OBSERVATION_RISK_REWARD),
        "positionAdvice": _clean_sentence(source.get("positionAdvice"), OBSERVATION_POSITION),
        "invalidation": _clean_sentence(source.get("invalidation"), OBSERVATION_INVALIDATION),
        "watchPoints": [
            _clean_sentence(item, "等待新鲜运行证据")
            for item in (_as_list(source.get("watchPoints")) or ["等待新鲜运行证据", "确认风险门禁仍为只读"])
        ][:4],
        "riskNotes": [
            _clean_sentence(item, "严格遵守只读与 advisory-only 边界")
            for item in (_as_list(source.get("riskNotes")) or ["严格遵守只读与 advisory-only 边界", "Telegram 只推送，不接收交易命令"])
        ][:4],
        "executionBoundary": _clean_sentence(source.get("executionBoundary"), "仅建议，不执行交易。"),
    }
    while len(advice["watchPoints"]) < 2:
        advice["watchPoints"].append("等待新鲜运行证据")
    while len(advice["riskNotes"]) < 2:
        advice["riskNotes"].append("严格遵守只读与 advisory-only 边界")
    return advice


def degraded_observation_advice(*, reason: str, original: dict[str, Any] | None = None) -> dict[str, Any]:
    original = normalize_raw_advice(original)
    reason_zh = {
        "fallback_snapshot": "行情或账户快照处于回退模式",
        "runtime_not_fresh": "运行快照不新鲜",
        "kill_switch_active": "熔断或风险锁处于激活状态",
        "execution_language_detected": "DeepSeek 输出含执行类语言",
        "local_deepseek_conflict": "本地多 Agent 与 DeepSeek 方向冲突",
        "deepseek_not_available": "DeepSeek 未返回可用结构化建议",
    }.get(reason, reason)
    return {
        "headline": f"安全复核降级：{reason_zh}。",
        "verdict": OBSERVATION_VERDICT,
        "signalGrade": "数据复核级" if reason in {"fallback_snapshot", "runtime_not_fresh"} else "风险复核级",
        "confidencePct": original.get("confidencePct") or "--",
        "marketSummary": original.get("marketSummary") or "等待新鲜运行快照后复核。",
        "technicalSummary": original.get("technicalSummary") or "当前不允许生成入场计划。",
        "bullCase": original.get("bullCase") or "多头证据不足，等待确认。",
        "bearCase": original.get("bearCase") or "空头证据不足，等待确认。",
        "newsRisk": original.get("newsRisk") or "暂无可执行新闻结论。",
        "sentimentPositioning": original.get("sentimentPositioning") or "情绪仅作背景，不作为入场依据。",
        "planStatus": OBSERVATION_PLAN_STATUS,
        "entryZone": OBSERVATION_ENTRY,
        "targets": [OBSERVATION_TARGET, OBSERVATION_TARGET, OBSERVATION_TARGET],
        "defense": OBSERVATION_DEFENSE,
        "riskReward": OBSERVATION_RISK_REWARD,
        "positionAdvice": OBSERVATION_POSITION,
        "invalidation": OBSERVATION_INVALIDATION,
        "watchPoints": [
            "等待 runtimeFresh=true 且 fallback=false 的 HFM/MT5 快照",
            "确认 Telegram 仍为 push-only 且没有交易命令入口",
            "确认熔断、点差、新闻过滤和治理门禁均未阻断观察",
        ],
        "riskNotes": [
            f"降级原因：{reason_zh}",
            "本条消息不会触发下单、平仓、撤单或实盘参数修改",
        ],
        "executionBoundary": f"validator={reason}；advisory-only；Telegram push-only；不会下单、平仓、撤单、修改实盘或解除熔断。",
    }


def _advice_digest(advice: dict[str, Any]) -> str:
    raw = json.dumps(advice, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def validate_deepseek_advice(report: dict[str, Any], deepseek_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate raw DeepSeek advice and return a safe effective advice.

    The return value deliberately contains both validator status and the effective
    advice that downstream Telegram formatters should use.  Raw DeepSeek text is
    not required by callers and should not be trusted directly.
    """
    payload = _as_dict(deepseek_payload)
    raw_advice = normalize_raw_advice(_as_dict(payload.get("advice"))) if payload.get("ok") else None
    quality = evidence_quality(report)
    reasons: list[str] = []
    unsafe_terms: list[str] = []
    valid = bool(payload.get("ok") and raw_advice)

    if not payload.get("ok"):
        reasons.append("deepseek_not_available")
        valid = False

    if raw_advice:
        unsafe_terms = find_unsafe_execution_terms(raw_advice)
        if unsafe_terms:
            reasons.append("execution_language_detected")
            valid = False

        if quality.blocks_directional_advice:
            reasons.append(quality.reason)
            valid = False

        if has_directional_conflict(report, raw_advice):
            reasons.append("local_deepseek_conflict")
            valid = False

    primary_reason = reasons[0] if reasons else "ok"
    effective_advice = normalize_raw_advice(raw_advice) if raw_advice else degraded_observation_advice(reason="deepseek_not_available")
    if not valid:
        effective_advice = degraded_observation_advice(reason=primary_reason, original=raw_advice)

    local = local_action(report)
    deepseek_bias = infer_deepseek_bias(raw_advice or effective_advice)
    agreement = "no_deepseek"
    if payload.get("ok"):
        if primary_reason == "local_deepseek_conflict":
            agreement = "local_and_deepseek_conflict"
        elif local == deepseek_bias or deepseek_bias == "HOLD":
            agreement = "local_and_deepseek_compatible"
        else:
            agreement = "local_and_deepseek_mixed"

    return {
        "ok": True,
        "schema": SCHEMA,
        "valid": valid,
        "status": "pass" if valid else "downgraded",
        "provider": payload.get("provider") or "deepseek",
        "model": payload.get("model") or "unknown",
        "reasons": reasons,
        "primaryReason": primary_reason,
        "unsafeExecutionTerms": unsafe_terms,
        "agreement": agreement,
        "localAction": local,
        "localConfidencePct": round(local_confidence(report), 2),
        "deepseekBias": deepseek_bias,
        "evidenceQuality": {
            "source": quality.source,
            "fallback": quality.fallback,
            "runtimeFresh": quality.runtime_fresh,
            "runtimeAgeSeconds": quality.runtime_age_seconds,
            "killSwitchActive": quality.kill_switch_active,
            "riskLevel": quality.risk_level,
            "blocksDirectionalAdvice": quality.blocks_directional_advice,
        },
        "effectiveAdvice": effective_advice,
        "rawAdviceDigest": _advice_digest(raw_advice or {}),
        "safety": {
            "advisoryOnly": True,
            "telegramPushOnly": True,
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "livePresetMutationAllowed": False,
            "canOverrideKillSwitch": False,
            "canMutateGovernanceDecision": False,
        },
    }
