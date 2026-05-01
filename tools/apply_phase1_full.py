from __future__ import annotations

import argparse
import json
from pathlib import Path

from install_phase1_dashboard_routes import install as install_dashboard
from install_phase1_frontend import install as install_frontend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply QuantGod Phase 1 dashboard/frontend hooks")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    results: dict[str, object] = {"repoRoot": str(repo_root)}
    if not args.skip_dashboard:
        results["dashboard"] = install_dashboard(repo_root)
    if not args.skip_frontend:
        results["frontend"] = install_frontend(repo_root)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
