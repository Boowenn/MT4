import tempfile
import unittest
from pathlib import Path

from tools.strategy_json.schema import ALLOWED_STRATEGY_FAMILIES
from tools.strategy_ga.fitness import evidence_metrics, score_seed
from tools.strategy_json.schema import base_strategy_seed
from tools.usdjpy_strategy_backtest.report import build_sample, run_backtest, status
from tools.usdjpy_strategy_backtest.schema import equity_path, report_path, trades_path
from tools.usdjpy_strategy_backtest.sqlite_store import connect


class USDJPYStrategyBacktestTests(unittest.TestCase):
    def test_sample_and_run_write_usdjpy_backtest_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            sample = build_sample(runtime_dir, overwrite=True)
            self.assertEqual(sample["symbol"], "USDJPYc")
            self.assertGreaterEqual(sample["barCount"], 100)

            report = run_backtest(runtime_dir, write=True)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["symbol"], "USDJPYc")
            self.assertEqual(report["singleSourceOfTruth"], "STRATEGY_JSON_USDJPY_SQLITE_BACKTEST")
            self.assertFalse(report["safety"]["orderSendAllowed"])
            self.assertFalse(report["safety"]["livePresetMutationAllowed"])
            self.assertIn("netR", report["metrics"])
            self.assertIn("profitFactor", report["metrics"])
            self.assertIn("maxDrawdownR", report["metrics"])
            self.assertTrue(report_path(runtime_dir).exists())
            self.assertTrue(trades_path(runtime_dir).exists())
            self.assertTrue(equity_path(runtime_dir).exists())

            current = status(runtime_dir)
            self.assertEqual(current["barCounts"]["H1"], sample["barCount"])
            self.assertEqual(current["latestReport"]["schema"], "quantgod.strategy_backtest.report.v1")
            with connect(runtime_dir) as conn:
                run_rows = conn.execute("SELECT COUNT(*) AS count FROM strategy_runs").fetchone()
                self.assertGreaterEqual(int(run_rows["count"]), 1)
                self.assertEqual(report["engine"]["coverage"], "ALL_SUPPORTED_USDJPY_SHADOW_FAMILIES")
                self.assertIn("costModel", report["engine"])
                self.assertIn("parityVector", report["engine"])

    def test_backtest_rejects_non_usdjpy_strategy_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            bad = base_strategy_seed("BAD")
            bad["symbol"] = "EURUSDc"
            report = run_backtest(runtime_dir, bad, write=False)
            self.assertFalse(report["ok"])
            self.assertEqual(report["validation"]["blockerCode"], "NON_USDJPY_REJECTED")
            self.assertEqual(report["metrics"], {})

    def test_ga_fitness_consumes_strategy_backtest_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            seed = base_strategy_seed("FITNESS")
            run_backtest(runtime_dir, seed, write=True)

            metrics = evidence_metrics(runtime_dir)
            self.assertTrue(metrics["strategyBacktest"]["present"])
            self.assertIn("profitFactor", metrics["strategyBacktest"])

            score = score_seed(seed, runtime_dir)
            self.assertIn("strategyBacktest", score)
            self.assertTrue(score["strategyBacktest"]["present"])
            self.assertEqual(score["strategyBacktest"]["strategyId"], seed["strategyId"])

    def test_all_usdjpy_strategy_families_have_backtest_runner_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            build_sample(runtime_dir, overwrite=True)
            for family in sorted(ALLOWED_STRATEGY_FAMILIES):
                with self.subTest(family=family):
                    seed = base_strategy_seed(f"BT-{family}", family=family, direction="LONG")
                    report = run_backtest(runtime_dir, seed, write=False)
                    self.assertTrue(report["ok"], report)
                    self.assertEqual(report["strategyFamily"], family)
                    self.assertEqual(report["engine"]["coverage"], "ALL_SUPPORTED_USDJPY_SHADOW_FAMILIES")
                    self.assertIn(family, report["engine"]["supportedFamilies"])
                    self.assertIn("netR", report["metrics"])
                    self.assertNotIn("暂未接入", str(report.get("reasonZh")))

    def test_ga_fitness_backtests_each_seed_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            build_sample(runtime_dir, overwrite=True)
            rsi_seed = base_strategy_seed("GA-RSI", family="RSI_Reversal", direction="LONG")
            ma_seed = base_strategy_seed("GA-MA", family="MA_Cross", direction="LONG")

            rsi_score = score_seed(rsi_seed, runtime_dir)
            ma_score = score_seed(ma_seed, runtime_dir)

            self.assertEqual(rsi_score["strategyBacktest"]["strategyFamily"], "RSI_Reversal")
            self.assertEqual(ma_score["strategyBacktest"]["strategyFamily"], "MA_Cross")
            self.assertNotEqual(
                rsi_score["strategyBacktest"]["strategyId"],
                ma_score["strategyBacktest"]["strategyId"],
            )


if __name__ == "__main__":
    unittest.main()
