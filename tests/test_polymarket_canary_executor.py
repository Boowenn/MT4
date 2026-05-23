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

MODULE_PATH = ROOT / "tools" / "run_polymarket_canary_executor_v1.py"
spec = importlib.util.spec_from_file_location("run_polymarket_canary_executor_v1", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["run_polymarket_canary_executor_v1"] = module
spec.loader.exec_module(module)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PolymarketCanaryExecutorTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def args(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            runtime_dir=str(root / "runtime"),
            dashboard_dir=str(root / "dashboard"),
            governance_path="",
            canary_contract_path="",
            copy_discovery_path="",
            lock_file=str(root / "runtime" / "Polymarket_Canary_Isolated" / "REAL_MONEY_CANARY.lock"),
            max_orders=1,
            default_limit_price=0.50,
            min_order_size=1.0,
            plan_only=True,
        )

    def configure_env(self, root: Path) -> None:
        lock = root / "runtime" / "Polymarket_Canary_Isolated" / "REAL_MONEY_CANARY.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("REAL_MONEY_CANARY_OK\n", encoding="utf-8")
        os.environ.update({
            "QG_POLYMARKET_REAL_EXECUTION": "true",
            "QG_POLYMARKET_CANARY_ACK": "REAL_MONEY_CANARY_OK",
            "QG_POLYMARKET_CANARY_KILL_SWITCH": "false",
            "QG_POLYMARKET_WALLET_ADAPTER": "isolated_clob",
            "QG_POLYMARKET_PRIVATE_KEY": "0x" + "1" * 64,
            "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
            "QG_POLYMARKET_CHAIN_ID": "137",
        })

    def test_plan_only_executor_uses_copy_trader_shadow_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.configure_env(root)
            write_json(
                root / "dashboard" / module.COPY_DISCOVERY_NAME,
                {
                    "walletRiskPolicy": {
                        "status": "AUTONOMOUS_REAL_WALLET_ALLOWED",
                        "realWalletExecutionAllowed": True,
                        "autonomousUnlockAllowed": True,
                        "humanApprovalRequired": False,
                        "operatorApprovalRequired": False,
                        "hardBlockers": [],
                    },
                    "shadowCandidates": [{
                        "asset": "72094069823942324362885404801938332659316240217382754851102758232469673300092",
                        "conditionId": "0xabc",
                        "marketTitle": "Example market",
                        "url": "https://polymarket.com/event/example",
                        "outcome": "Yes",
                        "curPrice": 0.35,
                        "copyScore": 99,
                        "trader": "0x" + "2" * 40,
                        "riskPlan": {
                            "realWalletEligibleNow": True,
                            "walletWriteAllowed": True,
                            "orderSendAllowed": True,
                            "maxStakeUSDC": 1,
                            "takeProfitPct": 35,
                            "stopLossPct": 18,
                            "trailingStopPct": 12,
                            "blockers": [],
                        },
                    }],
                },
            )

            snapshot = module.build_snapshot(self.args(root))

            self.assertEqual(snapshot["summary"]["planSource"], "copy_trader_shadow_candidates")
            self.assertEqual(snapshot["summary"]["plannedOrders"], 1)
            self.assertEqual(snapshot["summary"]["eligibleCopyCandidateRows"], 1)
            plan = snapshot["plannedOrders"][0]
            self.assertEqual(plan["track"], "copy_trader")
            self.assertTrue(plan["tokenIdPresent"])
            self.assertEqual(plan["stakeUSDC"], 1)
            self.assertIn("PLAN_ONLY_FORCED", plan["blockers"])
            self.assertFalse(snapshot["safety"]["orderSendAllowed"])


if __name__ == "__main__":
    unittest.main()
