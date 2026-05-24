import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

MODULE_PATH = ROOT / "tools" / "sync_polymarket_micro_live_unlock.py"
spec = importlib.util.spec_from_file_location("sync_polymarket_micro_live_unlock", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["sync_polymarket_micro_live_unlock"] = module
spec.loader.exec_module(module)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PolymarketMicroLiveUnlockTests(unittest.TestCase):
    def args(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            runtime_dir=str(root / "runtime"),
            dashboard_dir=str(root / "dashboard"),
            repo_env=str(root / ".env.local"),
            launchd_env=str(root / "launchd.env"),
            lock_file=str(root / "runtime" / "Polymarket_Canary_Isolated" / "REAL_MONEY_CANARY.lock"),
            min_shadow_samples=30,
            min_walk_batches=3,
            dry_run=False,
        )

    def write_passing_inputs(self, root: Path) -> None:
        dashboard = root / "dashboard"
        write_json(
            dashboard / module.COPY_DISCOVERY_NAME,
            {
                "summary": {
                    "shadowCandidates": 100,
                    "telegramWallets": 20,
                    "telegramSignals": 100,
                },
                "sourceStatus": {"telegramChannel": {"configured": True}},
                "walletRiskPolicy": {"realWalletRequested": True, "autonomousUnlockAllowed": True},
            },
        )
        write_json(
            dashboard / module.SHADOW_REPLAY_NAME,
            {
                "status": "PASSED",
                "passed": True,
                "summary": {"samples": 171, "profitFactor": 2.4, "netPnlUSDC": 18.7},
            },
        )
        write_json(
            dashboard / module.WALK_FORWARD_NAME,
            {"status": "PASSED", "passed": True, "batches": 3, "passRatePct": 100, "netPnlUSDC": 18.7},
        )
        write_json(
            dashboard / module.ISOLATED_RUNTIME_NAME,
            {
                "runtimePrepared": True,
                "adapter": {"name": "isolated_clob", "configured": True},
                "clob": {"hostConfigured": True, "host": "https://clob.polymarket.com"},
            },
        )

    def test_passing_strategy_unlocks_software_switches_without_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            self.write_passing_inputs(root)

            payload = module.snapshot(args)

            self.assertEqual(payload["status"], "MICRO_LIVE_SOFTWARE_UNLOCKED_PRIVATE_KEY_MISSING")
            self.assertTrue(payload["strategyGatePassed"])
            self.assertTrue(payload["softwareSwitchesUnlocked"])
            self.assertFalse(payload["privateKeyConfigured"])
            self.assertTrue(Path(args.lock_file).exists())
            env_text = Path(args.repo_env).read_text(encoding="utf-8")
            self.assertIn("QG_POLYMARKET_REAL_EXECUTION=true", env_text)
            self.assertIn("QG_POLYMARKET_CANARY_KILL_SWITCH=false", env_text)
            self.assertIn("QG_POLYMARKET_CANARY_ACK=REAL_MONEY_CANARY_OK", env_text)
            self.assertNotIn("QG_POLYMARKET_PRIVATE_KEY", env_text)
            self.assertFalse(payload["safety"]["orderSendAllowedByThisTool"])

    def test_failed_strategy_relocks_switches_and_removes_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            self.write_passing_inputs(root)
            Path(args.lock_file).parent.mkdir(parents=True, exist_ok=True)
            Path(args.lock_file).write_text("REAL_MONEY_CANARY_OK\n", encoding="utf-8")
            write_json(root / "dashboard" / module.SHADOW_REPLAY_NAME, {"status": "FAILED", "passed": False, "samples": 12})

            payload = module.snapshot(args)

            self.assertEqual(payload["status"], "MICRO_LIVE_LOCKED_BY_STRATEGY_GATE")
            self.assertFalse(payload["strategyGatePassed"])
            self.assertFalse(payload["softwareSwitchesUnlocked"])
            self.assertFalse(Path(args.lock_file).exists())
            env_text = Path(args.repo_env).read_text(encoding="utf-8")
            self.assertIn("QG_POLYMARKET_REAL_EXECUTION=false", env_text)
            self.assertIn("QG_POLYMARKET_CANARY_KILL_SWITCH=true", env_text)

    def test_source_scoped_policy_unlocks_without_global_replay_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self.args(root)
            dashboard = root / "dashboard"
            write_json(
                dashboard / module.COPY_DISCOVERY_NAME,
                {
                    "summary": {
                        "shadowCandidates": 12,
                        "telegramWallets": 8,
                        "telegramSignals": 72,
                    },
                    "sourceStatus": {"telegramChannel": {"configured": True}},
                    "walletRiskPolicy": {
                        "realWalletRequested": True,
                        "autonomousUnlockAllowed": True,
                        "strategyEvidenceGatePassed": True,
                        "sourceScopedMicroLiveGatePassed": True,
                        "sourceScopedMicroLiveGate": {
                            "promotedSources": ["telegram_telethon:ai 1000x polymarket"],
                            "promotedCompositeBucketCount": 3,
                        },
                    },
                },
            )
            write_json(dashboard / module.SHADOW_REPLAY_NAME, {"status": "FAILED", "passed": False, "samples": 211})
            write_json(dashboard / module.WALK_FORWARD_NAME, {"status": "FAILED", "passed": False, "batches": 3})
            write_json(dashboard / module.ISOLATED_RUNTIME_NAME, {"runtimePrepared": True})

            payload = module.snapshot(args)

            self.assertTrue(payload["strategyGatePassed"])
            self.assertTrue(payload["softwareSwitchesUnlocked"])
            self.assertEqual(payload["gate"]["evidenceMode"], "SOURCE_SCOPED_MICRO_LIVE")
            self.assertTrue(Path(args.lock_file).exists())
            env_text = Path(args.repo_env).read_text(encoding="utf-8")
            self.assertIn("QG_POLYMARKET_REAL_EXECUTION=true", env_text)
            self.assertIn("QG_POLYMARKET_CANARY_KILL_SWITCH=false", env_text)


if __name__ == "__main__":
    unittest.main()
