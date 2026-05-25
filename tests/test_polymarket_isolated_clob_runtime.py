import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

SETUP_PATH = ROOT / "tools" / "setup_polymarket_isolated_clob_runtime.py"
DISCOVERY_PATH = ROOT / "tools" / "build_polymarket_copy_trader_discovery.py"


def load_tool_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


setup_runtime = load_tool_module("setup_polymarket_isolated_clob_runtime", SETUP_PATH)
discovery = load_tool_module("build_polymarket_copy_trader_discovery", DISCOVERY_PATH)


class EnvPatch:
    def __init__(self, **values):
        self.values = values
        self.previous = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)

    def __exit__(self, *_exc):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class PolymarketIsolatedClobRuntimeTests(unittest.TestCase):
    def setup_args(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            runtime_dir=str(root / "runtime"),
            dashboard_dir=str(root / "dashboard"),
            isolated_root=str(root / "isolated"),
            adapter="isolated_clob",
            clob_host="https://clob.polymarket.com",
            chain_id=137,
            max_position_usdc=1.0,
            max_daily_loss_usdc=2.0,
            max_open_positions=3,
        )

    def test_setup_writes_prepare_only_manifest_without_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp, EnvPatch(
            QG_POLYMARKET_REAL_EXECUTION="false",
            QG_POLYMARKET_CANARY_KILL_SWITCH="true",
            QG_POLYMARKET_PRIVATE_KEY="super-secret-test-key",
            QG_POLYMARKET_FUNDER="0xabc",
        ):
            root = Path(tmp)
            args = self.setup_args(root)

            snapshot = setup_runtime.build_snapshot(args)
            written = setup_runtime.write_outputs(snapshot, Path(args.runtime_dir), Path(args.dashboard_dir))
            manifest = json.loads((Path(args.dashboard_dir) / setup_runtime.OUTPUT_NAME).read_text(encoding="utf-8"))
            text = json.dumps(manifest, ensure_ascii=False)

            self.assertTrue(snapshot["runtimePrepared"])
            self.assertEqual(snapshot["status"], "PREPARED_REAL_WALLET_BLOCKED")
            self.assertFalse(snapshot["safety"]["orderSendAllowed"])
            self.assertFalse(snapshot["safety"]["walletWriteAllowed"])
            self.assertTrue(snapshot["wallet"]["privateKeyConfigured"])
            self.assertEqual(snapshot["wallet"]["effectiveV2SignatureType"], 1)
            self.assertNotIn("super-secret-test-key", text)
            self.assertGreaterEqual(len(written), 4)
            self.assertTrue((Path(args.isolated_root) / "audit" / setup_runtime.ORDER_INTENT_LEDGER).exists())

    def test_setup_flags_v2_1271_signer_mismatch_before_order_post(self):
        with tempfile.TemporaryDirectory() as tmp, EnvPatch(
            QG_POLYMARKET_REAL_EXECUTION="true",
            QG_POLYMARKET_CANARY_KILL_SWITCH="false",
            QG_POLYMARKET_PRIVATE_KEY="0x" + "1" * 64,
            QG_POLYMARKET_FUNDER="0x" + "a" * 40,
            QG_POLYMARKET_CLOB_V2_SIGNATURE_TYPE="3",
        ):
            root = Path(tmp)
            args = self.setup_args(root)

            snapshot = setup_runtime.build_snapshot(args)

            self.assertEqual(snapshot["wallet"]["effectiveV2SignatureType"], 3)
            self.assertEqual(snapshot["wallet"]["signerPreflight"]["status"], "SIGNER_MISMATCH")
            self.assertIn("v2_api_key_signer_mismatch_risk", snapshot["preflight"]["blockers"])
            self.assertFalse(snapshot["preflight"]["passedForRealOrders"])

    def test_discovery_preflight_accepts_isolated_manifest_but_keeps_real_wallet_blocked(self):
        with tempfile.TemporaryDirectory() as tmp, EnvPatch(
            QG_POLYMARKET_REAL_EXECUTION="false",
            QG_POLYMARKET_CANARY_KILL_SWITCH="true",
            QG_POLYMARKET_WALLET_ADAPTER=None,
            QG_POLYMARKET_CLOB_HOST=None,
            QG_POLYMARKET_PRIVATE_KEY=None,
        ):
            root = Path(tmp)
            args = self.setup_args(root)
            snapshot = setup_runtime.build_snapshot(args)
            setup_runtime.write_outputs(snapshot, Path(args.runtime_dir), Path(args.dashboard_dir))

            preflight = discovery.wallet_runtime_preflight(Path(args.runtime_dir), Path(args.dashboard_dir))

            self.assertTrue(preflight["isolatedRuntimePrepared"])
            self.assertTrue(preflight["walletAdapterIsolatedClob"])
            self.assertTrue(preflight["clobHostConfigured"])
            self.assertFalse(preflight["passed"])
            self.assertIn("real_execution_switch_false", preflight["blockers"])
            self.assertIn("wallet_kill_switch_on_or_unset", preflight["blockers"])
            self.assertIn("private_key_env_missing", preflight["blockers"])
            self.assertNotIn("wallet_adapter_not_isolated_clob", preflight["blockers"])
            self.assertNotIn("clob_host_env_missing", preflight["blockers"])


if __name__ == "__main__":
    unittest.main()
