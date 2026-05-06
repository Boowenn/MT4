from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.usdjpy_runtime_dataset.builder import build_runtime_dataset
from tools.usdjpy_runtime_dataset.config_proposal import build_live_config_proposal
from tools.usdjpy_runtime_dataset.param_tuner import build_param_tuning_report
from tools.usdjpy_runtime_dataset.replay import build_replay_report


class USDJPYRuntimeDatasetTests(unittest.TestCase):
    def test_builds_usdjpy_only_dataset_and_retune_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            with (runtime / "QuantGod_EntryBlockers.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "symbol",
                    "strategy",
                    "direction",
                    "status",
                    "reason",
                    "riskPips",
                    "posteriorPips60",
                    "maeR",
                ])
                writer.writeheader()
                writer.writerow({
                    "symbol": "USDJPYc",
                    "strategy": "RSI_Reversal",
                    "direction": "LONG",
                    "status": "READY_BUY_SIGNAL",
                    "reason": "READY_BUY_SIGNAL but no entry",
                    "riskPips": "5",
                    "posteriorPips60": "8",
                    "maeR": "-0.4",
                })
                writer.writerow({
                    "symbol": "EURUSDc",
                    "strategy": "RSI_Reversal",
                    "direction": "LONG",
                    "status": "READY_BUY_SIGNAL",
                    "reason": "must be ignored",
                })
            with (runtime / "QuantGod_CloseHistory.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "strategy", "direction", "profitUSC", "profitR", "mfeR", "maeR", "exitReason"])
                writer.writeheader()
                writer.writerow({
                    "symbol": "USDJPYc",
                    "strategy": "RSI_Reversal",
                    "direction": "LONG",
                    "profitUSC": "0.4",
                    "profitR": "0.35",
                    "mfeR": "1.5",
                    "maeR": "-0.25",
                    "exitReason": "breakeven_or_trailing",
                })

            dataset = build_runtime_dataset(runtime, write=True)
            replay = build_replay_report(runtime, write=True)
            tuning = build_param_tuning_report(runtime, write=True)
            proposal = build_live_config_proposal(runtime, write=True)

            self.assertEqual(dataset["summary"]["sampleCount"], 2)
            self.assertNotIn("EURUSDc", str(dataset["samples"]))
            self.assertEqual(replay["summary"]["missedOpportunityCount"], 1)
            self.assertEqual(replay["summary"]["earlyExitCount"], 1)
            self.assertEqual(replay["unitPolicy"]["primary"], "R")
            relaxed = {item["scenario"]: item for item in replay["scenarioComparisons"]}["relaxed_entry_v1"]
            let_profit = {item["scenario"]: item for item in replay["scenarioComparisons"]}["let_profit_run_v1"]
            self.assertGreater(relaxed["netRDelta"], 0)
            self.assertGreater(let_profit["netRDelta"], 0)
            self.assertGreaterEqual(tuning["summary"]["candidateCount"], 2)
            self.assertTrue(all("expectedImpact" in item for item in tuning["candidates"]))
            self.assertTrue(all("replayVariant" in item for item in tuning["candidates"] if item["param"] != "dataCollection"))
            self.assertEqual(proposal["status"], "PROPOSAL_READY_FOR_REVIEW")
            self.assertTrue(proposal["expectedImpact"])
            self.assertTrue(all("riskDelta" in item for item in proposal["changes"]))
            self.assertFalse(proposal["autoApplyAllowed"])
            self.assertFalse(proposal["safety"]["orderSendAllowed"])
            self.assertTrue((runtime / "datasets" / "usdjpy" / "QuantGod_USDJPYRuntimeDataset.json").exists())
            self.assertTrue((runtime / "adaptive" / "QuantGod_USDJPYLiveConfigProposal.json").exists())

    def test_early_exit_requires_r_multiple_not_usc_mixed_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            with (runtime / "QuantGod_CloseHistory.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["symbol", "strategy", "direction", "profitUSC", "mfeR", "exitReason"])
                writer.writeheader()
                writer.writerow({
                    "symbol": "USDJPYc",
                    "strategy": "RSI_Reversal",
                    "direction": "LONG",
                    "profitUSC": "0.8",
                    "mfeR": "2.0",
                    "exitReason": "breakeven_or_trailing",
                })

            dataset = build_runtime_dataset(runtime, write=True)
            replay = build_replay_report(runtime, write=False)

            self.assertEqual(dataset["summary"]["sampleCount"], 1)
            self.assertEqual(replay["summary"]["earlyExitCount"], 0)
            self.assertEqual(replay["summary"]["missingExitRCount"], 1)


if __name__ == "__main__":
    unittest.main()
