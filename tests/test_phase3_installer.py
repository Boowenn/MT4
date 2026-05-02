from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.apply_phase3_full import patch_dashboard, patch_frontend_package


class Phase3InstallerTests(unittest.TestCase):
    def test_patch_dashboard_injects_phase3_before_phase2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dashboard").mkdir()
            server = root / "Dashboard" / "dashboard_server.js"
            server.write_text(
                "const phase2ApiRoutes = require('./phase2_api_routes'); const server = http.createServer((req, res) => { const requestUrl = req.url || '/'; if (phase2ApiRoutes.isPhase2Path(requestUrl)) {} });",
                encoding="utf-8",
            )
            self.assertTrue(patch_dashboard(root))
            text = server.read_text(encoding="utf-8")
            self.assertIn("phase3_api_routes", text)
            self.assertIn("phase3ApiRoutes.isPhase3Path", text)

    def test_patch_frontend_package_adds_monaco(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frontend").mkdir()
            pkg = root / "frontend" / "package.json"
            pkg.write_text(json.dumps({"dependencies": {"vue": "^3.5.0"}}), encoding="utf-8")
            self.assertTrue(patch_frontend_package(root))
            data = json.loads(pkg.read_text(encoding="utf-8"))
            self.assertIn("monaco-editor", data["dependencies"])
