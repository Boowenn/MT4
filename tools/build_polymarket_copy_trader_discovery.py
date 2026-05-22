#!/usr/bin/env python3
"""Discover strong Polymarket traders for read-only shadow copy trading.

This worker only reads public Polymarket profile/leaderboard endpoints and an
optional Telegram export. It never signs orders, never loads a wallet, and never
places bets. Its output is the copy-trading source of truth for the dashboard
and downstream shadow replay.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import certifi  # type: ignore
except Exception:  # pragma: no cover - optional local dependency
    certifi = None


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
OUTPUT_NAME = "QuantGod_PolymarketCopyTraderDiscovery.json"
LEDGER_NAME = "QuantGod_PolymarketCopyTraderDiscovery.csv"
DATA_API_BASE = "https://data-api.polymarket.com"
WALLET_RE = re.compile(r"0x[a-fA-F0-9]{40}")
TELEGRAM_TRADER_RE = re.compile(
    r"(?P<user>[A-Za-z0-9_.-]{2,80})\s*\|\s*Rank\s*#(?P<rank>\d+)\s*\|\s*(?P<wallet>0x[a-fA-F0-9]{4,}(?:\.\.\.)?[a-fA-F0-9]{4,})",
    re.IGNORECASE,
)
SIGNAL_SIDE_RE = re.compile(r"\b(?P<side>BUY|SELL)\s+(?P<outcome>[A-Za-z][A-Za-z0-9_ ./'-]{0,60})", re.IGNORECASE)
DOCS = {
    "leaderboard": "https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings",
    "positions": "https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user",
    "closedPositions": "https://docs.polymarket.com/api-reference/core/get-closed-positions-for-a-user",
    "activity": "https://docs.polymarket.com/api-reference/core/get-user-activity",
}

_SSL_CONTEXT: ssl.SSLContext | None = None


@dataclass(frozen=True)
class OutputTargets:
    runtime_dir: Path
    dashboard_dir: Path | None


def parse_csv(value: str, fallback: list[str]) -> list[str]:
    items = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return items or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--leaderboard-categories", default="OVERALL,POLITICS,SPORTS,CRYPTO,ECONOMICS,TECH,FINANCE")
    parser.add_argument("--leaderboard-periods", default="MONTH,ALL,WEEK")
    parser.add_argument("--leaderboard-limit", type=int, default=20)
    parser.add_argument("--max-traders", type=int, default=30)
    parser.add_argument("--positions-limit", type=int, default=30)
    parser.add_argument("--closed-limit", type=int, default=50)
    parser.add_argument("--activity-limit", type=int, default=40)
    parser.add_argument("--min-closed-positions", type=int, default=8)
    parser.add_argument("--min-current-value", type=float, default=50.0)
    parser.add_argument("--min-shadow-score", type=float, default=60.0)
    parser.add_argument("--request-timeout", type=float, default=12.0)
    parser.add_argument("--telegram-export", default="")
    parser.add_argument("--telegram-bot-env", default=".env.telegram.local")
    parser.add_argument("--telegram-bot-updates-limit", type=int, default=100)
    parser.add_argument("--telegram-telethon-env", default="")
    parser.add_argument("--telegram-telethon-session", default="")
    parser.add_argument("--telegram-telethon-limit", type=int, default=300)
    parser.add_argument("--telegram-channel-name", default="预测市场内幕钱包监控")
    parser.add_argument("--real-wallet-enabled", default="false")
    parser.add_argument("--real-wallet-auto-unlock", default="true")
    parser.add_argument("--real-wallet-require-telegram", default="true")
    parser.add_argument("--shadow-replay-path", default="")
    parser.add_argument("--walk-forward-path", default="")
    parser.add_argument("--min-shadow-replay-trades", type=int, default=30)
    parser.add_argument("--min-shadow-profit-factor", type=float, default=1.10)
    parser.add_argument("--min-shadow-net-pnl-usdc", type=float, default=0.01)
    parser.add_argument("--min-walk-forward-batches", type=int, default=3)
    parser.add_argument("--min-walk-forward-pass-rate-pct", type=float, default=60.0)
    parser.add_argument("--max-validation-age-hours", type=float, default=168.0)
    parser.add_argument("--real-wallet-take-profit-pct", type=float, default=35.0)
    parser.add_argument("--real-wallet-stop-loss-pct", type=float, default=18.0)
    parser.add_argument("--real-wallet-trailing-stop-pct", type=float, default=12.0)
    parser.add_argument("--real-wallet-max-position-usdc", type=float, default=1.0)
    parser.add_argument("--real-wallet-max-daily-loss-usdc", type=float, default=2.0)
    parser.add_argument("--real-wallet-max-open-positions", type=int, default=3)
    parser.add_argument("--real-wallet-min-entry-price", type=float, default=0.04)
    parser.add_argument("--real-wallet-max-entry-price", type=float, default=0.90)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(value: Any) -> str:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def str_to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def round4(value: Any) -> float:
    return round(safe_number(value), 4)


def certifi_ssl_context() -> ssl.SSLContext | None:
    global _SSL_CONTEXT
    if certifi is None:
        return None
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    return _SSL_CONTEXT


def public_urlopen(request: urllib.request.Request, timeout: float):
    context = certifi_ssl_context()
    if context is not None:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_json(path: str, params: dict[str, Any], timeout: float) -> tuple[Any, str]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")}, doseq=True)
    url = f"{DATA_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "QuantGodCopyTraderDiscovery/1.0 read-only",
        },
        method="GET",
    )
    with public_urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")), url


def as_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def read_optional_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_validation_payload(
    explicit_path: str,
    file_name: str,
    runtime_dir: Path,
    dashboard_dir: Path,
) -> tuple[dict[str, Any], str]:
    candidates: list[Path] = []
    if explicit_path.strip():
        candidates.append(Path(explicit_path).expanduser())
    candidates.extend([runtime_dir / file_name, dashboard_dir / file_name])
    for path in candidates:
        payload = read_optional_json(path)
        if payload:
            return payload, str(path)
    return {}, str(candidates[0]) if candidates else ""


def parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def generated_at_value(payload: dict[str, Any]) -> str:
    for key in ("generatedAtIso", "generatedAt", "updatedAtIso", "updatedAt", "timestamp"):
        value = payload.get(key)
        if value:
            return str(value)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for key in ("generatedAtIso", "generatedAt", "updatedAtIso", "updatedAt", "timestamp"):
        value = summary.get(key)
        if value:
            return str(value)
    return ""


def validation_age_hours(payload: dict[str, Any]) -> float | None:
    parsed = parse_iso_datetime(generated_at_value(payload))
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0)


def first_number(container: dict[str, Any], keys: tuple[str, ...], default: float = 0.0) -> float:
    for key in keys:
        if key in container:
            return safe_number(container.get(key), default)
    return default


def first_int(container: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    for key in keys:
        if key in container:
            return safe_int(container.get(key), default)
    return default


def first_bool(container: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    for key in keys:
        if key in container:
            return str_to_bool(container.get(key))
    return None


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str_to_bool(value)


def read_telegram_wallets(path_text: str, channel_name: str) -> dict[str, Any]:
    path_text = path_text.strip()
    result = {
        "channelName": channel_name,
        "configured": bool(path_text),
        "mode": "telegram_export_readonly",
        "active": False,
        "path": path_text,
        "wallets": [],
        "walletCount": 0,
        "signals": [],
        "signalCount": 0,
        "filesRead": 0,
        "error": "",
        "nextAction": "导出 Telegram 频道消息或配置 Telethon 只读抓取后，提取内幕钱包/信号来源。",
    }
    if not path_text:
        return result
    root = Path(path_text).expanduser()
    if not root.exists():
        result["error"] = "telegram_export_path_missing"
        return result
    files: list[Path] = []
    if root.is_file():
        files = [root]
    else:
        for suffix in ("*.json", "*.txt", "*.html", "*.htm", "*.csv"):
            files.extend(sorted(root.rglob(suffix))[:30])
    wallets: set[str] = set()
    signals: list[dict[str, Any]] = []
    for file_path in files[:50]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")[:5_000_000]
        except OSError:
            continue
        wallets.update(item.lower() for item in WALLET_RE.findall(text))
        signals.extend(extract_telegram_signals([text], "telegram_export", channel_name))
        result["filesRead"] += 1
    result["wallets"] = sorted(wallets)
    result["walletCount"] = len(wallets)
    result["signals"] = signals[:100]
    result["signalCount"] = len(result["signals"])
    result["active"] = bool(wallets or signals)
    if wallets or signals:
        result["nextAction"] = "Telegram 导出已接入；这些钱包会和公开排行榜一起做强交易员排序。"
    else:
        result["error"] = "no_wallets_found_in_export"
    return result


def read_env_values(path_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    path_text = str(path_text or "").strip()
    if not path_text:
        return values
    path = Path(path_text).expanduser()
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(text_fragments(item))
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(text_fragments(item))
        return parts
    return []


def first_regex_number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extract_telegram_signals(fragments: list[str], source: str, channel_name: str) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in fragments:
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        side_match = SIGNAL_SIDE_RE.search(text)
        amount = first_regex_number(r"Amount:\s*\$?([0-9,.]+)", text)
        price = first_regex_number(r"Price:\s*([0-9.]+)\s*¢?", text)
        for match in TELEGRAM_TRADER_RE.finditer(text):
            wallet_text = match.group("wallet")
            wallet_full = wallet_text.lower() if WALLET_RE.fullmatch(wallet_text) else ""
            key = (match.group("user").lower(), str(match.group("rank")), wallet_text.lower())
            if key in seen:
                continue
            seen.add(key)
            signals.append(
                {
                    "source": source,
                    "channelName": channel_name,
                    "userName": match.group("user"),
                    "rank": safe_int(match.group("rank")),
                    "wallet": wallet_full,
                    "walletPreview": wallet_text if not wallet_full else "",
                    "side": side_match.group("side").upper() if side_match else "",
                    "outcome": (side_match.group("outcome").strip() if side_match else "")[:80],
                    "amountUSDC": round4(amount) if amount is not None else None,
                    "priceCents": round4(price) if price is not None else None,
                    "textPreview": text[:260],
                }
            )
    return signals[:100]


def read_telegram_bot_updates(env_path: str, channel_name: str, limit: int, timeout: float) -> dict[str, Any]:
    values = read_env_values(env_path)
    token = values.get("QG_TELEGRAM_BOT_TOKEN") or values.get("TELEGRAM_BOT_TOKEN") or ""
    result = {
        "configured": bool(token),
        "mode": "telegram_bot_api_readonly",
        "active": False,
        "envPath": env_path,
        "updates": 0,
        "matchedUpdates": 0,
        "wallets": [],
        "walletCount": 0,
        "signals": [],
        "signalCount": 0,
        "channelTitles": [],
        "error": "",
        "nextAction": "把只读 bot 加入频道并允许接收 channel_post，或使用 Telegram 导出/Telethon user session。",
    }
    if not token:
        result["error"] = "bot_token_missing"
        return result
    url = (
        "https://api.telegram.org/bot"
        + urllib.parse.quote(token, safe=":")
        + "/getUpdates?"
        + urllib.parse.urlencode(
            {
                "limit": max(1, min(100, limit)),
                "allowed_updates": json.dumps(["channel_post", "message"]),
            }
        )
    )
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "QuantGodTelegramReadonly/1.0"},
        method="GET",
    )
    try:
        with public_urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        result["error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
        return result
    if not payload.get("ok"):
        result["error"] = "telegram_bot_api_not_ok"
        return result
    updates = payload.get("result") if isinstance(payload.get("result"), list) else []
    result["updates"] = len(updates)
    wallets: set[str] = set()
    signals: list[dict[str, Any]] = []
    titles: set[str] = set()
    matched = 0
    for update in updates:
        message = update.get("channel_post") or update.get("message") or {}
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        title = str(chat.get("title") or chat.get("username") or chat.get("type") or "")
        if title:
            titles.add(title)
        fragments = text_fragments(message)
        text = "\n".join(fragments)
        if channel_name and title and channel_name not in title:
            continue
        matched += 1
        wallets.update(item.lower() for item in WALLET_RE.findall(text))
        signals.extend(extract_telegram_signals(fragments, "telegram_bot_api", channel_name))
    result["matchedUpdates"] = matched
    result["channelTitles"] = sorted(titles)
    result["wallets"] = sorted(wallets)
    result["walletCount"] = len(wallets)
    result["signals"] = signals[:100]
    result["signalCount"] = len(result["signals"])
    result["active"] = bool(wallets or signals)
    if wallets or signals:
        result["nextAction"] = "Telegram Bot API 已读到频道钱包；这些钱包会和公开排行榜一起排序。"
    elif updates:
        result["error"] = "updates_present_but_no_matching_wallets"
    else:
        result["error"] = "no_bot_updates"
    return result


def read_telegram_telethon_history(
    env_path: str,
    session_path: str,
    channel_name: str,
    limit: int,
    timeout: float,
) -> dict[str, Any]:
    env = read_env_values(env_path)
    api_id = env.get("QG_TELEGRAM_API_ID") or env.get("TELEGRAM_API_ID") or ""
    api_hash = env.get("QG_TELEGRAM_API_HASH") or env.get("TELEGRAM_API_HASH") or ""
    session = (
        session_path
        or env.get("QG_TELETHON_SESSION")
        or env.get("TELETHON_SESSION")
        or str((Path(env_path).expanduser().parent if env_path else Path.cwd()) / "runtime" / "telegram" / "polymarket_channel")
    )
    entity_hint = (
        env.get("QG_POLYMARKET_TELEGRAM_ENTITY")
        or env.get("QG_POLYMARKET_TELEGRAM_CHANNEL")
        or env.get("QG_POLYMARKET_TELEGRAM_CHANNEL_NAME")
        or channel_name
    )
    result = {
        "configured": bool(api_id and api_hash),
        "mode": "telegram_telethon_user_session_readonly",
        "active": False,
        "envPath": env_path,
        "sessionPath": session,
        "entityHint": entity_hint,
        "channelName": channel_name,
        "messagesRead": 0,
        "wallets": [],
        "walletCount": 0,
        "signals": [],
        "signalCount": 0,
        "matchedDialogs": [],
        "signalPreviews": [],
        "error": "",
        "nextAction": "配置 QG_TELEGRAM_API_ID / QG_TELEGRAM_API_HASH 并登录 Telethon user session，读取频道历史。",
    }
    if not api_id or not api_hash:
        result["error"] = "telethon_api_id_hash_missing"
        return result
    try:
        import asyncio
        from telethon import TelegramClient  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        result["error"] = f"telethon_not_installed:{type(exc).__name__}"
        result["nextAction"] = "运行 python3 -m pip install --user telethon 后，再登录 Telethon user session。"
        return result

    async def collect() -> dict[str, Any]:
        wallets: set[str] = set()
        previews: list[dict[str, Any]] = []
        matched_dialogs: list[str] = []
        client = TelegramClient(str(Path(session).expanduser()), int(api_id), api_hash)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return {
                    "ok": False,
                    "error": "telethon_session_not_authorized",
                    "wallets": [],
                    "signals": [],
                    "messagesRead": 0,
                    "matchedDialogs": [],
                    "signalPreviews": [],
                }
            entity = None
            try:
                entity = await client.get_entity(entity_hint)
            except Exception:
                async for dialog in client.iter_dialogs(limit=300):
                    title = str(getattr(dialog, "name", "") or "")
                    if channel_name and channel_name in title:
                        entity = dialog.entity
                        matched_dialogs.append(title)
                        break
            if entity is None:
                return {
                    "ok": False,
                    "error": "telethon_channel_not_found",
                    "wallets": [],
                    "signals": [],
                    "messagesRead": 0,
                    "matchedDialogs": matched_dialogs,
                    "signalPreviews": [],
                }
            title = str(getattr(entity, "title", "") or getattr(entity, "username", "") or entity_hint)
            if title:
                matched_dialogs.append(title)
            messages_read = 0
            signals: list[dict[str, Any]] = []
            async for message in client.iter_messages(entity, limit=max(1, min(2000, int(limit)))):
                messages_read += 1
                text = str(getattr(message, "raw_text", "") or "")
                fragments = [text]
                for attr in ("reply_markup", "entities"):
                    value = getattr(message, attr, None)
                    if not value:
                        continue
                    try:
                        if hasattr(value, "to_dict"):
                            fragments.extend(text_fragments(value.to_dict()))
                        else:
                            fragments.extend(text_fragments(value))
                    except Exception:
                        continue
                joined = "\n".join(fragments)
                found = [item.lower() for item in WALLET_RE.findall(joined)]
                wallets.update(found)
                signals.extend(extract_telegram_signals(fragments, "telegram_telethon", channel_name))
                if found or "polymarket" in joined.lower() or "wallet" in joined.lower() or "钱包" in joined:
                    previews.append(
                        {
                            "messageId": getattr(message, "id", None),
                            "date": str(getattr(message, "date", "") or ""),
                            "wallets": sorted(set(found))[:10],
                            "textPreview": " ".join(joined.split())[:260],
                        }
                    )
            return {
                "ok": True,
                "error": "",
                "wallets": sorted(wallets),
                "signals": signals[:100],
                "messagesRead": messages_read,
                "matchedDialogs": sorted(set(matched_dialogs)),
                "signalPreviews": previews[:20],
            }
        finally:
            await client.disconnect()

    try:
        collected = asyncio.run(asyncio.wait_for(collect(), timeout=max(5.0, float(timeout) * 2.0)))
    except Exception as exc:  # pragma: no cover - network/session dependent
        result["error"] = f"{type(exc).__name__}:{str(exc)[:180]}"
        return result
    result["messagesRead"] = safe_int(collected.get("messagesRead"))
    result["matchedDialogs"] = collected.get("matchedDialogs") or []
    result["signalPreviews"] = collected.get("signalPreviews") or []
    result["wallets"] = collected.get("wallets") or []
    result["walletCount"] = len(result["wallets"])
    result["signals"] = collected.get("signals") or []
    result["signalCount"] = len(result["signals"])
    result["active"] = bool(result["wallets"] or result["signals"])
    result["error"] = str(collected.get("error") or "")
    if result["active"]:
        result["nextAction"] = "Telethon user session 已读取频道历史；钱包会和公开排行榜一起排序。"
    elif result["messagesRead"]:
        result["nextAction"] = "Telethon 已读到频道消息，但未提取到完整钱包地址；继续解析信号文本或等待新消息。"
    return result


def read_telegram_sources(args: argparse.Namespace) -> dict[str, Any]:
    export = read_telegram_wallets(args.telegram_export, args.telegram_channel_name)
    bot = read_telegram_bot_updates(
        args.telegram_bot_env,
        args.telegram_channel_name,
        args.telegram_bot_updates_limit,
        args.request_timeout,
    )
    telethon_env = args.telegram_telethon_env or args.telegram_bot_env
    telethon = read_telegram_telethon_history(
        telethon_env,
        args.telegram_telethon_session,
        args.telegram_channel_name,
        args.telegram_telethon_limit,
        args.request_timeout,
    )
    sources = (export, bot, telethon)
    wallets = sorted(set(str(item).lower() for source in sources for item in (source.get("wallets") or [])))
    signals = [signal for source in sources for signal in (source.get("signals") or []) if isinstance(signal, dict)]
    configured = bool(export.get("configured") or bot.get("configured") or telethon.get("configured"))
    errors = [str(item.get("error")) for item in sources if item.get("error")]
    return {
        "channelName": args.telegram_channel_name,
        "configured": configured,
        "mode": "telegram_export_bot_or_telethon_readonly",
        "active": bool(wallets or signals),
        "wallets": wallets,
        "walletCount": len(wallets),
        "signals": signals[:150],
        "signalCount": len(signals[:150]),
        "sources": {
            "export": export,
            "botApi": bot,
            "telethon": telethon,
        },
        "error": "|".join(errors),
        "nextAction": (
            "Telegram 已接入并提取到钱包/交易员信号；进入强交易员排序。"
            if wallets or signals else
            "Telegram App 里能看到频道不等于系统能读取；需要导出频道历史、把 bot 拉进频道，或登录 Telethon user session。"
        ),
    }


def merge_leaderboard_rows(rows: list[dict[str, Any]], source: str, wallet_map: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        wallet = str(row.get("proxyWallet") or "").lower()
        if not WALLET_RE.fullmatch(wallet):
            continue
        bucket = wallet_map.setdefault(
            wallet,
            {
                "proxyWallet": wallet,
                "userName": row.get("userName") or row.get("name") or "",
                "xUsername": row.get("xUsername") or "",
                "verifiedBadge": bool(row.get("verifiedBadge")),
                "leaderboardSources": [],
                "leaderboard": {},
                "sourceKinds": set(),
            },
        )
        if row.get("userName") and not bucket.get("userName"):
            bucket["userName"] = row.get("userName")
        if row.get("xUsername") and not bucket.get("xUsername"):
            bucket["xUsername"] = row.get("xUsername")
        bucket["verifiedBadge"] = bool(bucket.get("verifiedBadge") or row.get("verifiedBadge"))
        bucket["leaderboardSources"].append(source)
        bucket["sourceKinds"].add("public_leaderboard")
        metric = bucket["leaderboard"].setdefault(source, {})
        metric.update(
            {
                "rank": safe_int(row.get("rank")),
                "pnl": round4(row.get("pnl")),
                "volume": round4(row.get("vol")),
            }
        )


def closed_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [safe_number(row.get("realizedPnl")) for row in rows]
    wins = sum(1 for value in pnls if value > 0)
    losses = sum(1 for value in pnls if value < 0)
    gross_win = sum(value for value in pnls if value > 0)
    gross_loss = sum(value for value in pnls if value < 0)
    closed = len(pnls)
    profit_factor = None
    if gross_loss < 0:
        profit_factor = gross_win / abs(gross_loss)
    elif gross_win > 0:
        profit_factor = 99.0
    latest_ts = max((safe_number(row.get("timestamp")) for row in rows), default=0.0)
    return {
        "closed": closed,
        "wins": wins,
        "losses": losses,
        "winRatePct": round((wins / closed) * 100.0, 2) if closed else None,
        "grossWin": round(gross_win, 4),
        "grossLoss": round(gross_loss, 4),
        "realizedPnl": round(sum(pnls), 4),
        "avgPnl": round(sum(pnls) / closed, 4) if closed else None,
        "profitFactor": round(profit_factor, 4) if profit_factor is not None else None,
        "latestClosedIso": epoch_to_iso(latest_ts),
    }


def latest_activity_ts(rows: list[dict[str, Any]]) -> float:
    return max((safe_number(row.get("timestamp")) for row in rows), default=0.0)


def month_metric(entry: dict[str, Any], field: str) -> float:
    for key in ("MONTH:OVERALL:PNL", "MONTH:SPORTS:PNL", "MONTH:POLITICS:PNL", "MONTH:CRYPTO:PNL"):
        metrics = entry.get("leaderboard", {}).get(key) or {}
        if field in metrics:
            return safe_number(metrics.get(field))
    best = 0.0
    for source, metrics in (entry.get("leaderboard") or {}).items():
        if str(source).startswith("MONTH:"):
            best = max(best, safe_number(metrics.get(field)))
    return best


def all_metric(entry: dict[str, Any], field: str) -> float:
    best = 0.0
    for source, metrics in (entry.get("leaderboard") or {}).items():
        if str(source).startswith("ALL:"):
            best = max(best, safe_number(metrics.get(field)))
    return best


def week_metric(entry: dict[str, Any], field: str) -> float:
    best = 0.0
    for source, metrics in (entry.get("leaderboard") or {}).items():
        if str(source).startswith("WEEK:"):
            best = max(best, safe_number(metrics.get(field)))
    return best


def recency_days(ts: float) -> float | None:
    if ts <= 0:
        return None
    return max(0.0, (time.time() - ts) / 86400.0)


def trader_score(entry: dict[str, Any], stats: dict[str, Any], positions: list[dict[str, Any]], activity: list[dict[str, Any]]) -> tuple[float, list[str], list[str]]:
    month_pnl = month_metric(entry, "pnl")
    week_pnl = week_metric(entry, "pnl")
    all_pnl = all_metric(entry, "pnl")
    month_vol = month_metric(entry, "volume")
    pf = safe_number(stats.get("profitFactor"))
    win_rate = safe_number(stats.get("winRatePct"))
    closed = safe_int(stats.get("closed"))
    latest_ts = max(latest_activity_ts(activity), max((safe_number(row.get("timestamp")) for row in positions), default=0.0))
    days = recency_days(latest_ts)
    score = 0.0
    score += min(25.0, math.log1p(max(month_pnl, 0.0)) / math.log1p(1_000_000.0) * 25.0)
    score += min(12.0, math.log1p(max(week_pnl, 0.0)) / math.log1p(250_000.0) * 12.0)
    score += min(12.0, math.log1p(max(all_pnl, 0.0)) / math.log1p(2_500_000.0) * 12.0)
    score += min(8.0, math.log1p(max(month_vol, 0.0)) / math.log1p(10_000_000.0) * 8.0)
    if pf:
        score += min(14.0, max(0.0, (pf - 1.0) * 9.0))
    if win_rate:
        score += min(10.0, max(0.0, (win_rate - 45.0) * 0.55))
    score += min(8.0, closed / 30.0 * 8.0)
    if days is not None:
        score += 8.0 if days <= 3 else 6.0 if days <= 7 else 3.0 if days <= 21 else 0.0
    if positions:
        score += 5.0
    if "telegram_channel" in entry.get("sourceKinds", set()):
        score += 4.0
    if entry.get("verifiedBadge"):
        score += 2.0

    blockers: list[str] = []
    warnings: list[str] = []
    if month_pnl <= 0 and week_pnl <= 0 and all_pnl <= 0:
        blockers.append("leaderboard_pnl_not_positive")
    if closed < 8:
        warnings.append("closed_sample_thin")
    if pf and pf < 1.05:
        warnings.append("recent_closed_pf_below_1_05")
    if days is None or days > 21:
        blockers.append("trader_activity_stale")
    if not positions:
        warnings.append("no_current_positions_to_shadow")
    recent_pnl = safe_number(stats.get("realizedPnl"))
    if closed >= 8 and recent_pnl < 0:
        warnings.append("recent_closed_pnl_negative")
        score -= 8.0
    return max(0.0, min(100.0, round(score, 2))), blockers, warnings


def compact_position(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "proxyWallet": str(row.get("proxyWallet") or "").lower(),
        "conditionId": row.get("conditionId", ""),
        "asset": row.get("asset", ""),
        "title": row.get("title", ""),
        "slug": row.get("slug", ""),
        "eventSlug": row.get("eventSlug", ""),
        "outcome": row.get("outcome", ""),
        "oppositeOutcome": row.get("oppositeOutcome", ""),
        "size": round4(row.get("size")),
        "avgPrice": round4(row.get("avgPrice")),
        "curPrice": round4(row.get("curPrice")),
        "initialValue": round4(row.get("initialValue")),
        "currentValue": round4(row.get("currentValue")),
        "cashPnl": round4(row.get("cashPnl")),
        "percentPnl": round4(row.get("percentPnl")),
        "endDate": row.get("endDate", ""),
        "url": f"https://polymarket.com/event/{urllib.parse.quote(str(row.get('eventSlug') or row.get('slug') or ''))}",
    }


def validation_signal(
    name: str,
    payload: dict[str, Any],
    path: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    merged = {**payload, **summary, **metrics}
    age_hours = validation_age_hours(payload)
    max_age = max(1.0, float(args.max_validation_age_hours))
    blockers: list[str] = []
    if not payload:
        blockers.append(f"{name}_missing")
    elif age_hours is None:
        blockers.append(f"{name}_timestamp_missing")
    elif age_hours > max_age:
        blockers.append(f"{name}_stale")

    explicit = first_bool(
        merged,
        (
            "validated",
            "passed",
            "pass",
            "walkForwardPassed",
            "shadowReplayPassed",
            "autoUnlockApproved",
            "realWalletGatePassed",
        ),
    )
    status_text = str(merged.get("status") or merged.get("decision") or "").upper()
    status_pass = any(token in status_text for token in ("PASS", "PASSED", "VALIDATED", "APPROVED", "OK_GREEN"))

    if name == "shadow_replay":
        samples = first_int(
            merged,
            ("trades", "tradeCount", "closedTrades", "samples", "outcomeSamples", "validatedCandidates", "rows"),
        )
        net_pnl = first_number(merged, ("netPnlUSDC", "netPnl", "shadowNetPnlUSDC", "totalPnlUSDC", "realizedPnl"))
        profit_factor = first_number(merged, ("profitFactor", "pf"), 0.0)
        metric_pass = (
            samples >= int(args.min_shadow_replay_trades)
            and net_pnl >= float(args.min_shadow_net_pnl_usdc)
            and profit_factor >= float(args.min_shadow_profit_factor)
        )
        if payload and samples < int(args.min_shadow_replay_trades):
            blockers.append("shadow_replay_samples_lt_min")
        if payload and net_pnl < float(args.min_shadow_net_pnl_usdc):
            blockers.append("shadow_replay_net_pnl_not_positive")
        if payload and profit_factor < float(args.min_shadow_profit_factor):
            blockers.append("shadow_replay_pf_lt_min")
        return {
            "name": name,
            "path": path,
            "present": bool(payload),
            "passed": bool(payload) and not blockers and (explicit is True or status_pass or metric_pass),
            "ageHours": round(age_hours, 2) if age_hours is not None else None,
            "samples": samples,
            "netPnlUSDC": round(net_pnl, 4),
            "profitFactor": round(profit_factor, 4),
            "blockers": blockers,
        }

    batches = first_int(merged, ("batches", "windows", "walkForwardBatches", "periods", "rows"))
    pass_rate = first_number(merged, ("passRatePct", "passedRatePct", "winRatePct", "successRatePct"), 0.0)
    net_pnl = first_number(merged, ("netPnlUSDC", "netPnl", "walkForwardNetPnlUSDC", "totalPnlUSDC", "realizedPnl"))
    metric_pass = (
        batches >= int(args.min_walk_forward_batches)
        and pass_rate >= float(args.min_walk_forward_pass_rate_pct)
        and net_pnl >= 0.0
    )
    if payload and batches < int(args.min_walk_forward_batches):
        blockers.append("walk_forward_batches_lt_min")
    if payload and pass_rate < float(args.min_walk_forward_pass_rate_pct):
        blockers.append("walk_forward_pass_rate_lt_min")
    if payload and net_pnl < 0.0:
        blockers.append("walk_forward_net_pnl_negative")
    return {
        "name": name,
        "path": path,
        "present": bool(payload),
        "passed": bool(payload) and not blockers and (explicit is True or status_pass or metric_pass),
        "ageHours": round(age_hours, 2) if age_hours is not None else None,
        "batches": batches,
        "passRatePct": round(pass_rate, 4),
        "netPnlUSDC": round(net_pnl, 4),
        "blockers": blockers,
    }


def wallet_runtime_preflight() -> dict[str, Any]:
    real_switch = env_bool("QG_POLYMARKET_REAL_EXECUTION")
    kill_switch_off = str(os.environ.get("QG_POLYMARKET_CANARY_KILL_SWITCH", "true")).strip().lower() == "false"
    adapter = os.environ.get("QG_POLYMARKET_WALLET_ADAPTER", "")
    checks = {
        "realExecutionSwitch": real_switch,
        "killSwitchOff": kill_switch_off,
        "walletAdapterIsolatedClob": adapter == "isolated_clob",
        "privateKeyConfigured": bool(os.environ.get("QG_POLYMARKET_PRIVATE_KEY")),
        "clobHostConfigured": bool(os.environ.get("QG_POLYMARKET_CLOB_HOST")),
        "neverEchoesSecretValues": True,
    }
    blockers = []
    if not checks["realExecutionSwitch"]:
        blockers.append("real_execution_switch_false")
    if not checks["killSwitchOff"]:
        blockers.append("wallet_kill_switch_on_or_unset")
    if not checks["walletAdapterIsolatedClob"]:
        blockers.append("wallet_adapter_not_isolated_clob")
    if not checks["privateKeyConfigured"]:
        blockers.append("private_key_env_missing")
    if not checks["clobHostConfigured"]:
        blockers.append("clob_host_env_missing")
    return {
        **checks,
        "passed": not blockers,
        "blockers": blockers,
    }


def wallet_risk_policy(
    args: argparse.Namespace,
    telegram_active: bool,
    validation: dict[str, Any],
) -> dict[str, Any]:
    requested = str_to_bool(args.real_wallet_enabled)
    auto_unlock = str_to_bool(args.real_wallet_auto_unlock)
    require_telegram = str_to_bool(args.real_wallet_require_telegram)
    runtime = wallet_runtime_preflight()
    shadow = validation.get("shadowReplay") if isinstance(validation.get("shadowReplay"), dict) else {}
    walk_forward = validation.get("walkForward") if isinstance(validation.get("walkForward"), dict) else {}
    blockers: list[str] = []
    if not requested:
        blockers.append("real_wallet_not_requested")
    if not auto_unlock:
        blockers.append("autonomous_unlock_disabled")
    if require_telegram and not telegram_active:
        blockers.append("telegram_source_not_active")
    if not shadow.get("passed"):
        blockers.append("shadow_replay_not_validated")
    if not walk_forward.get("passed"):
        blockers.append("walk_forward_not_validated")
    blockers.extend(str(item) for item in runtime.get("blockers") or [])
    execution_allowed = requested and auto_unlock and not blockers
    if execution_allowed:
        status = "AUTONOMOUS_REAL_WALLET_ALLOWED"
    elif requested:
        status = "AUTONOMOUS_REAL_WALLET_BLOCKED_BY_EVIDENCE_GATE"
    else:
        status = "CONFIGURED_DISABLED"
    return {
        "status": status,
        "realWalletRequested": requested,
        "autonomousUnlockAllowed": auto_unlock,
        "humanApprovalRequired": False,
        "operatorApprovalRequired": False,
        "manualReviewRequired": False,
        "autoUnlockMode": "EVIDENCE_GATED_NO_HUMAN_APPROVAL",
        "autoUnlockDecision": "ALLOW_REAL_WALLET" if execution_allowed else "BLOCK_REAL_WALLET",
        "realWalletExecutionAllowed": execution_allowed,
        "walletWriteAllowed": execution_allowed,
        "orderSendAllowed": execution_allowed,
        "takeProfitPct": round(args.real_wallet_take_profit_pct, 4),
        "stopLossPct": round(args.real_wallet_stop_loss_pct, 4),
        "trailingStopPct": round(args.real_wallet_trailing_stop_pct, 4),
        "maxPositionUSDC": round(args.real_wallet_max_position_usdc, 4),
        "maxDailyLossUSDC": round(args.real_wallet_max_daily_loss_usdc, 4),
        "maxOpenPositions": max(1, int(args.real_wallet_max_open_positions)),
        "minEntryPrice": round(args.real_wallet_min_entry_price, 4),
        "maxEntryPrice": round(args.real_wallet_max_entry_price, 4),
        "hardBlockers": blockers,
        "validation": validation,
        "runtimePreflight": runtime,
        "autoUnlockCriteria": [
            "Telegram 来源可读并能提取钱包/信号",
            f"shadow replay >= {int(args.min_shadow_replay_trades)} 笔且 PF >= {float(args.min_shadow_profit_factor):.2f} 且净 PnL > 0",
            f"walk-forward >= {int(args.min_walk_forward_batches)} 批且 pass rate >= {float(args.min_walk_forward_pass_rate_pct):.0f}%",
            "真实钱包 runtime 配置齐全、kill switch 关闭、isolated_clob adapter 可用",
            "每笔订单必须带 TP/SL、追踪止损、单笔上限、日亏损上限和最大持仓数",
        ],
        "nextAction": (
            "系统会自动判断是否放开真实钱包；满足全部硬门槛时不需要人工批准。"
            "当前若仍有 hardBlockers，则自动保持钱包隔离。"
        ),
    }


def candidate_risk_plan(position: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    entry = safe_number(position.get("curPrice"))
    tp_pct = safe_number(policy.get("takeProfitPct"), 35.0)
    sl_pct = safe_number(policy.get("stopLossPct"), 18.0)
    take_profit = min(0.99, entry * (1.0 + tp_pct / 100.0)) if entry > 0 else 0.0
    stop_loss = max(0.01, entry * (1.0 - sl_pct / 100.0)) if entry > 0 else 0.0
    entry_ok = (
        entry >= safe_number(policy.get("minEntryPrice"), 0.04)
        and entry <= safe_number(policy.get("maxEntryPrice"), 0.90)
    )
    blockers = list(policy.get("hardBlockers") or []) + ([] if entry_ok else ["entry_price_outside_policy_band"])
    real_wallet_eligible = bool(policy.get("realWalletExecutionAllowed")) and not blockers
    return {
        "mode": "AUTONOMOUS_BRACKET_EXIT_GATE",
        "entryReferencePrice": round(entry, 4),
        "takeProfitPct": policy.get("takeProfitPct"),
        "takeProfitPrice": round(take_profit, 4),
        "stopLossPct": policy.get("stopLossPct"),
        "stopLossPrice": round(stop_loss, 4),
        "trailingStopPct": policy.get("trailingStopPct"),
        "maxStakeUSDC": policy.get("maxPositionUSDC"),
        "maxDailyLossUSDC": policy.get("maxDailyLossUSDC"),
        "entryPriceAllowed": entry_ok,
        "realWalletEligibleNow": real_wallet_eligible,
        "walletWriteAllowed": real_wallet_eligible,
        "orderSendAllowed": real_wallet_eligible,
        "humanApprovalRequired": False,
        "blockers": blockers,
    }


def build_shadow_candidates(
    traders: list[dict[str, Any]],
    min_current_value: float,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for trader in traders:
        if not trader.get("eligibleForShadowCopy"):
            continue
        for position in trader.get("currentPositions") or []:
            current_value = safe_number(position.get("currentValue"))
            price = safe_number(position.get("curPrice"))
            if current_value < min_current_value:
                continue
            if price <= 0.02 or price >= 0.98:
                continue
            candidate_score = round(
                safe_number(trader.get("copyScore")) * 0.72
                + min(14.0, math.log1p(current_value) / math.log1p(250_000.0) * 14.0)
                + min(14.0, max(-8.0, safe_number(position.get("percentPnl")) * 0.18)),
                2,
            )
            risk_plan = candidate_risk_plan(position, policy)
            real_wallet_ready = bool(risk_plan.get("realWalletEligibleNow"))
            candidates.append(
                {
                    "generatedAtIso": utc_now_iso(),
                    "action": "AUTO_REAL_WALLET_CANDIDATE" if real_wallet_ready else "SHADOW_COPY_WATCH_ONLY",
                    "walletWriteAllowed": real_wallet_ready,
                    "orderSendAllowed": real_wallet_ready,
                    "humanApprovalRequired": False,
                    "source": "copy_trader_discovery",
                    "trader": trader.get("userName") or trader.get("proxyWallet"),
                    "proxyWallet": trader.get("proxyWallet"),
                    "copyScore": trader.get("copyScore"),
                    "candidateScore": candidate_score,
                    "marketTitle": position.get("title", ""),
                    "marketSlug": position.get("slug", ""),
                    "eventSlug": position.get("eventSlug", ""),
                    "conditionId": position.get("conditionId", ""),
                    "asset": position.get("asset", ""),
                    "outcome": position.get("outcome", ""),
                    "side": "COPY_LONG_OUTCOME",
                    "curPrice": position.get("curPrice"),
                    "avgPrice": position.get("avgPrice"),
                    "currentValue": position.get("currentValue"),
                    "traderCashPnl": position.get("cashPnl"),
                    "traderPercentPnl": position.get("percentPnl"),
                    "endDate": position.get("endDate", ""),
                    "url": position.get("url", ""),
                    "riskPlan": risk_plan,
                }
            )
    candidates.sort(key=lambda row: safe_number(row.get("candidateScore")), reverse=True)
    return candidates


def discover(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else runtime_dir
    categories = parse_csv(args.leaderboard_categories, ["OVERALL"])
    periods = parse_csv(args.leaderboard_periods, ["MONTH", "ALL", "WEEK"])
    wallet_map: dict[str, dict[str, Any]] = {}
    fetch_errors: list[dict[str, str]] = []
    leaderboard_rows = 0

    for period in periods:
        for category in categories:
            for order_by in ("PNL",):
                source = f"{period}:{category}:{order_by}"
                try:
                    payload, url = fetch_json(
                        "/v1/leaderboard",
                        {
                            "timePeriod": period,
                            "category": category,
                            "orderBy": order_by,
                            "limit": max(1, min(50, args.leaderboard_limit)),
                        },
                        args.request_timeout,
                    )
                    rows = as_rows(payload)
                    leaderboard_rows += len(rows)
                    merge_leaderboard_rows(rows, source, wallet_map)
                    for row in rows:
                        wallet = str(row.get("proxyWallet") or "").lower()
                        if wallet in wallet_map:
                            wallet_map[wallet].setdefault("sourceUrls", []).append(url)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                    fetch_errors.append({"source": source, "error": f"{type(exc).__name__}:{str(exc)[:180]}"})

    telegram = read_telegram_sources(args)
    telegram_signals = [item for item in (telegram.get("signals") or []) if isinstance(item, dict)]
    signals_by_user: dict[str, list[dict[str, Any]]] = {}
    signals_by_wallet: dict[str, list[dict[str, Any]]] = {}
    for signal in telegram_signals:
        user = str(signal.get("userName") or "").strip().lower()
        wallet = str(signal.get("wallet") or "").strip().lower()
        if user:
            signals_by_user.setdefault(user, []).append(signal)
        if wallet:
            signals_by_wallet.setdefault(wallet, []).append(signal)
    for wallet in telegram.get("wallets") or []:
        bucket = wallet_map.setdefault(
            wallet,
            {
                "proxyWallet": wallet,
                "userName": "",
                "xUsername": "",
                "verifiedBadge": False,
                "leaderboardSources": [],
                "leaderboard": {},
                "sourceKinds": set(),
            },
        )
        bucket["sourceKinds"].add("telegram_channel")
        bucket.setdefault("leaderboardSources", []).append("TELEGRAM_CHANNEL_WALLET")
        if wallet in signals_by_wallet:
            bucket.setdefault("telegramSignals", []).extend(signals_by_wallet[wallet][:10])

    for bucket in wallet_map.values():
        names = [
            str(bucket.get("userName") or "").strip().lower(),
            str(bucket.get("xUsername") or "").strip().lower(),
        ]
        matched_signals = [signal for name in names if name for signal in signals_by_user.get(name, [])]
        if not matched_signals:
            continue
        bucket["sourceKinds"].add("telegram_channel")
        bucket.setdefault("leaderboardSources", []).append("TELEGRAM_CHANNEL_TRADER_SIGNAL")
        bucket.setdefault("telegramSignals", []).extend(matched_signals[:10])

    preselected = sorted(
        wallet_map.values(),
        key=lambda item: (
            month_metric(item, "pnl"),
            all_metric(item, "pnl"),
            len(item.get("leaderboardSources") or []),
        ),
        reverse=True,
    )[: max(1, args.max_traders)]

    traders: list[dict[str, Any]] = []
    for entry in preselected:
        wallet = entry["proxyWallet"]
        errors: list[str] = []
        try:
            positions_payload, _ = fetch_json(
                "/positions",
                {
                    "user": wallet,
                    "limit": max(0, min(500, args.positions_limit)),
                    "sortBy": "CURRENT",
                    "sortDirection": "DESC",
                    "sizeThreshold": 1,
                },
                args.request_timeout,
            )
            positions = as_rows(positions_payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            positions = []
            errors.append(f"positions:{type(exc).__name__}:{str(exc)[:120]}")
        try:
            closed_payload, _ = fetch_json(
                "/closed-positions",
                {
                    "user": wallet,
                    "limit": max(0, min(50, args.closed_limit)),
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                },
                args.request_timeout,
            )
            closed = as_rows(closed_payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            closed = []
            errors.append(f"closed:{type(exc).__name__}:{str(exc)[:120]}")
        try:
            activity_payload, _ = fetch_json(
                "/activity",
                {
                    "user": wallet,
                    "limit": max(0, min(500, args.activity_limit)),
                    "type": "TRADE",
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                },
                args.request_timeout,
            )
            activity = as_rows(activity_payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            activity = []
            errors.append(f"activity:{type(exc).__name__}:{str(exc)[:120]}")

        stats = closed_stats(closed)
        score, blockers, warnings = trader_score(entry, stats, positions, activity)
        if safe_int(stats.get("closed")) >= args.min_closed_positions:
            if stats.get("profitFactor") is not None and safe_number(stats.get("profitFactor")) < 1.05:
                blockers.append("recent_closed_pf_below_1_05")
            if safe_number(stats.get("realizedPnl")) <= 0:
                blockers.append("recent_closed_pnl_not_positive")
        current_positions = [compact_position(row) for row in positions[:10]]
        latest_ts = max(
            latest_activity_ts(activity),
            max((safe_number(row.get("timestamp")) for row in closed), default=0.0),
        )
        eligible = (
            score >= args.min_shadow_score
            and not blockers
            and safe_int(stats.get("closed")) >= args.min_closed_positions
            and bool(current_positions)
        )
        traders.append(
            {
                "proxyWallet": wallet,
                "userName": entry.get("userName", ""),
                "xUsername": entry.get("xUsername", ""),
                "verifiedBadge": bool(entry.get("verifiedBadge")),
                "sourceKinds": sorted(str(x) for x in entry.get("sourceKinds", set())),
                "leaderboardSources": sorted(set(entry.get("leaderboardSources") or [])),
                "telegramSignalCount": len(entry.get("telegramSignals") or []),
                "telegramSignals": (entry.get("telegramSignals") or [])[:5],
                "leaderboard": entry.get("leaderboard") or {},
                "monthPnl": round4(month_metric(entry, "pnl")),
                "monthVolume": round4(month_metric(entry, "volume")),
                "weekPnl": round4(week_metric(entry, "pnl")),
                "allPnl": round4(all_metric(entry, "pnl")),
                "closedStats": stats,
                "copyScore": score,
                "eligibleForShadowCopy": eligible,
                "blockers": blockers,
                "warnings": warnings + errors,
                "currentPositionCount": len(current_positions),
                "currentPositionValue": round(sum(safe_number(row.get("currentValue")) for row in current_positions), 4),
                "latestActivityIso": epoch_to_iso(latest_ts),
                "currentPositions": current_positions,
            }
        )

    traders.sort(key=lambda row: safe_number(row.get("copyScore")), reverse=True)
    shadow_replay, shadow_replay_path = resolve_validation_payload(
        args.shadow_replay_path,
        "QuantGod_PolymarketCopyTraderShadowReplay.json",
        runtime_dir,
        dashboard_dir,
    )
    walk_forward, walk_forward_path = resolve_validation_payload(
        args.walk_forward_path,
        "QuantGod_PolymarketCopyTraderWalkForward.json",
        runtime_dir,
        dashboard_dir,
    )
    validation = {
        "shadowReplay": validation_signal("shadow_replay", shadow_replay, shadow_replay_path, args),
        "walkForward": validation_signal("walk_forward", walk_forward, walk_forward_path, args),
    }
    policy = wallet_risk_policy(args, bool(telegram.get("active")), validation)
    shadow_candidates = build_shadow_candidates(traders, args.min_current_value, policy)
    eligible_count = sum(1 for row in traders if row.get("eligibleForShadowCopy"))
    real_wallet_candidate_count = sum(1 for row in shadow_candidates if row.get("orderSendAllowed"))
    status = "OK" if traders else "UNAVAILABLE"
    if traders and not shadow_candidates:
        status = "OK_NO_SHADOW_CANDIDATES"

    return {
        "generatedAtIso": utc_now_iso(),
        "mode": "POLYMARKET_COPY_TRADER_DISCOVERY_READONLY",
        "status": status,
        "safety": {
            "readOnly": True,
            "placesOrders": False,
            "startsExecutor": False,
            "loadsWallet": False,
            "walletWriteAllowed": False,
            "orderSendAllowed": False,
            "walletPolicyAllowsExecution": policy.get("realWalletExecutionAllowed"),
            "humanApprovalRequired": False,
            "boundary": "public/authorized source discovery only; output is shadow-copy evidence, not execution",
        },
        "docs": DOCS,
        "copyTraderDiscovery": {
            "status": status,
            "active": bool(traders),
            "currentTraderDiscovery": bool(traders),
            "freshTraderRanking": bool(traders),
            "archiveReplayOnly": False,
        },
        "sourceStatus": {
            "publicLeaderboard": {
                "active": leaderboard_rows > 0,
                "rows": leaderboard_rows,
                "categories": categories,
                "periods": periods,
                "errors": fetch_errors[:12],
            },
            "telegramChannel": telegram,
        },
        "config": {
            "leaderboardLimit": args.leaderboard_limit,
            "maxTraders": args.max_traders,
            "positionsLimit": args.positions_limit,
            "closedLimit": args.closed_limit,
            "activityLimit": args.activity_limit,
            "minClosedPositions": args.min_closed_positions,
            "minCurrentValue": args.min_current_value,
            "minShadowScore": args.min_shadow_score,
            "realWalletAutoUnlock": args.real_wallet_auto_unlock,
            "realWalletRequireTelegram": args.real_wallet_require_telegram,
        },
        "walletRiskPolicy": policy,
        "summary": {
            "leaderboardRows": leaderboard_rows,
            "candidateWallets": len(wallet_map),
            "rankedTraders": len(traders),
            "eligibleTraders": eligible_count,
            "telegramWallets": safe_int(telegram.get("walletCount")),
            "telegramSignals": safe_int(telegram.get("signalCount")),
            "currentPositions": sum(safe_int(row.get("currentPositionCount")) for row in traders),
            "shadowCandidates": len(shadow_candidates),
            "topTrader": (traders[0].get("userName") or traders[0].get("proxyWallet")) if traders else "",
            "topScore": traders[0].get("copyScore") if traders else 0,
            "walletRiskPolicyStatus": policy.get("status"),
            "realWalletExecutionAllowed": policy.get("realWalletExecutionAllowed"),
            "humanApprovalRequired": False,
            "realWalletCandidates": real_wallet_candidate_count,
        },
        "traders": traders,
        "shadowCandidates": shadow_candidates[:100],
        "nextActions": [
            "把 shadowCandidates 写入跟单 replay/outcome ledger，验证跟随延迟、盘口深度和退出规则。",
            "Telegram 频道先作为只读钱包/信号来源；未接入前自动门控会阻断真实钱包。",
            "只有 copied-trader discovery + shadow replay + walk-forward + runtime preflight 全部为正，系统才会自动放开 micro-live。",
        ],
    }


def write_outputs(snapshot: dict[str, Any], targets: OutputTargets) -> None:
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    output_paths = [targets.runtime_dir / OUTPUT_NAME]
    if targets.dashboard_dir:
        output_paths.append(targets.dashboard_dir / OUTPUT_NAME)
    for path in output_paths:
        atomic_write_text(path, text)

    rows = []
    for trader in snapshot.get("traders") or []:
        stats = trader.get("closedStats") or {}
        rows.append(
            {
                "generatedAtIso": snapshot.get("generatedAtIso", ""),
                "proxyWallet": trader.get("proxyWallet", ""),
                "userName": trader.get("userName", ""),
                "copyScore": trader.get("copyScore", 0),
                "eligibleForShadowCopy": trader.get("eligibleForShadowCopy", False),
                "monthPnl": trader.get("monthPnl", 0),
                "weekPnl": trader.get("weekPnl", 0),
                "allPnl": trader.get("allPnl", 0),
                "closed": stats.get("closed", 0),
                "winRatePct": stats.get("winRatePct", ""),
                "profitFactor": stats.get("profitFactor", ""),
                "recentRealizedPnl": stats.get("realizedPnl", 0),
                "currentPositionCount": trader.get("currentPositionCount", 0),
                "currentPositionValue": trader.get("currentPositionValue", 0),
                "telegramSignalCount": trader.get("telegramSignalCount", 0),
                "latestActivityIso": trader.get("latestActivityIso", ""),
                "blockers": "|".join(trader.get("blockers") or []),
                "warnings": "|".join(trader.get("warnings") or []),
            }
        )
    fieldnames = [
        "generatedAtIso",
        "proxyWallet",
        "userName",
        "copyScore",
        "eligibleForShadowCopy",
        "monthPnl",
        "weekPnl",
        "allPnl",
        "closed",
        "winRatePct",
        "profitFactor",
        "recentRealizedPnl",
        "currentPositionCount",
        "currentPositionValue",
        "telegramSignalCount",
        "latestActivityIso",
        "blockers",
        "warnings",
    ]
    for path in [targets.runtime_dir / LEDGER_NAME] + ([targets.dashboard_dir / LEDGER_NAME] if targets.dashboard_dir else []):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    args = parse_args()
    snapshot = discover(args)
    write_outputs(
        snapshot,
        OutputTargets(
            runtime_dir=Path(args.runtime_dir),
            dashboard_dir=Path(args.dashboard_dir) if args.dashboard_dir else None,
        ),
    )
    summary = snapshot.get("summary") or {}
    print(
        f"{OUTPUT_NAME}: {snapshot.get('status')} | "
        f"ranked={summary.get('rankedTraders', 0)} | "
        f"eligible={summary.get('eligibleTraders', 0)} | "
        f"shadowCandidates={summary.get('shadowCandidates', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
