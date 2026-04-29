import importlib.util
import json
import os
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mt5_trading_client.py"
SPEC = importlib.util.spec_from_file_location("mt5_trading_client", MODULE_PATH)
client = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(client)


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
TickInfo = namedtuple("TickInfo", "bid ask last volume time")
OrderSendResult = namedtuple("OrderSendResult", "retcode order comment")


class FakeMt5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_REMOVE = 8
    ORDER_TIME_GTC = 0
    ORDER_TIME_SPECIFIED = 2
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008

    def __init__(self):
        self.order_send_calls = []

    def terminal_info(self):
        return TerminalInfo(True, True, False, "Fake HFM MT5", "Fake Broker", "C:\\MT5", "C:\\MT5", "C:\\Common", 65001, 100000)

    def account_info(self):
        return AccountInfo(123456, "Fake-Live", "Trader", "USC", "Fake Broker", 10000, 10000, 0, 0, 10000, 0, 1000, True, True)

    def positions_get(self):
        return [
            PositionInfo(777, 777, "EURUSDc", self.POSITION_TYPE_BUY, 0.01, 1.1, 1.101, 1.09, 1.12, 1.0, 0.0, 520001, "QG", 1777389974)
        ]

    def orders_get(self):
        return []

    def symbol_info_tick(self, symbol):
        return TickInfo(1.1001, 1.1003, 1.1002, 100, 1777389999)

    def order_send(self, request):
        self.order_send_calls.append(request)
        retcode = self.TRADE_RETCODE_PLACED if request.get("action") == self.TRADE_ACTION_PENDING else self.TRADE_RETCODE_DONE
        return OrderSendResult(retcode, 987654, "accepted")

    def last_error(self):
        return (1, "Success")


class Mt5TradingClientTests(unittest.TestCase):
    def write_config(self, runtime: Path, **overrides):
        config = {**client.DEFAULT_CONFIG, **overrides}
        path = runtime / client.DEFAULT_CONFIG_NAME
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def write_lock(self, runtime: Path, **overrides):
        lock = {
            "lockId": "lock-test",
            "expiresAtIso": "2099-01-01T00:00:00Z",
            "accountLogin": 123456,
            "server": "Fake-Live",
            "mode": "DASHBOARD_TICKET_OPS",
            "allowedActions": ["order", "close", "cancel", "login"],
            "allowedRoutes": ["MA_Cross"],
            "allowedCanonicalSymbols": ["EURUSD"],
            "maxOrdersPerDay": 5,
            "maxLotsPerOrder": 0.01,
            "operator": "unit-test",
            **overrides,
        }
        path = runtime / "auth_lock.json"
        path.write_text(json.dumps(lock), encoding="utf-8")
        return path

    def test_default_order_is_dry_run_and_audited_without_mt5_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            fake = FakeMt5()
            result = client.execute_endpoint(
                "order",
                {
                    "route": "MA_Cross",
                    "symbol": "EURUSDc",
                    "side": "buy",
                    "orderType": "buy",
                    "lots": 0.01,
                    "dryRun": True,
                },
                runtime_dir=runtime,
                mt5=fake,
            )
            self.assertEqual(result["decision"], "DRY_RUN_ACCEPTED")
            self.assertFalse(result["safety"]["orderSendAllowed"])
            self.assertEqual(fake.order_send_calls, [])
            self.assertTrue((runtime / client.AUDIT_LEDGER_NAME).exists())

    def test_live_order_requires_config_env_and_auth_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            lock_path = self.write_lock(runtime)
            self.write_config(
                runtime,
                tradingEnabled=True,
                dryRun=False,
                killSwitch=False,
                ownerMode="DASHBOARD_TICKET_OPS",
                requireEnvEnable=False,
                signatureRequired=False,
                allowDashboardMarketOrders=True,
                authLockPath=str(lock_path),
                maxPortfolioLots=0.03,
                maxTotalLotsPerCanonical=0.03,
                maxOrdersPerRouteSymbolDay=5,
            )
            fake = FakeMt5()
            result = client.execute_endpoint(
                "order",
                {
                    "route": "MA_Cross",
                    "symbol": "EURUSDc",
                    "side": "buy",
                    "orderType": "buy",
                    "lots": 0.01,
                    "dryRun": False,
                },
                runtime_dir=runtime,
                mt5=fake,
            )
            self.assertEqual(result["decision"], "ORDER_SEND_ACCEPTED")
            self.assertTrue(result["safety"]["orderSendAllowed"])
            self.assertEqual(len(fake.order_send_calls), 1)

    def test_profile_save_never_persists_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            result = client.execute_endpoint(
                "save-profile",
                {
                    "profileId": "hfm-live",
                    "accountLogin": 123456,
                    "server": "Fake-Live",
                    "terminalPath": "C:\\MT5\\terminal64.exe",
                    "password": "secret-should-not-be-saved",
                    "passwordEnvVar": "QG_TEST_PASSWORD",
                },
                runtime_dir=runtime,
            )
            self.assertTrue(result["ok"])
            saved = json.loads((runtime / client.DEFAULT_PROFILES_NAME).read_text(encoding="utf-8"))
            text = json.dumps(saved)
            self.assertNotIn("secret-should-not-be-saved", text)
            self.assertFalse(saved["profiles"][0]["passwordPersisted"])


if __name__ == "__main__":
    unittest.main()
