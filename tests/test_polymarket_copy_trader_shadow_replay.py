import argparse
import importlib.util
import os
import sys
import unittest
from unittest import mock
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
        "min_trader_bucket_samples": 8,
        "min_source_bucket_samples": 30,
        "min_source_trader_bucket_samples": 8,
        "min_market_family_bucket_samples": 12,
        "min_entry_price_band_bucket_samples": 12,
        "min_trader_market_family_bucket_samples": 8,
        "min_trader_entry_price_band_bucket_samples": 8,
        "promotion_hold_hours": 6.0,
        "promotion_hard_demote_profit_factor": 0.35,
        "promotion_hard_demote_net_pnl_usdc": -2.0,
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

    def test_discovery_extracts_slug_from_polymarket_event_button_url(self):
        context = discovery.extract_kreo_context(
            "查看预测市场 https://polymarket.com/event/2026-mens-french-open-winner/"
            "will-alexander-zverev-win-the-2026-mens-french-open?r=min234"
        )

        self.assertEqual(context["marketSlug"], "will-alexander-zverev-win-the-2026-mens-french-open")

    def test_discovery_extracts_ai1000x_chinese_smart_wallet_signal(self):
        text = (
            "⚡ 聪明钱包实时异动 📍 Will Alexander Zverev win the 2026 Men's French Open? "
            "🎯 动作：买入 YES ├ 信号价：$0.08 └ 金额：$741 👛 钱包表现 "
            "├ 钱包：0xe52cd0a2aaace3f759780230409e4bf3a6c901f4 "
            "├ 名称：sharpname ├ Smart Score：90 ├ 回测 PnL：+$34196.45 └ 胜率：52% "
            "查看预测市场 https://polymarket.com/event/2026-mens-french-open-winner/"
            "will-alexander-zverev-win-the-2026-mens-french-open?r=min234"
        )

        signals = discovery.extract_telegram_signals([text], "telegram_telethon", "AI 1000x Polymarket")

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["channelName"], "AI 1000x Polymarket")
        self.assertEqual(signals[0]["side"], "BUY")
        self.assertEqual(signals[0]["outcome"], "YES")
        self.assertEqual(signals[0]["priceCents"], 8.0)
        self.assertEqual(signals[0]["amountUSDC"], 741.0)
        self.assertEqual(signals[0]["smartScore"], 90.0)
        self.assertEqual(signals[0]["marketSlug"], "will-alexander-zverev-win-the-2026-mens-french-open")

    def test_discovery_parses_multiple_telegram_channels(self):
        channels = discovery.parse_telegram_channels(["预测市场内幕钱包监控, AI 1000x Polymarket"])

        self.assertEqual(channels, ["预测市场内幕钱包监控", "AI 1000x Polymarket"])

    def test_discovery_matches_channel_title_with_suffix_icon(self):
        self.assertTrue(
            discovery.channel_title_matches(
                "AI 1000x Polymarket 📢",
                ["预测市场内幕钱包监控", "AI 1000x Polymarket"],
            )
        )

    def test_discovery_resolves_truncated_telegram_wallet_preview(self):
        signals = [{"userName": "edge", "wallet": "", "walletPreview": "0xC8ab...6418"}]
        wallets = ["0xc8ab97a9089a9ff7e6ef0688e6e591a066946418"]

        resolved = discovery.resolve_signal_wallet_previews(signals, wallets)

        self.assertEqual(resolved[0]["wallet"], wallets[0])

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

    def test_summary_keeps_open_samples_as_warning_after_thresholds_pass(self):
        rows = [{"validatedExit": True, "netPnlUSDC": 0.05, "currentPrice": 0.7, "blockers": []} for _ in range(30)]
        rows.append({"validatedExit": False, "netPnlUSDC": 0.01, "currentPrice": 0.7, "blockers": []})

        summary = replay.build_summary(rows, args())

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["blockers"], [])
        self.assertIn("open_or_unresolved_signals_present", summary["warnings"])

    def test_quality_buckets_quarantine_weak_trader_after_min_samples(self):
        rows = [
            {"source": "telegram_telethon", "trader": "weak", "validatedExit": True, "netPnlUSDC": -0.18}
            for _ in range(8)
        ]

        buckets = replay.build_quality_buckets(rows, args())

        self.assertIn("weak", buckets["quarantine"]["traders"])
        self.assertEqual(buckets["byTrader"][0]["status"], "QUARANTINE")

    def test_quality_buckets_split_telegram_channels_as_sources(self):
        rows = [
            {
                "source": "telegram_telethon",
                "channelName": "AI 1000x Polymarket",
                "trader": "source_a",
                "validatedExit": True,
                "netPnlUSDC": -0.05,
            }
            for _ in range(2)
        ] + [
            {
                "source": "telegram_telethon",
                "channelName": "预测市场内幕钱包监控",
                "trader": "source_b",
                "validatedExit": True,
                "netPnlUSDC": 0.05,
            }
            for _ in range(2)
        ]

        buckets = replay.build_quality_buckets(rows, args(min_source_bucket_samples=2))
        source_keys = {row["bucketKey"] for row in buckets["bySource"]}

        self.assertIn("telegram_telethon:ai 1000x polymarket", source_keys)
        self.assertIn("telegram_telethon:预测市场内幕钱包监控", source_keys)

    def test_quality_buckets_promote_micro_scalp_composite_buckets(self):
        rows = [
            {
                "source": "telegram_telethon",
                "trader": "edge",
                "marketFamily": "geopolitics",
                "entryPriceBand": "0.20_0.40",
                "validatedExit": True,
                "currentPrice": 0.31,
                "blockers": [],
                "netPnlUSDC": 0.02,
            }
            for _ in range(8)
        ]

        buckets = replay.build_quality_buckets(rows, args())

        self.assertIn("edge:geopolitics", buckets["promotions"]["traderMarketFamilies"])
        self.assertIn("edge:0.20_0.40", buckets["promotions"]["traderEntryPriceBands"])
        self.assertEqual(buckets["microScalpPolicy"]["promotedCompositeBucketCount"], 2)

    def test_quality_buckets_retain_recent_promotions_during_hold_window(self):
        rows = [
            {
                "source": "telegram_telethon",
                "channelName": "AI 1000x Polymarket",
                "trader": "edge",
                "validatedExit": True,
                "netPnlUSDC": -0.02,
            }
            for _ in range(30)
        ]
        current = replay.build_quality_buckets(rows, args(min_source_bucket_samples=30))
        previous = {
            "bySource": [{
                "bucketType": "source",
                "bucketKey": "telegram_telethon:ai 1000x polymarket",
                "status": "PROMOTABLE",
                "promotionHoldUntilIso": (replay.utc_now() + replay.timedelta(hours=1)).isoformat(),
            }]
        }

        retained = replay.retain_previous_promotions(
            current,
            previous,
            args(
                min_source_bucket_samples=30,
                promotion_hold_hours=6,
                promotion_hard_demote_profit_factor=-1.0,
                promotion_hard_demote_net_pnl_usdc=-2.0,
            ),
        )

        source = retained["bySource"][0]
        self.assertEqual(source["status"], "PROMOTABLE_PROBATION")
        self.assertTrue(source["retainedPromotion"])
        self.assertIn("telegram_telethon:ai 1000x polymarket", retained["promotions"]["sources"])
        self.assertNotIn("telegram_telethon:ai 1000x polymarket", retained["quarantine"]["sources"])

    def test_merge_signals_keeps_prior_rows_and_overwrites_current_duplicate(self):
        previous_rows = [{
            "source": "telegram_telethon",
            "trader": "leader",
            "messageId": 7,
            "marketSlug": "old-market",
            "side": "BUY",
            "outcome": "Yes",
            "signalPrice": 0.4,
            "textPreview": "old",
        }]
        current = [{
            "source": "telegram_telethon",
            "userName": "leader",
            "messageId": 7,
            "marketSlug": "old-market",
            "side": "BUY",
            "outcome": "Yes",
            "priceCents": 45,
            "textPreview": "new",
        }]

        merged = replay.merge_signals(current, previous_rows, 20)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["priceCents"], 45)

    def test_replay_adds_self_discovered_candidates_as_source(self):
        discovery_payload = {
            "shadowCandidates": [{
                "generatedAtIso": "2026-05-24T11:00:00+00:00",
                "trader": "explorer",
                "proxyWallet": "0x0000000000000000000000000000000000000001",
                "marketTitle": "Will SS Lazio win on 2026-05-24?",
                "marketSlug": "sea-laz-pis-2026-05-24-laz",
                "outcome": "Yes",
                "curPrice": 0.60,
            }]
        }

        signals = replay.current_discovery_candidate_signals(discovery_payload, 10)
        row = replay.replay_signal(0, signals[0], [quote()], args())
        buckets = replay.build_quality_buckets([row for _ in range(30)], args(min_source_bucket_samples=30))

        self.assertEqual(signals[0]["source"], "copy_trader_discovery")
        self.assertEqual(signals[0]["channelName"], "self_explore")
        self.assertEqual(row["sourceBucket"], "copy_trader_discovery:self_explore")
        self.assertIn("copy_trader_discovery:self_explore", [item["bucketKey"] for item in buckets["bySource"]])

    def test_merge_signals_sorts_cross_channel_rows_by_date_before_message_id(self):
        rows = replay.merge_signals(
            [
                {
                    "source": "telegram_telethon",
                    "channelName": "AI 1000x Polymarket",
                    "userName": "newer",
                    "messageId": 10,
                    "messageDate": "2026-05-24 06:30:00+00:00",
                    "marketSlug": "newer",
                    "side": "BUY",
                    "outcome": "YES",
                    "priceCents": 50,
                },
                {
                    "source": "telegram_telethon",
                    "channelName": "预测市场内幕钱包监控",
                    "userName": "older",
                    "messageId": 99999,
                    "messageDate": "2026-05-24 06:00:00+00:00",
                    "marketSlug": "older",
                    "side": "BUY",
                    "outcome": "YES",
                    "priceCents": 50,
                },
            ],
            [],
            2,
        )

        self.assertEqual(rows[0]["userName"], "newer")

    def test_merge_signals_keeps_current_telegram_when_prior_backlog_is_full(self):
        previous_rows = [
            {
                "source": "copy_trader_discovery",
                "channelName": "self_explore",
                "trader": f"prior_{index}",
                "messageId": f"self-{index}",
                "messageDate": "2026-05-24T14:59:00+00:00",
                "marketSlug": f"prior-market-{index}",
                "side": "BUY",
                "outcome": "Yes",
                "signalPrice": 0.5,
                "textPreview": "prior",
            }
            for index in range(10)
        ]
        current = [
            {
                "source": "telegram_telethon",
                "channelName": "AI 1000x Polymarket",
                "userName": "ai_source",
                "messageId": 1,
                "messageDate": "2026-05-24 14:50:00+00:00",
                "marketSlug": "ai-market",
                "side": "BUY",
                "outcome": "YES",
                "priceCents": 50,
            },
            {
                "source": "telegram_telethon",
                "channelName": "预测市场内幕钱包监控",
                "userName": "insider_source",
                "messageId": 2,
                "messageDate": "2026-05-24 14:49:00+00:00",
                "marketSlug": "insider-market",
                "side": "BUY",
                "outcome": "YES",
                "priceCents": 50,
            },
        ]

        rows = replay.merge_signals(current, previous_rows, 5)

        self.assertIn("ai_source", [row["userName"] for row in rows])
        self.assertIn("insider_source", [row["userName"] for row in rows])

    def test_replay_inferrs_channel_for_legacy_rows(self):
        ai_row = {"textPreview": "⚡ 聪明钱包实时异动 📍 Market 🎯 动作：买入 YES"}
        old_row = {"textPreview": "🧠 Smart Money 📌 Market 🟢 BUY Yes"}

        self.assertEqual(replay.infer_channel_name(ai_row), "AI 1000x Polymarket")
        self.assertEqual(replay.infer_channel_name(old_row), "预测市场内幕钱包监控")

    def test_discovery_quality_gate_blocks_quarantined_trader(self):
        traders = [{
            "userName": "weak",
            "sourceKinds": ["telegram_channel"],
            "eligibleForShadowCopy": True,
            "blockers": [],
            "warnings": [],
        }]
        gate = discovery.replay_quality_gate({
            "qualityBuckets": {
                "quarantine": {"traders": ["weak"], "sources": [], "sourceTraders": [], "weakBucketCount": 1},
                "byTrader": [{
                    "bucketKey": "weak",
                    "status": "QUARANTINE",
                    "samples": 8,
                    "netPnlUSDC": -1.44,
                    "profitFactor": 0.0,
                    "action": "exclude_from_shadow_candidates",
                }],
            }
        })

        discovery.apply_replay_quality_gate(traders, gate)

        self.assertFalse(traders[0]["eligibleForShadowCopy"])
        self.assertIn("copy_replay_trader_bucket_quarantined", traders[0]["blockers"])
        self.assertEqual(traders[0]["copyReplayQuality"]["status"], "QUARANTINE")

    def test_discovery_promoted_micro_bucket_can_restore_shadow_eligibility(self):
        traders = [{
            "userName": "edge",
            "sourceKinds": ["telegram_channel"],
            "eligibleForShadowCopy": False,
            "currentPositionCount": 2,
            "blockers": ["leaderboard_pnl_not_positive"],
            "warnings": [],
        }]
        gate = {
            "active": True,
            "promotedCompositeTraders": ["edge"],
            "quarantinedTraders": [],
            "weakSources": [],
            "quarantinedSourceTraders": [],
            "byTrader": {},
        }

        discovery.apply_replay_quality_gate(traders, gate)

        self.assertTrue(traders[0]["eligibleForShadowCopy"])
        self.assertIn("copy_replay_promoted_micro_bucket_overrides_broad_score", traders[0]["warnings"])

    def test_discovery_real_wallet_candidate_requires_promoted_micro_bucket(self):
        traders = [{
            "userName": "edge",
            "proxyWallet": "0x0000000000000000000000000000000000000001",
            "copyScore": 90,
            "eligibleForShadowCopy": True,
            "currentPositions": [{
                "title": "Israel ceasefire by Friday?",
                "slug": "israel-ceasefire-by-friday",
                "eventSlug": "israel-ceasefire",
                "outcome": "Yes",
                "curPrice": 0.31,
                "currentValue": 250,
                "percentPnl": 1.0,
            }],
        }]
        policy = {
            "realWalletExecutionAllowed": True,
            "hardBlockers": [],
            "takeProfitPct": 2,
            "takeProfitUSDC": 0.05,
            "stopLossPct": 4,
            "trailingStopPct": 2,
            "maxPositionUSDC": 5,
            "maxDailyLossUSDC": 2,
            "minEntryPrice": 0.04,
            "maxEntryPrice": 0.90,
        }
        gate = {
            "active": True,
            "hasMicroBuckets": True,
            "realWalletRequiresPromotedCompositeBucket": True,
            "promotedTraderMarketFamilies": ["edge:geopolitics"],
            "promotedTraderEntryPriceBands": [],
            "promotedMarketFamilies": [],
            "promotedEntryPriceBands": [],
            "quarantinedMarketFamilies": [],
            "quarantinedEntryPriceBands": [],
            "quarantinedTraderMarketFamilies": [],
            "quarantinedTraderEntryPriceBands": [],
            "byMarketFamily": {},
            "byEntryPriceBand": {},
            "byTraderMarketFamily": {},
            "byTraderEntryPriceBand": {},
        }

        candidates = discovery.build_shadow_candidates(traders, 50, policy, gate)
        blocked_candidates = discovery.build_shadow_candidates(
            traders,
            50,
            policy,
            {**gate, "promotedTraderMarketFamilies": []},
        )
        broad_market_override_candidates = discovery.build_shadow_candidates(
            traders,
            50,
            policy,
            {
                **gate,
                "promotedTraderMarketFamilies": [],
                "promotedTraderEntryPriceBands": ["edge:0.20_0.40"],
                "quarantinedMarketFamilies": ["geopolitics"],
            },
        )

        self.assertTrue(candidates[0]["orderSendAllowed"])
        self.assertEqual(candidates[0]["microScalpSuitability"]["status"], "PROMOTABLE")
        self.assertFalse(blocked_candidates[0]["orderSendAllowed"])
        self.assertIn("copy_replay_micro_bucket_not_promoted", blocked_candidates[0]["riskPlan"]["blockers"])
        self.assertTrue(broad_market_override_candidates[0]["orderSendAllowed"])
        self.assertIn(
            "copy_replay_broad_market_bucket_weak_but_specific_micro_bucket_promoted",
            broad_market_override_candidates[0]["riskPlan"]["microScalpWarnings"],
        )

    def test_discovery_source_scoped_micro_live_requires_promoted_matched_source(self):
        policy = {
            "realWalletExecutionAllowed": True,
            "hardBlockers": [],
            "takeProfitPct": 2,
            "takeProfitUSDC": 0.05,
            "stopLossPct": 4,
            "trailingStopPct": 2,
            "maxPositionUSDC": 5,
            "maxDailyLossUSDC": 2,
            "minEntryPrice": 0.04,
            "maxEntryPrice": 0.90,
        }
        position = {
            "title": "LoL: Ninjas in Pyjamas vs EDward Gaming (BO5) - LPL Play-In",
            "slug": "lol-nip-edg-2026-05-24",
            "eventSlug": "lol-nip-edg-2026-05-24",
            "outcome": "EDward Gaming",
            "curPrice": 0.655,
            "currentValue": 250,
            "percentPnl": 1.0,
        }
        traders = [
            {
                "userName": "edge",
                "proxyWallet": "0x0000000000000000000000000000000000000001",
                "copyScore": 90,
                "eligibleForShadowCopy": True,
                "telegramSignals": [{
                    "source": "telegram_telethon",
                    "channelName": "AI 1000x Polymarket",
                    "marketSlug": "lol-nip-edg-2026-05-24",
                    "outcome": "EDward Gaming",
                }],
                "currentPositions": [position],
            },
            {
                "userName": "weak",
                "proxyWallet": "0x0000000000000000000000000000000000000002",
                "copyScore": 90,
                "eligibleForShadowCopy": True,
                "telegramSignals": [{
                    "source": "telegram_telethon",
                    "channelName": "预测市场内幕钱包监控",
                    "marketSlug": "lol-nip-edg-2026-05-24",
                    "outcome": "EDward Gaming",
                }],
                "currentPositions": [position],
            },
        ]
        gate = {
            "active": True,
            "hasMicroBuckets": True,
            "realWalletRequiresPromotedCompositeBucket": True,
            "promotedSources": ["telegram_telethon:ai 1000x polymarket"],
            "promotedSourceTraders": [],
            "weakSources": ["telegram_telethon:预测市场内幕钱包监控"],
            "quarantinedSourceTraders": [],
            "promotedTraderMarketFamilies": ["edge:other", "weak:other"],
            "promotedTraderEntryPriceBands": [],
            "promotedMarketFamilies": [],
            "promotedEntryPriceBands": [],
            "quarantinedMarketFamilies": [],
            "quarantinedEntryPriceBands": [],
            "quarantinedTraderMarketFamilies": [],
            "quarantinedTraderEntryPriceBands": [],
            "bySource": {},
            "bySourceTrader": {},
            "byMarketFamily": {},
            "byEntryPriceBand": {},
            "byTraderMarketFamily": {},
            "byTraderEntryPriceBand": {},
        }

        candidates = discovery.build_shadow_candidates(traders, 50, policy, gate)
        by_trader = {row["trader"]: row for row in candidates}

        self.assertTrue(by_trader["edge"]["orderSendAllowed"])
        self.assertTrue(by_trader["edge"]["microScalpSuitability"]["sourceAttribution"]["signalPositionMatched"])
        self.assertFalse(by_trader["weak"]["orderSendAllowed"])
        self.assertIn("copy_replay_source_bucket_quarantined", by_trader["weak"]["riskPlan"]["blockers"])
        self.assertIn("copy_replay_source_bucket_not_promoted", by_trader["weak"]["riskPlan"]["blockers"])

    def test_discovery_promoted_source_trader_cannot_override_weak_parent_source(self):
        policy = {
            "realWalletExecutionAllowed": True,
            "hardBlockers": [],
            "takeProfitPct": 2,
            "takeProfitUSDC": 0.05,
            "stopLossPct": 4,
            "trailingStopPct": 2,
            "maxPositionUSDC": 5,
            "maxDailyLossUSDC": 2,
            "minEntryPrice": 0.04,
            "maxEntryPrice": 0.90,
        }
        traders = [{
            "userName": "edge",
            "proxyWallet": "0x0000000000000000000000000000000000000001",
            "copyScore": 90,
            "eligibleForShadowCopy": True,
            "telegramSignals": [{
                "source": "telegram_telethon",
                "channelName": "weak channel",
                "marketSlug": "lol-nip-edg-2026-05-24",
                "outcome": "EDward Gaming",
            }],
            "currentPositions": [{
                "title": "LoL: Ninjas in Pyjamas vs EDward Gaming (BO5) - LPL Play-In",
                "slug": "lol-nip-edg-2026-05-24",
                "eventSlug": "lol-nip-edg-2026-05-24",
                "outcome": "EDward Gaming",
                "curPrice": 0.655,
                "currentValue": 250,
                "percentPnl": 1.0,
            }],
        }]
        gate = {
            "active": True,
            "hasMicroBuckets": True,
            "realWalletRequiresPromotedCompositeBucket": True,
            "promotedSources": [],
            "promotedSourceTraders": ["telegram_telethon:weak channel:edge"],
            "weakSources": ["telegram_telethon:weak channel"],
            "quarantinedSourceTraders": [],
            "promotedTraderMarketFamilies": ["edge:other"],
            "promotedTraderEntryPriceBands": [],
            "promotedMarketFamilies": [],
            "promotedEntryPriceBands": [],
            "quarantinedMarketFamilies": [],
            "quarantinedEntryPriceBands": [],
            "quarantinedTraderMarketFamilies": [],
            "quarantinedTraderEntryPriceBands": [],
            "bySource": {},
            "bySourceTrader": {},
            "byMarketFamily": {},
            "byEntryPriceBand": {},
            "byTraderMarketFamily": {},
            "byTraderEntryPriceBand": {},
        }

        candidates = discovery.build_shadow_candidates(traders, 50, policy, gate)

        self.assertFalse(candidates[0]["orderSendAllowed"])
        self.assertTrue(candidates[0]["microScalpSuitability"]["promotedSourceTrader"])
        self.assertIn("copy_replay_source_bucket_quarantined", candidates[0]["riskPlan"]["blockers"])
        self.assertIn(
            "copy_replay_source_trader_promotion_ignored_because_parent_source_quarantined",
            candidates[0]["riskPlan"]["microScalpWarnings"],
        )

    def test_discovery_self_explore_source_can_promote_without_telegram_match(self):
        traders = [{
            "userName": "explorer",
            "proxyWallet": "0x0000000000000000000000000000000000000001",
            "copyScore": 90,
            "eligibleForShadowCopy": True,
            "telegramSignals": [],
            "currentPositions": [{
                "title": "Will SS Lazio win on 2026-05-24?",
                "slug": "sea-laz-pis-2026-05-24-laz",
                "eventSlug": "sea-laz-pis-2026-05-24",
                "outcome": "Yes",
                "curPrice": 0.60,
                "currentValue": 250,
                "percentPnl": 1.0,
            }],
        }]
        policy = {
            "realWalletExecutionAllowed": True,
            "hardBlockers": [],
            "takeProfitPct": 2,
            "takeProfitUSDC": 0.05,
            "stopLossPct": 4,
            "trailingStopPct": 2,
            "maxPositionUSDC": 5,
            "maxDailyLossUSDC": 2,
            "minEntryPrice": 0.04,
            "maxEntryPrice": 0.90,
        }
        gate = {
            "active": True,
            "hasMicroBuckets": True,
            "realWalletRequiresPromotedCompositeBucket": True,
            "promotedSources": ["copy_trader_discovery:self_explore"],
            "promotedSourceTraders": ["copy_trader_discovery:self_explore:explorer"],
            "weakSources": [],
            "quarantinedSourceTraders": [],
            "promotedTraderMarketFamilies": ["explorer:sports"],
            "promotedTraderEntryPriceBands": [],
            "promotedMarketFamilies": [],
            "promotedEntryPriceBands": [],
            "quarantinedMarketFamilies": [],
            "quarantinedEntryPriceBands": [],
            "quarantinedTraderMarketFamilies": [],
            "quarantinedTraderEntryPriceBands": [],
            "bySource": {},
            "bySourceTrader": {},
            "byMarketFamily": {},
            "byEntryPriceBand": {},
            "byTraderMarketFamily": {},
            "byTraderEntryPriceBand": {},
        }

        candidates = discovery.build_shadow_candidates(traders, 50, policy, gate)

        self.assertTrue(candidates[0]["orderSendAllowed"])
        self.assertTrue(candidates[0]["microScalpSuitability"]["sourceAttribution"]["selfDiscoveryPositionMatched"])
        self.assertIn("copy_trader_discovery:self_explore", candidates[0]["microScalpSuitability"]["sourceAttribution"]["sourceKeys"])

    def test_source_quarantine_blocks_promoted_micro_candidate(self):
        traders = [{
            "userName": "edge",
            "proxyWallet": "0xedge",
            "copyScore": 90,
            "eligibleForShadowCopy": True,
            "sourceKinds": ["telegram_telethon:weak channel"],
            "telegramSignals": [{
                "source": "telegram_telethon",
                "channelName": "weak channel",
                "marketSlug": "sea-laz-pis-2026-05-24-laz",
                "outcome": "Yes",
            }],
            "currentPositions": [{
                "title": "Will SS Lazio win on 2026-05-24?",
                "slug": "sea-laz-pis-2026-05-24-laz",
                "eventSlug": "sea-laz-pis-2026-05-24",
                "outcome": "Yes",
                "curPrice": 0.60,
                "currentValue": 250,
                "percentPnl": 1.0,
            }],
        }]
        policy = {
            "realWalletExecutionAllowed": True,
            "hardBlockers": [],
            "takeProfitPct": 2,
            "takeProfitUSDC": 0.05,
            "stopLossPct": 4,
            "trailingStopPct": 2,
            "maxPositionUSDC": 5,
            "maxDailyLossUSDC": 2,
            "minEntryPrice": 0.04,
            "maxEntryPrice": 0.90,
        }
        gate = {
            "active": True,
            "hasMicroBuckets": True,
            "realWalletRequiresPromotedCompositeBucket": True,
            "promotedSources": [],
            "promotedSourceTraders": ["telegram_telethon:weak channel:edge"],
            "weakSources": ["telegram_telethon:weak channel"],
            "quarantinedSourceTraders": [],
            "promotedTraderMarketFamilies": ["edge:sports"],
            "promotedTraderEntryPriceBands": [],
            "promotedMarketFamilies": [],
            "promotedEntryPriceBands": [],
            "quarantinedMarketFamilies": [],
            "quarantinedEntryPriceBands": [],
            "quarantinedTraderMarketFamilies": [],
            "quarantinedTraderEntryPriceBands": [],
            "bySource": {},
            "bySourceTrader": {},
            "byMarketFamily": {},
            "byEntryPriceBand": {},
            "byTraderMarketFamily": {},
            "byTraderEntryPriceBand": {},
        }

        candidates = discovery.build_shadow_candidates(traders, 50, policy, gate)

        self.assertFalse(candidates[0]["orderSendAllowed"])
        self.assertEqual(candidates[0]["microScalpSuitability"]["status"], "QUARANTINE")
        self.assertIn("copy_replay_source_bucket_quarantined", candidates[0]["riskPlan"]["blockers"])

    def test_profit_lock_blocks_when_recent_loss_wave_erases_peak(self):
        rows = []
        pnl_values = [0.2, 0.2, 0.2, -0.7]
        for index, pnl in enumerate(pnl_values, start=1):
            rows.append({
                "sequence": index,
                "messageDate": f"2026-05-2{index}T00:00:00+00:00",
                "currentPrice": 0.5,
                "validatedExit": True,
                "netPnlUSDC": pnl,
                "blockers": [],
            })

        summary = replay.build_summary(
            rows,
            args(
                min_shadow_replay_trades=1,
                min_shadow_profit_factor=0.0,
                min_shadow_net_pnl_usdc=-999.0,
                profit_lock_min_peak_usdc=0.25,
                profit_lock_max_drawdown_usdc=0.25,
                profit_lock_max_drawdown_pct=60.0,
            ),
        )

        self.assertTrue(summary["profitLock"]["active"])
        self.assertIn("shadow_replay_profit_lock_drawdown", summary["blockers"])

    def test_discovery_wallet_policy_allows_source_scoped_gate_without_global_replay(self):
        wallet_args = argparse.Namespace(
            runtime_dir="/tmp/quantgod-test-runtime",
            dashboard_dir="/tmp/quantgod-test-dashboard",
            real_wallet_enabled="true",
            real_wallet_auto_unlock="true",
            real_wallet_require_telegram="true",
            min_shadow_replay_trades=30,
            min_shadow_profit_factor=1.10,
            min_shadow_net_pnl_usdc=0.01,
            min_walk_forward_batches=3,
            min_walk_forward_pass_rate_pct=60.0,
            real_wallet_take_profit_pct=2.0,
            real_wallet_take_profit_usdc=0.05,
            real_wallet_stop_loss_pct=4.0,
            real_wallet_trailing_stop_pct=2.0,
            real_wallet_max_position_usdc=5.0,
            real_wallet_max_daily_loss_usdc=2.0,
            real_wallet_max_open_positions=3,
            real_wallet_min_entry_price=0.04,
            real_wallet_max_entry_price=0.90,
        )
        validation = {
            "shadowReplay": {"passed": False},
            "walkForward": {"passed": False},
        }
        gate = {
            "active": True,
            "promotedSources": ["telegram_telethon:ai 1000x polymarket"],
            "promotedSourceTraders": [],
            "promotedCompositeBucketCount": 2,
            "weakSources": ["telegram_telethon:预测市场内幕钱包监控"],
        }
        env = {
            "QG_POLYMARKET_REAL_EXECUTION": "true",
            "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
            "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
            "QG_POLYMARKET_PRIVATE_KEY": "unit-test-secret",
            "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
        }

        with mock.patch.dict(os.environ, env, clear=False):
            policy = discovery.wallet_risk_policy(wallet_args, True, validation, gate)

        self.assertTrue(policy["sourceScopedMicroLiveGatePassed"])
        self.assertTrue(policy["realWalletExecutionAllowed"])
        self.assertNotIn("shadow_replay_not_validated", policy["hardBlockers"])
        self.assertNotIn("walk_forward_not_validated", policy["hardBlockers"])
        self.assertIn("global_shadow_replay_not_validated_but_source_scope_promoted", policy["warnings"])

    def test_discovery_wallet_policy_blocks_source_scope_when_parent_source_quarantined(self):
        wallet_args = argparse.Namespace(
            runtime_dir="/tmp/quantgod-test-runtime",
            dashboard_dir="/tmp/quantgod-test-dashboard",
            real_wallet_enabled="true",
            real_wallet_auto_unlock="true",
            real_wallet_require_telegram="true",
            min_shadow_replay_trades=30,
            min_shadow_profit_factor=1.10,
            min_shadow_net_pnl_usdc=0.01,
            min_walk_forward_batches=3,
            min_walk_forward_pass_rate_pct=60.0,
            real_wallet_take_profit_pct=2.0,
            real_wallet_take_profit_usdc=0.05,
            real_wallet_stop_loss_pct=4.0,
            real_wallet_trailing_stop_pct=2.0,
            real_wallet_max_position_usdc=5.0,
            real_wallet_max_daily_loss_usdc=2.0,
            real_wallet_max_open_positions=3,
            real_wallet_min_entry_price=0.04,
            real_wallet_max_entry_price=0.90,
        )
        validation = {
            "shadowReplay": {"passed": False},
            "walkForward": {"passed": False},
        }
        gate = {
            "active": True,
            "promotedSources": [],
            "promotedSourceTraders": ["telegram_telethon:weak channel:edge"],
            "promotedCompositeBucketCount": 2,
            "weakSources": ["telegram_telethon:weak channel"],
        }
        env = {
            "QG_POLYMARKET_REAL_EXECUTION": "true",
            "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
            "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
            "QG_POLYMARKET_PRIVATE_KEY": "unit-test-secret",
            "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
        }

        with mock.patch.dict(os.environ, env, clear=False):
            policy = discovery.wallet_risk_policy(wallet_args, True, validation, gate)

        self.assertFalse(policy["sourceScopedMicroLiveGatePassed"])
        self.assertFalse(policy["realWalletExecutionAllowed"])
        self.assertIn("source_scoped_promoted_parent_source_quarantined", policy["hardBlockers"])
        self.assertTrue(policy["sourceScopedMicroLiveGate"]["quarantinedSourceScopeBlocked"])
        self.assertFalse(policy["sourceScopedMicroLiveGate"]["ignoresQuarantinedSources"])

    def test_discovery_wallet_policy_allows_source_trader_gate_without_promoted_source(self):
        wallet_args = argparse.Namespace(
            runtime_dir="/tmp/quantgod-test-runtime",
            dashboard_dir="/tmp/quantgod-test-dashboard",
            real_wallet_enabled="true",
            real_wallet_auto_unlock="true",
            real_wallet_require_telegram="true",
            min_shadow_replay_trades=30,
            min_shadow_profit_factor=1.10,
            min_shadow_net_pnl_usdc=0.01,
            min_walk_forward_batches=3,
            min_walk_forward_pass_rate_pct=60.0,
            real_wallet_take_profit_pct=2.0,
            real_wallet_take_profit_usdc=0.05,
            real_wallet_stop_loss_pct=4.0,
            real_wallet_trailing_stop_pct=2.0,
            real_wallet_max_position_usdc=5.0,
            real_wallet_max_daily_loss_usdc=2.0,
            real_wallet_max_open_positions=3,
            real_wallet_min_entry_price=0.04,
            real_wallet_max_entry_price=0.90,
        )
        validation = {
            "shadowReplay": {"passed": False},
            "walkForward": {"passed": False},
        }
        gate = {
            "active": True,
            "promotedSources": [],
            "promotedSourceTraders": ["copy_trader_discovery:self_explore:explorer"],
            "promotedCompositeBucketCount": 2,
            "weakSources": [],
        }
        env = {
            "QG_POLYMARKET_REAL_EXECUTION": "true",
            "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
            "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
            "QG_POLYMARKET_PRIVATE_KEY": "unit-test-secret",
            "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
        }

        with mock.patch.dict(os.environ, env, clear=False):
            policy = discovery.wallet_risk_policy(wallet_args, True, validation, gate)

        self.assertTrue(policy["sourceScopedMicroLiveGatePassed"])
        self.assertTrue(policy["realWalletExecutionAllowed"])


if __name__ == "__main__":
    unittest.main()
