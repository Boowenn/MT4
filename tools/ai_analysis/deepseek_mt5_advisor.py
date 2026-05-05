"""DeepSeek-backed Chinese MT5 advisory layer for Telegram reports.

This module is deliberately advisory-only. It sends only a sanitized market and
risk summary to DeepSeek; it must never send credentials, account identifiers,
order tickets, passwords, tokens, or mutation instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping


class DeepSeekAdvisorError(RuntimeError):
    """Raised when DeepSeek cannot return a usable advisory response."""


Opener = Callable[[urllib.request.Request, int], Any]


@dataclass(frozen=True)
class DeepSeekAdvisorConfig:
    enabled: bool
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout_seconds: int = 45
    max_tokens: int = 1800
    temperature: float = 0.25

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_deepseek_config(
    *,
    repo_root: str | Path | None = None,
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DeepSeekAdvisorConfig:
    env = dict(os.environ if environ is None else environ)
    root = Path(repo_root or Path.cwd()).resolve()
    configured_env_file = env_file or env.get("QG_MT5_AI_DEEPSEEK_ENV_FILE") or root / ".env.deepseek.local"
    file_values = load_env_file(Path(configured_env_file).expanduser()) if configured_env_file else {}
    merged = {**file_values, **env}
    enabled = truthy(merged.get("QG_MT5_AI_DEEPSEEK_ENABLED", "1"))
    api_key = (
        merged.get("DEEPSEEK_API_KEY")
        or merged.get("QG_DEEPSEEK_API_KEY")
        or merged.get("QG_MT5_AI_DEEPSEEK_API_KEY")
        or ""
    )
    return DeepSeekAdvisorConfig(
        enabled=enabled,
        api_key=api_key,
        base_url=merged.get("DEEPSEEK_BASE_URL") or merged.get("QG_DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        model=merged.get("QG_MT5_AI_DEEPSEEK_MODEL") or merged.get("DEEPSEEK_MODEL") or "deepseek-v4-flash",
        timeout_seconds=int(merged.get("QG_MT5_AI_DEEPSEEK_TIMEOUT_SECONDS") or 45),
        max_tokens=int(merged.get("QG_MT5_AI_DEEPSEEK_MAX_TOKENS") or 1800),
        temperature=float(merged.get("QG_MT5_AI_DEEPSEEK_TEMPERATURE") or 0.25),
    )


def default_urlopen(request: urllib.request.Request, timeout_seconds: int) -> Any:
    try:
        import certifi  # type: ignore

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    return urllib.request.urlopen(request, timeout=timeout_seconds, context=context)


def chat_completions_url(base_url: str) -> str:
    base = str(base_url or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def anthropic_messages_url(base_url: str) -> str:
    base = str(base_url or "https://api.deepseek.com/anthropic").rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    return f"{base}/v1/messages"


def uses_anthropic_gateway(base_url: str) -> bool:
    return "/anthropic" in str(base_url or "").lower()


def sanitize_report_for_deepseek(report: dict[str, Any]) -> dict[str, Any]:
    snapshot = report.get("snapshot") if isinstance(report.get("snapshot"), dict) else {}
    current_price = snapshot.get("current_price") if isinstance(snapshot.get("current_price"), dict) else {}
    technical = report.get("technical") if isinstance(report.get("technical"), dict) else {}
    risk = report.get("risk") if isinstance(report.get("risk"), dict) else {}
    news = report.get("news") if isinstance(report.get("news"), dict) else {}
    sentiment = report.get("sentiment") if isinstance(report.get("sentiment"), dict) else {}
    bull = report.get("bull_case") if isinstance(report.get("bull_case"), dict) else {}
    bear = report.get("bear_case") if isinstance(report.get("bear_case"), dict) else {}
    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    return {
        "symbol": report.get("symbol"),
        "generatedAt": report.get("generatedAt"),
        "timeframes": report.get("timeframes") if isinstance(report.get("timeframes"), list) else [],
        "dataQuality": {
            "source": snapshot.get("source"),
            "fallback": bool(snapshot.get("fallback")),
            "runtimeFresh": bool(snapshot.get("runtimeFresh")),
            "runtimeAgeSeconds": snapshot.get("runtimeAgeSeconds"),
        },
        "price": {
            "bid": current_price.get("bid"),
            "ask": current_price.get("ask"),
            "last": current_price.get("last"),
            "spread": current_price.get("spread"),
        },
        "technical": {
            "direction": technical.get("direction"),
            "trend": technical.get("trend") if isinstance(technical.get("trend"), dict) else {},
            "indicators": technical.get("indicators") if isinstance(technical.get("indicators"), dict) else {},
            "keyLevels": technical.get("key_levels") if isinstance(technical.get("key_levels"), dict) else {},
            "signalStrength": technical.get("signal_strength"),
            "reasoning": technical.get("reasoning"),
        },
        "risk": {
            "riskLevel": risk.get("risk_level"),
            "riskScore": risk.get("risk_score"),
            "killSwitchActive": bool(risk.get("kill_switch_active")),
            "tradeable": risk.get("tradeable"),
            "positionExposure": risk.get("position_exposure"),
            "factors": risk.get("factors") if isinstance(risk.get("factors"), list) else [],
            "reasoning": risk.get("reasoning"),
        },
        "news": {
            "riskLevel": news.get("risk_level"),
            "activeNewsBlock": bool(news.get("active_news_block")),
            "reasoning": news.get("reasoning"),
        },
        "sentiment": {
            "bias": sentiment.get("bias"),
            "score": sentiment.get("score"),
            "reasoning": sentiment.get("reasoning"),
        },
        "localDebate": {
            "bullThesis": bull.get("thesis"),
            "bullConviction": bull.get("conviction"),
            "bearThesis": bear.get("thesis"),
            "bearConviction": bear.get("conviction"),
        },
        "localDecision": {
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "entryPrice": decision.get("entry_price"),
            "stopLoss": decision.get("stop_loss"),
            "takeProfit": decision.get("take_profit"),
            "riskRewardRatio": decision.get("risk_reward_ratio"),
            "positionSizeSuggestion": decision.get("position_size_suggestion"),
            "reasoning": decision.get("reasoning"),
        },
        "hardBoundary": {
            "advisoryOnly": True,
            "telegramPushOnly": True,
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "livePresetMutationAllowed": False,
            "canOverrideKillSwitch": False,
        },
    }


SYSTEM_PROMPT = """你是 QuantGod MT5 的中文只读交易研究分析师。
你只能根据用户提供的脱敏证据生成中文建议。禁止要求下单、平仓、撤单、修改实盘参数、解除熔断或绕过风控。
如果 dataQuality.fallback=true 或 runtimeFresh=false，必须把 planStatus 写成“暂停，仅允许观察复核”，entryZone/targets/defense 不得给真实入场价位，并强调不能据此入场。
输出必须是 JSON 对象，不要 Markdown，不要英文标题。字段必须完整，所有自然语言用中文。
字段：
headline, verdict, signalGrade, confidencePct, marketSummary, technicalSummary, bullCase, bearCase, newsRisk, sentimentPositioning,
planStatus, entryZone, targets, defense, riskReward, positionAdvice, invalidation, watchPoints, riskNotes, executionBoundary。
targets 必须是 3 个字符串；watchPoints 和 riskNotes 各 2 到 4 条。每个字段尽量短，像 Telegram 交易报告。"""


class DeepSeekMt5Advisor:
    def __init__(self, config: DeepSeekAdvisorConfig, opener: Opener | None = None) -> None:
        self.config = config
        self.opener = opener or default_urlopen

    def analyze(self, report: dict[str, Any]) -> dict[str, Any]:
        if not self.config.enabled:
            return {"ok": False, "status": "disabled", "provider": "deepseek", "model": self.config.model}
        if not self.config.configured:
            return {"ok": False, "status": "missing_api_key", "provider": "deepseek", "model": self.config.model}
        sanitized = sanitize_report_for_deepseek(report)
        user_content = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
        payload = self._build_payload(user_content)
        data = self._post(payload)
        content = self._extract_content(data)
        try:
            parsed = self._parse_json(content)
            status = "ok"
        except DeepSeekAdvisorError:
            parsed = non_json_observation_advice(content)
            status = "ok_text_fallback"
        return {
            "ok": True,
            "status": status,
            "provider": "deepseek",
            "model": self.config.model,
            "advice": normalize_advice(parsed),
            "safety": {
                "advisoryOnly": True,
                "sanitizedPayloadOnly": True,
                "orderSendAllowed": False,
                "credentialStorageAllowed": False,
                "livePresetMutationAllowed": False,
            },
        }

    def _build_payload(self, user_content: str) -> dict[str, Any]:
        if uses_anthropic_gateway(self.config.base_url):
            return {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            }
        return {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        is_anthropic = uses_anthropic_gateway(self.config.base_url)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if is_anthropic:
            headers["anthropic-version"] = "2023-06-01"
        request = urllib.request.Request(
            anthropic_messages_url(self.config.base_url) if is_anthropic else chat_completions_url(self.config.base_url),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self.opener(request, self.config.timeout_seconds) as response:  # type: ignore[misc]
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise DeepSeekAdvisorError(f"DeepSeek HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise DeepSeekAdvisorError(f"DeepSeek request failed: {error.reason}") from error
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise DeepSeekAdvisorError("DeepSeek returned non-JSON response") from error

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        content_blocks = data.get("content")
        if isinstance(content_blocks, list):
            text_parts = [
                str(item.get("text") or "").strip()
                for item in content_blocks
                if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text") or "").strip()
            ]
            if text_parts:
                return "\n".join(text_parts).strip()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise DeepSeekAdvisorError("DeepSeek response missing choices[0].message.content") from error
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekAdvisorError("DeepSeek response content is empty")
        return content.strip()

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            text = text[first : last + 1]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise DeepSeekAdvisorError("DeepSeek response is not valid JSON") from error
        if not isinstance(parsed, dict):
            raise DeepSeekAdvisorError("DeepSeek JSON response must be an object")
        return parsed


def normalize_advice(raw: dict[str, Any]) -> dict[str, Any]:
    def text(key: str, fallback: str = "暂无") -> str:
        value = raw.get(key)
        if value is None or value == "":
            return fallback
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return "；".join(parts) if parts else fallback
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return str(value).strip()

    def list_text(key: str, count: int, fallback: str) -> list[str]:
        value = raw.get(key)
        items: list[str] = []
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        elif value:
            items = [str(value).strip()]
        while len(items) < count:
            items.append(fallback)
        return items[:count]

    return {
        "headline": text("headline", "DeepSeek 已完成中文研判。"),
        "verdict": text("verdict", "观望，不开新仓"),
        "signalGrade": text("signalGrade", "观察级"),
        "confidencePct": text("confidencePct", "--"),
        "marketSummary": text("marketSummary"),
        "technicalSummary": text("technicalSummary"),
        "bullCase": text("bullCase"),
        "bearCase": text("bearCase"),
        "newsRisk": text("newsRisk"),
        "sentimentPositioning": text("sentimentPositioning"),
        "planStatus": text("planStatus", "暂停，仅允许观察复核"),
        "entryZone": text("entryZone", "不生成"),
        "targets": list_text("targets", 3, "不生成"),
        "defense": text("defense", "不生成"),
        "riskReward": text("riskReward", "未评估"),
        "positionAdvice": text("positionAdvice", "不构成下单建议"),
        "invalidation": text("invalidation", "证据不足或风险升高时保持观望"),
        "watchPoints": list_text("watchPoints", 2, "等待新鲜运行证据"),
        "riskNotes": list_text("riskNotes", 2, "严格遵守只读与风控边界"),
        "executionBoundary": text("executionBoundary", "仅建议，不执行交易。"),
    }


def non_json_observation_advice(content: str) -> dict[str, Any]:
    """Convert a non-JSON DeepSeek reply into a safe observation-only payload.

    DeepSeek sometimes ignores JSON mode and returns prose.  We still want the
    operator to see that analysis, but never as an actionable trade plan.
    """
    text = " ".join(str(content or "").replace("```", " ").split())
    if not text:
        text = "DeepSeek 返回了非结构化内容，未形成可执行交易计划。"
    excerpt = text[:260]
    return {
        "headline": "DeepSeek 返回非结构化研判，已按观察摘要处理。",
        "verdict": "观望，不开新仓",
        "signalGrade": "观察级",
        "confidencePct": "--",
        "marketSummary": excerpt,
        "technicalSummary": "模型没有返回结构化入场、止损、目标位，因此不生成交易计划。",
        "bullCase": "等待结构化证据确认。",
        "bearCase": "等待结构化证据确认。",
        "newsRisk": "未从非结构化回复中生成可执行新闻结论。",
        "sentimentPositioning": "仅作背景观察。",
        "planStatus": "暂停，仅允许观察复核",
        "entryZone": "不生成",
        "targets": ["不生成", "不生成", "不生成"],
        "defense": "不生成",
        "riskReward": "未评估",
        "positionAdvice": "不构成下单建议；仅允许人工观察复核",
        "invalidation": "DeepSeek 未返回结构化 JSON，保持观望",
        "watchPoints": ["等待下一次结构化 DeepSeek 输出", "继续检查实时快照、点差、新闻与熔断状态"],
        "riskNotes": ["非结构化回复不允许生成入场建议", "Telegram 只推送，不接收交易命令"],
        "executionBoundary": "text_fallback；advisory-only；Telegram push-only；不会下单、平仓、撤单或修改实盘参数。",
    }
