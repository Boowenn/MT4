from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
import unittest

from tools.vibe_coding.config import load_config
from tools.vibe_coding.safety import validate_strategy_code
from tools.vibe_coding.vibe_coding_service import VibeCodingService


class VibeCodingPhase3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["QG_RUNTIME_DIR"] = self.tmp.name
        os.environ["QG_VIBE_STRATEGY_DIR"] = str(Path(self.tmp.name) / "vibe_strategies")
        os.environ["QG_VIBE_HISTORY_DIR"] = str(Path(self.tmp.name) / "vibe_history")

    def test_safety_rejects_dangerous_import_and_open(self):
        code = """
from tools.vibe_coding.strategy_template import BaseStrategy
import os
class Bad(BaseStrategy):
    def evaluate(self, bars):
        open('x.txt', 'w').write('bad')
        return {'signal': None, 'confidence': 0}
"""
        result = validate_strategy_code(code)
        self.assertFalse(result.ok)
        messages = " ".join(issue.message for issue in result.issues)
        self.assertIn("import not allowed", messages)
        self.assertIn("dangerous", messages)

    def test_generate_backtest_analyze_cycle(self):
        service = VibeCodingService(load_config())
        generated = asyncio.run(service.generate_strategy("Buy RSI oversold rebound with H1 trend filter", "EURUSDc", "H1"))
        self.assertTrue(generated["ok"])
        strategy_id = generated["strategy"]["strategy_id"]
        backtest = asyncio.run(service.run_backtest(strategy_id, "EURUSDc", "H1", 20))
        self.assertTrue(backtest["ok"])
        self.assertIn("metrics", backtest)
        analysis = asyncio.run(service.analyze_backtest(strategy_id, backtest))
        self.assertTrue(analysis["ok"])
        self.assertIn("recommendations", analysis)
        listed = service.list_strategies()
        self.assertEqual(len(listed["strategies"]), 1)

    def test_iterate_creates_new_version(self):
        service = VibeCodingService(load_config())
        generated = asyncio.run(service.generate_strategy("Sell MA breakdown", "USDJPYc", "M15"))
        sid = generated["strategy"]["strategy_id"]
        iterated = asyncio.run(service.iterate_strategy(sid, "add volatility filter"))
        self.assertTrue(iterated["ok"])
        self.assertEqual(iterated["strategy"]["version"], "v2")
