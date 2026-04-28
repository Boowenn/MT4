import csv
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_mt5_backend_backtest_loop.py"
SPEC = importlib.util.spec_from_file_location("run_mt5_backend_backtest_loop", MODULE_PATH)
backend = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(backend)


def synthetic_breakout_bars(count: int = 120) -> list[dict[str, object]]:
    bars = []
    price = 1.1000
    base_time = 1777380000
    for index in range(count):
        if index < 30:
            price += 0.00002
        else:
            price += 0.00050
        open_price = price - 0.00010
        close = price
        bars.append(
            {
                "time": base_time + index * 900,
                "open": round(open_price, 5),
                "high": round(close + 0.00005, 5),
                "low": round(open_price - 0.00005, 5),
                "close": round(close, 5),
                "tickVolume": 100 + index,
                "spread": 12,
            }
        )
    return bars


class Mt5BackendBacktestLoopTests(unittest.TestCase):
    def test_safety_metadata_disallows_live_mutation(self):
        self.assertTrue(backend.SAFETY["readOnly"])
        self.assertTrue(backend.SAFETY["pythonBacktestOnly"])
        self.assertFalse(backend.SAFETY["usesMt5StrategyTester"])
        self.assertFalse(backend.SAFETY["orderSendAllowed"])
        self.assertFalse(backend.SAFETY["closeAllowed"])
        self.assertFalse(backend.SAFETY["cancelAllowed"])
        self.assertFalse(backend.SAFETY["symbolSelectAllowed"])
        self.assertFalse(backend.SAFETY["credentialStorageAllowed"])
        self.assertFalse(backend.SAFETY["livePresetMutationAllowed"])
        self.assertFalse(backend.SAFETY["mutatesMt5"])

    def test_task_from_candidate_parses_string_booleans_safely(self):
        task = backend.task_from_candidate(
            {
                "candidateId": "cand-1",
                "routeKey": "SR_Breakout",
                "symbol": "EURUSDc",
                "timeframe": "15m",
                "testerOnly": "false",
                "livePresetMutation": "false",
            }
        )
        self.assertEqual(task["timeframe"], "M15")
        self.assertFalse(task["testerOnly"])
        self.assertFalse(task["livePresetMutation"])

    def test_fixture_run_writes_backend_contract_without_mt5_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            runtime.mkdir()
            plan = runtime / backend.SCHEDULER_NAME
            bars_path = root / "bars.json"
            plan.write_text(
                json.dumps(
                    {
                        "routePlans": [
                            {
                                "routeKey": "SR_Breakout",
                                "candidates": [
                                    {
                                        "candidateId": "sr-fixture-v1",
                                        "routeKey": "SR_Breakout",
                                        "strategy": "SR_Breakout",
                                        "symbol": "EURUSDc",
                                        "timeframe": "M15",
                                        "testerOnly": True,
                                        "livePresetMutation": False,
                                        "presetOverrides": {
                                            "PilotSRLookback": 24,
                                            "PilotSRBreakPips": 0.1,
                                            "PilotATRPeriod": 14,
                                            "PilotATRMulitplierSL": 0.4,
                                            "PilotRewardRatio": 1.0,
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bars_path.write_text(json.dumps({"EURUSDc|M15": synthetic_breakout_bars()}), encoding="utf-8")

            args = backend.parse_args(
                [
                    "--repo-root",
                    str(root),
                    "--runtime-dir",
                    str(runtime),
                    "--input-bars",
                    str(bars_path),
                    "--from-date",
                    "2026-04-01",
                    "--to-date",
                    "2026-04-28",
                    "--max-tasks",
                    "1",
                ]
            )
            payload = backend.run_backend_loop(args)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "MT5_BACKEND_BACKTEST_LOOP_V1")
            self.assertEqual(payload["safety"], backend.SAFETY)
            self.assertTrue(payload["mt5Status"]["skipped"])
            self.assertEqual(payload["summary"]["taskCount"], 1)
            self.assertEqual(payload["rows"][0]["candidateId"], "sr-fixture-v1")
            self.assertEqual(payload["rows"][0]["canonicalSymbol"], "EURUSD")
            self.assertFalse(payload["rows"][0]["orderSendAllowed"])
            self.assertFalse(payload["rows"][0]["livePresetMutation"])
            self.assertGreater(payload["rows"][0]["barCount"], 60)
            self.assertGreater(payload["rows"][0]["closedTrades"], 0)

    def test_cli_main_writes_json_and_ledgers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            runtime.mkdir()
            bars_path = root / "bars.json"
            output = root / "out.json"
            ledger = root / "ledger.csv"
            trades = root / "trades.csv"
            bars_path.write_text(json.dumps({"EURUSDc|M15": synthetic_breakout_bars()}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                code = backend.main(
                    [
                        "--repo-root",
                        str(root),
                        "--runtime-dir",
                        str(runtime),
                        "--output",
                        str(output),
                        "--ledger",
                        str(ledger),
                        "--trade-ledger",
                        str(trades),
                        "--input-bars",
                        str(bars_path),
                        "--max-tasks",
                        "1",
                        "--route",
                        "SR_Breakout",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            self.assertTrue(ledger.exists())
            self.assertTrue(trades.exists())
            doc = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(doc["mode"], "MT5_BACKEND_BACKTEST_LOOP_V1")
            self.assertEqual(doc["safety"], backend.SAFETY)
            with ledger.open(newline="", encoding="utf-8") as handle:
                ledger_rows = list(csv.DictReader(handle))
            self.assertEqual(len(ledger_rows), 1)
            self.assertEqual(ledger_rows[0]["routeKey"], "SR_Breakout")


if __name__ == "__main__":
    unittest.main()
