#!/usr/bin/env python3
"""Apply QuantGod Phase 3 integration hooks to an existing checkout.

The overlay already contains new files. This installer only patches existing
entry points idempotently:
- Dashboard/dashboard_server.js: require + dispatch phase3_api_routes.
- frontend/src/App.vue: optional Phase3Workspace insertion.
- frontend/package.json: add monaco-editor dependency.
- README.md: add a concise Phase 3 status note.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def patch_dashboard(repo: Path) -> bool:
    target = repo / "Dashboard" / "dashboard_server.js"
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    original = text
    if "phase3_api_routes" not in text:
        if "const phase2ApiRoutes = require('./phase2_api_routes');" in text:
            text = text.replace(
                "const phase2ApiRoutes = require('./phase2_api_routes');",
                "const phase2ApiRoutes = require('./phase2_api_routes');\nconst phase3ApiRoutes = require('./phase3_api_routes');",
                1,
            )
        elif "const phase1ApiRoutes = require('./phase1_api_routes');" in text:
            text = text.replace(
                "const phase1ApiRoutes = require('./phase1_api_routes');",
                "const phase1ApiRoutes = require('./phase1_api_routes');\nconst phase3ApiRoutes = require('./phase3_api_routes');",
                1,
            )
        else:
            text = "const phase3ApiRoutes = require('./phase3_api_routes');\n" + text
    hook = """if (phase3ApiRoutes.isPhase3Path(requestUrl)) {
    phase3ApiRoutes
      .handle(req, res, { repoRoot, rootDir, defaultRuntimeDir })
      .catch((error) => phase3ApiRoutes.sendError(res, 500, requestUrl, error));
    return;
  }
  """
    if "phase3ApiRoutes.isPhase3Path(requestUrl)" not in text:
        marker = "if (phase2ApiRoutes.isPhase2Path(requestUrl))"
        if marker in text:
            text = text.replace(marker, hook + marker, 1)
        else:
            marker = "if (phase1ApiRoutes.isPhase1Path(requestUrl))"
            text = text.replace(marker, hook + marker, 1)
    if text != original:
        target.write_text(text, encoding="utf-8")
        return True
    return False


def patch_frontend_package(repo: Path) -> bool:
    target = repo / "frontend" / "package.json"
    if not target.exists():
        return False
    data = json.loads(target.read_text(encoding="utf-8"))
    deps = data.setdefault("dependencies", {})
    changed = False
    if "monaco-editor" not in deps:
        deps["monaco-editor"] = "^0.52.2"
        changed = True
    if changed:
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def patch_app_vue(repo: Path) -> bool:
    target = repo / "frontend" / "src" / "App.vue"
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    original = text
    if "Phase3Workspace" not in text:
        if "const workspaces = [" in text and "id: 'ai'" in text:
            text = text.replace(
                "  { id: 'ai', label: 'AI 工作台', sub: '分析引擎', icon: Activity, desc: '对照 QuantDinger 的 AI 分析入口：即时分析、机会雷达、历史记忆与下一步建议' },",
                "  { id: 'ai', label: 'AI 工作台', sub: '分析引擎', icon: Activity, desc: '对照 QuantDinger 的 AI 分析入口：即时分析、机会雷达、历史记忆与下一步建议' },\n"
                "  { id: 'phase3', label: '策略工坊', sub: 'Vibe / AI V2', icon: Layers, desc: '自然语言策略生成、research-only 回测、AI 多智能体辩论与 K 线叠加' },",
                1,
            )
        if "import Phase2OperationsWorkspace" in text:
            text = text.replace(
                "import Phase2OperationsWorkspace from './components/phase2/Phase2OperationsWorkspace.vue';",
                "import Phase2OperationsWorkspace from './components/phase2/Phase2OperationsWorkspace.vue';\n"
                "import Phase3Workspace from './components/phase3/Phase3Workspace.vue';",
                1,
            )
        elif "<script setup" in text:
            text = text.replace(
                "<script setup>",
                "<script setup>\nimport Phase3Workspace from './components/phase3/Phase3Workspace.vue';",
                1,
            )
        nav_marker = """        <button
          class="nav-item"
          :class="{ active: state.active === 'phase2' }"
          type="button"
          @click="setActive('phase2')"
        >"""
        nav_block = """        <button
          class="nav-item"
          :class="{ active: state.active === 'phase3' }"
          type="button"
          @click="setActive('phase3')"
        >
          <Layers :size="18" />
          <span>
            <strong>策略工坊</strong>
            <small>Vibe / AI V2</small>
          </span>
        </button>

"""
        if nav_marker in text:
            text = text.replace(nav_marker, nav_block + nav_marker, 1)
        section_marker = """      <section v-if="state.active === 'phase2'" class="stack page-phase2">
        <Phase2OperationsWorkspace />
      </section>"""
        section_block = section_marker + """

      <section v-if="state.active === 'phase3'" class="stack page-phase3">
        <Phase3Workspace />
      </section>"""
        if section_marker in text:
            text = text.replace(section_marker, section_block, 1)
    if text != original:
        target.write_text(text, encoding="utf-8")
        return True
    return False


def patch_readme(repo: Path) -> bool:
    target = repo / "README.md"
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    if "Phase 3 Vibe Coding" in text:
        return False
    note = """

### Phase 3 Vibe Coding / AI V2 / K-line Enhancements

Phase 3 adds a local-first Vibe Coding strategy workbench, AI Analysis V2 with News/Sentiment/Bull/Bear debate and local RAG memory, plus K-line AI signal overlays and polling configuration. These surfaces are research/advisory only: generated Python strategies run in local backtests, AI debate cannot trigger orders, and no Phase 3 API can mutate live presets, credentials, Governance decisions, or Kill Switch state.
"""
    marker = "## Strategies"
    if marker in text:
        text = text.replace(marker, note + "\n" + marker, 1)
    else:
        text += note
    target.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    changes = {
        "dashboard_server": patch_dashboard(repo),
        "frontend_package": patch_frontend_package(repo),
        "app_vue": patch_app_vue(repo),
        "readme": patch_readme(repo),
    }
    print(json.dumps({"ok": True, "repoRoot": str(repo), "changes": changes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
