import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mt5_adaptive_control_executor.py"
SPEC = importlib.util.spec_from_file_location("mt5_adaptive_control_executor", MODULE_PATH)
executor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(executor)


class Mt5AdaptiveControlExecutorTests(unittest.TestCase):
    def test_stages_promotion_gate_actions_without_live_preset_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / executor.PROMOTION_GATE_NAME).write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "route": "MA_Cross",
                                "decision": "KEEP_LIVE",
                                "versionId": "ma-v1",
                                "reason": "stable evidence",
                            },
                            {
                                "route": "RSI_Reversal",
                                "decision": "DEMOTE",
                                "versionId": "rsi-v1",
                                "reason": "drawdown",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = executor.run(runtime, apply_staging=True)
            self.assertTrue(result["ok"])
            self.assertEqual(result["summary"]["actions"], 2)
            self.assertTrue((runtime / executor.STAGING_PRESET_NAME).exists())
            self.assertTrue((runtime / executor.LEDGER_NAME).exists())
            self.assertFalse(result["safety"]["livePresetMutationAllowed"])
            self.assertFalse(result["safety"]["mutatesMt5"])

    def test_live_apply_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            result = executor.run(runtime, apply_staging=True, apply_live=True)
            self.assertGreaterEqual(result["summary"]["blocked"], 1)
            self.assertFalse(result["safety"]["mutatesMt5"])
            self.assertIn("kill_switch_on", result["actions"][0]["blockers"])


if __name__ == "__main__":
    unittest.main()
