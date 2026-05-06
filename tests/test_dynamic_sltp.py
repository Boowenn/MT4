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

    def test_candidate_outcome_fields_are_calibrated_by_route_and_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "QuantGod_ShadowCandidateOutcomeLedger.csv").write_text(
                "EventId,Symbol,CandidateRoute,Timeframe,CandidateDirection,Regime,LongClosePips,ShortClosePips,LongMFEPips,LongMAEPips,ShortMFEPips,ShortMAEPips\n"
                "A1,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.0,-2.0,4.0,1.0,1.0,4.0\n"
                "A2,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.4,-2.4,4.4,1.2,1.2,4.4\n"
                "A3,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,1.8,-1.8,3.8,1.0,1.0,3.8\n"
                "A4,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.1,-2.1,4.1,1.1,1.1,4.1\n"
                "A5,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.3,-2.3,4.3,1.2,1.2,4.3\n"
                "A6,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,1.9,-1.9,3.9,1.0,1.0,3.9\n"
                "A7,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.2,-2.2,4.2,1.1,1.1,4.2\n"
                "A8,USDJPYc,RSI_REVERSAL_SHADOW,M15,BUY,RANGE,2.5,-2.5,4.5,1.2,1.2,4.5\n",
                encoding="utf-8",
            )
            payload = build_calibration(runtime, symbols=["USDJPYc"], write=False)
            plan = select_plan(payload, "USDJPYc", strategy="RSI_Reversal", direction="LONG")
            self.assertIsNotNone(plan)
            self.assertEqual(plan["state"], "CALIBRATED")
            self.assertGreater(plan["initialStop"], 0.0)
            self.assertNotEqual(plan["strategy"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
