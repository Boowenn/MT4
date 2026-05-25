import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_polymarket_research_bridge.py"
SPEC = importlib.util.spec_from_file_location("build_polymarket_research_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["build_polymarket_research_bridge"] = bridge
SPEC.loader.exec_module(bridge)


class PolymarketResearchBridgeTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_account_env_prefers_current_qg_polymarket_runtime(self):
        os.environ.update(
            {
                "QG_POLYMARKET_PRIVATE_KEY": "0x" + "1" * 64,
                "QG_POLYMARKET_FUNDER": "0x" + "a" * 40,
                "QG_POLYMARKET_SIGNATURE_TYPE": "1",
                "QG_POLYMARKET_REAL_EXECUTION": "true",
                "QG_POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
                "QG_POLYMARKET_CHAIN_ID": "137",
            }
        )

        env = bridge.account_env_from_sources(Path("/missing/.env"))

        self.assertEqual(env["PRIVATE_KEY"], "0x" + "1" * 64)
        self.assertEqual(env["POLY_FUNDER"], "0x" + "a" * 40)
        self.assertEqual(env["POLY_SIGNATURE_TYPE"], "1")
        self.assertEqual(env["_envPath"], "process.env:QG_POLYMARKET_*")
        self.assertEqual(env["DRY_RUN"], "false")

    def test_archived_snapshot_refreshes_account_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "history.sqlite"
            con = sqlite3.connect(db_path)
            con.execute(
                "CREATE TABLE qd_polymarket_research_snapshots (generated_at TEXT, raw_json TEXT)"
            )
            con.execute(
                "INSERT INTO qd_polymarket_research_snapshots VALUES (?, ?)",
                (
                    "2026-05-24T00:00:00Z",
                    json.dumps(
                        {
                            "summary": {"all": {"entries": 1}},
                            "accountSnapshot": {"accountCash": 7.1, "authState": "stale"},
                        }
                    ),
                ),
            )
            con.commit()
            con.close()
            original = bridge.read_account_snapshot
            bridge.read_account_snapshot = lambda *_args, **_kwargs: {
                "accountCash": 6.038926,
                "authState": "read_only_ok",
            }
            try:
                snapshot = bridge.build_snapshot(root, db_path, 14, 10, skip_account_snapshot=False)
            finally:
                bridge.read_account_snapshot = original

        self.assertEqual(snapshot["status"], "OK_ARCHIVED_SNAPSHOT")
        self.assertEqual(snapshot["accountSnapshot"]["accountCash"], 6.038926)
        self.assertEqual(snapshot["accountSnapshot"]["authState"], "read_only_ok")


if __name__ == "__main__":
    unittest.main()
