import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_daily_autopilot.py"
SPEC = importlib.util.spec_from_file_location("run_daily_autopilot", MODULE_PATH)
autopilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(autopilot)


class DailyAutopilotTests(unittest.TestCase):
    def test_run_step_passes_env_overrides_without_order_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = autopilot.run_step(
                "env_probe",
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ['QG_RUNTIME_DIR']); print(os.environ['QG_MAC_RUNTIME_SOURCE'])",
                ],
                tmp_path,
                env_overrides={
                    "QG_RUNTIME_DIR": str(tmp_path / "runtime"),
                    "QG_MAC_RUNTIME_SOURCE": "local",
                },
            )

            self.assertEqual(result["status"], "OK")
            self.assertIn(str(tmp_path / "runtime"), result["stdoutTail"])
            self.assertIn("local", result["stdoutTail"])

    def test_mac_wrappers_are_valid_bash(self):
        repo_root = MODULE_PATH.parents[1]
        env = {**os.environ, "QG_MAC_RUNTIME_SOURCE": "local"}
        result = subprocess.run(
            ["bash", "-n", "tools/run_mac_daily_autopilot.sh", "tools/run_mac_polymarket_readonly_cycle.sh"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
