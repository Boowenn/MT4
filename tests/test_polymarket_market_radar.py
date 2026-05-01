import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

RADAR_SPEC = importlib.util.spec_from_file_location("build_polymarket_market_radar", TOOLS_DIR / "build_polymarket_market_radar.py")
radar = importlib.util.module_from_spec(RADAR_SPEC)
assert RADAR_SPEC.loader is not None
RADAR_SPEC.loader.exec_module(radar)

WORKER_SPEC = importlib.util.spec_from_file_location("run_polymarket_radar_worker_v2", TOOLS_DIR / "run_polymarket_radar_worker_v2.py")
worker = importlib.util.module_from_spec(WORKER_SPEC)
assert WORKER_SPEC.loader is not None
WORKER_SPEC.loader.exec_module(worker)


class PolymarketMarketRadarTests(unittest.TestCase):
    def test_sports_edge_filter_quarantines_weak_shadow_candidates(self):
        event = {
            "id": "event-1",
            "title": "Will Arsenal win the 2025-26 Champions League?",
            "category": "Sports",
            "markets": [{
                "id": "market-1",
                "question": "Will Arsenal win the 2025-26 Champions League?",
                "active": True,
                "closed": False,
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["0.55","0.45"]',
                "clobTokenIds": '["yes-token","no-token"]',
                "volumeNum": 30000,
                "volume24hr": 1000,
                "liquidityNum": 2000,
                "acceptingOrders": True,
                "spread": 0.02,
            }],
        }

        rows = radar.flatten_event(event, min_volume=5000, min_liquidity=1000)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["category"], "sports")
        self.assertEqual(row["recommendedAction"], "OBSERVE_ONLY")
        self.assertEqual(row["suggestedShadowTrack"], "poly_sports_edge_filter_quarantine_shadow_v2")
        self.assertFalse(row["strictEdgeFilter"]["passed"])
        self.assertIn("strict_edge_filter_volume24h_low", row["riskFlags"])
        self.assertIn("strict_edge_filter_liquidity_low", row["riskFlags"])
        self.assertIn("strict_edge_filter_divergence_low", row["riskFlags"])

    def test_sports_edge_filter_passes_only_strict_shadow_candidates(self):
        event = {
            "id": "event-2",
            "title": "Will Arsenal win the 2025-26 Champions League?",
            "category": "Sports",
            "markets": [{
                "id": "market-2",
                "question": "Will Arsenal win the 2025-26 Champions League?",
                "active": True,
                "closed": False,
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["0.72","0.28"]',
                "clobTokenIds": '["yes-token","no-token"]',
                "volumeNum": 150000,
                "volume24hr": 9000,
                "liquidityNum": 12000,
                "acceptingOrders": True,
                "spread": 0.02,
            }],
        }

        rows = radar.flatten_event(event, min_volume=5000, min_liquidity=1000)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["recommendedAction"], "SHADOW_REVIEW")
        self.assertEqual(row["suggestedShadowTrack"], "poly_sports_edge_filter_strict_score_liquidity_v2")
        self.assertTrue(row["strictEdgeFilter"]["passed"])
        self.assertEqual(row["strictEdgeFilter"]["blockers"], [])

    def test_worker_queue_ignores_non_shadow_review_actions(self):
        rows = [
            {
                "marketId": "quarantine",
                "question": "Weak sports route",
                "recommendedAction": "OBSERVE_ONLY",
                "risk": "low",
                "aiRuleScore": 80,
                "liquidity": 50000,
                "volume24h": 20000,
                "suggestedShadowTrack": "poly_sports_edge_filter_quarantine_shadow_v2",
            },
            {
                "marketId": "ready",
                "question": "Strict sports route",
                "recommendedAction": "SHADOW_REVIEW",
                "risk": "low",
                "aiRuleScore": 80,
                "liquidity": 50000,
                "volume24h": 20000,
                "suggestedShadowTrack": "poly_sports_edge_filter_strict_score_liquidity_v2",
            },
        ]
        args = SimpleNamespace(queue_risk="low,medium", queue_min_score=45, queue_top=10)

        queue = worker.build_candidate_queue(rows, args, "2026-05-02T00:00:00+00:00", "run")

        self.assertEqual([item["marketId"] for item in queue], ["ready"])


if __name__ == "__main__":
    unittest.main()
