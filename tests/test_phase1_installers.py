from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.install_phase1_dashboard_routes import install as install_dashboard
from tools.install_phase1_frontend import install as install_frontend


class Phase1InstallerTests(unittest.TestCase):
    def test_dashboard_installer_adds_commonjs_hook(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            dashboard_dir = repo / "Dashboard"
            dashboard_dir.mkdir(parents=True)
            (dashboard_dir / "phase1_api_routes.js").write_text("module.exports = {};\n", encoding="utf-8")
            server = dashboard_dir / "dashboard_server.js"
            server.write_text(
                "const http = require('http');\nconst path = require('path');\n"
                "http.createServer((req, res) => {\n  res.end('ok');\n});\n",
                encoding="utf-8",
            )
            result = install_dashboard(repo)
            patched = server.read_text(encoding="utf-8")
            self.assertTrue(result["ok"])
            self.assertIn("phase1_api_routes", patched)
            self.assertIn("QuantGod Phase 1 local advisory/read-only API routes", patched)
            self.assertIn("phase1ApiRoutes.isPhase1Path", patched)


    def test_dashboard_installer_handles_current_one_line_server_shape(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            dashboard_dir = repo / "Dashboard"
            dashboard_dir.mkdir(parents=True)
            (dashboard_dir / "phase1_api_routes.js").write_text("module.exports = {};\n", encoding="utf-8")
            server = dashboard_dir / "dashboard_server.js"
            server.write_text(
                "const http = require('http'); const https = require('https'); const fs = require('fs'); const path = require('path'); "
                "const server = http.createServer((req, res) => { const requestUrl = req.url || '/'; res.end(requestUrl); });\n",
                encoding="utf-8",
            )
            install_dashboard(repo)
            patched = server.read_text(encoding="utf-8")
            self.assertIn("phase1_api_routes", patched)
            self.assertIn("phase1ApiRoutes.isPhase1Path", patched)
            self.assertIn("const requestUrl", patched)

    def test_frontend_installer_adds_klinecharts_and_workspace_mount(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            frontend = repo / "frontend"
            src = frontend / "src"
            src.mkdir(parents=True)
            (frontend / "package.json").write_text(
                json.dumps({"dependencies": {"vue": "^3.5.13"}, "devDependencies": {}}),
                encoding="utf-8",
            )
            app = src / "App.vue"
            app.write_text(
                "<template>\n  <div>QuantGod</div>\n</template>\n<script setup>\nconst ready = true;\n</script>\n",
                encoding="utf-8",
            )
            result = install_frontend(repo)
            package_data = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
            patched_app = app.read_text(encoding="utf-8")
            self.assertTrue(result["ok"])
            self.assertIn("klinecharts", package_data["dependencies"])
            self.assertIn("Phase1Workspace", patched_app)
            self.assertIn("QuantGod Phase 1 workspace start", patched_app)


if __name__ == "__main__":
    unittest.main()
