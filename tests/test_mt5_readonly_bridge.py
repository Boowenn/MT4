import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mt5_readonly_bridge.py"
SPEC = importlib.util.spec_from_file_location("mt5_readonly_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bridge)


class Mt5ReadOnlyBridgeTests(unittest.TestCase):
    def test_safety_metadata_disallows_mutation(self):
        self.assertTrue(bridge.SAFETY["readOnly"])
        self.assertFalse(bridge.SAFETY["orderSendAllowed"])
        self.assertFalse(bridge.SAFETY["closeAllowed"])
        self.assertFalse(bridge.SAFETY["cancelAllowed"])
        self.assertFalse(bridge.SAFETY["credentialStorageAllowed"])
        self.assertFalse(bridge.SAFETY["livePresetMutationAllowed"])
        self.assertFalse(bridge.SAFETY["mutatesMt5"])

    def test_parse_args_defaults_to_snapshot(self):
        args = bridge.parse_args([])
        self.assertEqual(args.endpoint, "snapshot")
        self.assertEqual(args.group, "*")
        self.assertEqual(args.limit, bridge.DEFAULT_SYMBOL_LIMIT)
        self.assertEqual(args.symbols_limit, bridge.DEFAULT_SYMBOL_LIMIT)

    def test_mutating_endpoint_names_are_not_registered(self):
        self.assertNotIn("order", bridge.ENDPOINTS)
        self.assertNotIn("close", bridge.ENDPOINTS)
        self.assertNotIn("cancel", bridge.ENDPOINTS)

    def test_public_error_keeps_read_only_safety(self):
        payload = bridge.public_error("offline", detail="missing package")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "UNAVAILABLE")
        self.assertEqual(payload["detail"], "missing package")
        self.assertEqual(payload["safety"], bridge.SAFETY)

    def test_symbol_filter_is_whitespace_only(self):
        self.assertEqual(bridge.normalize_symbol_filter("  EURUSDc  "), "EURUSDc")
        self.assertEqual(bridge.normalize_symbol_filter(None), "")


if __name__ == "__main__":
    unittest.main()
