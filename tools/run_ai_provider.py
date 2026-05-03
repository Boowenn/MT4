#!/usr/bin/env python3
"""QuantGod local AI provider router CLI.

The CLI is for single-user local configuration/health checks only. It never
stores API keys, receives commands, or exposes any trading capability.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
for candidate in (str(REPO_ROOT), str(TOOLS_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from ai_analysis.providers.base import AIProviderError, assert_ai_provider_safety, provider_safety_payload  # noqa: E402
from ai_analysis.providers.router import load_ai_provider, load_ai_provider_config, supported_models_payload  # noqa: E402

SCHEMA = "quantgod.ai_provider_router.v1"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def config_payload(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_provider_config(repo_root=REPO_ROOT, env_file=args.env_file)
    return {
        "schema": SCHEMA,
        "ok": True,
        "mode": "config",
        "config": config.redacted(),
        "safety": provider_safety_payload(),
    }


def status_payload(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_provider_config(repo_root=REPO_ROOT, env_file=args.env_file)
    return {
        "schema": SCHEMA,
        "ok": True,
        "mode": "status",
        "provider": config.provider,
        "model": config.model,
        "enabled": config.enabled,
        "configured": config.configured,
        "liveCheckRequired": bool(config.enabled and config.configured),
        "note": "Run health --live to perform a network provider call.",
        "safety": provider_safety_payload(),
    }


def health_payload(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_provider_config(repo_root=REPO_ROOT, env_file=args.env_file)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": True,
        "mode": "health",
        "provider": config.provider,
        "model": config.model,
        "enabled": config.enabled,
        "configured": config.configured,
        "live": bool(args.live),
        "safety": provider_safety_payload(),
    }
    if not args.live:
        payload["status"] = "config_only"
        payload["message"] = "No network call made. Pass --live to call the provider."
        return payload
    provider = load_ai_provider(config)
    response = provider.chat_json(
        system_prompt="Return a compact JSON object with ok=true, purpose='health', and advisoryOnly=true.",
        user_payload={"schema": SCHEMA, "purpose": "health", "advisoryOnly": True},
        purpose="health",
    )
    payload["providerResponse"] = response.to_dict()
    payload["ok"] = bool(response.ok)
    payload["status"] = response.status
    return payload


def chat_payload(args: argparse.Namespace) -> dict[str, Any]:
    config = load_ai_provider_config(repo_root=REPO_ROOT, env_file=args.env_file)
    if not args.live:
        return {
            "schema": SCHEMA,
            "ok": True,
            "mode": "chat-json",
            "status": "dry_run",
            "config": config.redacted(),
            "userPayload": json.loads(args.user_json or "{}"),
            "safety": provider_safety_payload(),
        }
    provider = load_ai_provider(config)
    response = provider.chat_json(
        system_prompt=args.system_prompt,
        user_payload=json.loads(args.user_json or "{}"),
        purpose=args.purpose,
    )
    return {
        "schema": SCHEMA,
        "ok": bool(response.ok),
        "mode": "chat-json",
        "providerResponse": response.to_dict(),
        "safety": provider_safety_payload(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=None, help="Optional local .env.ai.local path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("config", help="Print redacted provider configuration")
    sub.add_parser("status", help="Print provider readiness without a network call")
    sub.add_parser("models", help="Print supported provider/model IDs")

    health = sub.add_parser("health", help="Provider health check; config-only unless --live is passed")
    health.add_argument("--live", action="store_true", help="Perform a real provider API call")

    chat = sub.add_parser("chat-json", help="Send a JSON request through the provider; dry-run unless --live is passed")
    chat.add_argument("--live", action="store_true", help="Perform a real provider API call")
    chat.add_argument("--purpose", default="advisory")
    chat.add_argument("--system-prompt", default="Return a JSON object. Do not include execution instructions.")
    chat.add_argument("--user-json", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        assert_ai_provider_safety(os.environ)
        if args.command == "config":
            print_json(config_payload(args))
        elif args.command == "status":
            print_json(status_payload(args))
        elif args.command == "models":
            print_json(supported_models_payload())
        elif args.command == "health":
            print_json(health_payload(args))
        elif args.command == "chat-json":
            print_json(chat_payload(args))
        else:  # pragma: no cover
            parser.error(f"unsupported command: {args.command}")
    except (AIProviderError, ValueError, json.JSONDecodeError) as error:
        print_json({"schema": SCHEMA, "ok": False, "error": str(error), "safety": provider_safety_payload()})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
