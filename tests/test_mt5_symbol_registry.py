import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mt5_symbol_registry.py"
SPEC = importlib.util.spec_from_file_location("mt5_symbol_registry", MODULE_PATH)
registry = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(registry)


class Mt5SymbolRegistryTests(unittest.TestCase):
    def test_forex_suffix_maps_to_canonical_symbol(self):
        row = registry.normalize_symbol_row(
            {
                "name": "EURUSDc",
                "description": "Euro vs US Dollar (Cent)",
                "path": "ForexCent\\EURUSDc",
                "currencyBase": "EUR",
                "currencyProfit": "USD",
                "digits": 5,
                "point": 0.00001,
                "volumeMin": 0.01,
                "volumeStep": 0.01,
            }
        )
        self.assertEqual(row["canonicalSymbol"], "EURUSD")
        self.assertEqual(row["brokerSuffix"], "c")
        self.assertEqual(row["assetClass"], "Forex")
        self.assertEqual(row["baseCurrency"], "EUR")
        self.assertEqual(row["quoteCurrency"], "USD")

    def test_raw_suffix_and_jpy_pair(self):
        row = registry.normalize_symbol_row(
            {
                "name": "USDJPY.raw",
                "description": "US Dollar vs Japanese Yen",
                "path": "Forex\\USDJPY.raw",
                "currency_base": "USD",
                "currency_profit": "JPY",
            }
        )
        self.assertEqual(row["canonicalSymbol"], "USDJPY")
        self.assertEqual(row["brokerSuffix"], ".raw")
        self.assertEqual(row["assetClass"], "Forex")

    def test_metal_prefix_maps_to_metals(self):
        row = registry.normalize_symbol_row(
            {
                "name": "XAUUSDc",
                "description": "Gold vs US Dollar",
                "path": "Metals\\XAUUSDc",
            }
        )
        self.assertEqual(row["canonicalSymbol"], "XAUUSD")
        self.assertEqual(row["assetClass"], "Metals")
        self.assertEqual(row["baseCurrency"], "XAU")
        self.assertEqual(row["quoteCurrency"], "USD")

    def test_metal_cross_keeps_quote_currency(self):
        row = registry.normalize_symbol_row(
            {
                "name": "XAUEURc",
                "description": "Gold vs Euro / Spot",
                "path": "Metals & Energies\\Spot\\Gold & Silver Cent\\XAUEURc",
            }
        )
        self.assertEqual(row["canonicalSymbol"], "XAUEUR")
        self.assertEqual(row["assetClass"], "Metals")
        self.assertEqual(row["baseCurrency"], "XAU")
        self.assertEqual(row["quoteCurrency"], "EUR")

    def test_build_registry_summary_and_resolve(self):
        payload = registry.build_registry_from_symbols(
            [
                {"name": "EURUSDc", "description": "Euro vs US Dollar", "path": "ForexCent\\EURUSDc"},
                {"name": "USDJPYc", "description": "US Dollar vs Japanese Yen", "path": "ForexCent\\USDJPYc"},
                {"name": "XAUUSDc", "description": "Gold vs US Dollar", "path": "Metals\\XAUUSDc"},
            ],
            generated_at="2026-04-28T00:00:00Z",
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["totalSymbols"], 3)
        self.assertEqual(payload["summary"]["assetClassCounts"]["Forex"], 2)
        self.assertEqual(payload["summary"]["assetClassCounts"]["Metals"], 1)

        resolved = registry.add_resolve_payload(payload, "EURUSD")
        self.assertEqual(resolved["matchCount"], 1)
        self.assertEqual(resolved["resolved"]["brokerSymbol"], "EURUSDc")

    def test_safety_metadata_is_read_only(self):
        self.assertTrue(registry.SAFETY["readOnly"])
        self.assertFalse(registry.SAFETY["orderSendAllowed"])
        self.assertFalse(registry.SAFETY["closeAllowed"])
        self.assertFalse(registry.SAFETY["cancelAllowed"])
        self.assertFalse(registry.SAFETY["symbolSelectAllowed"])
        self.assertFalse(registry.SAFETY["mutatesMt5"])


if __name__ == "__main__":
    unittest.main()
