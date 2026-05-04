from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from tools.build_advisor_compliance_check import check_advisor_compliance, _as_bool, _parse_set_file

class AdvisorComplianceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rt = Path(self.tmp.name)
        self.rt.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_advisor(self, routes):
        (self.rt / "QuantGod_GovernanceAdvisor.json").write_text(json.dumps({
            "generatedAt": "2026-05-04T09:00:00+09:00",
            "routeDecisions": routes
        }), encoding="utf-8")

    def _write_preset(self, values):
        lines = [f"{k}={v}" for k, v in values.items()]
        (self.rt / "test_preset.set").write_text("\n".join(lines), encoding="utf-8")

    def test_advisor_demotes_but_preset_still_live(self):
        self._write_advisor([{"key": "RSI_Reversal", "recommendedAction": "DEMOTE_REVIEW"}])
        self._write_preset({"EnablePilotRsiH1Live": "true"})
        alerts = check_advisor_compliance(self.rt, self.rt / "test_preset.set")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["route"], "RSI_Reversal")
        self.assertTrue(alerts[0]["preset_says_live"])
        self.assertFalse(alerts[0]["advisor_says_should_be_live"])

    def test_advisor_and_preset_match_no_alert(self):
        self._write_advisor([{"key": "RSI_Reversal", "recommendedAction": "KEEP_LIVE"}])
        self._write_preset({"EnablePilotRsiH1Live": "true"})
        alerts = check_advisor_compliance(self.rt, self.rt / "test_preset.set")
        self.assertEqual(len(alerts), 0)

    def test_advisor_keeps_live_but_preset_disabled(self):
        self._write_advisor([{"key": "RSI_Reversal", "recommendedAction": "KEEP_LIVE"}])
        self._write_preset({"EnablePilotRsiH1Live": "false"})
        alerts = check_advisor_compliance(self.rt, self.rt / "test_preset.set")
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["preset_says_live"] == False)

    def test_multiple_routes_mixed_compliance(self):
        self._write_advisor([
            {"key": "RSI_Reversal", "recommendedAction": "DEMOTE_REVIEW"},
            {"key": "BB_Triple", "recommendedAction": "KEEP_SIM_ITERATE"},
        ])
        self._write_preset({"EnablePilotRsiH1Live": "true", "EnablePilotBBH1Live": "false"})
        alerts = check_advisor_compliance(self.rt, self.rt / "test_preset.set")
        self.assertEqual(len(alerts), 2)
        routes = {a["route"] for a in alerts}
        self.assertIn("RSI_Reversal", routes)
        self.assertIn("BB_Triple", routes)

    def test_empty_advisor_returns_no_alerts(self):
        alerts = check_advisor_compliance(self.rt, self.rt / "nonexistent.set")
        self.assertEqual(len(alerts), 0)

    def test_parse_set_file_bool_values(self):
        self.assertTrue(_as_bool("true"))
        self.assertTrue(_as_bool("1"))
        self.assertTrue(_as_bool("yes"))
        self.assertFalse(_as_bool("false"))
        self.assertFalse(_as_bool("0"))
        self.assertFalse(_as_bool(""))


if __name__ == "__main__":
    unittest.main()
