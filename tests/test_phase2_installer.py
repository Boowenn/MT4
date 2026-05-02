from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.apply_phase2_full import patch_requirements, patch_root_package


class Phase2InstallerTests(unittest.TestCase):
    def test_requirements_adds_pytest_cov_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements-dev.txt").write_text("pytest>=8.0\nruff>=0.5\n", encoding="utf-8")
            self.assertTrue(patch_requirements(root))
            self.assertFalse(patch_requirements(root))
            text = (root / "requirements-dev.txt").read_text(encoding="utf-8")
            self.assertEqual(text.count("pytest-cov"), 1)

    def test_root_package_has_node_test_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(patch_root_package(root))
            text = (root / "package.json").read_text(encoding="utf-8")
            self.assertIn("node --test tests/node/*.mjs", text)


if __name__ == "__main__":
    unittest.main()

class Phase2InstallerPatchFunctionTests(unittest.TestCase):
    def test_core_repo_patches_are_idempotent(self) -> None:
        from tools.apply_phase2_full import (
            patch_ai_notify_hook,
            patch_app_vue,
            patch_ci,
            patch_dashboard_server,
            patch_env_example,
            patch_main_js,
            patch_package_json,
            patch_readme,
            patch_services_api,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dashboard").mkdir(parents=True)
            (root / "Dashboard" / "dashboard_server.js").write_text(
                "const phase1ApiRoutes = require('./phase1_api_routes'); if (phase1ApiRoutes.isPhase1Path(requestUrl)) { return; }",
                encoding="utf-8",
            )
            (root / "frontend" / "src" / "services").mkdir(parents=True)
            (root / "frontend" / "package.json").write_text('{"dependencies":{"vue":"^3.5.0"}}', encoding="utf-8")
            (root / "frontend" / "src" / "main.js").write_text("import { createApp } from 'vue';\nimport App from './App.vue';\ncreateApp(App).mount('#app');\n", encoding="utf-8")
            (root / "frontend" / "src" / "App.vue").write_text(
                "<template><main></main></template>\n<script setup>\nimport Phase1Workspace from './components/phase1/Phase1Workspace.vue';\nconst workspaces = [\n { id: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3, desc: '统一文件/API 新鲜度与核心 ledger 表格' }\n];\n</script>\n",
                encoding="utf-8",
            )
            (root / "frontend" / "src" / "services" / "api.js").write_text(
                "async function fetchCsv(url) { return parseCsv(await fetchText(url, '')); }\n"
                "export async function loadDashboardState(){return {a: await fetchJson('/QuantGod_GovernanceAdvisor.json'), b: await fetchCsv('/QuantGod_TradeJournal.csv')}}\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text("The MT5 work is intentionally split into phases:\n", encoding="utf-8")
            (root / "tools" / "ai_analysis").mkdir(parents=True)
            (root / "tools" / "ai_analysis" / "analysis_service.py").write_text("def run():\n    report = {}\n    return report\n", encoding="utf-8")

            self.assertTrue(patch_dashboard_server(root))
            self.assertTrue(patch_package_json(root))
            self.assertTrue(patch_main_js(root))
            self.assertTrue(patch_app_vue(root))
            self.assertTrue(patch_services_api(root))
            self.assertTrue(patch_ci(root))
            self.assertTrue(patch_env_example(root))
            self.assertTrue(patch_readme(root))
            self.assertTrue(patch_ai_notify_hook(root))

            self.assertFalse(patch_dashboard_server(root))
            self.assertFalse(patch_package_json(root))
            self.assertFalse(patch_main_js(root))
            self.assertFalse(patch_app_vue(root))
            self.assertFalse(patch_services_api(root))
            self.assertFalse(patch_env_example(root))
            self.assertFalse(patch_readme(root))
            self.assertFalse(patch_ai_notify_hook(root))

            server = (root / "Dashboard" / "dashboard_server.js").read_text(encoding="utf-8")
            self.assertIn("phase2_api_routes", server)
            self.assertIn("phase2ApiRoutes.isPhase2Path", server)
            pkg = (root / "frontend" / "package.json").read_text(encoding="utf-8")
            self.assertIn("ant-design-vue", pkg)
            api = (root / "frontend" / "src" / "services" / "api.js").read_text(encoding="utf-8")
            self.assertIn("/api/governance/advisor", api)
            self.assertIn("fetchRowsJson('/api/trades/journal?limit=500')", api)
            app = (root / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
            self.assertIn("Phase2OperationsWorkspace", app)
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Phase 2 integration layer", readme)
            ai = (root / "tools" / "ai_analysis" / "analysis_service.py").read_text(encoding="utf-8")
            self.assertIn("QUANTGOD_PHASE2_NOTIFY_HOOK", ai)
