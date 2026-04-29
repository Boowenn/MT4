from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EA_PATH = ROOT / "MQL5" / "Experts" / "QuantGod_MultiStrategy.mq5"
LIVE_PRESET_PATH = ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
BACKTEST_USDJPY_PATH = ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_Backtest_USDJPYc.set"
BACKTEST_EURUSD_PATH = ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_Backtest_EURUSDc.set"


class Mt5RsiExitProtectionTests(unittest.TestCase):
    def test_ea_has_rsi_only_fast_exit_inputs(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn('DashboardBuild      = "QuantGod-v3.16-mt5-non-rsi-live-auth-lock"', text)
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
        self.assertIn("input bool   PilotRsiFailFastCloseOnMaxLoss = true;", text)
        self.assertIn("input bool   EnablePilotRsiTimeStopProtect = true;", text)
        self.assertIn("input int    PilotRsiMaxHoldMinutes       = 90;", text)
        self.assertIn("input bool   PilotRsiCloseOnServerDayChange = true;", text)
        self.assertIn("input bool   PilotRsiBlockSellInUptrend   = true;", text)
        self.assertIn("input bool   PilotRsiRangeTightBuyOnly    = true;", text)

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

    def test_rsi_time_stop_and_regime_guards_are_wired(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("void ManagePilotRsiTimeStops()", text)
        self.assertIn("routeProtect=RSI_TIME_STOP", text)
        self.assertIn("ManagePilotRsiTimeStops();", text)
        self.assertIn("PilotRsiBlockSellInUptrend && IsUptrendRegimeLabel(regime.label)", text)
        self.assertIn("PilotRsiRangeTightBuyOnly && IsRangeTightRegimeLabel(regime.label)", text)
        self.assertIn("RSI H1 SELL blocked in", text)

    def test_route_live_switches_are_rechecked_at_order_send(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("bool SendPilotMarketOrder(string symbol, int direction, double slPrice, double tpPrice, string strategyKey)", text)
        self.assertIn('strategyKey == "MA_Cross"', text)
        self.assertIn("if(!EnablePilotMA)", text)
        self.assertIn("IsNonRsiLegacyPilotRoute(strategyKey) && !NonRsiLegacyLiveAuthorizationActive()", text)
        self.assertIn("non-RSI legacy live authorization lock disabled", text)
        self.assertIn("else if(!IsLegacyPilotRouteLiveEnabled(strategyKey))", text)
        self.assertIn("legacy route live switch disabled", text)

    def test_non_rsi_legacy_routes_need_second_live_authorization_key(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("input bool   EnableNonRsiLegacyLiveAuthorization = false;", text)
        self.assertIn('input string NonRsiLegacyLiveAuthorizationTag = "";', text)
        self.assertIn("bool IsNonRsiLegacyPilotRoute(string strategyKey)", text)
        self.assertIn("MQLInfoInteger(MQL_TESTER)", text)
        self.assertIn('"ALLOW_NON_RSI_LEGACY_TESTER"', text)
        self.assertIn('"ALLOW_NON_RSI_LEGACY_LIVE"', text)
        self.assertIn("bool NonRsiLegacyLiveAuthorizationActive()", text)
        self.assertIn("return (EnablePilotBBH1Live && NonRsiLegacyLiveAuthorizationActive());", text)
        self.assertIn("return (EnablePilotMacdH1Live && NonRsiLegacyLiveAuthorizationActive());", text)
        self.assertIn("return (EnablePilotSRM15Live && NonRsiLegacyLiveAuthorizationActive());", text)
        self.assertIn('\\"nonRsiLegacyLiveAuthorization\\"', text)
        self.assertIn("nonRsiLegacyLiveAuthorizationState=", text)

    def test_ma_disabled_does_not_disable_legacy_route_loop(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn("if(!IsPilotLiveMode())\n      return;", text)
        self.assertNotIn("if(!IsPilotLiveMode() || !EnablePilotMA)", text)
        self.assertIn('ProcessLegacyPilotRoute("RSI_Reversal"', text)
        self.assertIn('g_maRuntimeStates[i].status = "ROUTE_DISABLED";', text)

    def test_base_ma_exit_defaults_are_not_tightened(self):
        text = LIVE_PRESET_PATH.read_text(encoding="utf-8")
        self.assertIn("PilotBreakevenMinAgeMinutes=60", text)
        self.assertIn("PilotBreakevenTriggerPips=6.0", text)
        self.assertIn("PilotTrailingStartPips=10.0", text)
        self.assertIn("PilotTrailingDistancePips=5.0", text)
        self.assertIn("PilotMaxTotalPositions=1", text)
        self.assertIn("PilotLotSize=0.01", text)

    def test_live_preset_is_downshifted_to_usdjpy_rsi_iteration(self):
        text = LIVE_PRESET_PATH.read_text(encoding="utf-8")
        self.assertIn("DashboardBuild=QuantGod-v3.16-mt5-non-rsi-live-auth-lock", text)
        self.assertIn("Watchlist=USDJPY", text)
        self.assertIn("EnablePilotMA=false", text)
        self.assertIn("EnablePilotRsiH1Live=true", text)
        self.assertIn("EnablePilotBBH1Live=false", text)
        self.assertIn("EnableNonRsiLegacyLiveAuthorization=false", text)
        self.assertIn("NonRsiLegacyLiveAuthorizationTag=", text)
        self.assertIn("EnablePilotMacdH1Live=false", text)
        self.assertIn("EnablePilotSRM15Live=false", text)
        self.assertIn("PilotRsiOverbought=85", text)
        self.assertIn("PilotRsiOversold=15", text)
        self.assertIn("PilotRsiBandTolerancePct=0.006", text)
        self.assertIn("PilotSessionStartHour=8", text)
        self.assertIn("PilotSessionEndHour=15", text)
        self.assertIn("PilotNewsPreBlockMinutes=30", text)
        self.assertIn("PilotNewsHighImpactPreBlockMinutes=60", text)
        self.assertIn("PilotNewsPostBlockMinutes=30", text)
        self.assertIn("PilotNewsBiasMinutes=60", text)

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
            self.assertIn("PilotRsiFailFastCloseOnMaxLoss=true", text)
            self.assertIn("EnablePilotRsiTimeStopProtect=true", text)
            self.assertIn("PilotRsiMaxHoldMinutes=90", text)
            self.assertIn("PilotRsiCloseOnServerDayChange=true", text)
            self.assertIn("PilotRsiBlockSellInUptrend=true", text)
            self.assertIn("PilotRsiRangeTightBuyOnly=true", text)

    def test_eurusd_backtest_only_authorizes_non_rsi_legacy_routes_in_tester(self):
        text = BACKTEST_EURUSD_PATH.read_text(encoding="utf-8")
        self.assertIn("DashboardBuild=QuantGod-v3.16-mt5-non-rsi-live-auth-lock-backtest", text)
        self.assertIn("EnablePilotBBH1Live=true", text)
        self.assertIn("EnablePilotMacdH1Live=true", text)
        self.assertIn("EnablePilotSRM15Live=true", text)
        self.assertIn("EnableNonRsiLegacyLiveAuthorization=true", text)
        self.assertIn("NonRsiLegacyLiveAuthorizationTag=ALLOW_NON_RSI_LEGACY_TESTER", text)

    def test_shadow_outcome_unknown_direction_keeps_opportunity_signal(self):
        text = EA_PATH.read_text(encoding="utf-8")
        self.assertIn('return "LONG_OPPORTUNITY";', text)
        self.assertIn('return "SHORT_OPPORTUNITY";', text)
        self.assertIn('return "NEUTRAL_OPPORTUNITY";', text)


if __name__ == "__main__":
    unittest.main()
