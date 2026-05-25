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
            "QG_POLYMARKET_VALIDATE_EXISTING_LIVE_ORDERS": "false",
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
            self.assertEqual(plan["sourceProxyWallet"], "")
            self.assertIn("PLAN_ONLY_FORCED", plan["blockers"])
            self.assertFalse(snapshot["safety"]["orderSendAllowed"])

    def test_detects_v2_api_key_signer_mismatch(self):
        exc = RuntimeError(
            "PolyApiException[status_code=400, error_message={'error': "
            "'the order signer address has to be the address of the API KEY'}]"
        )

        self.assertTrue(module.is_v2_api_key_signer_mismatch(exc))
        self.assertFalse(module.is_v2_api_key_signer_mismatch(RuntimeError("insufficient balance")))

    def test_v2_signature_type_keeps_proxy_wallet_legacy_type(self):
        os.environ["QG_POLYMARKET_SIGNATURE_TYPE"] = "1"
        os.environ["QG_POLYMARKET_FUNDER"] = "0x" + "a" * 40

        self.assertEqual(module.clob_v2_signature_type(), 1)

    def test_signer_preflight_catches_1271_api_key_mismatch(self):
        class FakeClient:
            def get_address(self):
                return "0x" + "1" * 40

        preflight = module.clob_signer_preflight(
            FakeClient(),
            signature_type=3,
            funder="0x" + "a" * 40,
        )

        self.assertEqual(preflight["status"], "SIGNER_MISMATCH")
        self.assertFalse(preflight["apiKeySignerMatchesOrderSigner"])

    def test_existing_live_order_blocks_duplicate_send_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.configure_env(root)
            args = self.args(root)
            args.plan_only = False
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
                        "asset": "token-1",
                        "conditionId": "condition-1",
                        "marketTitle": "Example market",
                        "curPrice": 0.5,
                        "copyScore": 99,
                        "trader": "source",
                        "riskPlan": {
                            "realWalletEligibleNow": True,
                            "walletWriteAllowed": True,
                            "orderSendAllowed": True,
                            "maxStakeUSDC": 1,
                            "blockers": [],
                        },
                    }],
                },
            )
            audit = root / "dashboard" / module.ORDER_AUDIT_LEDGER
            audit.parent.mkdir(parents=True, exist_ok=True)
            candidate_id = "COPY-" + module.stable_id("token-1", "condition-1", "source", "")
            audit.write_text(
                "generated_at,run_id,mode,candidate_id,governance_id,market_id,question,track,side,token_id_present,limit_price,stake_usdc,size,take_profit_usdc,decision,order_sent,wallet_write_allowed,order_send_allowed,blockers,adapter_status,response_id,response_status,tx_hash\n"
                f"2026-05-25T00:00:00Z,run,REAL_ORDER_ATTEMPTED,{candidate_id},,condition-1,Example market,copy_trader,BUY,True,0.5,1,2,0.05,READY_TO_SEND_IF_ADAPTER_OK,True,True,True,,ORDER_SENT_V2,order-1,live,\n",
                encoding="utf-8",
            )

            snapshot = module.build_snapshot(args)

            self.assertEqual(snapshot["decision"], "EXISTING_LIVE_ORDER_TRACKED")
            self.assertEqual(snapshot["summary"]["existingLiveOrders"], 1)
            self.assertEqual(snapshot["summary"]["sendablePlannedOrders"], 0)
            self.assertEqual(snapshot["plannedOrders"][0]["adapterStatus"], "EXISTING_LIVE_ORDER")
            self.assertTrue(snapshot["plannedOrders"][0]["orderSent"])

    def test_existing_live_order_is_ignored_after_clob_terminal_status(self):
        candidate_id = "COPY-" + module.stable_id("token-1", "condition-1", "source", "")
        plan = {"candidateId": candidate_id, "marketId": "condition-1"}
        rows = [
            {
                "candidate_id": candidate_id,
                "market_id": "condition-1",
                "order_sent": "true",
                "response_id": "order-1",
                "response_status": "live",
            }
        ]

        self.assertEqual(
            module.active_existing_order_for_plan(plan, rows, lambda order_id: "MATCHED"),
            {},
        )
        self.assertEqual(
            module.active_existing_order_for_plan(plan, rows, lambda order_id: "NOT_OPEN"),
            {},
        )
        self.assertEqual(
            module.active_existing_order_for_plan(plan, rows, lambda order_id: "OPEN")["response_id"],
            "order-1",
        )


if __name__ == "__main__":
    unittest.main()
