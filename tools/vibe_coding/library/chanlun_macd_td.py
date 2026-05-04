"""Research-only Chanlun MACD + TD strategy adapter."""

from __future__ import annotations

import json

CHANLUN_MACD_TD_SOURCE = {
    "name": "Chanlun MACD 背驰 + TD 研究策略",
    "repo": "https://github.com/haigechanlun/chanlun_auto_trading",
    "sourceFile": "https://github.com/haigechanlun/chanlun_auto_trading/blob/main/strategy/backtest_macd_td.py",
    "license": "MIT",
    "noticeFile": "THIRD_PARTY_NOTICES.md",
    "copyright": "Copyright (c) 2026 haigechanlun",
    "adaptation": "QuantGod research-only BaseStrategy adapter; no live trading integration.",
}


_TEMPLATE = r'''
from tools.vibe_coding.strategy_template import BaseStrategy
import math


class ChanlunMacdTdResearchStrategy(BaseStrategy):
    name = "ChanlunMacdTdResearchStrategy"
    version = "v1"
    description = "研究版 MACD 背驰 + TD9 组合策略，改编自 haigechanlun/chanlun_auto_trading。只用于 QuantGod Vibe 回测与人工复核。"
    timeframe = __TIMEFRAME_LITERAL__
    symbols = [__SYMBOL_LITERAL__]
    source = __SOURCE_LITERAL__

    def _values(self, series):
        return [float(value) for value in series.values]

    def _ema(self, values, period):
        if not values:
            return []
        alpha = 2.0 / (float(period) + 1.0)
        out = [float(values[0])]
        for value in values[1:]:
            out.append(float(value) * alpha + out[-1] * (1.0 - alpha))
        return out

    def _rsi(self, closes, period=14):
        if len(closes) <= period:
            return 50.0
        gains = []
        losses = []
        for index in range(len(closes) - period, len(closes)):
            change = closes[index] - closes[index - 1]
            gains.append(max(change, 0.0))
            losses.append(abs(min(change, 0.0)))
        avg_gain = sum(gains) / float(period)
        avg_loss = sum(losses) / float(period)
        if avg_loss <= 0:
            return 100.0 if avg_gain > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) <= 1:
            return 0.0
        trs = []
        for index in range(max(1, len(closes) - period), len(closes)):
            trs.append(max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1])))
        return sum(trs) / len(trs) if trs else 0.0

    def _macd(self, closes, fast=12, slow=26, signal=9):
        ema_fast = self._ema(closes, fast)
        ema_slow = self._ema(closes, slow)
        macd_line = [ema_fast[index] - ema_slow[index] for index in range(len(closes))]
        signal_line = self._ema(macd_line, signal)
        hist = [macd_line[index] - signal_line[index] for index in range(len(closes))]
        return macd_line, hist

    def _extremes(self, values, window=3):
        peaks = []
        troughs = []
        for index in range(window, len(values) - window):
            current = values[index]
            peak = True
            trough = True
            for offset in range(1, window + 1):
                if not (current > values[index - offset] and current > values[index + offset]):
                    peak = False
                if not (current < values[index - offset] and current < values[index + offset]):
                    trough = False
            if peak:
                peaks.append((index, current))
            if trough:
                troughs.append((index, current))
        return peaks, troughs

    def _bullish_divergence(self, price_troughs, macd_troughs):
        if len(price_troughs) < 2 or len(macd_troughs) < 2:
            return False, 0.0
        p1, p2 = price_troughs[-2], price_troughs[-1]
        m1, m2 = macd_troughs[-2], macd_troughs[-1]
        if p2[1] < p1[1] and m2[1] > m1[1]:
            price_part = abs((p2[1] - p1[1]) / p1[1]) * 50.0 if p1[1] else 0.0
            macd_part = ((m2[1] - m1[1]) / abs(m1[1])) * 50.0 if m1[1] else 0.5
            return True, min(1.0, max(0.0, price_part + macd_part))
        return False, 0.0

    def _bearish_divergence(self, price_peaks, macd_peaks):
        if len(price_peaks) < 2 or len(macd_peaks) < 2:
            return False, 0.0
        p1, p2 = price_peaks[-2], price_peaks[-1]
        m1, m2 = macd_peaks[-2], macd_peaks[-1]
        if p2[1] > p1[1] and m2[1] < m1[1]:
            price_part = abs((p2[1] - p1[1]) / p1[1]) * 50.0 if p1[1] else 0.0
            macd_part = abs((m2[1] - m1[1]) / abs(m1[1])) * 50.0 if m1[1] else 0.5
            return True, min(1.0, max(0.0, price_part + macd_part))
        return False, 0.0

    def _td_setup(self, closes, period=9):
        if len(closes) < period + 4:
            return 0
        buy = True
        sell = True
        for offset in range(1, period + 1):
            if closes[-offset] > closes[-offset - 4]:
                buy = False
            if closes[-offset] < closes[-offset - 4]:
                sell = False
        if buy:
            return 1
        if sell:
            return -1
        return 0

    def _volume_ratio(self, volumes, period=20):
        if len(volumes) < period + 1:
            return 1.0
        base = volumes[-period - 1:-1]
        mean_volume = sum(base) / float(len(base)) if base else 0.0
        return volumes[-1] / mean_volume if mean_volume > 0 else 1.0

    def indicators(self, bars):
        closes = self._values(bars["close"])
        highs = self._values(bars["high"])
        lows = self._values(bars["low"])
        macd_line, macd_hist = self._macd(closes)
        return {
            "macd": macd_line[-1],
            "macd_hist": macd_hist[-1],
            "ema20": self._ema(closes, 20)[-1],
            "ema60": self._ema(closes, 60)[-1],
            "rsi": self._rsi(closes),
            "atr": self._atr(highs, lows, closes),
            "td9": self._td_setup(closes),
        }

    def evaluate(self, bars):
        if len(bars) < 90:
            return {"signal": None, "confidence": 0.0, "sl_pips": 12.0, "tp_pips": 20.0, "reasoning": "需要至少 90 根K线，当前样本不足。"}
        closes = self._values(bars["close"])
        highs = self._values(bars["high"])
        lows = self._values(bars["low"])
        try:
            volumes = self._values(bars["volume"])
        except Exception:
            volumes = [1.0 for _ in closes]

        macd_line, _ = self._macd(closes)
        fast_macd, _ = self._macd(closes, 8, 17, 6)
        price_peaks, price_troughs = self._extremes(closes)
        macd_peaks, macd_troughs = self._extremes(macd_line)
        fast_peaks, fast_troughs = self._extremes(fast_macd)
        bullish, bull_strength = self._bullish_divergence(price_troughs, macd_troughs)
        fast_bullish, fast_bull_strength = self._bullish_divergence(price_troughs, fast_troughs)
        bearish, bear_strength = self._bearish_divergence(price_peaks, macd_peaks)
        fast_bearish, fast_bear_strength = self._bearish_divergence(price_peaks, fast_peaks)

        ema20 = self._ema(closes, 20)[-1]
        ema60 = self._ema(closes, 60)[-1]
        rsi = self._rsi(closes)
        atr = self._atr(highs, lows, closes)
        td9 = self._td_setup(closes)
        volume_ratio = self._volume_ratio(volumes)
        close = closes[-1]
        pip = 0.01 if close > 20 else 0.0001
        sl_pips = max(8.0, min(80.0, (atr * 1.5) / pip if atr > 0 else 18.0))
        tp_pips = max(sl_pips * 1.4, min(140.0, sl_pips * 2.0))

        buy_conditions = []
        if bullish or fast_bullish:
            buy_conditions.append("MACD 底背驰")
        if td9 == 1:
            buy_conditions.append("TD9 买入结构")
        if rsi < 40:
            buy_conditions.append("RSI 低位")
        if close < ema60:
            buy_conditions.append("价格低于 EMA60")
        if volume_ratio >= 0.8:
            buy_conditions.append("成交量确认")

        sell_conditions = []
        if bearish or fast_bearish:
            sell_conditions.append("MACD 顶背驰")
        if td9 == -1:
            sell_conditions.append("TD9 卖出结构")
        if rsi > 60:
            sell_conditions.append("RSI 高位")
        if close > ema60:
            sell_conditions.append("价格高于 EMA60")

        bull_score = max(bull_strength, fast_bull_strength) + (0.15 if td9 == 1 else 0.0) + (0.10 if rsi < 40 else 0.0) + (0.05 if volume_ratio >= 0.8 else 0.0)
        bear_score = max(bear_strength, fast_bear_strength) + (0.15 if td9 == -1 else 0.0) + (0.10 if rsi > 60 else 0.0)

        if len(buy_conditions) >= 3 and bull_score >= 0.35:
            return {"signal": "BUY", "confidence": min(0.9, 0.42 + bull_score), "sl_pips": round(sl_pips, 2), "tp_pips": round(tp_pips, 2), "reasoning": "研究信号：{}；RSI {:.1f}，EMA20/60 {:.5f}/{:.5f}，量比 {:.2f}。仅进入 Vibe 回测与人工复核，不自动上实盘。".format("、".join(buy_conditions), rsi, ema20, ema60, volume_ratio)}
        if len(sell_conditions) >= 3 and bear_score >= 0.35:
            return {"signal": "SELL", "confidence": min(0.86, 0.40 + bear_score), "sl_pips": round(sl_pips, 2), "tp_pips": round(tp_pips, 2), "reasoning": "研究信号：{}；RSI {:.1f}，EMA20/60 {:.5f}/{:.5f}。仅进入 Vibe 回测与人工复核，不自动上实盘。".format("、".join(sell_conditions), rsi, ema20, ema60)}
        return {"signal": None, "confidence": min(0.34, max(bull_score, bear_score)), "sl_pips": round(sl_pips, 2), "tp_pips": round(tp_pips, 2), "reasoning": "暂未形成 MACD 背驰 + TD9 + 过滤条件共振；保持观察。"}
'''.strip() + "\n"


def chanlun_macd_td_template(symbol: str | None = None, timeframe: str | None = None) -> str:
    return (
        _TEMPLATE
        .replace("__SYMBOL_LITERAL__", json.dumps(str(symbol or "EURUSDc"), ensure_ascii=False))
        .replace("__TIMEFRAME_LITERAL__", json.dumps(str(timeframe or "M15"), ensure_ascii=False))
        .replace("__SOURCE_LITERAL__", json.dumps(CHANLUN_MACD_TD_SOURCE, ensure_ascii=False, sort_keys=True))
    )
