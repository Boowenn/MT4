import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "quantgod_mt5_readonly_monitor.py"
SPEC = importlib.util.spec_from_file_location("quantgod_mt5_readonly_monitor", MODULE_PATH)
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(monitor)


class QuantGodMt5ReadonlyMonitorTests(unittest.TestCase):
    def test_resolve_runtime_dir_prefers_live_mt5_files_when_default_dashboard_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configured = root / "Dashboard"
            configured.mkdir()
            mt5_root = root / "MetaTrader 5"
            mt5_files = mt5_root / "MQL5" / "Files"
            mt5_files.mkdir(parents=True)
            (mt5_files / "QuantGod_Dashboard.json").write_text("{}", encoding="utf-8")
            old_root = monitor.DEFAULT_MT5_ROOT
            old_mode = os.environ.get("QG_MAC_RUNTIME_SOURCE")
            monitor.DEFAULT_MT5_ROOT = mt5_root
            os.environ["QG_MAC_RUNTIME_SOURCE"] = "auto"
            try:
                self.assertEqual(monitor.resolve_runtime_dir(configured), mt5_files)
            finally:
                monitor.DEFAULT_MT5_ROOT = old_root
                if old_mode is None:
                    os.environ.pop("QG_MAC_RUNTIME_SOURCE", None)
                else:
                    os.environ["QG_MAC_RUNTIME_SOURCE"] = old_mode


if __name__ == "__main__":
    unittest.main()
