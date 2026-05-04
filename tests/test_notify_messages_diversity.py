"""Diversity matrix test — prevents message content regression.

Feeds the SAME baseline payload to all 5 message kinds and asserts that
every pair produces *visibly different* output.  This test is a merge
gate: if someone copies a template between renderers, the similarity
check catches it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from notify.messages import KIND_TITLE_PREFIX, render


BASELINE = {
    "symbol": "USDJPYc",
    "timeframe": "M15",
    "timeframes": ["M15", "H1"],
    "decision": {
        "action": "BUY",
        "confidence": 0.72,
        "signalGrade": "A 级",
        "entryZone": "153.05 – 153.15",
        "stopLoss": "152.80",
        "stopLossPips": 25,
        "targets": ["153.60", "153.95", "154.40"],
        "riskReward": "1:2.2",
        "invalidation": "1H 收盘跌破 152.95",
        "risk": "medium",
    },
    "deepseek_advice": {
        "ok": True,
        "model": "deepseek-v4-flash",
        "advice": {
            "marketSummary": "套利情绪持续，技术面突破确认",
            "bullCase": "M15/H1 共振突破",
            "bearCase": "D1 阻力仍在",
            "newsRisk": "无高影响事件",
            "sentimentPositioning": "机构偏多",
        },
    },
    "_event_type": "KILL_SWITCH",
    "reason": "daily_drawdown_exceeded",
    "pnl": 245.60,
    "dailyPnl": 245.60,
    "recovery": "手动复核",
    "wins": 8,
    "losses": 3,
    "routes": "mt5_rsi_failfast (5)",
    "shadowSignals": 5,
    "message": "ping",
}


class DiversityMatrixTests(unittest.TestCase):
    """Every pair of kinds must produce visibly different messages."""

    KINDS = ["ai_advisory", "deepseek_insight", "daily_digest", "runtime_event", "test"]

    @classmethod
    def setUpClass(cls) -> None:
        cls.messages: dict[str, str] = {}
        for kind in cls.KINDS:
            msg = render(kind, dict(BASELINE))
            assert msg is not None, f"{kind} returned None for BUY baseline"
            cls.messages[kind] = msg

    def test_no_kind_returns_empty(self) -> None:
        for kind, msg in self.messages.items():
            with self.subTest(kind=kind):
                self.assertGreater(len(msg), 10, f"{kind} output too short")

    def test_first_lines_are_all_different(self) -> None:
        """The very first line of every kind must be unique."""
        first_lines: dict[str, str] = {}
        for kind, msg in self.messages.items():
            first_lines[kind] = msg.split("\n")[0]

        for k1, v1 in first_lines.items():
            for k2, v2 in first_lines.items():
                if k1 >= k2:
                    continue
                self.assertNotEqual(
                    v1,
                    v2,
                    f"{k1} / {k2} share the same first line: {v1!r}",
                )

    def test_prefixes_match_registry(self) -> None:
        """Every kind's first line must start with its registered prefix."""
        for kind, msg in self.messages.items():
            with self.subTest(kind=kind):
                first_line = msg.split("\n")[0]
                expected_prefix = KIND_TITLE_PREFIX.get(kind)
                if expected_prefix:
                    self.assertTrue(
                        first_line.startswith(expected_prefix),
                        f"{kind} first line {first_line!r} does not start with {expected_prefix!r}",
                    )

    def test_pairwise_similarity_below_threshold(self) -> None:
        """No two kinds should share >70% of characters."""
        for k1 in self.KINDS:
            for k2 in self.KINDS:
                if k1 >= k2:
                    continue
                m1 = self.messages[k1]
                m2 = self.messages[k2]
                common = sum(1 for a, b in zip(m1, m2) if a == b)
                ratio = common / max(len(m1), len(m2))
                self.assertLess(
                    ratio,
                    0.7,
                    f"{k1} / {k2} character similarity {ratio:.0%} exceeds 70% threshold — "
                    f"messages have likely regressed to look the same",
                )

    def test_lengths_are_distinct(self) -> None:
        """Each kind should have a meaningfully different length profile."""
        lengths = {k: len(v) for k, v in self.messages.items()}
        # ai_advisory and deepseek_insight should differ significantly
        ai_len = lengths["ai_advisory"]
        ds_len = lengths["deepseek_insight"]
        self.assertNotEqual(
            ai_len,
            ds_len,
            "ai_advisory and deepseek_insight must have different lengths",
        )
        # deepseek should be longer (has more sections)
        self.assertGreater(
            ds_len,
            ai_len,
            "deepseek_insight should be longer than ai_advisory",
        )
        # daily_digest should be shortest among the three
        dd_len = lengths["daily_digest"]
        self.assertLess(dd_len, ai_len, "daily_digest should be shorter than ai_advisory")


if __name__ == "__main__":
    unittest.main()
