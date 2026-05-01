from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

REQUIRE_MARKER = "// QuantGod Phase 1 API routes"
HANDLER_MARKER = "// QuantGod Phase 1 local advisory/read-only API routes"

REQUIRE_LINE = (
    "const phase1ApiRoutes = require('./phase1_api_routes'); "
    "// QuantGod Phase 1 API routes\n"
)

DISPATCH_BLOCK = """\n    // QuantGod Phase 1 local advisory/read-only API routes\n    if (phase1ApiRoutes.isPhase1Path(req.url)) {\n      phase1ApiRoutes\n        .handle(req, res, {})\n        .catch((error) => phase1ApiRoutes.sendUnhandledError(res, error, req.url));\n      return;\n    }\n"""

CREATE_SERVER_PATTERNS = [
    r"http\.createServer\(async\s*\(req,\s*res\)\s*=>\s*\{",
    r"http\.createServer\(\s*async\s+function\s*\(req,\s*res\)\s*\{",
    r"http\.createServer\(\s*\(req,\s*res\)\s*=>\s*\{",
    r"http\.createServer\(\s*function\s*\(req,\s*res\)\s*\{",
]


def install(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    dashboard = repo_root / "Dashboard" / "dashboard_server.js"
    routes = repo_root / "Dashboard" / "phase1_api_routes.js"
    if not dashboard.exists():
        raise FileNotFoundError(f"Dashboard server not found: {dashboard}")
    if not routes.exists():
        raise FileNotFoundError(f"Phase 1 route module not found: {routes}")

    original = dashboard.read_text(encoding="utf-8")
    updated = original

    require_inserted = False
    if REQUIRE_MARKER not in updated:
        updated, require_inserted = _insert_require(updated)
        if not require_inserted:
            raise RuntimeError("Unable to insert phase1_api_routes require into dashboard_server.js")

    handler_inserted = False
    if HANDLER_MARKER not in updated:
        updated, handler_inserted = _insert_dispatch(updated)
        if not handler_inserted:
            raise RuntimeError(
                "Unable to locate http.createServer request handler. "
                "Open Dashboard/dashboard_server.js and insert the dispatch block manually near the top of the request handler."
            )

    if updated != original:
        backup = dashboard.with_suffix(".js.phase1.bak")
        if not backup.exists():
            shutil.copy2(dashboard, backup)
        dashboard.write_text(updated, encoding="utf-8")

    return {
        "ok": True,
        "dashboard": str(dashboard),
        "changed": updated != original,
        "requireInserted": require_inserted,
        "handlerInserted": handler_inserted,
    }


def _insert_require(source: str) -> tuple[str, bool]:
    preferred = [
        "const path = require('path');",
        'const path = require("path");',
        "const http = require('http');",
        'const http = require("http");',
    ]
    for marker in preferred:
        index = source.find(marker)
        if index != -1:
            insert_at = index + len(marker)
            separator = "\n" if not source[insert_at: insert_at + 1] == "\n" else ""
            return source[:insert_at] + "\n" + REQUIRE_LINE + separator + source[insert_at:], True
    return source, False


def _insert_dispatch(source: str) -> tuple[str, bool]:
    for pattern in CREATE_SERVER_PATTERNS:
        match = re.search(pattern, source)
        if match:
            insert_at = match.end()
            return source[:insert_at] + DISPATCH_BLOCK + source[insert_at:], True
    return source, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install QuantGod Phase 1 dashboard API route hook")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    result = install(Path(args.repo_root))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
