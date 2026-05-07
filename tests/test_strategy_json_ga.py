import tempfile
import unittest
from pathlib import Path

from tools.strategy_ga.generation_runner import read_candidates, run_generation
from tools.strategy_ga.telegram_text import ga_to_chinese_text
from tools.strategy_json.schema import base_strategy_seed
from tools.strategy_json.validator import validate_strategy_json


class StrategyJsonGATests(unittest.TestCase):
    def test_validator_rejects_execution_primitives_and_live_privileges(self):
        seed = base_strategy_seed("GA-USDJPY-TEST")
        seed["entry"]["conditions"].append("OrderSend()")
        self.assertFalse(validate_strategy_json(seed)["valid"])

        seed = base_strategy_seed("GA-USDJPY-TEST")
        seed["risk"]["maxLot"] = 2.1
        self.assertEqual(validate_strategy_json(seed)["blockerCode"], "MAX_LOT_TOO_HIGH")

        seed = base_strategy_seed("GA-USDJPY-TEST")
        seed["risk"]["stage"] = "MICRO_LIVE"
        self.assertEqual(validate_strategy_json(seed)["blockerCode"], "LIVE_STAGE_REJECTED")

        seed = base_strategy_seed("GA-USDJPY-TEST")
        seed["symbol"] = "EURUSDc"
        self.assertEqual(validate_strategy_json(seed)["blockerCode"], "NON_USDJPY_REJECTED")

    def test_validator_allows_explicit_false_safety_boundary_fields(self):
        seed = base_strategy_seed("GA-USDJPY-SAFE")
        result = validate_strategy_json(seed)
        self.assertTrue(result["valid"], result)
        self.assertFalse(result["normalized"]["safety"]["orderSendAllowed"])
        self.assertFalse(result["normalized"]["safety"]["telegramCommandExecutionAllowed"])

    def test_generation_writes_trace_files_and_never_promotes_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            result = run_generation(runtime_dir, write=True)
            ga_dir = runtime_dir / "ga"

            for name in [
                "QuantGod_GAStatus.json",
                "QuantGod_GAGenerationLatest.json",
                "QuantGod_GACandidateRuns.jsonl",
                "QuantGod_GAEliteStrategies.json",
                "QuantGod_GABlockerSummary.json",
                "QuantGod_GAEvolutionPath.json",
            ]:
                self.assertTrue((ga_dir / name).exists(), name)

            self.assertTrue(result["candidates"])
            for row in result["candidates"]:
                self.assertEqual(row["strategyJson"]["symbol"], "USDJPYc")
                self.assertIn("generationId", row)
                self.assertIn("seedId", row)
                self.assertIn("fitness", row)
                self.assertIn("blockerCode", row)
                self.assertNotIn(row["promotionStage"], {"MICRO_LIVE", "LIVE_LIMITED"})
                self.assertFalse(row["safety"]["orderSendAllowed"])
                self.assertFalse(row["safety"]["livePresetMutationAllowed"])

            latest = read_candidates(runtime_dir)
            self.assertEqual(len(latest["candidates"]), len(result["candidates"]))

    def test_generation_rejects_only_dangerous_seed_fields_not_safe_field_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_generation(Path(tmp), write=False)
            self.assertNotIn("SAFETY_REJECTED", {row["blockerCode"] for row in result["candidates"]})

    def test_telegram_text_is_chinese_push_only_and_no_execution_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_generation(Path(tmp), write=True)
            text = ga_to_chinese_text(result)
            self.assertIn("GA 进化报告", text)
            self.assertIn("安全边界", text)
            self.assertIn("不直接实盘", text)
            self.assertNotIn("OrderSend", text)


if __name__ == "__main__":
    unittest.main()
