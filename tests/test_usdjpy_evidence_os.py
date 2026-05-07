import tempfile
import unittest
from pathlib import Path

from tools.strategy_ga.fitness import score_seed
from tools.strategy_json.schema import base_strategy_seed
from tools.usdjpy_evidence_os.report import build_evidence_os
from tools.usdjpy_strategy_backtest.report import ingest_klines, run_backtest


class USDJPYEvidenceOSTests(unittest.TestCase):
    def test_ingest_snapshot_backtest_and_evidence_os_write_audit_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            snapshot = runtime_dir / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json"
            snapshot.write_text(
                """
                {
                  "symbol": "USDJPYc",
                  "kline_h1": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.2,"low":155.0,"close":155.15,"volume":100},
                    {"timeIso":"2026-05-07T01:00:00Z","open":155.15,"high":155.3,"low":155.1,"close":155.25,"volume":100}
                  ],
                  "kline_m15": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.12,"low":155.0,"close":155.1,"volume":25}
                  ],
                  "kline_h4": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.4,"low":155.0,"close":155.3,"volume":400}
                  ],
                  "kline_d1": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.8,"low":154.9,"close":155.5,"volume":1000}
                  ]
                }
                """,
                encoding="utf-8",
            )

            ingest = ingest_klines(runtime_dir)
            self.assertTrue(ingest["sourceFound"])
            self.assertEqual(ingest["insertedOrUpdated"]["H1"], 2)

            backtest = run_backtest(runtime_dir, write=True)
            self.assertTrue(backtest["ok"], backtest)
            self.assertIn("multiTimeframe", backtest)
            self.assertEqual(backtest["multiTimeframe"]["contexts"]["H4"]["barCount"], 1)

            evidence = build_evidence_os(runtime_dir, write=True)
            self.assertTrue(evidence["ok"])
            self.assertIn("parity", evidence)
            self.assertIn("executionFeedback", evidence)
            self.assertIn("caseMemory", evidence)
            self.assertFalse(evidence["safety"]["orderSendAllowed"])
            self.assertTrue((runtime_dir / "evidence_os" / "QuantGod_StrategyParityReport.json").exists())

    def test_ga_fitness_consumes_parity_execution_and_case_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            run_backtest(runtime_dir, write=True)
            build_evidence_os(runtime_dir, write=True)
            score = score_seed(base_strategy_seed("GA-EVIDENCE-OS"), runtime_dir)
            self.assertIn("parity", score)
            self.assertIn("executionFeedback", score)
            self.assertIn("caseMemory", score)
            self.assertIn("evidencePenalty", score)


if __name__ == "__main__":
    unittest.main()

