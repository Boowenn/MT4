from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.state_store import STATE_STORE_SAFETY, StateStore, build_config
from tools.state_store.ingest import ingest_sources


class StateStoreTests(unittest.TestCase):
    def make_repo(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="qg-state-store-test-"))
        (temp / "runtime").mkdir(parents=True)
        (temp / "Dashboard").mkdir(parents=True)
        (temp.parent / "QuantGodDocs" / "docs" / "contracts").mkdir(parents=True, exist_ok=True)
        return temp

    def test_safety_defaults_are_non_execution(self) -> None:
        for key in (
            "canExecuteTrade",
            "orderSendAllowed",
            "closeAllowed",
            "cancelAllowed",
            "credentialStorageAllowed",
            "livePresetMutationAllowed",
            "canOverrideKillSwitch",
            "canMutateGovernanceDecision",
            "canPromoteOrDemoteRoute",
            "telegramCommandExecutionAllowed",
        ):
            self.assertIs(STATE_STORE_SAFETY[key], False)
        self.assertIs(STATE_STORE_SAFETY["localOnly"], True)
        self.assertIs(STATE_STORE_SAFETY["readOnlyDataPlane"], True)

    def test_init_and_ingest_local_evidence(self) -> None:
        repo = self.make_repo()
        runtime = repo / "runtime"
        docs_contract = repo.parent / "QuantGodDocs" / "docs" / "contracts" / "api-contract.json"
        docs_contract.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "project": "QuantGod",
                    "lastReviewed": "2026-05-02",
                    "endpointGroups": [
                        {"name": "state", "phase": "phase2", "endpoints": [{"method": "GET", "path": "/api/state"}]}
                    ],
                }
            ),
            encoding="utf-8",
        )
        (runtime / "QuantGod_AIAnalysisRun.json").write_text(
            json.dumps({"runId": "ai-1", "symbol": "XAUUSD", "status": "ok", "generatedAt": "2026-05-02T00:00:00Z"}),
            encoding="utf-8",
        )
        (runtime / "QuantGod_VibeStrategy.json").write_text(
            json.dumps({"strategyId": "vibe-1", "name": "Research only", "status": "draft"}),
            encoding="utf-8",
        )
        (runtime / "QuantGod_NotificationHistory.json").write_text(
            json.dumps({"events": [{"eventId": "n-1", "eventType": "TEST", "status": "sent"}]}),
            encoding="utf-8",
        )

        config = build_config(repo_root=repo, db_path=repo / "runtime" / "state.sqlite")
        store = StateStore(config)
        status = store.init()
        self.assertTrue(status["ok"])
        result = ingest_sources(config, ["all"])
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["counts"]["ai-analysis"], 1)
        self.assertGreaterEqual(result["counts"]["vibe"], 1)
        self.assertGreaterEqual(result["counts"]["notifications"], 1)
        self.assertEqual(result["counts"]["api-contract"], 1)
        self.assertEqual(store.query_ai_runs(symbol="XAUUSD")[0]["run_id"], "ai-1")
        self.assertTrue(store.query_ai_runs(symbol="XAUUSD")[0]["advisory_only"])
        self.assertTrue(store.query_vibe_strategies()[0]["research_only"])
        self.assertTrue(store.query_notifications()[0]["push_only"])

    def test_cli_status_outputs_json(self) -> None:
        repo = self.make_repo()
        db_path = repo / "runtime" / "state.sqlite"
        script = REPO_ROOT / "tools" / "run_state_store.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo), "--db", str(db_path), "status"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("qg_events", payload["tables"])
        self.assertFalse(payload["safety"]["orderSendAllowed"])


if __name__ == "__main__":
    unittest.main()
