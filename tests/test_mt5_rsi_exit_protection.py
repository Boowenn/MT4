from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EA_PATH = ROOT / "MQL5" / "Experts" / "QuantGod_MultiStrategy.mq5"
LIVE_PRESET_PATH = ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
BACKTEST_USDJPY_PATH = ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_Backtest_USDJPYc.set"


class Mt5RsiExitProtectionTests(unittest.TestCase):
    def test_ea_has_rsi_only_fast_exit_inputs(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn('DashboardBuild      = "QuantGod-v3.14-mt5-rsi-failfast"', text)
        self.assertIn("input bool   EnablePilotRsiFastExitProtect = true;", text)
        self.assertIn("input int    PilotRsiProtectMinAgeMinutes = 10;", text)
        self.assertIn("input double PilotRsiBreakevenTriggerPips = 5.0;", text)
        self.assertIn("input double PilotRsiTrailingStartPips    = 8.0;", text)
        self.assertIn("input double PilotRsiTrailingDistancePips = 3.5;", text)
        self.assertIn("input double PilotRsiTrailingStepPips     = 0.5;", text)
        self.assertIn("input bool   EnablePilotRsiFailFastProtect = true;", text)
        self.assertIn("input int    PilotRsiFailFastMinAgeMinutes = 120;", text)
        self.assertIn("input double PilotRsiFailFastMinLossPips   = 8.0;", text)
        self.assertIn("input double PilotRsiFailFastMaxLossUSC    = 1.20;", text)
        self.assertIn("input double PilotRsiFailFastStopBufferPips = 2.5;", text)
        self.assertIn("input bool   PilotRsiFailFastCloseOnMaxLoss = false;", text)

    def test_rsi_fast_exit_is_scoped_by_comment(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("bool IsPilotRsiPositionComment(string comment)", text)
        self.assertIn('StringFind(ToUpperString(comment), "QG_RSI_REV")', text)
        self.assertIn("bool isRsiPosition = IsPilotRsiPositionComment(comment);", text)
        self.assertIn("isRsiPosition ? rsiBreakevenOn : baseBreakevenOn", text)
        self.assertIn("isRsiPosition ? MathMax(0, PilotRsiProtectMinAgeMinutes)", text)
        self.assertIn('routeProtect=", (isRsiPosition ? "RSI_FAST" : "BASE")', text)

    def test_rsi_failfast_is_scoped_and_tightens_stops_before_closing(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("void ManagePilotRsiFailFastStops()", text)
        self.assertIn("if(!IsPilotRsiPositionComment(comment))", text)
        self.assertIn("PilotRsiFailFastCloseOnMaxLoss && cashTriggerOn", text)
        self.assertIn("ModifyPilotPositionStops(ticket, symbol, targetSL, currentTP)", text)
        self.assertIn("routeProtect=RSI_FAILFAST", text)
        self.assertIn("ManagePilotRsiFailFastStops();", text)

    def test_base_ma_exit_defaults_are_not_tightened(self):
        text = LIVE_PRESET_PATH.read_text(encoding="utf-8")
        self.assertIn("PilotBreakevenMinAgeMinutes=60", text)
        self.assertIn("PilotBreakevenTriggerPips=6.0", text)
        self.assertIn("PilotTrailingStartPips=10.0", text)
        self.assertIn("PilotTrailingDistancePips=5.0", text)
        self.assertIn("PilotMaxTotalPositions=1", text)
        self.assertIn("PilotLotSize=0.01", text)

    def test_live_and_usdjpy_backtest_presets_include_rsi_fast_exit(self):
        for path in (LIVE_PRESET_PATH, BACKTEST_USDJPY_PATH):
            text = path.read_text(encoding="utf-8")
            self.assertIn("EnablePilotRsiFastExitProtect=true", text)
            self.assertIn("PilotRsiProtectMinAgeMinutes=10", text)
            self.assertIn("PilotRsiBreakevenTriggerPips=5.0", text)
            self.assertIn("PilotRsiBreakevenLockPips=1.0", text)
            self.assertIn("PilotRsiTrailingStartPips=8.0", text)
            self.assertIn("PilotRsiTrailingDistancePips=3.5", text)
            self.assertIn("PilotRsiTrailingStepPips=0.5", text)
            self.assertIn("EnablePilotRsiFailFastProtect=true", text)
            self.assertIn("PilotRsiFailFastMinAgeMinutes=120", text)
            self.assertIn("PilotRsiFailFastMinLossPips=8.0", text)
            self.assertIn("PilotRsiFailFastMaxLossUSC=1.20", text)
            self.assertIn("PilotRsiFailFastStopBufferPips=2.5", text)
            self.assertIn("PilotRsiFailFastStepPips=0.5", text)
            self.assertIn("PilotRsiFailFastCloseOnMaxLoss=false", text)


if __name__ == "__main__":
    unittest.main()
