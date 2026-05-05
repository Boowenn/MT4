import json, tempfile, unittest
from pathlib import Path
from tools.entry_trigger_lab.data_loader import sample_runtime
from tools.entry_trigger_lab.trigger_engine import build_trigger_plan
from tools.entry_trigger_lab.telegram_text import build_telegram_text

class EntryTriggerLabTests(unittest.TestCase):
    def test_builds_read_only_trigger_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp); sample_runtime(runtime,["USDJPYc"],overwrite=True)
            plan=build_trigger_plan(runtime,["USDJPYc"],directions=["LONG","SHORT"])
            self.assertEqual(plan["schema"],"quantgod.entry_trigger_lab.v1")
            self.assertFalse(plan["safety"]["orderSendAllowed"])
            self.assertFalse(plan["safety"]["brokerExecutionAllowed"])
            self.assertEqual(len(plan["decisions"]),2)
    def test_degraded_fastlane_blocks_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp); sample_runtime(runtime,["USDJPYc"],overwrite=True)
            quality=runtime/"quality"/"QuantGod_MT5FastLaneQuality.json"
            payload=json.loads(quality.read_text(encoding="utf-8")); payload["symbols"]["USDJPYc"]["quality"]="DEGRADED"
            quality.write_text(json.dumps(payload), encoding="utf-8")
            plan=build_trigger_plan(runtime,["USDJPYc"],directions=["LONG"]); decision=plan["decisions"][0]
            self.assertEqual(decision["state"],"BLOCKED")
            self.assertFalse(decision["confirmations"]["快通道质量通过"])
    def test_missing_runtime_evidence_blocks_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp)
            rows=[
                {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"4.2","scoreR":"0.42"},
                {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"2.7","scoreR":"0.27"},
                {"symbol":"USDJPYc","direction":"LONG","horizonMinutes":"15","pips":"1.3","scoreR":"0.13"},
            ]
            ledger=runtime/"ShadowCandidateOutcomeLedger.csv"; runtime.mkdir(parents=True, exist_ok=True)
            with ledger.open("w", encoding="utf-8", newline="") as fh:
                import csv
                writer=csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader(); writer.writerows(rows)
            plan=build_trigger_plan(runtime,["USDJPYc"],directions=["LONG"]); decision=plan["decisions"][0]
            self.assertEqual(decision["state"],"BLOCKED")
            self.assertFalse(decision["confirmations"]["运行快照存在"])
            self.assertFalse(decision["confirmations"]["快通道质量存在"])
            self.assertFalse(decision["confirmations"]["自适应入场闸门存在"])
            self.assertIn("缺少运行快照", "；".join(decision["reasons"]))
    def test_missing_adaptive_gate_blocks_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp); sample_runtime(runtime,["USDJPYc"],overwrite=True)
            (runtime/"adaptive"/"QuantGod_DynamicEntryGate.json").unlink()
            plan=build_trigger_plan(runtime,["USDJPYc"],directions=["LONG"]); decision=plan["decisions"][0]
            self.assertEqual(decision["state"],"BLOCKED")
            self.assertFalse(decision["confirmations"]["自适应入场闸门存在"])
            self.assertIn("缺少自适应入场闸门证据", "；".join(decision["reasons"]))
    def test_chinese_telegram_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp); sample_runtime(runtime,["USDJPYc"],overwrite=True)
            text=build_telegram_text(build_trigger_plan(runtime,["USDJPYc"],directions=["LONG"]), symbol="USDJPYc")
            self.assertIn("入场触发实验室", text)
            self.assertIn("不会下单", text)
            self.assertNotIn("OrderSend", text)
if __name__ == "__main__": unittest.main()
