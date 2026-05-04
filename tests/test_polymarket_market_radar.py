import importlib.util
import json
import sys
import tempfile
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

    def test_geopolitical_markets_are_not_misclassified_as_sports(self):
        event = {
            "id": "event-geo",
            "title": "Russia x Ukraine ceasefire by end of 2026?",
            "category": "Sports",
            "tags": ["Sports"],
            "markets": [{
                "id": "market-geo",
                "question": "Russia x Ukraine ceasefire by end of 2026?",
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

        row = radar.flatten_event(event, min_volume=5000, min_liquidity=1000)[0]

        self.assertEqual(row["category"], "politics")
        self.assertEqual(row["strictEdgeFilter"], {"applies": False})
        self.assertNotEqual(row["suggestedShadowTrack"], "poly_sports_edge_filter_strict_score_liquidity_v2")

    def test_short_crypto_tokens_do_not_match_inside_common_words(self):
        event = {
            "id": "event-sports",
            "title": "Will Bayern Munich win the 2025-26 Champions League?",
            "category": "Sports",
            "markets": [{
                "id": "market-sports",
                "question": "Will Bayern Munich win the 2025-26 Champions League?",
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

        row = radar.flatten_event(event, min_volume=5000, min_liquidity=1000)[0]

        self.assertEqual(row["category"], "sports")
        self.assertNotEqual(row["category"], "crypto")

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
                "clobStatus": "SKIPPED",
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
                "clobStatus": "OK",
                "aiRuleScore": 80,
                "liquidity": 50000,
                "volume24h": 20000,
                "suggestedShadowTrack": "poly_sports_edge_filter_strict_score_liquidity_v2",
            },
        ]
        args = SimpleNamespace(queue_risk="low,medium", queue_min_score=45, queue_top=10)

        queue = worker.build_candidate_queue(rows, args, "2026-05-02T00:00:00+00:00", "run")

        self.assertEqual([item["marketId"] for item in queue], ["ready"])

    def test_worker_queue_requires_verified_clob_depth(self):
        rows = [{
            "marketId": "unchecked",
            "question": "Unchecked market",
            "recommendedAction": "SHADOW_REVIEW",
            "risk": "low",
            "clobStatus": "NOT_CHECKED_LIMIT",
            "aiRuleScore": 90,
            "liquidity": 50000,
            "volume24h": 20000,
            "suggestedShadowTrack": "poly_high_liquidity_divergence_shadow_v1",
        }]
        args = SimpleNamespace(queue_risk="low,medium", queue_min_score=45, queue_top=10)

        self.assertEqual(worker.build_candidate_queue(rows, args, "2026-05-02T00:00:00+00:00", "run"), [])

    def test_worker_stale_cache_fallback_is_review_only(self):
        cache = {
            "markets": {
                "m1": {
                    "marketId": "m1",
                    "question": "Cached market",
                    "category": "sports",
                    "risk": "low",
                    "suggestedShadowTrack": "poly_sports_edge_filter_strict_score_liquidity_v2",
                    "lastProbability": 62.5,
                    "lastAiRuleScore": 80,
                    "lastLiquidity": 50000,
                    "lastVolume24h": 20000,
                    "clobStatus": "OK",
                    "clobDepthScore": 60,
                    "staleCycles": 1,
                }
            }
        }

        rows = worker.stale_rows_from_trend_cache(cache, "2026-05-04T00:00:00+00:00", "run", 10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recommendedAction"], "OBSERVE_ONLY")
        self.assertEqual(rows[0]["trendDirection"], "stale_cache")

    def test_worker_main_uses_stale_cache_after_gamma_error(self):
        original_parse_args = worker.parse_args
        original_build_gamma_snapshot = worker.build_gamma_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            dashboard_dir = Path(tmp) / "dashboard"
            dashboard_dir.mkdir(parents=True)
            (dashboard_dir / worker.TREND_CACHE_NAME).write_text(json.dumps({
                "markets": {
                    "m1": {
                        "marketId": "m1",
                        "question": "Cached market",
                        "category": "sports",
                        "risk": "low",
                        "lastAiRuleScore": 80,
                        "staleCycles": 0,
                    }
                }
            }), encoding="utf-8")
            worker.parse_args = lambda: SimpleNamespace(
                runtime_dir=str(runtime_dir),
                dashboard_dir=str(dashboard_dir),
                endpoint="https://example.invalid",
                limit=1,
                top=10,
                min_volume=0,
                min_liquidity=0,
                timeout=1,
                cycles=1,
                max_cycles=1,
                interval_seconds=0,
                queue_top=10,
                queue_min_score=45,
                queue_risk="low,medium",
                stale_retention_cycles=12,
                input_radar="",
                skip_clob_depth=True,
                clob_depth_limit=0,
                clob_timeout=1,
            )
            worker.build_gamma_snapshot = lambda args: {
                "status": "ERROR",
                "generatedAt": "2026-05-04T00:00:00+00:00",
                "summary": {},
                "radar": [],
                "error": "URLError: DNS",
            }
            try:
                self.assertEqual(worker.main(), 0)
                payload = json.loads((dashboard_dir / worker.WORKER_NAME).read_text(encoding="utf-8"))
            finally:
                worker.parse_args = original_parse_args
                worker.build_gamma_snapshot = original_build_gamma_snapshot

        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["cycles"][0]["status"], "STALE_CACHE")
        self.assertEqual(payload["summary"]["candidateQueueSize"], 0)

    def test_clob_wide_spread_blocks_shadow_review_queue_entry(self):
        original_fetch = radar.fetch_order_book
        original_summary = radar.summarize_order_book
        radar.fetch_order_book = lambda token_id, timeout: {"status": "OK"}
        radar.summarize_order_book = lambda book: {
            "clobStatus": "OK",
            "clobBestBid": 0.01,
            "clobBestAsk": 0.99,
            "clobMidpoint": 0.5,
            "clobSpread": 0.98,
            "clobLiquidityUsd": 100000.0,
            "clobDepthScore": 65.0,
        }
        try:
            rows = [{
                "marketId": "wide-spread",
                "category": "politics",
                "risk": "low",
                "riskFlags": [],
                "recommendedAction": "SHADOW_REVIEW",
                "aiRuleScore": 92,
                "yesTokenId": "yes-token",
            }]

            radar.enrich_clob_depth(rows, limit=1, timeout=1.0, skip=False)

            self.assertEqual(rows[0]["recommendedAction"], "OBSERVE_ONLY")
            self.assertEqual(rows[0]["risk"], "medium")
            self.assertIn("clob_spread_wide", rows[0]["riskFlags"])
            self.assertLess(rows[0]["aiRuleScore"], 92)
        finally:
            radar.fetch_order_book = original_fetch
            radar.summarize_order_book = original_summary


if __name__ == "__main__":
    unittest.main()
