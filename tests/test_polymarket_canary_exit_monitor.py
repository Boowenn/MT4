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
            "latest_trade_for_order": module.latest_trade_for_order,
            "current_exit_price": module.current_exit_price,
            "current_position_size": module.current_position_size,
            "send_exit_order": module.send_exit_order,
        }
        module.make_client = lambda: object()
        module.latest_trade_for_order = lambda client, order_id: {"asset_id": "token-1", "price": 0.5}
        module.current_exit_price = lambda client, token_id: 0.48
        module.current_position_size = lambda client, token_id: 6.0
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


if __name__ == "__main__":
    unittest.main()
