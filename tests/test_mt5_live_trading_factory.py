import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "live_trading_factory.py"
SPEC = importlib.util.spec_from_file_location("live_trading_factory", MODULE_PATH)
factory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(factory)


class LiveTradingFactoryTests(unittest.TestCase):
    def test_factory_describes_guarded_mt5_client(self):
        payload = factory.describe_factory()
        self.assertEqual(payload["mode"], "LIVE_TRADING_FACTORY_V1")
        mt5 = payload["clients"][0]
        self.assertTrue(mt5["guardedMutation"])
        self.assertTrue(mt5["defaultDryRun"])
        self.assertTrue(mt5["authorizationLockRequired"])
        self.assertFalse(mt5["livePresetMutationAllowed"])

    def test_create_mt5_client_keeps_default_order_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = factory.create_client("MT5", market_category="Forex", runtime_dir=tmp)
            result = client.place_limit_order(
                {
                    "route": "MA_Cross",
                    "symbol": "EURUSDc",
                    "side": "buy",
                    "lots": 0.01,
                    "price": 1.099,
                    "dryRun": True,
                }
            )
            self.assertEqual(result["decision"], "DRY_RUN_ACCEPTED")
            self.assertFalse(result["safety"]["orderSendAllowed"])
            self.assertTrue((Path(tmp) / "QuantGod_MT5TradingAuditLedger.csv").exists())

    def test_rejects_unknown_broker(self):
        with self.assertRaises(ValueError):
            factory.create_client("IBKR")


if __name__ == "__main__":
    unittest.main()
