from pathlib import Path
import unittest


EA_PATH = Path(__file__).resolve().parents[1] / "MQL5" / "Experts" / "QuantGod_MultiStrategy.mq5"


def _ea_text() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def _diagnostic_function_body() -> str:
    text = _ea_text()
    start = text.index("string BuildUsdJpyRsiEntryDiagnosticsJson()")
    end = text.index("void ExportDashboard", start)
    return text[start:end]


class Mt5UsdJpyRsiEntryDiagnosticsTest(unittest.TestCase):
    def test_ea_exports_usdjpy_rsi_entry_diagnostics(self) -> None:
        text = _ea_text()
        self.assertIn("BuildUsdJpyRsiEntryDiagnosticsJson", text)
        self.assertIn("QuantGod_USDJPYRsiEntryDiagnostics.json", text)
        self.assertIn("usdJpyRsiEntryDiagnostics", text)
        self.assertIn("usdJpyRsiEntryDiagnosticsJson = BuildUsdJpyRsiEntryDiagnosticsJson()", text)

    def test_diagnostics_explain_core_entry_gates(self) -> None:
        body = _diagnostic_function_body()
        for token in [
            "LiveTradePermissionBlocker",
            "PilotNewsBlocksSymbol",
            "PilotLossCooldownActive",
            "PilotStartupEntryGuardBlocks",
            "IsPilotSessionOpen",
            "CountPilotPositions",
            "HasManualPositionOnSymbol",
            "EvaluatePilotRsiH1Signal",
            "RSIValue",
            "PilotMaxSpreadPips",
            "whyNoEntry",
        ]:
            self.assertIn(token, body)

    def test_diagnostics_use_existing_ea_input_names(self) -> None:
        body = _diagnostic_function_body()
        for token in [
            "PilotBBPeriod",
            "PilotBBDeviation",
            "PilotRsiBandTolerancePct",
            "PilotSessionStartHour",
            "PilotSessionEndHour",
        ]:
            self.assertIn(token, body)
        for stale_token in [
            "PilotRsiBBPeriod",
            "PilotRsiBBDeviation",
            "PilotRsiBandTouchTolerancePct",
            "PilotSessionStartHourUtc",
            "PilotSessionEndHourUtc",
        ]:
            self.assertNotIn(stale_token, body)

    def test_diagnostic_export_is_read_only(self) -> None:
        body = _diagnostic_function_body()
        forbidden = [
            "OrderSend(",
            "OrderSendAsync",
            "PositionClose",
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "OrderModify",
        ]
        for token in forbidden:
            self.assertNotIn(token, body)

    def test_diagnostics_have_operator_chinese_states(self) -> None:
        text = _ea_text()
        for phrase in [
            "RSI 买入路线已恢复",
            "交易权限未通过",
            "当前不在 EA 入场时段",
            "新闻过滤阻断中",
            "点差超过 EA 入场限制",
        ]:
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
