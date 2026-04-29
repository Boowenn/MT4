#!/usr/bin/env python3
"""Guarded MT5 adaptive-control executor.

This closes the last QuantDinger-style lifecycle gap: Governance/PromotionGate
recommendations can become durable control actions.  By default the executor is
dry-run/staging-only and cannot mutate the HFM live preset.  Live preset writes
require explicit flags, environment enablement, a signed authorization lock,
and `allowLivePresetMutation=true`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import mt5_trading_client
except ImportError:  # pragma: no cover
    sys.path.append(str(Path(__file__).resolve().parent))
    import mt5_trading_client  # type: ignore


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
PROMOTION_GATE_NAME = "QuantGod_VersionPromotionGate.json"
GOVERNANCE_NAME = "QuantGod_GovernanceAdvisor.json"
OUTPUT_NAME = "QuantGod_MT5AdaptiveControlActions.json"
LEDGER_NAME = "QuantGod_MT5AdaptiveControlLedger.csv"
STAGING_PRESET_NAME = "QuantGod_MT5AdaptiveControlStaging.set"
MODE = "MT5_ADAPTIVE_CONTROL_EXECUTOR_V1"
WORKER_VERSION = "mt5-adaptive-control-executor-v1"

DEFAULT_CONFIG = {
    "mode": "MT5_ADAPTIVE_CONTROL_CONFIG_V1",
    "dryRun": True,
    "killSwitch": True,
    "allowStagingPreset": True,
    "allowLivePresetMutation": False,
    "requireEnvEnable": True,
    "envEnableVar": "QG_MT5_ADAPTIVE_APPLY_ENABLED",
    "authLockPath": str(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "QuantGod" / "mt5_trading_auth_lock.json"),
    "signatureRequired": True,
    "signatureSecretEnvVar": "QG_MT5_AUTH_SECRET",
    "allowedRoutes": ["MA_Cross", "RSI_Reversal", "BB_Triple", "MACD_Divergence", "SR_Breakout"],
    "livePresetPath": r"C:\Program Files\HFM Metatrader 5\MQL5\Presets\QuantGod_MT5_HFM_LivePilot.set",
}

LEDGER_FIELDS = [
    "LedgerId",
    "EventTimeIso",
    "ActionId",
    "Route",
    "Decision",
    "ApplyMode",
    "DryRun",
    "LivePresetMutationAllowed",
    "Reason",
    "Source",
    "StagingPresetPath",
    "LivePresetPath",
    "WorkerVersion",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path).replace("\ufeff", ""))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config(runtime_dir: Path, config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or runtime_dir / "QuantGod_MT5AdaptiveControlConfig.json"
    payload = read_json(path)
    merged = dict(DEFAULT_CONFIG)
    merged.update(payload)
    merged["_configPath"] = str(path)
    return merged


def env_enabled(config: dict[str, Any]) -> bool:
    if not as_bool(config.get("requireEnvEnable"), True):
        return True
    return str(os.environ.get(clean(config.get("envEnableVar") or "QG_MT5_ADAPTIVE_APPLY_ENABLED", 80), "")).lower() in {"1", "true", "yes", "y", "on"}


def extract_route_actions(promotion_gate: dict[str, Any], governance: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    candidates = []
    for key in ("rows", "routes", "recommendations", "decisions"):
        value = promotion_gate.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    if not candidates:
        for key in ("strategyDecisions", "routeDecisions"):
            value = governance.get(key)
            if isinstance(value, list):
                candidates.extend(value)

    for item in candidates:
        if not isinstance(item, dict):
            continue
        route = clean(item.get("route") or item.get("strategy") or item.get("strategyName"), 80)
        if not route:
            continue
        decision = clean(
            item.get("decision")
            or item.get("promotionDecision")
            or item.get("recommendation")
            or item.get("action")
            or "REVIEW",
            80,
        ).upper()
        if any(token in decision for token in ("PROMOTE", "ENABLE", "KEEP_LIVE")):
            action = "STAGE_ENABLE_ROUTE"
        elif any(token in decision for token in ("DEMOTE", "DISABLE", "PAUSE")):
            action = "STAGE_DISABLE_ROUTE"
        elif any(token in decision for token in ("RETUNE", "ITERATE")):
            action = "STAGE_RETUNE_ROUTE"
        else:
            action = "REVIEW_ONLY"
        actions.append(
            {
                "actionId": f"adaptive-{route}-{len(actions) + 1}",
                "route": route,
                "action": action,
                "decision": decision,
                "reason": clean(item.get("reason") or item.get("summary") or item.get("nextStep"), 500),
                "source": clean(item.get("versionId") or item.get("candidateId") or "promotion_gate", 160),
            }
        )
    return actions


def fallback_actions() -> list[dict[str, Any]]:
    return [
        {
            "actionId": "adaptive-review-only",
            "route": "ALL",
            "action": "REVIEW_ONLY",
            "decision": "NO_PROMOTION_GATE_ROWS",
            "reason": "No structured PromotionGate/Governance route decisions were available.",
            "source": "fallback",
        }
    ]


def parse_set_file(path: Path) -> list[str]:
    if path.exists():
        return read_text(path).splitlines()
    return []


def update_preset_lines(lines: list[str], actions: list[dict[str, Any]]) -> list[str]:
    output = list(lines)
    stamp = f"; QuantGod adaptive staging generated {utc_now()}"
    output.append(stamp)
    for action in actions:
        route = clean(action.get("route"), 80)
        if route == "ALL":
            continue
        key = f"; AdaptiveAction.{route}"
        value = f"{key}={clean(action.get('action'), 80)}|{clean(action.get('decision'), 80)}|{clean(action.get('source'), 120)}"
        output.append(value)
    return output


def write_staging_preset(runtime_dir: Path, config: dict[str, Any], actions: list[dict[str, Any]]) -> Path:
    live_path = Path(clean(config.get("livePresetPath"), 260))
    lines = parse_set_file(live_path)
    if not lines:
        lines = ["; QuantGod adaptive staging preset"]
    staging = runtime_dir / STAGING_PRESET_NAME
    staging.write_text("\n".join(update_preset_lines(lines, actions)) + "\n", encoding="utf-8")
    return staging


def append_ledger(runtime_dir: Path, row: dict[str, Any]) -> None:
    path = runtime_dir / LEDGER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in LEDGER_FIELDS})


def validate_apply(config: dict[str, Any], action: dict[str, Any], *, apply_live: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if as_bool(config.get("killSwitch"), True):
        reasons.append("kill_switch_on")
    if as_bool(config.get("dryRun"), True):
        reasons.append("dry_run")
    if not env_enabled(config):
        reasons.append("adaptive_env_disabled")
    if clean(action.get("route"), 80) not in {clean(item, 80) for item in config.get("allowedRoutes", [])} and clean(action.get("route"), 80) != "ALL":
        reasons.append("route_not_allowed")
    if apply_live and not as_bool(config.get("allowLivePresetMutation"), False):
        reasons.append("live_preset_mutation_disabled")
    if apply_live:
        auth = mt5_trading_client.validate_auth_lock(config, {"endpoint": "adaptive-control", "route": action.get("route")}, None)
        if not auth["ok"]:
            reasons.extend(auth["reasons"])
    return not reasons, reasons


def run(
    runtime_dir: Path,
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    config_path: Path | None = None,
    apply_staging: bool = False,
    apply_live: bool = False,
) -> dict[str, Any]:
    config = load_config(runtime_dir, config_path)
    promotion_gate = read_json(runtime_dir / PROMOTION_GATE_NAME)
    governance = read_json(runtime_dir / GOVERNANCE_NAME)
    actions = extract_route_actions(promotion_gate, governance) or fallback_actions()
    staging_path = ""
    live_path = clean(config.get("livePresetPath"), 260)

    if apply_staging and as_bool(config.get("allowStagingPreset"), True):
        staging_path = str(write_staging_preset(runtime_dir, config, actions))

    rows = []
    for action in actions:
        ok, reasons = validate_apply(config, action, apply_live=apply_live)
        decision = "LIVE_PRESET_APPLIED" if ok and apply_live else "STAGING_WRITTEN" if staging_path else "DRY_RUN_ACTION"
        if reasons:
            decision = "BLOCKED"
        row = {
            "LedgerId": str(uuid.uuid4()),
            "EventTimeIso": utc_now(),
            "ActionId": action["actionId"],
            "Route": action["route"],
            "Decision": decision,
            "ApplyMode": "live" if apply_live else "staging" if staging_path else "dry_run",
            "DryRun": str(as_bool(config.get("dryRun"), True)).lower(),
            "LivePresetMutationAllowed": str(as_bool(config.get("allowLivePresetMutation"), False)).lower(),
            "Reason": ",".join(reasons) if reasons else action.get("reason", ""),
            "Source": action.get("source", ""),
            "StagingPresetPath": staging_path,
            "LivePresetPath": live_path,
            "WorkerVersion": WORKER_VERSION,
        }
        append_ledger(runtime_dir, row)
        rows.append({**action, "decisionStatus": decision, "blockers": reasons})

    if apply_live and all(not row.get("blockers") for row in rows) and staging_path:
        shutil.copy2(staging_path, live_path)

    payload = {
        "ok": True,
        "mode": MODE,
        "generatedAtIso": utc_now(),
        "repoRoot": str(repo_root),
        "runtimeDir": str(runtime_dir),
        "safety": {
            "readOnly": False,
            "adaptiveControlExecutor": True,
            "dryRun": as_bool(config.get("dryRun"), True),
            "killSwitch": as_bool(config.get("killSwitch"), True),
            "envEnabled": env_enabled(config),
            "orderSendAllowed": False,
            "closeAllowed": False,
            "cancelAllowed": False,
            "livePresetMutationAllowed": as_bool(config.get("allowLivePresetMutation"), False) and apply_live,
            "auditLedgerRequired": True,
            "mutatesMt5": bool(apply_live and as_bool(config.get("allowLivePresetMutation"), False)),
        },
        "summary": {
            "actions": len(actions),
            "blocked": sum(1 for row in rows if row.get("blockers")),
            "stagingPresetPath": staging_path,
            "livePresetPath": live_path,
            "ledger": str(runtime_dir / LEDGER_NAME),
        },
        "actions": rows,
    }
    write_json(runtime_dir / OUTPUT_NAME, payload)
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantGod guarded MT5 adaptive-control executor")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--config", default="")
    parser.add_argument("--apply-staging", action="store_true")
    parser.add_argument("--apply-live", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = run(
        Path(args.runtime_dir),
        repo_root=Path(args.repo_root),
        config_path=Path(args.config) if args.config else None,
        apply_staging=args.apply_staging,
        apply_live=args.apply_live,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
