import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load_module(name):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = load_module("mt5_pending_order_worker")
platform = load_module("mt5_platform_store")


class Mt5PendingWorkerAndPlatformTests(unittest.TestCase):
    def write_intents(self, runtime: Path):
        payload = {
            "mode": "TEST_INTENTS",
            "intents": [
                {
                    "sourceCandidateId": "candidate-1",
                    "route": "MA_Cross",
                    "symbol": "EURUSDc",
                    "side": "buy",
                    "orderType": "buy_limit",
                    "lots": 0.01,
                    "entryPrice": 1.099,
                    "stopLoss": 1.094,
                    "takeProfit": 1.109,
                    "dryRun": True,
                }
            ],
        }
        path = runtime / worker.INTENTS_NAME
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_pending_worker_dry_run_writes_ledgers_and_skips_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            self.write_intents(runtime)

            first = worker.run_worker(runtime, force_dry_run=True)
            self.assertTrue(first["ok"])
            self.assertEqual(first["summary"]["accepted"], 1)
            self.assertTrue((runtime / worker.LEDGER_NAME).exists())

            second = worker.run_worker(runtime, force_dry_run=True)
            self.assertTrue(second["ok"])
            self.assertEqual(second["summary"]["skipped"], 1)

    def test_platform_store_syncs_trading_and_pending_audit_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            self.write_intents(runtime)
            worker.run_worker(runtime, force_dry_run=True)

            state = platform.run(
                runtime,
                operator={"operatorId": "owner", "displayName": "Owner", "role": "admin", "status": "active"},
            )
            self.assertTrue(state["ok"])
            self.assertEqual(state["summary"]["operators"], 1)
            self.assertGreaterEqual(state["summary"]["auditEvents"], 1)
            self.assertTrue((runtime / platform.DB_NAME).exists())
            self.assertTrue((runtime / platform.OUTPUT_NAME).exists())
            self.assertFalse(state["safety"]["orderSendAllowed"])


if __name__ == "__main__":
    unittest.main()
