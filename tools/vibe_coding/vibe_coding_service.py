"""Core Vibe Coding service: natural language → safe Python strategy."""

from __future__ import annotations

import json
import re
from typing import Any

from .backtest_analyzer import BacktestAnalyzer
from .backtest_connector import BacktestConnector, BacktestRequest
from .config import VibeCodingConfig, load_config, phase3_vibe_safety
from .library import CHANLUN_MACD_TD_SOURCE, chanlun_macd_td_template
from .safety import validate_strategy_code
from .strategy_registry import StrategyRegistry, utc_now


def _safe_identifier(value: str, fallback: str = "VibeGeneratedStrategy") -> str:
    words = re.findall(r"[A-Za-z0-9]+", value or "")[:6]
    if not words:
        return fallback
    name = "".join(word.capitalize() for word in words)
    if not name[0].isalpha():
        name = f"Vibe{name}"
    return f"{name}Strategy"


def fallback_strategy_code(description: str, symbol: str | None, timeframe: str | None, version: str = "v1") -> str:
    class_name = _safe_identifier(description)
    desc_literal = json.dumps(str(description or "Vibe strategy"), ensure_ascii=False)
    symbol_literal = json.dumps(str(symbol or "EURUSDc"), ensure_ascii=False)
    tf_literal = json.dumps(str(timeframe or "H1"), ensure_ascii=False)
    return f"""
from tools.vibe_coding.strategy_template import BaseStrategy
import math


class {class_name}(BaseStrategy):
    name = "{class_name}"
    version = "{version}"
    description = {desc_literal}
    timeframe = {tf_literal}
    symbols = [{symbol_literal}]

    def indicators(self, bars):
        close = bars["close"]
        fast = close.rolling(9).mean().iloc[-1]
        slow = close.rolling(21).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
        loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss and not math.isnan(loss) else 0.0
        rsi = 100 - (100 / (1 + rs)) if rs else 50.0
        return {{"ma_fast": float(fast), "ma_slow": float(slow), "rsi": float(rsi)}}

    def evaluate(self, bars):
        if len(bars) < 30:
            return {{"signal": None, "confidence": 0.0, "sl_pips": 12.0, "tp_pips": 18.0, "reasoning": "Need at least 30 bars"}}
        ind = self.indicators(bars)
        close = float(bars["close"].iloc[-1])
        prev_close = float(bars["close"].iloc[-2])
        momentum_up = close > prev_close
        if ind["ma_fast"] > ind["ma_slow"] and ind["rsi"] < 72 and momentum_up:
            return {{"signal": "BUY", "confidence": 0.55, "sl_pips": 12.0, "tp_pips": 20.0, "reasoning": "Fallback prototype: fast MA above slow MA with positive momentum"}}
        if ind["ma_fast"] < ind["ma_slow"] and ind["rsi"] > 28 and not momentum_up:
            return {{"signal": "SELL", "confidence": 0.55, "sl_pips": 12.0, "tp_pips": 20.0, "reasoning": "Fallback prototype: fast MA below slow MA with negative momentum"}}
        return {{"signal": None, "confidence": 0.2, "sl_pips": 12.0, "tp_pips": 18.0, "reasoning": "No confluence"}}
""".strip() + "\n"


