#!/usr/bin/env python3
"""Set up a read-only Telethon session for Polymarket copy-trader intake.

This helper is intentionally narrow: it logs in a local Telegram user session,
probes the configured channel, and stores only local config values in
.env.telegram.local. It never places orders, sends messages, or prints secrets.
"""
from __future__ import annotations

import argparse
import asyncio
from getpass import getpass
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from telegram_notifier.config import parse_env_file, update_env_file

DEFAULT_CHANNEL = "预测市场内幕钱包监控"
DEFAULT_SESSION = "runtime/telegram/polymarket_channel"
WALLET_PREFIX = "0x"


def emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def clean(value: object) -> str:
    return str(value or "").strip()


def redact(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


def env_value(values: Mapping[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = clean(values.get(key))
        if value:
            return value
    return default


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_env_path(repo_root: Path, env_file: str) -> Path:
    path = Path(env_file).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def resolve_session_path(env_file: Path, session: str) -> Path:
    path = Path(session or DEFAULT_SESSION).expanduser()
    if not path.is_absolute():
        path = env_file.parent / path
    return path


def prompt_value(label: str, current: str, *, secret: bool = False, required: bool = True) -> str:
    current_hint = "configured" if current else "missing"
    prompt = f"{label} [{current_hint}]: "
    if secret:
        value = getpass(prompt).strip()
    else:
        value = input(prompt).strip()
    if value:
        return value
    if current:
        return current
    if required:
        raise RuntimeError(f"{label} is required")
    return ""


async def probe_channel(api_id: int, api_hash: str, session_path: Path, channel: str, limit: int) -> dict[str, Any]:
    try:
        from telethon import TelegramClient, errors  # type: ignore
    except Exception as exc:  # pragma: no cover - optional local dependency
        return {
            "ok": False,
            "error": f"telethon_not_installed:{type(exc).__name__}",
            "nextAction": "Run python3 -m pip install --user telethon, then rerun this helper.",
        }

    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return {
                "ok": False,
                "authorized": False,
                "error": "telethon_session_not_authorized",
                "nextAction": "Run with --interactive-login to enter phone/code and create the local session.",
            }
        entity = None
        matched_dialogs: list[str] = []
        try:
            entity = await client.get_entity(channel)
        except Exception:
            async for dialog in client.iter_dialogs(limit=300):
                title = clean(getattr(dialog, "name", ""))
                if channel and channel in title:
                    entity = dialog.entity
                    matched_dialogs.append(title)
                    break
        if entity is None:
            return {
                "ok": False,
                "authorized": True,
                "error": "channel_not_found",
                "channel": channel,
                "matchedDialogs": matched_dialogs,
            }
        title = clean(getattr(entity, "title", "")) or clean(getattr(entity, "username", "")) or channel
        if title:
            matched_dialogs.append(title)
        messages_read = 0
        wallet_like_messages = 0
        previews: list[dict[str, Any]] = []
        async for message in client.iter_messages(entity, limit=max(1, min(500, limit))):
            messages_read += 1
            text = clean(getattr(message, "raw_text", ""))
            has_wallet_like = WALLET_PREFIX in text.lower() or "钱包" in text or "wallet" in text.lower()
            if has_wallet_like:
                wallet_like_messages += 1
                previews.append(
                    {
                        "messageId": getattr(message, "id", None),
                        "date": clean(getattr(message, "date", "")),
                        "textPreview": " ".join(text.split())[:180],
                    }
                )
        return {
            "ok": True,
            "authorized": True,
            "channel": title,
            "matchedDialogs": sorted(set(matched_dialogs)),
            "messagesRead": messages_read,
            "walletLikeMessages": wallet_like_messages,
            "previews": previews[:5],
            "nextAction": "Run tools/run_mac_polymarket_readonly_cycle.sh to feed the Telethon source into copy-trader discovery.",
        }
    finally:
        await client.disconnect()


async def interactive_login(api_id: int, api_hash: str, session_path: Path, phone: str) -> dict[str, Any]:
    try:
        from telethon import TelegramClient, errors  # type: ignore
    except Exception as exc:  # pragma: no cover - optional local dependency
        return {"ok": False, "error": f"telethon_not_installed:{type(exc).__name__}"}

    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return {"ok": True, "authorized": True, "alreadyAuthorized": True}
        phone = phone or input("Telegram phone number: ").strip()
        if not phone:
            raise RuntimeError("Telegram phone number is required")
        sent = await client.send_code_request(phone)
        code = input("Telegram login code: ").strip()
        if not code:
            raise RuntimeError("Telegram login code is required")
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
        except errors.SessionPasswordNeededError:
            password = getpass("Telegram 2FA password: ")
            await client.sign_in(password=password)
        return {"ok": True, "authorized": bool(await client.is_user_authorized()), "alreadyAuthorized": False}
    finally:
        await client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure read-only Telethon for Polymarket Telegram copy-trader intake.")
    parser.add_argument("--repo-root", default=str(default_repo_root()), help="QuantGodBackend repo root.")
    parser.add_argument("--env-file", default=".env.telegram.local", help="Local Telegram env file. Never commit this file.")
    parser.add_argument("--channel", default="", help="Telegram channel title, username, link, or id.")
    parser.add_argument("--session", default="", help="Telethon session path.")
    parser.add_argument("--limit", type=int, default=80, help="Messages to probe after login.")
    parser.add_argument("--interactive-login", action="store_true", help="Prompt for API credentials, phone, code, and optional 2FA.")
    parser.add_argument("--no-write-env", action="store_true", help="Do not write API/session/channel values to the local env file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    env_file = resolve_env_path(repo_root, args.env_file)
    values = parse_env_file(env_file)

    api_id_text = env_value(values, "QG_TELEGRAM_API_ID", "TELEGRAM_API_ID")
    api_hash = env_value(values, "QG_TELEGRAM_API_HASH", "TELEGRAM_API_HASH")
    phone = env_value(values, "QG_TELEGRAM_PHONE", "TELEGRAM_PHONE")
    channel = clean(args.channel) or env_value(
        values,
        "QG_POLYMARKET_TELEGRAM_ENTITY",
        "QG_POLYMARKET_TELEGRAM_CHANNEL",
        "QG_POLYMARKET_TELEGRAM_CHANNEL_NAME",
        default=DEFAULT_CHANNEL,
    )
    session = clean(args.session) or env_value(values, "QG_TELETHON_SESSION", "TELETHON_SESSION", default=DEFAULT_SESSION)

    try:
        if args.interactive_login:
            api_id_text = prompt_value("Telegram API ID", api_id_text)
            api_hash = prompt_value("Telegram API hash", api_hash, secret=True)
            phone = prompt_value("Telegram phone", phone, required=False)
        if not api_id_text or not api_hash:
            emit(
                {
                    "ok": False,
                    "envFile": str(env_file),
                    "apiIdConfigured": bool(api_id_text),
                    "apiHashConfigured": bool(api_hash),
                    "sessionPath": str(resolve_session_path(env_file, session)),
                    "channel": channel,
                    "error": "missing_api_credentials",
                    "nextAction": "Add QG_TELEGRAM_API_ID and QG_TELEGRAM_API_HASH, or rerun with --interactive-login.",
                }
            )
            return 2
        api_id = int(api_id_text)
        session_path = resolve_session_path(env_file, session)
        if not args.no_write_env:
            update_env_file(
                env_file,
                {
                    "QG_TELEGRAM_API_ID": str(api_id),
                    "QG_TELEGRAM_API_HASH": api_hash,
                    "QG_POLYMARKET_TELEGRAM_CHANNEL_NAME": channel,
                    "QG_POLYMARKET_TELEGRAM_ENTITY": channel,
                    "QG_TELETHON_SESSION": str(session_path.relative_to(env_file.parent) if session_path.is_relative_to(env_file.parent) else session_path),
                },
            )
        login_result: dict[str, Any] = {"ok": True, "authorized": None, "skipped": True}
        if args.interactive_login:
            login_result = asyncio.run(interactive_login(api_id, api_hash, session_path, phone))
            if not login_result.get("ok"):
                emit({"ok": False, "envFile": str(env_file), "sessionPath": str(session_path), "login": login_result})
                return 1
        probe = asyncio.run(probe_channel(api_id, api_hash, session_path, channel, args.limit))
        emit(
            {
                "ok": bool(probe.get("ok")),
                "envFile": str(env_file),
                "apiIdConfigured": True,
                "apiIdRedacted": redact(str(api_id), keep=2),
                "apiHashConfigured": True,
                "sessionPath": str(session_path),
                "channel": channel,
                "login": login_result,
                "probe": probe,
            }
        )
        return 0 if probe.get("ok") else 1
    except Exception as exc:
        emit({"ok": False, "envFile": str(env_file), "error": f"{type(exc).__name__}:{str(exc)[:220]}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
