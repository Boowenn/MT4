#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CSV_REPLACEMENTS = {
    "/QuantGod_ShadowSignalLedger.csv": "/api/shadow/signals?limit=500",
    "/QuantGod_ShadowOutcomeLedger.csv": "/api/shadow/outcomes?limit=500",
    "/QuantGod_ShadowCandidateLedger.csv": "/api/shadow/candidates?limit=500",
    "/QuantGod_ShadowCandidateOutcomeLedger.csv": "/api/shadow/candidate-outcomes?limit=500",
    "/QuantGod_CloseHistory.csv": "/api/trades/close-history?limit=500",
    "/QuantGod_TradeJournal.csv": "/api/trades/journal?limit=500",
    "/QuantGod_ParamLabResultsLedger.csv": "/api/paramlab/results-ledger?limit=500",
    "/QuantGod_ParamLabAutoSchedulerLedger.csv": "/api/paramlab/scheduler-ledger?limit=500",
    "/QuantGod_ParamLabReportWatcherLedger.csv": "/api/paramlab/report-watcher-ledger?limit=500",
    "/QuantGod_ParamLabRunRecoveryLedger.csv": "/api/paramlab/recovery-ledger?limit=500",
    "/QuantGod_AutoTesterWindowLedger.csv": "/api/paramlab/tester-window-ledger?limit=500",
    "/QuantGod_MT5ResearchStatsLedger.csv": "/api/research/stats-ledger?limit=500",
    "/QuantGod_StrategyEvaluationReport.csv": "/api/research/strategy-evaluation?limit=500",
    "/QuantGod_RegimeEvaluationReport.csv": "/api/research/regime-evaluation?limit=500",
    "/QuantGod_MT5TradingAuditLedger.csv": "/api/trades/trading-audit?limit=500",
    "/QuantGod_ManualAlphaLedger.csv": "/api/research/manual-alpha?limit=500",
    "/QuantGod_PolymarketMarketRadar.csv": "/api/polymarket/radar-ledger?limit=500",
    "/QuantGod_PolymarketAiScoreV1.csv": "/api/polymarket/ai-score-ledger?limit=500",
    "/QuantGod_PolymarketCanaryExecutorLedger.csv": "/api/polymarket/canary-executor-ledger?limit=500",
    "/QuantGod_PolymarketCanaryPositionLedger.csv": "/api/polymarket/canary-position-ledger?limit=500",
    "/QuantGod_PolymarketCanaryOrderAuditLedger.csv": "/api/polymarket/canary-order-audit-ledger?limit=500",
    "/QuantGod_PolymarketCanaryExitLedger.csv": "/api/polymarket/canary-exit-ledger?limit=500",
    "/QuantGod_PolymarketAutoGovernanceLedger.csv": "/api/polymarket/auto-governance-ledger?limit=500",
    "/QuantGod_PolymarketCrossMarketLinkage.csv": "/api/polymarket/cross-market-linkage-ledger?limit=500",
    "/QuantGod_PolymarketSingleMarketAnalysisLedger.csv": "/api/polymarket/single-market-analysis-ledger?limit=500",
    "/QuantGod_PolymarketRadarWorkerV2.csv": "/api/polymarket/radar-worker-ledger?limit=500",
}

