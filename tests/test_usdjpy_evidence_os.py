import tempfile
import unittest
from pathlib import Path

from tools.strategy_ga.fitness import score_seed
from tools.strategy_json.schema import base_strategy_seed
from tools.usdjpy_evidence_os.report import build_evidence_os
from tools.usdjpy_evidence_os.telegram_gateway import build_notification_event, dispatch_pending, enqueue_event, gateway_status
from tools.usdjpy_strategy_backtest.report import ingest_klines, run_backtest


class USDJPYEvidenceOSTests(unittest.TestCase):
    def test_ingest_snapshot_backtest_and_evidence_os_write_audit_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            snapshot = runtime_dir / "QuantGod_MT5RuntimeSnapshot_USDJPYc.json"
            snapshot.write_text(
                """
                {
                  "symbol": "USDJPYc",
                  "kline_h1": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.2,"low":155.0,"close":155.15,"volume":100},
                    {"timeIso":"2026-05-07T01:00:00Z","open":155.15,"high":155.3,"low":155.1,"close":155.25,"volume":100}
                  ],
                  "kline_m15": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.12,"low":155.0,"close":155.1,"volume":25}
                  ],
                  "kline_h4": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.4,"low":155.0,"close":155.3,"volume":400}
                  ],
                  "kline_d1": [
                    {"timeIso":"2026-05-07T00:00:00Z","open":155.1,"high":155.8,"low":154.9,"close":155.5,"volume":1000}
                  ]
                }
                """,
                encoding="utf-8",
            )

            ingest = ingest_klines(runtime_dir)
            self.assertTrue(ingest["sourceFound"])
            self.assertEqual(ingest["insertedOrUpdated"]["H1"], 2)

            backtest = run_backtest(runtime_dir, write=True)
            self.assertTrue(backtest["ok"], backtest)
            self.assertIn("multiTimeframe", backtest)
            self.assertEqual(backtest["multiTimeframe"]["contexts"]["H4"]["barCount"], 1)

            (runtime_dir / "QuantGod_RuntimeTradeEvents.jsonl").write_text(
                "\n".join(
                    [
                        '{"generatedAt":"2026-05-07T01:00:01Z","eventType":"ORDER_FILL","symbol":"USDJPYc","price":155.24,"volume":0.05,"retcode":10009,"policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal","expectedPrice":155.23,"latencyMs":420,"profitR":0.2}',
                        '{"generatedAt":"2026-05-07T02:00:01Z","eventType":"ORDER_REJECT","symbol":"USDJPYc","price":155.40,"volume":0.05,"retcode":10030,"policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal"}',
                    ]
                ),
                encoding="utf-8",
            )
            (runtime_dir / "QuantGod_LiveExecutionFeedback.jsonl").write_text(
                "\n".join(
                    [
                        '{"schema":"quantgod.live_execution_feedback.v1","feedbackId":"send-001","eventType":"ORDER_ACCEPTED","symbol":"USDJPYc","side":"BUY","policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal","intentId":"pilot-001","expectedPrice":155.23,"fillPrice":155.24,"slippagePips":0.1,"spreadAtEntry":0.3,"latencyMs":110,"retcode":10009}',
                        '{"schema":"quantgod.live_execution_feedback.v1","feedbackId":"send-002","eventType":"ORDER_REJECTED","symbol":"USDJPYc","side":"BUY","policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal","intentId":"pilot-002","expectedPrice":155.40,"fillPrice":0,"slippagePips":0,"spreadAtEntry":0.4,"latencyMs":95,"retcode":10030}',
                    ]
                ),
                encoding="utf-8",
            )
            (runtime_dir / "QuantGod_LiveExecutionFeedbackHistory.jsonl").write_text(
                "\n".join(
                    [
                        '{"schema":"quantgod.live_execution_feedback.v1","feedbackId":"history-001","eventType":"ORDER_FILL","symbol":"USDJPYc","side":"BUY","policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal","dealTicket":1,"fillPrice":155.24,"profitR":0.0}',
                        '{"schema":"quantgod.live_execution_feedback.v1","feedbackId":"history-002","eventType":"ORDER_CLOSE","symbol":"USDJPYc","side":"SELL","policyId":"USDJPY_LIVE_LOOP","strategyId":"RSI_Reversal","dealTicket":2,"fillPrice":155.42,"profitR":0.45,"exitReason":"HISTORY_EXIT"}',
                    ]
                ),
                encoding="utf-8",
            )
            evidence = build_evidence_os(runtime_dir, write=True)
            self.assertTrue(evidence["ok"])
            self.assertIn("parity", evidence)
            self.assertIn("executionFeedback", evidence)
            self.assertIn("caseMemory", evidence)
            self.assertEqual(evidence["executionFeedback"]["metrics"]["acceptedCount"], 1)
            self.assertEqual(evidence["executionFeedback"]["metrics"]["fillCount"], 3)
            self.assertEqual(evidence["executionFeedback"]["metrics"]["rejectCount"], 2)
            sources = {row["source"] for row in evidence["executionFeedback"]["recentFeedback"]}
            self.assertIn("QuantGod_LiveExecutionFeedback.jsonl", sources)
            self.assertIn("QuantGod_LiveExecutionFeedbackHistory.jsonl", sources)
            self.assertIn("qualityGates", evidence["executionFeedback"])
            self.assertFalse(evidence["safety"]["orderSendAllowed"])
            self.assertTrue((runtime_dir / "evidence_os" / "QuantGod_StrategyParityReport.json").exists())

    def test_independent_telegram_gateway_queues_dedupes_and_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            event = build_notification_event(
                "unit_test",
                "EVIDENCE_OS_TEST",
                "INFO",
                "【QuantGod 测试】Gateway 只做中文 push，不接收交易命令。",
            )
            first = enqueue_event(runtime_dir, event)
            second = enqueue_event(runtime_dir, event)
            self.assertEqual(first["queued"], 1)
            self.assertEqual(second["queued"], 0)
            dispatched = dispatch_pending(runtime_dir, send=False)
            self.assertEqual(dispatched["dispatchedCount"], 1)
            status = gateway_status(runtime_dir)
            self.assertEqual(status["pendingCount"], 0)
            self.assertFalse(status["commandsAllowed"])
            self.assertTrue((runtime_dir / "notifications" / "QuantGod_TelegramGatewayLedger.jsonl").exists())

    def test_ga_fitness_consumes_parity_execution_and_case_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            run_backtest(runtime_dir, write=True)
            build_evidence_os(runtime_dir, write=True)
            score = score_seed(base_strategy_seed("GA-EVIDENCE-OS"), runtime_dir)
            self.assertIn("parity", score)
            self.assertIn("executionFeedback", score)
            self.assertIn("caseMemory", score)
            self.assertIn("evidencePenalty", score)


if __name__ == "__main__":
    unittest.main()
