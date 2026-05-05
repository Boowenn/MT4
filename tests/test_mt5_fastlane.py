from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.mt5_fastlane.quality import build_quality_report, build_telegram_text
from tools.mt5_fastlane.schema import assert_safe_payload, safety_payload
from tools.run_mt5_fastlane import main as fastlane_main


class Mt5FastLaneTests(unittest.TestCase):
    def test_sample_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fastlane_main(["--runtime-dir", tmp, "--symbols", "USDJPYc", "sample"]), 0)
            report = build_quality_report(tmp, symbols=["USDJPYc"], write=True)
            self.assertTrue(report["heartbeatFound"])
            self.assertEqual(len(report["symbols"]), 1)
            self.assertEqual(report["symbols"][0]["quality"], "FAST")
            self.assertTrue((Path(tmp) / "quality" / "QuantGod_MT5FastLaneQuality.json").exists())

    def test_safety_rejects_secrets_and_execution_flags(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_payload({"token": "x"})
        with self.assertRaises(ValueError):
            assert_safe_payload({"orderSendAllowed": True})
        assert_safe_payload({"safety": safety_payload(), "message": "只读"})

    def test_telegram_text_is_chinese_and_advisory_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fastlane_main(["--runtime-dir", tmp, "--symbols", "USDJPYc", "sample"])
            text = build_telegram_text(build_quality_report(tmp, symbols=["USDJPYc"], write=False))
            self.assertIn("MT5 快通道质量审查", text)
            self.assertIn("不会下单", text)
            self.assertIn("USDJPYc", text)


if __name__ == "__main__":
    unittest.main()
