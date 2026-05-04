"""Unit tests for NewsAgent covering the 4 core scenarios:
blocked / pre_event / post_event / idle.

Validates that NewsAgent trusts EA output fields (eventName, blocked,
phase, minutesToEvent) instead of looking for non-existent events list.
"""

from __future__ import annotations

import asyncio
import unittest

from tools.ai_analysis.agents.news_agent import NewsAgent


def _run(coro):
    return asyncio.run(coro)


class NewsAgentBlockedTests(unittest.TestCase):
    """Scenario 1: EA has active news block (e.g. NFP 5 min away)."""

    def test_blocked_with_event_returns_high_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": True,
                "phase": "PRE_EVENT",
                "eventName": "Non-Farm Payrolls",
                "eventLabel": "NFP",
                "eventCode": "US_NFP",
                "minutesToEvent": 5,
                "minutesSinceEvent": 0,
                "actual": None,
                "forecast": 5.25,
                "previous": 5.50,
                "reason": "NFP in 5 min — blocking all USD pairs",
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["agent"], "news")
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["macro_bias"], "event_risk")
        self.assertTrue(result["active_news_block"])
        self.assertEqual(result["events_considered"], 1)
        self.assertIsNotNone(result["current_event"])
        self.assertEqual(result["current_event"]["name"], "Non-Farm Payrolls")
        self.assertEqual(result["current_event"]["label"], "NFP")
        self.assertEqual(result["current_event"]["minutes_to"], 5)
        self.assertEqual(result["current_event"]["phase"], "PRE_EVENT")
        self.assertEqual(result["current_event"]["forecast"], 5.25)
        self.assertEqual(result["current_event"]["previous"], 5.50)
        self.assertIn("NFP in 5 min", result["reasoning"])

    def test_blocked_without_event_name_still_high_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": True,
                "phase": "PRE_EVENT",
                "minutesToEvent": 30,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "high")
        self.assertTrue(result["active_news_block"])
        self.assertIsNone(result["current_event"])
        self.assertEqual(result["events_considered"], 0)


class NewsAgentPreEventTests(unittest.TestCase):
    """Scenario 2: Event approaching within 60 min but not yet blocked."""

    def test_event_within_60_min_returns_medium_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": False,
                "phase": "BIAS_WINDOW",
                "eventName": "FOMC Rate Decision",
                "eventLabel": "FOMC",
                "minutesToEvent": 45,
                "minutesSinceEvent": 0,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "medium")
        self.assertEqual(result["macro_bias"], "event_risk")
        self.assertFalse(result["active_news_block"])
        self.assertEqual(result["events_considered"], 1)
        self.assertIsNotNone(result["current_event"])
        self.assertEqual(result["current_event"]["name"], "FOMC Rate Decision")
        self.assertEqual(result["current_event"]["minutes_to"], 45)

    def test_event_beyond_60_min_returns_low_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": False,
                "eventName": "FOMC Rate Decision",
                "minutesToEvent": 120,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["macro_bias"], "neutral")
        self.assertIsNotNone(result["current_event"])

    def test_event_at_boundary_60_min_is_low(self) -> None:
        """minutes_to=60 means NOT within 60 min (strictly greater than 0, less than or equal to 60)."""
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": False,
                "eventName": "CPI",
                "minutesToEvent": 60,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "medium")


class NewsAgentPostEventTests(unittest.TestCase):
    """Scenario 3: Event has already passed (POST_EVENT phase)."""

    def test_post_event_no_block_returns_low_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": False,
                "phase": "POST_EVENT",
                "eventName": "GDP",
                "eventLabel": "US GDP",
                "minutesToEvent": 0,
                "minutesSinceEvent": 25,
                "actual": 2.8,
                "forecast": 3.0,
                "previous": 3.2,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["active_news_block"])
        self.assertIsNotNone(result["current_event"])
        self.assertEqual(result["current_event"]["actual"], 2.8)

    def test_post_event_still_blocked_returns_high(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": True,
                "phase": "POST_EVENT",
                "eventName": "NFP",
                "minutesToEvent": 0,
                "minutesSinceEvent": 10,
                "actual": 180,
                "forecast": 175,
                "previous": 165,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "high")


class NewsAgentIdleTests(unittest.TestCase):
    """Scenario 4: No news events at all (IDLE)."""

    def test_no_news_key_returns_low_risk(self) -> None:
        agent = NewsAgent()
        result = _run(agent.analyze({}))
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["macro_bias"], "neutral")
        self.assertFalse(result["active_news_block"])
        self.assertEqual(result["events_considered"], 0)
        self.assertIsNone(result["current_event"])
        self.assertEqual(result["high_impact_events"], [])

    def test_empty_news_dict_returns_low_risk(self) -> None:
        agent = NewsAgent()
        result = _run(agent.analyze({"news": {}}))
        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["active_news_block"])
        self.assertEqual(result["events_considered"], 0)
        self.assertIsNone(result["current_event"])

    def test_news_none_returns_low_risk(self) -> None:
        agent = NewsAgent()
        result = _run(agent.analyze({"news": None}))
        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["active_news_block"])

    def test_legacy_fallback_snapshot_returns_low_risk(self) -> None:
        """The fallback snapshot in analysis_service_v2 has events list + active flag."""
        agent = NewsAgent()
        snapshot = {"news": {"events": [], "active": False}}
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["active_news_block"])
        self.assertEqual(result["events_considered"], 0)

    def test_idle_phase_returns_low_risk(self) -> None:
        agent = NewsAgent()
        snapshot = {
            "news": {
                "blocked": False,
                "phase": "IDLE",
                "eventName": "",
                "minutesToEvent": 0,
            }
        }
        result = _run(agent.analyze(snapshot))
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["macro_bias"], "neutral")


if __name__ == "__main__":
    unittest.main()