class VibeCodingService:
    def __init__(self, config: VibeCodingConfig | None = None):
        self.config = config or load_config()
        self.registry = StrategyRegistry(self.config)
        self.backtests = BacktestConnector(self.config, self.registry)
        self.analyzer = BacktestAnalyzer()
        self.config.history_dir.mkdir(parents=True, exist_ok=True)

    async def generate_strategy(self, description: str, target_symbol: str | None = None, target_tf: str | None = None) -> dict[str, Any]:
        description = str(description or "").strip()
        if not description:
            return {"ok": False, "error": "description is required", "safety": phase3_vibe_safety()}
        strategy_id = self.registry.next_strategy_id(description, _safe_identifier(description))
        code = fallback_strategy_code(description, target_symbol, target_tf, "v1")
        validation = validate_strategy_code(code, allowed_imports=self.config.allowed_imports, max_code_bytes=self.config.max_code_bytes)
        record = self.registry.save_strategy(
            code=code,
            description=description,
            symbol=target_symbol,
            timeframe=target_tf,
            strategy_id=strategy_id,
            name=_safe_identifier(description),
            validation=validation.to_dict(),
        )
        return {
            "ok": validation.ok,
            "schema": "quantgod.vibe_generated_strategy.v1",
            "generatedAt": utc_now(),
            "strategy": record.to_dict(),
            "code": code,
            "validation": validation.to_dict(),
            "llm": {"used": False, "mode": "deterministic_fallback", "model": self.config.llm_model},
            "safety": phase3_vibe_safety(),
        }

    async def import_library_strategy(
        self,
        name: str,
        target_symbol: str | None = None,
        target_tf: str | None = None,
    ) -> dict[str, Any]:
        library_name = str(name or "").strip().lower().replace("-", "_")
        aliases = {"chanlun", "chanlun_macd_td", "macd_td", "macd_divergence_td"}
        if library_name not in aliases:
            return {
                "ok": False,
                "error": "unsupported_library_strategy",
                "supported": sorted(aliases),
                "safety": phase3_vibe_safety(),
            }
        strategy_id = "vibe-chanlun-macd-td"
        description = "内置研究策略：MACD 背驰 + TD9 组合，改编自 haigechanlun/chanlun_auto_trading；仅用于 Vibe 回测和人工复核。"
        code = chanlun_macd_td_template(target_symbol, target_tf)
        validation = validate_strategy_code(
            code,
            allowed_imports=self.config.allowed_imports,
            max_code_bytes=self.config.max_code_bytes,
        )
        existing = self.registry.get_strategy(strategy_id, include_code=True)
        if existing.get("ok") and existing.get("code") == code:
            return {
                "ok": validation.ok,
                "schema": "quantgod.vibe_library_strategy_import.v1",
                "generatedAt": utc_now(),
                "imported": False,
                "strategy": existing["strategy"],
                "code": code,
                "validation": validation.to_dict(),
                "source": CHANLUN_MACD_TD_SOURCE,
                "llm": {"used": False, "mode": "builtin_research_template"},
                "safety": phase3_vibe_safety(),
            }
        record = self.registry.save_strategy(
            code=code,
            description=description,
            symbol=target_symbol or "EURUSDc",
            timeframe=target_tf or "M15",
            strategy_id=strategy_id,
            name="ChanlunMacdTdResearchStrategy",
            validation=validation.to_dict(),
        )
        return {
            "ok": validation.ok,
            "schema": "quantgod.vibe_library_strategy_import.v1",
            "generatedAt": utc_now(),
            "imported": True,
            "strategy": record.to_dict(),
            "code": code,
            "validation": validation.to_dict(),
            "source": CHANLUN_MACD_TD_SOURCE,
            "llm": {"used": False, "mode": "builtin_research_template"},
            "safety": phase3_vibe_safety(),
        }

    async def iterate_strategy(self, strategy_id: str, feedback: str, backtest_result: dict | None = None) -> dict[str, Any]:
        current = self.registry.get_strategy(strategy_id, include_code=True)
        if not current.get("ok"):
            return current
        meta = current["strategy"]
        description = f"{meta.get('description', '')}\nIteration feedback: {feedback}"
        version_number = len(current.get("versions") or []) + 1
        code = fallback_strategy_code(description, meta.get("symbol"), meta.get("timeframe"), f"v{version_number}")
        validation = validate_strategy_code(code, allowed_imports=self.config.allowed_imports, max_code_bytes=self.config.max_code_bytes)
        record = self.registry.save_strategy(
            code=code,
            description=description,
            symbol=meta.get("symbol"),
            timeframe=meta.get("timeframe"),
            strategy_id=strategy_id,
            name=meta.get("name"),
            parent_version=meta.get("version"),
            validation=validation.to_dict(),
        )
        return {
            "ok": validation.ok,
            "schema": "quantgod.vibe_generated_strategy_iteration.v1",
            "generatedAt": utc_now(),
            "strategy": record.to_dict(),
            "code": code,
            "validation": validation.to_dict(),
            "feedback": feedback,
            "backtest_context_used": bool(backtest_result),
            "llm": {"used": False, "mode": "deterministic_fallback", "model": self.config.llm_model},
            "safety": phase3_vibe_safety(),
        }

    async def run_backtest(self, strategy_id: str, symbol: str = "EURUSDc", timeframe: str = "H1", days: int = 30, version: str | None = None) -> dict[str, Any]:
        return self.backtests.run_backtest(BacktestRequest(strategy_id=strategy_id, symbol=symbol, timeframe=timeframe, days=int(days), version=version))

    async def analyze_backtest(self, strategy_id: str, backtest_result: dict) -> dict[str, Any]:
        return self.analyzer.analyze(strategy_id, backtest_result)

    def list_strategies(self) -> dict[str, Any]:
        return self.registry.list_strategies()

    def get_strategy(self, strategy_id: str, version: str | None = None) -> dict[str, Any]:
        return self.registry.get_strategy(strategy_id, version, include_code=True)

    def config_payload(self) -> dict[str, Any]:
        return {"ok": True, "schema": "quantgod.vibe_config.v1", "config": self.config.to_public_dict(), "safety": phase3_vibe_safety()}
