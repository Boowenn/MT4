import argparse
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

MODULE_PATH = ROOT / "tools" / "run_polymarket_canary_exit_monitor_v1.py"
spec = importlib.util.spec_from_file_location("run_polymarket_canary_exit_monitor_v1", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["run_polymarket_canary_exit_monitor_v1"] = module
spec.loader.exec_module(module)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PolymarketCanaryExitMonitorTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.copy()
        os.environ["QG_POLYMARKET_CANARY_EXIT_MONITOR_PLAN_ONLY"] = "false"
        self._originals = {
            "make_client": module.make_client,
            "make_readonly_client": module.make_readonly_client,
            "latest_trade_for_order": module.latest_trade_for_order,
            "order_status_for_order": module.order_status_for_order,
            "latest_wallet_sell_for_token": module.latest_wallet_sell_for_token,
            "current_exit_price": module.current_exit_price,
            "current_position_size": module.current_position_size,
            "public_position_size": module.public_position_size,
            "send_exit_order": module.send_exit_order,
        }
        module.make_readonly_client = lambda: object()
        module.make_client = lambda: object()
        module.latest_trade_for_order = lambda client, order_id: {"asset_id": "token-1", "price": 0.5}
        module.order_status_for_order = lambda client, order_id: {}
        module.latest_wallet_sell_for_token = lambda client, token_id, owner_id="", after_ts=0, size_hint=0.0: {}
        module.current_exit_price = lambda client, token_id: 0.48
        module.current_position_size = lambda client, token_id: 6.0
        module.public_position_size = lambda token_id: 6.0
        module.send_exit_order = lambda client, token_id, size, price: (
            True,
            "EXIT_ORDER_SENT_V2",
            {"success": True, "orderID": "exit-1"},
        )

    def tearDown(self):
        for name, value in self._originals.items():
            setattr(module, name, value)
        os.environ.clear()
        os.environ.update(self._old_env)

    def args(self, root: Path, plan_only: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            runtime_dir=str(root / "runtime"),
            dashboard_dir=str(root / "dashboard"),
            plan_only=plan_only,
        )

    def write_executor(self, root: Path) -> None:
        write_json(
            root / "dashboard" / module.EXECUTOR_RUN_NAME,
            {
                "plannedOrders": [
                    {
                        "candidateId": "COPY-1",
                        "orderSent": True,
                        "response": {"orderID": "entry-1"},
                        "marketId": "condition-1",
                        "tokenId": "token-1",
                        "question": "Example market",
                        "copiedTrader": "Source Alpha",
                        "sourceProxyWallet": "0xabc",
                        "outcome": "Yes",
                        "takeProfitPct": 35,
                        "stopLossPct": 18,
                        "trailingProfitPct": 12,
                    }
                ]
            },
        )

    def test_source_trader_no_longer_holding_triggers_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            write_json(
                root / "dashboard" / module.COPY_DISCOVERY_NAME,
                {
                    "traders": [
                        {
                            "userName": "Source Alpha",
                            "proxyWallet": "0xabc",
                            "currentPositions": [],
                        }
                    ]
                },
            )

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "EXIT_SOURCE_TRADER_CLOSED")
            self.assertEqual(position["reason"], "copied_trader_no_longer_holds_token")
            self.assertEqual(position["sourcePositionStatus"], "SOURCE_POSITION_NOT_HELD")
            self.assertTrue(position["exitSent"])
            self.assertEqual(snapshot["summary"]["sourceExitSignals"], 1)

    def test_source_trader_still_holding_does_not_force_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            write_json(
                root / "dashboard" / module.COPY_DISCOVERY_NAME,
                {
                    "traders": [
                        {
                            "userName": "Source Alpha",
                            "proxyWallet": "0xabc",
                            "currentPositions": [
                                {
                                    "conditionId": "condition-1",
                                    "asset": "token-1",
                                    "outcome": "Yes",
                                    "size": 42,
                                    "currentValue": 21,
                                    "curPrice": 0.5,
                                }
                            ],
                        }
                    ]
                },
            )

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "HOLD")
            self.assertEqual(position["sourcePositionStatus"], "SOURCE_POSITION_STILL_HELD")
            self.assertFalse(position["exitSent"])
            self.assertEqual(snapshot["summary"]["sourceExitSignals"], 0)

    def test_shadow_candidate_source_size_is_derived_from_value_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            write_json(
                root / "dashboard" / module.COPY_DISCOVERY_NAME,
                {
                    "shadowCandidates": [
                        {
                            "trader": "Source Alpha",
                            "proxyWallet": "0xabc",
                            "conditionId": "condition-1",
                            "asset": "token-1",
                            "outcome": "Yes",
                            "currentValue": 21,
                            "curPrice": 0.5,
                        }
                    ],
                    "traders": [
                        {
                            "userName": "Source Alpha",
                            "proxyWallet": "0xabc",
                            "currentPositions": [],
                        }
                    ],
                },
            )

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "HOLD")
            self.assertEqual(position["sourcePositionStatus"], "SOURCE_POSITION_STILL_HELD")
            self.assertEqual(position["sourcePositionSize"], 42)

    def test_absolute_micro_profit_triggers_exit_before_large_percent_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            data = json.loads((root / "dashboard" / module.EXECUTOR_RUN_NAME).read_text(encoding="utf-8"))
            data["plannedOrders"][0]["takeProfitPct"] = 35
            data["plannedOrders"][0]["takeProfitUSDC"] = 0.05
            write_json(root / "dashboard" / module.EXECUTOR_RUN_NAME, data)
            write_json(
                root / "dashboard" / module.COPY_DISCOVERY_NAME,
                {
                    "traders": [
                        {
                            "userName": "Source Alpha",
                            "proxyWallet": "0xabc",
                            "currentPositions": [
                                {
                                    "conditionId": "condition-1",
                                    "asset": "token-1",
                                    "outcome": "Yes",
                                    "size": 42,
                                    "currentValue": 21,
                                    "curPrice": 0.5,
                                }
                            ],
                        }
                    ]
                },
            )
            module.current_exit_price = lambda client, token_id: 0.51
            module.current_position_size = lambda client, token_id: 6.0

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "EXIT_TAKE_PROFIT_USDC")
            self.assertEqual(position["reason"], "take_profit_usdc_reached")
            self.assertEqual(position["takeProfitUSDC"], 0.05)
            self.assertEqual(position["takeProfitUSDCPrice"], 0.5083)
            self.assertEqual(position["unrealizedPnlUSDC"], 0.06)
            self.assertTrue(position["exitSent"])

    def test_zero_size_after_authenticated_fallback_does_not_send_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            module.current_exit_price = lambda client, token_id: 0.36
            module.public_position_size = lambda token_id: 0.0
            module.current_position_size = lambda client, token_id: 0.0

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "NO_SELLABLE_POSITION")
            self.assertEqual(position["reason"], "zero_sellable_position")
            self.assertEqual(position["adapterStatus"], "NOT_ATTEMPTED")
            self.assertFalse(position["exitSent"])
            self.assertTrue(snapshot["clobAuth"]["attempted"])
            self.assertEqual(snapshot["summary"]["clobAuthStatus"], "ATTEMPTED_OK")
            self.assertEqual(snapshot["summary"]["positionsTracked"], 0)
            self.assertEqual(snapshot["summary"]["openOrderOnly"], 1)

    def test_authenticated_balance_fallback_can_trigger_exit_when_public_api_lags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            module.public_position_size = lambda token_id: 0.0
            module.current_position_size = lambda client, token_id: 6.0
            module.current_exit_price = lambda client, token_id: 0.36

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["positionSizeSource"], "clob_balance_allowance_authenticated_fallback")
            self.assertEqual(position["decision"], "EXIT_STOP_LOSS")
            self.assertTrue(position["exitSent"])
            self.assertEqual(snapshot["summary"]["positionsTracked"], 1)

    def test_authenticated_clob_sell_trade_is_reflected_after_position_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_executor(root)
            module.public_position_size = lambda token_id: 0.0
            module.current_position_size = lambda client, token_id: 0.0
            module.current_exit_price = lambda client, token_id: 0.48
            module.order_status_for_order = lambda client, order_id: {
                "status": "MATCHED",
                "owner": "owner-1",
                "created_at": 123,
                "size_matched": "6",
            }
            module.latest_wallet_sell_for_token = (
                lambda client, token_id, owner_id="", after_ts=0, size_hint=0.0: {
                    "id": "trade-1",
                    "taker_order_id": "sell-1",
                    "side": "SELL",
                    "status": "CONFIRMED",
                    "price": "0.55",
                    "size": "6",
                    "transaction_hash": "0xabc",
                }
            )

            snapshot = module.build_snapshot(self.args(root))

            position = snapshot["positions"][0]
            self.assertEqual(position["decision"], "EXIT_WALLET_SELL_CONFIRMED")
            self.assertEqual(position["reason"], "clob_sell_trade_detected_after_entry")
            self.assertEqual(position["adapterStatus"], "CLOB_SELL_CONFIRMED_READONLY")
            self.assertEqual(position["exitOrderID"], "sell-1")
            self.assertEqual(position["exitPrice"], 0.55)
            self.assertEqual(position["realizedPnlUSDC"], 0.3)
            self.assertFalse(position["exitSent"])
            self.assertEqual(snapshot["summary"]["exitSignals"], 1)

    def test_v2_signature_type_uses_proxy_wallet_type_for_funder_wallet(self):
        os.environ["QG_POLYMARKET_SIGNATURE_TYPE"] = "1"
        os.environ["QG_POLYMARKET_FUNDER"] = "0x" + "a" * 40

        self.assertEqual(module.clob_v2_signature_type(), 1)

    def test_explicit_v2_signature_type_can_select_1271(self):
        os.environ["QG_POLYMARKET_SIGNATURE_TYPE"] = "1"
        os.environ["QG_POLYMARKET_CLOB_V2_SIGNATURE_TYPE"] = "3"
        os.environ["QG_POLYMARKET_FUNDER"] = "0x" + "a" * 40

        self.assertEqual(module.clob_v2_signature_type(), 3)

    def test_auth_config_prefers_derive_without_create_noise(self):
        calls = []

        class FakeClient:
            def derive_api_key(self):
                calls.append("derive")
                return {"apiKey": "derived"}

            def create_api_key(self):
                calls.append("create")
                return {"apiKey": "created"}

            def set_api_creds(self, creds):
                calls.append(("set", creds["apiKey"]))

        module.configure_client_api_creds(FakeClient())

        self.assertEqual(calls, ["derive", ("set", "derived")])



if __name__ == "__main__":
    unittest.main()
