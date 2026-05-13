from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.ga_multi_generation_stability.stability import build_report


class GAMultiGenerationStabilityTests(unittest.TestCase):
    def test_build_report_detects_stable_generation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            ga = runtime / "ga"
            ga.mkdir(parents=True)
            (ga / "QuantGod_GAStatus.json").write_text(json.dumps({"currentGeneration": 3}), encoding="utf-8")
            rows = []
            for generation in (1, 2, 3):
                for index in range(6):
                    rows.append(
                        {
                            "seedId": f"g{generation}-{index}",
                            "strategyId": f"S{index}",
                            "strategyFamily": "RSI_Reversal",
                            "generation": generation,
                            "fitness": 1.0 + generation + index / 100,
                            "status": "ELITE_SELECTED" if index == 0 else "NEEDS_MORE_DATA",
                            "promotionStage": "SHADOW",
                        }
                    )
            (ga / "QuantGod_GACandidateRuns.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            (ga / "QuantGod_GALineage.json").write_text(
                json.dumps(
                    {
                        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
                        "edges": [
                            {"source": "a", "target": "b"},
                            {"source": "b", "target": "c"},
                            {"source": "c", "target": "d"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            factory = runtime / "ga_factory"
            factory.mkdir(parents=True)
            (factory / "QuantGod_GAFactoryLedger.csv").write_text(
                "generatedAt,status\n2026-01-01T00:00:00Z,FACTORY_READY\n2026-01-01T00:05:00Z,FACTORY_READY\n",
                encoding="utf-8",
            )
            report = build_report(runtime, write=True)
            self.assertEqual(report["status"], "PASS")
            self.assertGreaterEqual(report["generationCount"], 3)
            self.assertGreaterEqual(report["candidateCount"], 18)
            self.assertGreaterEqual(report["eliteCount"], 1)
            self.assertTrue((runtime / "production_validation" / "QuantGod_GAMultiGenerationStabilityReport.json").exists())


if __name__ == "__main__":
    unittest.main()
