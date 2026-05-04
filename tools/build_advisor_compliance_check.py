#!/usr/bin/env python3
"""Detect governance-advisor-to-preset compliance drift and emit Telegram alerts."""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))

ROUTE_TO_LIVE_SWITCH = {
    "RSI_Reversal": "EnablePilotRsiH1Live",
    "BB_Triple": "EnablePilotBBH1Live",
    "MACD_Divergence": "EnablePilotMacdH1Live",
    "SR_Breakout": "EnablePilotSRM15Live",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _parse_set_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _as_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "y", "on"}


def check_advisor_compliance(runtime_dir: Path | None = None, preset_path: Path | None = None) -> list[dict[str, Any]]:
    rt = runtime_dir or (REPO_ROOT / "runtime")
    preset = preset_path or (REPO_ROOT / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set")
    advisor_state = _read_json(rt / "QuantGod_GovernanceAdvisor.json")
    preset_state = _parse_set_file(preset)
    if not advisor_state:
        return []
    route_decisions = advisor_state.get("routeDecisions") or []
    now = datetime.now(JST)
    alerts: list[dict[str, Any]] = []
    for row in route_decisions:
        key = str(row.get("key") or "")
        if key not in ROUTE_TO_LIVE_SWITCH:
            continue
        switch = ROUTE_TO_LIVE_SWITCH[key]
        action = str(row.get("recommendedAction") or "")
        recommended_live = action not in {"DEMOTE_REVIEW", "DEMOTE_LIVE", "DEMOTE_NOW"}
        actual_live = _as_bool(preset_state.get(switch, "false"))
        if actual_live == recommended_live:
            continue
        generated_at_str = str(advisor_state.get("generatedAt") or "")
        try:
            generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
            stale_hours = (now - generated_at.astimezone(JST)).total_seconds() / 3600
        except Exception:
            stale_hours = 999
        severity = "high" if stale_hours > 24 else ("medium" if stale_hours > 1 else "low")
        alerts.append({
            "severity": severity,
            "route": key,
            "recommendation": action,
            "recommendation_age_hours": round(stale_hours, 1),
            "preset_says_live": actual_live,
            "advisor_says_should_be_live": recommended_live,
            "message": f"{key}: advisor recommends {action} ({stale_hours:.0f}h ago) but preset {switch}={actual_live}",
        })
    return alerts


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Advisor compliance checker")
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--preset", default="")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    rt = Path(args.runtime_dir) if args.runtime_dir else None
    preset = Path(args.preset) if args.preset else None
    alerts = check_advisor_compliance(rt, preset)
    if args.json:
        print(json.dumps({"ok": True, "alerts": alerts, "count": len(alerts)}, ensure_ascii=False, indent=2))
    else:
        for a in alerts:
            print(f"[{a['severity'].upper()}] {a['message']}")
        if not alerts:
            print("OK: all advisor recommendations match preset state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
