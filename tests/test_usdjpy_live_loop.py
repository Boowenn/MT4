import json
import tempfile
import unittest
from pathlib import Path

from tools.usdjpy_live_loop.runner import build_live_loop
from tools.usdjpy_live_loop.schema import STATE_EVIDENCE_MISSING, STATE_READY
from tools.usdjpy_strategy_lab.data_loader import sample_runtime


def write_ready_preset(repo: Path) -> None:
    preset = repo / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
    preset.parent.mkdir(parents=True, exist_ok=True)
    preset.write_text(
        "\n".join([
            "Watchlist=USDJPY",
            "ShadowMode=false",
            "ReadOnlyMode=false",
            "EnablePilotAutoTrading=true",
            "EnablePilotRsiH1Live=true",
            "EnablePilotMA=false",
            "EnablePilotBBH1Live=false",
            "EnablePilotMacdH1Live=false",
            "EnablePilotSRM15Live=false",
            "EnableNonRsiLegacyLiveAuthorization=false",
            "PilotMaxTotalPositions=2",
            "PilotLotSize=0.01",
            "PilotBlockManualPerSymbol=false",
        ]),
        encoding="utf-8",
    )


class USDJPYLiveLoopTests(unittest.TestCase):
    def test_ready_sample_reports_existing_ea_route_without_tool_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            runtime = Path(tmp) / "runtime"
            write_ready_preset(root)
            sample_runtime(runtime, overwrite=True)
            payload = build_live_loop(root, runtime, write=True)
            self.assertEqual(payload["state"], STATE_READY)
            self.assertTrue(payload["presetReady"])
            self.assertTrue(payload["policyReady"])
            self.assertFalse(payload["safety"]["orderSendAllowedByTool"])
            self.assertTrue(payload["safety"]["existingEaOwnsExecution"])
            self.assertEqual(payload["intent"]["allowedLiveRoute"], "RSI_Reversal BUY")
            self.assertTrue((runtime / "live" / "QuantGod_USDJPYLiveLoopStatus.json").exists())
            self.assertTrue((runtime / "live" / "QuantGod_USDJPYLiveIntent.json").exists())

    def test_missing_runtime_fails_closed_even_if_preset_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            runtime = Path(tmp) / "runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            write_ready_preset(root)
            payload = build_live_loop(root, runtime, write=True)
            self.assertEqual(payload["state"], STATE_EVIDENCE_MISSING)
            self.assertFalse(payload["runtimeReady"])
            self.assertIn("缺少 USDJPY 运行快照", "；".join(payload["whyNoEntry"]))

    def test_written_daily_autopilot_is_chinese_operator_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            runtime = Path(tmp) / "runtime"
            write_ready_preset(root)
            sample_runtime(runtime, overwrite=True)
            build_live_loop(root, runtime, write=True)
            daily = json.loads((runtime / "live" / "QuantGod_USDJPYDailyAutopilot.json").read_text(encoding="utf-8"))
            self.assertIn("RSI", daily["allowedLiveRoute"])
            self.assertIn("买入", daily["topDirectionZh"])
            self.assertFalse(daily["safety"]["orderSendAllowedByTool"])


if __name__ == "__main__":
    unittest.main()

