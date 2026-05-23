import argparse
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPLAY_PATH = ROOT / "tools" / "build_polymarket_copy_trader_shadow_replay.py"
DISCOVERY_PATH = ROOT / "tools" / "build_polymarket_copy_trader_discovery.py"

replay_spec = importlib.util.spec_from_file_location("build_polymarket_copy_trader_shadow_replay", REPLAY_PATH)
replay = importlib.util.module_from_spec(replay_spec)
assert replay_spec and replay_spec.loader
sys.modules[replay_spec.name] = replay
replay_spec.loader.exec_module(replay)

discovery_spec = importlib.util.spec_from_file_location("build_polymarket_copy_trader_discovery", DISCOVERY_PATH)
discovery = importlib.util.module_from_spec(discovery_spec)
assert discovery_spec and discovery_spec.loader
sys.modules[discovery_spec.name] = discovery
discovery_spec.loader.exec_module(discovery)


def args(**overrides):
    defaults = {
        "follow_slippage_cents": 1.0,
        "take_profit_pct": 35.0,
        "stop_loss_pct": 18.0,
        "min_entry_price": 0.04,
        "max_entry_price": 0.90,
        "min_match_score": 0.42,
        "stake_usdc": 1.0,
        "min_shadow_replay_trades": 30,
        "min_shadow_profit_factor": 1.10,
        "min_shadow_net_pnl_usdc": 0.01,
        "walk_forward_batches": 3,
        "min_walk_forward_pass_rate_pct": 60.0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def quote(**overrides):
    payload = {
        "event_title": "Serie A",
        "question": "Will SS Lazio win on 2026-05-24?",
        "slug": "sea-laz-pis-2026-05-24-laz",
        "event_slug": "",
        "url": "https://polymarket.com/event/sea-laz-pis-2026-05-24-laz",
        "end_date": "2026-05-24T13:00:00Z",
        "active": True,
        "closed": False,
        "outcomes": ["Yes", "No"],
        "prices": {"yes": 0.60, "no": 0.40},
        "raw_score_text": "Serie A Will SS Lazio win on 2026-05-24? sea-laz-pis-2026-05-24-laz",
    }
    payload.update(overrides)
    return replay.MarketQuote(**payload)


class PolymarketCopyTraderShadowReplayTests(unittest.TestCase):
    def test_discovery_extracts_kreo_market_slug_from_button_url(self):
        context = discovery.extract_kreo_context(
            "⚡ Trade on Kreo https://t.me/KreoPolyBot?start=slug_predictmon--sea-laz-pis-2026-05-24-laz"
        )

        self.assertEqual(context["marketSlug"], "sea-laz-pis-2026-05-24-laz")
        self.assertEqual(context["marketSlugs"], ["sea-laz-pis-2026-05-24-laz"])

    def test_exact_slug_match_can_infer_yes_price_for_team_outcome(self):
        signal = {
            "side": "BUY",
            "outcome": "Lazio",
            "priceCents": 40,
            "marketSlug": "predictmon--sea-laz-pis-2026-05-24-laz",
            "textPreview": (
                "🧠 Smart Money 📌 Will SS Lazio win on 2026-05-24? "
                "📅 Resolves: May 24, 2026 🟢 BUY Lazio ├ Amount: $10.00 ├ Price: 40¢ "
                "👤 trader | Rank #1 | 0x1234...abcd"
            ),
        }

        row = replay.replay_signal(0, signal, [quote()], args())

        self.assertEqual(row["matchScore"], 1.0)
        self.assertEqual(row["currentPrice"], 0.60)
        self.assertTrue(row["matchedOutcome"].startswith("yes_inferred"))
        self.assertTrue(row["validatedExit"])
        self.assertEqual(row["exitReason"], "TAKE_PROFIT")
        self.assertGreater(row["netPnlUSDC"], 0)

    def test_sell_signal_stays_blocked_even_when_market_matches(self):
        signal = {
            "side": "SELL",
            "outcome": "No",
            "priceCents": 42,
            "marketSlug": "sea-laz-pis-2026-05-24-laz",
            "textPreview": "📌 Will SS Lazio win on 2026-05-24? 📅 Resolves: May 24, 2026 🔴 SELL No",
        }

        row = replay.replay_signal(0, signal, [quote()], args())

        self.assertIn("non_buy_signal_not_copyable", row["blockers"])
        self.assertFalse(row["validatedExit"])

    def test_walk_forward_passes_only_after_three_positive_batches(self):
        rows = [{"validatedExit": True, "netPnlUSDC": 0.05} for _ in range(30)]

        summary = replay.build_summary(rows, args())
        walk_forward = replay.build_walk_forward(rows, args())

        self.assertTrue(summary["passed"])
        self.assertTrue(walk_forward["passed"])
        self.assertEqual(walk_forward["batches"], 3)
        self.assertEqual(walk_forward["passRatePct"], 100.0)


if __name__ == "__main__":
    unittest.main()
