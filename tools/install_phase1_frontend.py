from __future__ import annotations

import argparse
import json
from pathlib import Path

PHASE1_IMPORT = "import Phase1Workspace from './components/phase1/Phase1Workspace.vue';"
IMPORT_MARKER = "// QuantGod Phase 1 workspace import"
TEMPLATE_MARKER_START = "<!-- QuantGod Phase 1 workspace start -->"
TEMPLATE_MARKER_END = "<!-- QuantGod Phase 1 workspace end -->"


def install(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    package_json = repo_root / "frontend" / "package.json"
    app_vue = repo_root / "frontend" / "src" / "App.vue"
    if not package_json.exists():
        raise FileNotFoundError(f"frontend/package.json not found: {package_json}")
    if not app_vue.exists():
        raise FileNotFoundError(f"frontend/src/App.vue not found: {app_vue}")

    package_changed = _ensure_package_dependency(package_json)
    app_changed = _ensure_app_mount(app_vue)
    return {
        "ok": True,
        "packageChanged": package_changed,
        "appChanged": app_changed,
        "packageJson": str(package_json),
        "appVue": str(app_vue),
    }


def _ensure_package_dependency(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    deps = data.setdefault("dependencies", {})
    if "klinecharts" in deps:
        return False
    deps["klinecharts"] = "^9.8.12"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _ensure_app_mount(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    original = source

    if PHASE1_IMPORT not in source:
        if "<script setup" in source:
            end = source.find(">", source.find("<script setup"))
            if end != -1:
                source = source[: end + 1] + f"\n{PHASE1_IMPORT} {IMPORT_MARKER}" + source[end + 1 :]
        else:
            # Vue 3 supports multiple roots, but registering a component in a
            # classic export-default component is project-specific. Leave a
            # clear manual hook rather than corrupting App.vue.
            manual = path.with_name("App.phase1.manual.vue")
            manual.write_text(_manual_app_example(), encoding="utf-8")

    if TEMPLATE_MARKER_START not in source:
        insert = (
            f"\n  {TEMPLATE_MARKER_START}\n"
            "  <Phase1Workspace />\n"
            f"  {TEMPLATE_MARKER_END}\n"
        )
        marker = "</template>"
        index = source.rfind(marker)
        if index != -1:
            source = source[:index] + insert + source[index:]

    if source != original:
        backup = path.with_suffix(".vue.phase1.bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(source, encoding="utf-8")
        return True
    return False


def _manual_app_example() -> str:
    return """<template>
  <Phase1Workspace />
</template>

<script setup>
import Phase1Workspace from './components/phase1/Phase1Workspace.vue';
</script>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install QuantGod Phase 1 frontend dependency and App.vue hook")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    result = install(Path(args.repo_root))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
