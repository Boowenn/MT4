import importlib.util
import unittest
from collections import namedtuple
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mt5_readonly_bridge.py"
SPEC = importlib.util.spec_from_file_location("mt5_readonly_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bridge)


TerminalInfo = namedtuple(
    "TerminalInfo",
    "connected trade_allowed dlls_allowed name company path data_path commondata_path codepage maxbars",
)
AccountInfo = namedtuple(
    "AccountInfo",
    "login server name currency company balance equity profit margin margin_free margin_level leverage trade_allowed trade_expert",
)
PositionInfo = namedtuple(
    "PositionInfo",
    "ticket identifier symbol type volume price_open price_current sl tp profit swap magic comment time",
)
OrderInfo = namedtuple(
    "OrderInfo",
    "ticket symbol type volume_initial volume_current price_open price_current sl tp magic comment time_setup",
)
SymbolInfo = namedtuple(
    "SymbolInfo",
    "name description path visible select currency_base currency_profit digits point spread trade_mode volume_min volume_max volume_step",
)
TickInfo = namedtuple("TickInfo", "bid ask last volume time")


class FakeMt5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2

    def __init__(self):
        self.calls = []

    def terminal_info(self):
        self.calls.append("terminal_info")
        return TerminalInfo(
            True,
            True,
            False,
            "Fake HFM MT5",
            "Fake Broker",
            "C:\\MT5",
            "C:\\MT5",
            "C:\\Common",
            65001,
            100000,
        )

    def account_info(self):
        self.calls.append("account_info")
        return AccountInfo(
            123456,
            "Fake-Live",
            "Read Only",
            "USC",
            "Fake Broker",
            10000.0,
            10025.0,
            25.0,
            1.0,
            10024.0,
            1002400.0,
            1000,
            True,
            True,
        )

    def positions_get(self, symbol=None):
        self.calls.append(("positions_get", symbol or ""))
        return [
            PositionInfo(
                1001,
                1001,
                symbol or "EURUSDc",
                self.POSITION_TYPE_BUY,
                0.01,
                1.10001,
                1.10021,
                1.09,
                1.12,
                2.0,
                0.0,
                520001,
                "fake position",
                1777389974,
            )
        ]

    def orders_get(self, symbol=None):
        self.calls.append(("orders_get", symbol or ""))
        return [
            OrderInfo(
                2001,
                symbol or "EURUSDc",
                self.ORDER_TYPE_BUY_LIMIT,
                0.01,
                0.01,
                1.099,
                0.0,
                1.09,
                1.12,
                520001,
                "fake order",
                1777389000,
            )
        ]

    def symbols_get(self, group="*"):
        self.calls.append(("symbols_get", group))
        return [
            SymbolInfo(
                "EURUSDc",
                "Euro vs US Dollar (Cent)",
                "ForexCent\\EURUSDc",
                True,
                True,
                "EUR",
                "USD",
                5,
                0.00001,
                17,
                4,
                0.01,
                200.0,
                0.01,
            )
        ]

    def symbol_info(self, symbol):
        self.calls.append(("symbol_info", symbol))
        return SymbolInfo(
            symbol,
            "Euro vs US Dollar (Cent)",
            f"ForexCent\\{symbol}",
            True,
            True,
            "EUR",
            "USD",
            5,
            0.00001,
            17,
            4,
            0.01,
            200.0,
            0.01,
        )

    def symbol_info_tick(self, symbol):
        self.calls.append(("symbol_info_tick", symbol))
        return TickInfo(1.1002, 1.10037, 1.1003, 100, 1777389999)

    def last_error(self):
        return (1, "Success")


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

    def test_snapshot_contract_with_fake_mt5(self):
        fake = FakeMt5()
        args = bridge.parse_args(["--endpoint", "snapshot", "--symbol", "EURUSDc", "--symbols-limit", "20"])
        payload = bridge.build_endpoint_payload(fake, args)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "MT5_READONLY_BRIDGE_V1")
        self.assertEqual(payload["endpoint"], "snapshot")
        self.assertEqual(payload["status"], "CONNECTED")
        self.assertEqual(payload["safety"], bridge.SAFETY)
        self.assertFalse(payload["safety"]["orderSendAllowed"])
        self.assertFalse(payload["safety"]["closeAllowed"])
        self.assertFalse(payload["safety"]["cancelAllowed"])

        self.assertIn("terminal", payload)
        self.assertIn("account", payload)
        self.assertIn("positions", payload)
        self.assertIn("orders", payload)
        self.assertIn("symbols", payload)
        self.assertIn("quote", payload)
        self.assertEqual(payload["positions"]["items"][0]["symbol"], "EURUSDc")
        self.assertEqual(payload["orders"]["items"][0]["type"], "buy_limit")
        self.assertEqual(payload["symbols"]["items"][0]["name"], "EURUSDc")
        self.assertTrue(payload["quote"]["ok"])
        self.assertEqual(payload["quote"]["symbol"], "EURUSDc")

        called_names = {call[0] if isinstance(call, tuple) else call for call in fake.calls}
        self.assertNotIn("order_send", called_names)
        self.assertNotIn("symbol_select", called_names)
        self.assertNotIn("positions_close", called_names)

    def test_each_readonly_endpoint_contract_keeps_safety(self):
        fake = FakeMt5()
        for endpoint in sorted(bridge.ENDPOINTS):
            args = bridge.parse_args(["--endpoint", endpoint, "--symbol", "EURUSDc"])
            payload = bridge.build_endpoint_payload(fake, args)
            self.assertIn("generatedAtIso", payload)
            self.assertEqual(payload["safety"], bridge.SAFETY)
            self.assertFalse(payload["safety"]["orderSendAllowed"])
            self.assertFalse(payload["safety"]["closeAllowed"])
            self.assertFalse(payload["safety"]["cancelAllowed"])


if __name__ == "__main__":
    unittest.main()