JSON_REPLACEMENTS = {
    "/QuantGod_GovernanceAdvisor.json": "/api/governance/advisor",
    "/QuantGod_BacktestSummary.json": "/api/dashboard/backtest-summary",
    "/QuantGod_ParamLabStatus.json": "/api/paramlab/status",
    "/QuantGod_ParamLabResults.json": "/api/paramlab/results",
    "/QuantGod_ParamLabAutoScheduler.json": "/api/paramlab/scheduler",
    "/QuantGod_ParamLabReportWatcher.json": "/api/paramlab/report-watcher",
    "/QuantGod_ParamLabRunRecovery.json": "/api/paramlab/recovery",
    "/QuantGod_AutoTesterWindow.json": "/api/paramlab/tester-window",
    "/QuantGod_MT5ResearchStats.json": "/api/research/stats",
    "/QuantGod_StrategyVersionRegistry.json": "/api/governance/version-registry",
    "/QuantGod_PolymarketSingleMarketAnalysis.json": "/api/polymarket/single-market-analysis",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def patch_once(text: str, needle: str, replacement: str) -> tuple[str, bool]:
    if replacement in text:
        return text, False
    if needle not in text:
        return text, False
    return text.replace(needle, replacement, 1), True


def patch_dashboard_server(root: Path) -> bool:
    path = root / "Dashboard" / "dashboard_server.js"
    if not path.exists():
        return False
    text = read_text(path)
    changed = False
    if "phase2_api_routes" not in text:
        text, did = patch_once(
            text,
            "const phase1ApiRoutes = require('./phase1_api_routes');",
            "const phase1ApiRoutes = require('./phase1_api_routes'); const phase2ApiRoutes = require('./phase2_api_routes');",
        )
        changed = changed or did
    phase2_handler = (
        "if (phase2ApiRoutes.isPhase2Path(requestUrl)) { phase2ApiRoutes.handle(req, res, { repoRoot, rootDir, defaultRuntimeDir }) "
        ".catch((error) => phase2ApiRoutes.sendError(res, 500, requestUrl, error)); return; } "
    )
    if "phase2ApiRoutes.isPhase2Path(requestUrl)" not in text:
        marker = "if (phase1ApiRoutes.isPhase1Path(requestUrl)) {"
        if marker in text:
            text = text.replace(marker, phase2_handler + marker, 1)
            changed = True
    if changed:
        write_text(path, text)
    return changed


def patch_package_json(root: Path) -> bool:
    path = root / "frontend" / "package.json"
    if not path.exists():
        return False
    payload = json.loads(read_text(path))
    deps = payload.setdefault("dependencies", {})
    before = json.dumps(payload, sort_keys=True)
    deps.setdefault("ant-design-vue", "^4.2.6")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if json.dumps(payload, sort_keys=True) != before:
        write_text(path, text)
        return True
    return False


def patch_main_js(root: Path) -> bool:
    path = root / "frontend" / "src" / "main.js"
    if not path.exists():
        return False
    text = read_text(path)
    if "ant-design-vue" in text:
        return False
    new_text = """import { createApp } from 'vue';
import Antd from 'ant-design-vue';
import 'ant-design-vue/dist/reset.css';
import App from './App.vue';
import './styles.css';

createApp(App).use(Antd).mount('#app');
"""
    write_text(path, new_text)
    return True


def patch_app_vue(root: Path) -> bool:
    path = root / "frontend" / "src" / "App.vue"
    if not path.exists():
        return False
    text = read_text(path)
    changed = False
    if "Phase2OperationsWorkspace" not in text:
        marker = "import Phase1Workspace from './components/phase1/Phase1Workspace.vue';"
        if marker in text:
            text = text.replace(marker, marker + "\nimport Phase2OperationsWorkspace from './components/phase2/Phase2OperationsWorkspace.vue';", 1)
            changed = True
    if "id: 'phase2'" not in text:
        needle = "{ id: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3, desc: '统一文件/API 新鲜度与核心 ledger 表格' }"
        replacement = needle + ",\n { id: 'phase2', label: 'Phase 2', sub: 'API / 通知', icon: Bell, desc: '统一 API、Telegram 通知与集成测试状态' }"
        if needle in text:
            text = text.replace(needle, replacement, 1)
            changed = True
    render_snippet = "<Phase2OperationsWorkspace v-if=\"state.active === 'phase2'\" />"
    if render_snippet not in text and "</template>" in text:
        text = text.replace("</template>", f"  {render_snippet}\n</template>", 1)
        changed = True
    if changed:
        write_text(path, text)
    return changed


def patch_services_api(root: Path) -> bool:
    path = root / "frontend" / "src" / "services" / "api.js"
    if not path.exists():
        return False
    text = read_text(path)
    changed = False
    if "async function fetchRowsJson" not in text:
        text, did = patch_once(
            text,
            "async function fetchCsv(url) { return parseCsv(await fetchText(url, '')); }",
            "async function fetchCsv(url) { return parseCsv(await fetchText(url, '')); } async function fetchRowsJson(url) { const payload = await fetchJson(url, null); if (Array.isArray(payload?.data?.rows)) return payload.data.rows; if (Array.isArray(payload?.rows)) return payload.rows; return []; }",
        )
        changed = changed or did
    for old, new in JSON_REPLACEMENTS.items():
        before = text
        text = text.replace(f"fetchJson('{old}')", f"fetchJson('{new}')")
        text = text.replace(f'fetchJson("{old}")', f'fetchJson("{new}")')
        changed = changed or before != text
    for old, new in CSV_REPLACEMENTS.items():
        before = text
        text = text.replace(f"fetchCsv('{old}')", f"fetchRowsJson('{new}')")
        text = text.replace(f'fetchCsv("{old}")', f'fetchRowsJson("{new}")')
        changed = changed or before != text
    text = text.replace("fetchJsonFirst(['/api/daily-review', '/QuantGod_DailyReview.json'])", "fetchJson('/api/daily-review')")
    text = text.replace("fetchJsonFirst(['/api/daily-autopilot', '/QuantGod_DailyAutopilot.json'])", "fetchJson('/api/daily-autopilot')")
    if changed:
        write_text(path, text)
    return changed


def patch_requirements(root: Path) -> bool:
    path = root / "requirements-dev.txt"
    existing = read_text(path) if path.exists() else "pytest>=8.0\nruff>=0.5\n"
    changed = False
    lines = [line.strip() for line in existing.splitlines() if line.strip()]
    for dep in ["pytest-cov>=5.0"]:
        if not any(line.split("==")[0].split(">=")[0] == dep.split(">=")[0] for line in lines):
            lines.append(dep)
            changed = True
    if changed or not path.exists():
        write_text(path, "\n".join(lines) + "\n")
    return changed


def patch_root_package(root: Path) -> bool:
    path = root / "package.json"
    payload = {}
    if path.exists():
        payload = json.loads(read_text(path))
    before = json.dumps(payload, sort_keys=True)
    payload.setdefault("name", "quantgod-phase2-integration")
    payload.setdefault("private", True)
    payload.setdefault("scripts", {})["test"] = "node --test tests/node/*.mjs"
    if json.dumps(payload, sort_keys=True) != before:
        write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return True
    return False


def patch_ci(root: Path) -> bool:
    path = root / ".github" / "workflows" / "ci.yml"
    text = """name: QuantGod CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: quantgod-ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  frontend:
    name: Vue build
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci
      - name: Build committed Vue dashboard
        working-directory: frontend
        run: npm run build
      - name: Verify built dashboard is committed
        run: git diff --exit-code -- Dashboard/vue-dist

  python-tests:
    name: Python unit tests + coverage
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dev dependencies
        run: pip install -r requirements-dev.txt
      - name: Run unittest suite
        run: python -m unittest discover tests -v
      - name: Coverage summary
        run: python -m pytest tests -q --cov=tools --cov-report=term-missing

  static-guards:
    name: Regression and safety guards
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Whitespace check
        run: git diff --check
      - name: QuantGod regression guard
        run: python tools/ci_guard.py

  integration-tests:
    name: Dashboard API integration tests
    runs-on: ubuntu-latest
    needs: [frontend, python-tests, static-guards]
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Run Node API contract tests
        run: npm test
"""
    if path.exists() and read_text(path) == text:
        return False
    write_text(path, text)
    return True


def patch_env_example(root: Path) -> bool:
    path = root / ".env.example"
    existing = read_text(path) if path.exists() else ""
    snippet = """
# Phase 2 Telegram push notifications. Keep real secrets in .env.local, not Git.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
QG_NOTIFY_ENABLED=true
NOTIFY_TRADE_SIGNAL=true
NOTIFY_RISK_ALERT=true
NOTIFY_AI_SUMMARY=true
NOTIFY_DAILY_DIGEST=true
NOTIFY_GOVERNANCE=false
"""
    if "TELEGRAM_BOT_TOKEN" in existing:
        return False
    write_text(path, existing.rstrip() + "\n" + snippet.lstrip())
    return True


def patch_readme(root: Path) -> bool:
    path = root / "README.md"
    if not path.exists():
        return False
    text = read_text(path)
    if "Phase 2 integration layer" in text:
        return False
    marker = "The MT5 work is intentionally split into phases:\n"
    addition = (
        marker
        + "  * Phase 1 AI analysis engine: available now. The Vue workbench exposes advisory-only AI analysis and K-line review; AI evidence is written for Governance review but cannot execute orders, override Kill Switch, or mutate live presets.\n"
        + "  * Phase 2 integration layer: available now. Dashboard data access is wrapped under `/api/*`, Telegram notification support is push-only, and CI includes API contract and coverage checks.\n"
    )
    if marker in text:
        text = text.replace(marker, addition, 1)
        write_text(path, text)
        return True
    return False


def patch_ai_notify_hook(root: Path) -> bool:
    path = root / "tools" / "ai_analysis" / "analysis_service.py"
    if not path.exists():
        return False
    text = read_text(path)
    if "QUANTGOD_PHASE2_NOTIFY_HOOK" in text:
        return False
    hook = '''
        # QUANTGOD_PHASE2_NOTIFY_HOOK: push-only Telegram AI summary, never trade execution.
        try:
            import os as _qg_notify_os
            if str(_qg_notify_os.getenv("QG_NOTIFY_AI_ANALYSIS_HOOK", "1")).lower() not in {"0", "false", "no", "off"}:
                from notify.notify_service import run_async as _qg_notify_run_async
                from notify.notify_service import send_ai_analysis_summary as _qg_notify_send_ai_analysis_summary
                _qg_report = report
                if hasattr(_qg_report, "to_dict"):
                    _qg_report = _qg_report.to_dict()
                elif not isinstance(_qg_report, dict):
                    _qg_report = getattr(_qg_report, "__dict__", {"summary": str(_qg_report)})
                _qg_notify_run_async(_qg_notify_send_ai_analysis_summary(_qg_report))
        except Exception:
            pass
'''
    matches = list(re.finditer(r"(^\s*)return\s+report\b", text, flags=re.MULTILINE))
    if not matches:
        return False
    match = matches[-1]
    indent = match.group(1)
    indented_hook = "\n".join((indent + line[8:] if line.startswith("        ") else line) for line in hook.splitlines())
    text = text[: match.start()] + indented_hook + "\n" + text[match.start() :]
    write_text(path, text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply QuantGod Phase 2 integration patches")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    actions = {
        "dashboard_server": patch_dashboard_server(root),
        "frontend_package": patch_package_json(root),
        "frontend_main": patch_main_js(root),
        "frontend_app": patch_app_vue(root),
        "frontend_api": patch_services_api(root),
        "requirements": patch_requirements(root),
        "root_package": patch_root_package(root),
        "ci": patch_ci(root),
        "env_example": patch_env_example(root),
        "readme": patch_readme(root),
        "ai_notify_hook": patch_ai_notify_hook(root),
    }
    print(json.dumps({"ok": True, "repoRoot": str(root), "actions": actions}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
