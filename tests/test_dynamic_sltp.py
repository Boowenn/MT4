from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.dynamic_sltp.calibrator import build_calibration, select_plan, write_sample_runtime
from tools.dynamic_sltp.schema import assert_safe_payload, safety_payload
from tools.dynamic_sltp.telegram_text import build_telegram_text
from tools.run_dynamic_sltp import main as cli_main


class DynamicSltpTests(unittest.TestCase):
    def test_sample_builds_calibrated_and_paused_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            write_sample_runtime(runtime, overwrite=True)
            payload = build_calibration(runtime, symbols=["USDJPYc"], write=True)
            self.assertEqual(payload["schema"], "quantgod.dynamic_sltp.calibration.v1")
            self.assertGreaterEqual(len(payload["plans"]), 2)
            states = {plan["direction"]: plan["state"] for plan in payload["plans"]}
            self.assertEqual(states["LONG"], "CALIBRATED")
            self.assertEqual(states["SHORT"], "PAUSED")
            self.assertTrue((runtime / "adaptive" / "QuantGod_DynamicSLTPCalibration.json").exists())
            assert_safe_payload(payload)

    def test_select_plan_prefers_calibrated_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            write_sample_runtime(runtime, overwrite=True)
            payload = build_calibration(runtime, write=False)
            plan = select_plan(payload, "USDJPYc", strategy="RSI_Reversal", direction="LONG")
            self.assertIsNotNone(plan)
            self.assertEqual(plan["state"], "CALIBRATED")
            self.assertGreater(plan["targets"]["tp2"], 0)

    def test_telegram_text_is_chinese_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            write_sample_runtime(runtime, overwrite=True)
            payload = build_calibration(runtime, write=False)
            text = build_telegram_text(payload, symbol="USDJPYc")
            self.assertIn("动态止盈止损校准", text)
            self.assertIn("不会下单", text)
            self.assertNotIn("OrderSend", text)

    def test_cli_sample_and_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli_main(["sample", "--runtime-dir", tmp, "--overwrite"]), 0)
            self.assertEqual(cli_main(["build", "--runtime-dir", tmp, "--symbols", "USDJPYc"]), 0)
            self.assertEqual(cli_main(["telegram-text", "--runtime-dir", tmp, "--symbol", "USDJPYc"]), 0)

    def test_safety_payload_disallows_execution(self) -> None:
        safety = safety_payload()
        self.assertTrue(safety["readOnlyDataPlane"])
        self.assertFalse(safety["orderSendAllowed"])
        self.assertFalse(safety["orderModifyAllowed"])


if __name__ == "__main__":
    unittest.main()
