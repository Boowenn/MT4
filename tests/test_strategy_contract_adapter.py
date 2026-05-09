from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.strategy_contract_adapter.builder import build_strategy_contract, read_strategy_contract_status
from tools.strategy_contract_adapter.schema import (
    CONTRACT_EA_FILE,
    CONTRACT_JSON_FILE,
    EA_STATUS_FILE,
    EA_SHADOW_EVALUATION_LEDGER_FILE,
    EA_SHADOW_EVALUATION_STATUS_FILE,
)
from tools.strategy_ga.fitness import score_seed
from tools.strategy_ga.seed_generator import case_memory_seed_pool
from tools.strategy_json.schema import base_strategy_seed
from tools.usdjpy_evidence_os.case_memory import build_case_memory


class StrategyContractAdapterTests(unittest.TestCase):
    def test_build_writes_shadow_only_contract_and_ea_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            payload = build_strategy_contract(runtime, write=True)

            self.assertTrue(payload["ok"])
            contract = payload["contract"]
            self.assertEqual(contract["contractMode"], "SHADOW_EVALUATION_ONLY")
            self.assertEqual(contract["focusSymbol"], "USDJPYc")
            self.assertFalse(contract["safety"]["orderSendAllowed"])
            self.assertFalse(contract["safety"]["livePresetMutationAllowed"])
            self.assertTrue((runtime / CONTRACT_JSON_FILE).exists())
            self.assertTrue((runtime / CONTRACT_EA_FILE).exists())
            ea_text = (runtime / CONTRACT_EA_FILE).read_text(encoding="utf-8")
            self.assertIn("orderSendAllowed=false", ea_text)
            self.assertIn("shadowOnly=true", ea_text)
            self.assertIn("strategyFamily=RSI_Reversal", ea_text)

    def test_status_reads_ea_ack_without_granting_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            build_strategy_contract(runtime, write=True)
            (runtime / EA_STATUS_FILE).write_text(
                json.dumps(
                    {
                        "status": "SHADOW_CONTRACT_READY",
                        "loaded": True,
                        "orderSendAllowed": False,
                        "livePresetMutationAllowed": False,
                        "reasonZh": "EA 已加载只读 Strategy JSON contract。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            status = read_strategy_contract_status(runtime)
            self.assertEqual(status["eaStatus"]["status"], "SHADOW_CONTRACT_READY")
            self.assertFalse(status["safety"]["orderSendAllowed"])

    def test_status_reads_ea_shadow_evaluation_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            build_strategy_contract(runtime, write=True)
            evaluation = {
                "schema": "quantgod.strategy_json_ea_shadow_evaluation.v1",
                "evaluationId": "eval-1",
                "status": "SHADOW_WOULD_ENTER",
                "blocker": "NONE",
                "selectedSeedId": "GA-USDJPY-001",
                "fingerprint": "abc123",
                "strategyId": "USDJPY_RSI_REVERSAL_LONG_CASE",
                "strategyFamily": "RSI_Reversal",
                "direction": "LONG",
                "lane": "MT5_SHADOW",
                "wouldEnter": True,
                "hardGuardsPass": True,
                "reasonZh": "EA shadow saw a contract signal.",
            }
            (runtime / EA_SHADOW_EVALUATION_STATUS_FILE).write_text(
                json.dumps(evaluation, ensure_ascii=False),
                encoding="utf-8",
            )
            (runtime / EA_SHADOW_EVALUATION_LEDGER_FILE).write_text(
                json.dumps(evaluation, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            status = read_strategy_contract_status(runtime)

            self.assertEqual(status["eaShadowEvaluation"]["status"], "SHADOW_WOULD_ENTER")
            self.assertEqual(status["eaShadowEvaluationRecent"][-1]["evaluationId"], "eval-1")

    def test_ea_shadow_evaluation_feeds_case_memory_and_ga_seed_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            evaluation = {
                "schema": "quantgod.strategy_json_ea_shadow_evaluation.v1",
                "evaluationId": "eval-ga",
                "status": "SHADOW_WOULD_ENTER",
                "blocker": "NONE",
                "selectedSeedId": "GA-USDJPY-CASE",
                "fingerprint": "fp-case",
                "strategyId": "USDJPY_RSI_REVERSAL_LONG_CASE",
                "strategyFamily": "RSI_Reversal",
                "direction": "LONG",
                "lane": "MT5_SHADOW",
                "wouldEnter": True,
                "hardGuardsPass": True,
                "rsiClosed1": 32.5,
                "rsiClosed2": 29.5,
                "spreadPips": 0.4,
            }
            (runtime / EA_SHADOW_EVALUATION_LEDGER_FILE).write_text(
                json.dumps(evaluation, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            cases = build_case_memory(runtime, write=True)
            seeds = case_memory_seed_pool(runtime)

            self.assertIn("STRATEGY_CONTRACT_SHADOW_SIGNAL", cases["caseTypeCounts"])
            self.assertTrue(any(case.get("strategy") == "RSI_Reversal" for case in cases["cases"]))
            self.assertGreaterEqual(cases["caseMemoryToGA"]["queuedHintCount"], 1)
            self.assertTrue(any(seed.get("mutationHint") == "promote_contract_candidate_to_tester" for seed in seeds))

    def test_generic_shadow_evaluation_feeds_case_memory_summary_and_ga_fitness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            rows = [
                {
                    "schema": "quantgod.strategy_json_ea_shadow_evaluation.v1",
                    "evaluationId": "eval-ma-observe",
                    "status": "SHADOW_OBSERVE",
                    "blocker": "NONE",
                    "selectedSeedId": "GA-USDJPY-MA-OBSERVE",
                    "fingerprint": "fp-ma-observe",
                    "strategyId": "USDJPY_MA_CROSS_LONG_SHADOW",
                    "strategyFamily": "MA_Cross",
                    "direction": "LONG",
                    "lane": "MT5_SHADOW",
                    "contractFamilyImplemented": True,
                    "wouldEnter": False,
                    "hardGuardsPass": True,
                    "reasonZh": "MA shadow adapter observed the contract.",
                },
                {
                    "schema": "quantgod.strategy_json_ea_shadow_evaluation.v1",
                    "evaluationId": "eval-ma-would-enter",
                    "status": "SHADOW_WOULD_ENTER",
                    "blocker": "NONE",
                    "selectedSeedId": "GA-USDJPY-MA-SIGNAL",
                    "fingerprint": "fp-ma-signal",
                    "strategyId": "USDJPY_MA_CROSS_LONG_SIGNAL",
                    "strategyFamily": "MA_Cross",
                    "direction": "LONG",
                    "lane": "MT5_SHADOW",
                    "contractFamilyImplemented": True,
                    "wouldEnter": True,
                    "hardGuardsPass": True,
                    "reasonZh": "MA shadow adapter saw a would-enter signal.",
                },
            ]
            (runtime / EA_SHADOW_EVALUATION_LEDGER_FILE).write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            cases = build_case_memory(runtime, write=True)
            shadow = cases["strategyContractShadowEvaluation"]
            ma_summary = shadow["genericAdapterSummary"]["MA_Cross"]

            self.assertIn("MA_Cross", shadow["genericAdapterStableFamilies"])
            self.assertEqual(ma_summary["shadowObserveCount"], 2)
            self.assertEqual(ma_summary["shadowWouldEnterCount"], 1)
            self.assertIn("STRATEGY_CONTRACT_SHADOW_SIGNAL", cases["caseTypeCounts"])
            self.assertTrue(any(case.get("strategy") == "MA_Cross" for case in cases["cases"]))

            score = score_seed(base_strategy_seed("GA-USDJPY-MA-SCORE", family="MA_Cross"), runtime)
            self.assertTrue(score["strategyContractShadow"]["adapterStable"])
            self.assertEqual(score["strategyContractShadow"]["strategyFamily"], "MA_Cross")
            self.assertGreater(score["strategyContractShadowBonus"], 0.0)

    def test_case_memory_uses_latest_shadow_evaluation_for_same_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            old_gap = {
                "schema": "quantgod.strategy_json_ea_shadow_evaluation.v1",
                "evaluationId": "eval-old-gap",
                "selectedSeedId": "GA-USDJPY-TOKYO",
                "fingerprint": "fp-tokyo",
                "strategyId": "USDJPY_TOKYO_RANGE_BREAKOUT_SHORT",
                "strategyFamily": "USDJPY_TOKYO_RANGE_BREAKOUT",
                "direction": "SHORT",
                "status": "UNSUPPORTED_STRATEGY_FAMILY_SHADOW_OBSERVE",
                "blocker": "EA_CONTRACT_FAMILY_NOT_IMPLEMENTED",
                "reasonZh": "old adapter gap",
            }
            latest_waiting = {
                **old_gap,
                "evaluationId": "eval-latest-wait",
                "status": "SHADOW_WAIT_INDICATORS",
                "blocker": "TOKYO_RANGE_WAIT_WINDOW",
                "reasonZh": "Tokyo adapter now evaluates the contract.",
            }
            (runtime / EA_SHADOW_EVALUATION_LEDGER_FILE).write_text(
                json.dumps(old_gap, ensure_ascii=False) + "\n" + json.dumps(latest_waiting, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            cases = build_case_memory(runtime, write=True)

            self.assertNotIn("STRATEGY_CONTRACT_EA_ADAPTER_GAP", cases["caseTypeCounts"])


if __name__ == "__main__":
    unittest.main()
