import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_mt5_research_stats.py"
SPEC = importlib.util.spec_from_file_location("build_mt5_research_stats", MODULE_PATH)
stats = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stats)


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Mt5ResearchStatsTests(unittest.TestCase):
    def test_canonical_symbol_pool_merges_broker_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            write_csv(
                runtime / stats.CLOSE_HISTORY_NAME,
                [
                    "ExitTicket",
                    "PositionId",
                    "Symbol",
                    "NetProfit",
                    "DurationMinutes",
                    "Strategy",
                    "Source",
                    "EntryRegime",
                    "RegimeTimeframe",
                    "CloseTime",
                ],
                [
                    [1, 10, "EURUSD", 2.0, 20, "MA_Cross", "EA", "RANGE", "H1", "2026.04.28 10:00"],
                    [2, 11, "EURUSDc", -1.0, 40, "MA_Cross", "EA", "RANGE", "H1", "2026.04.28 11:00"],
                    [3, 12, "USDJPY", 1.5, 30, "RSI_Reversal", "EA", "TREND_EXP_UP", "H1", "2026.04.28 12:00"],
                    [4, 13, "USDJPYc", 0.5, 30, "RSI_Reversal", "EA", "TREND_EXP_UP", "H1", "2026.04.28 13:00"],
                ],
            )
            write_csv(
                runtime / stats.TRADE_JOURNAL_NAME,
                ["DealTicket", "PositionId", "EventType", "Symbol", "Strategy", "Source", "Regime", "RegimeTimeframe", "EventTime"],
                [
                    [100, 10, "ENTRY", "EURUSD", "MA_Cross", "EA", "RANGE", "H1", "2026.04.28 09:40"],
                    [101, 11, "EXIT", "EURUSDc", "MA_Cross", "EA", "RANGE", "H1", "2026.04.28 11:00"],
                    [102, 12, "ENTRY", "USDJPY", "RSI_Reversal", "EA", "TREND_EXP_UP", "H1", "2026.04.28 11:30"],
                    [103, 13, "EXIT", "USDJPYc", "RSI_Reversal", "EA", "TREND_EXP_UP", "H1", "2026.04.28 13:00"],
                ],
            )
            write_csv(
                runtime / stats.OUTCOME_LABELS_NAME,
                ["PositionId", "ExitTicket", "Symbol", "Strategy", "Source", "NetProfit", "EntryRegime", "RegimeTimeframe", "OutcomeLabel", "LabelTimeServer"],
                [
                    [10, 1, "EURUSD", "MA_Cross", "EA", 2.0, "RANGE", "H1", "WIN", "2026.04.28 10:01"],
                    [11, 2, "EURUSDc", "MA_Cross", "EA", -1.0, "RANGE", "H1", "LOSS", "2026.04.28 11:01"],
                    [12, 3, "USDJPY", "RSI_Reversal", "EA", 1.5, "TREND_EXP_UP", "H1", "WIN", "2026.04.28 12:01"],
                    [13, 4, "USDJPYc", "RSI_Reversal", "EA", 0.5, "TREND_EXP_UP", "H1", "WIN", "2026.04.28 13:01"],
                ],
            )
            write_csv(
                runtime / stats.EVENT_LINKS_NAME,
                ["PositionId", "Symbol", "Strategy", "Source", "EntryDeal", "ExitDeal", "EntryRegime", "RegimeTimeframe", "Status", "OpenTime", "CloseTime"],
                [
                    [10, "EURUSD", "MA_Cross", "EA", 100, 1, "RANGE", "H1", "CLOSED", "2026.04.28 09:40", "2026.04.28 10:00"],
                    [11, "EURUSDc", "MA_Cross", "EA", 101, 2, "RANGE", "H1", "CLOSED", "2026.04.28 10:30", "2026.04.28 11:00"],
                    [12, "USDJPY", "RSI_Reversal", "EA", 102, 3, "TREND_EXP_UP", "H1", "CLOSED", "2026.04.28 11:30", "2026.04.28 12:00"],
                    [13, "USDJPYc", "RSI_Reversal", "EA", 103, 4, "TREND_EXP_UP", "H1", "CLOSED", "2026.04.28 12:30", "2026.04.28 13:00"],
                ],
            )

            payload = stats.build_stats(runtime, generated_at="2026-04-28T00:00:00Z")
            by_symbol = {row["canonicalSymbol"]: row for row in payload["canonicalSymbolSummary"]}

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["safety"]["readOnly"])
            self.assertFalse(payload["safety"]["orderSendAllowed"])
            self.assertEqual(payload["summary"]["liveUniverse"], ["USDJPYc"])
            self.assertEqual(payload["summary"]["liveUniverseMode"], "live_pilot_only")
            self.assertEqual(payload["summary"]["shadowResearchUniverse"][:3], ["USDJPYc", "EURUSDc", "XAUUSDc"])
            self.assertEqual(payload["summary"]["shadowResearchUniverseMode"], "shadow_candidate_paramlab_only")
            self.assertEqual(payload["universes"]["live"]["symbols"], ["USDJPYc"])
            self.assertEqual(payload["universes"]["shadowResearch"]["symbols"][:3], ["USDJPYc", "EURUSDc", "XAUUSDc"])
            self.assertEqual(by_symbol["EURUSD"]["closedTrades"], 2)
            self.assertEqual(set(by_symbol["EURUSD"]["sourceSymbols"]), {"EURUSD", "EURUSDc"})
            self.assertEqual(by_symbol["USDJPY"]["closedTrades"], 2)
            self.assertEqual(set(by_symbol["USDJPY"]["sourceSymbols"]), {"USDJPY", "USDJPYc"})

            slice_rows = {(row["route"], row["canonicalSymbol"], row["entryRegime"]): row for row in payload["rows"]}
            self.assertEqual(slice_rows[("MA_Cross", "EURUSD", "RANGE")]["closedTrades"], 2)
            self.assertEqual(slice_rows[("RSI_Reversal", "USDJPY", "TREND_EXP_UP")]["closedTrades"], 2)
            self.assertEqual(len(stats.ledger_rows(payload)), len(payload["rows"]))


if __name__ == "__main__":
    unittest.main()
