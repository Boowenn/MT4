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
ISOLATED_CLOB_RUNTIME_NAME = "QuantGod_PolymarketIsolatedClobRuntime.json"
DATA_API_BASE = "https://data-api.polymarket.com"
DEFAULT_TELEGRAM_CHANNELS = ["预测市场内幕钱包监控", "AI 1000x Polymarket"]
WALLET_RE = re.compile(r"0x[a-fA-F0-9]{40}")
TELEGRAM_TRADER_RE = re.compile(
    r"(?P<user>[A-Za-z0-9_.-]{2,80})\s*\|\s*Rank\s*#(?P<rank>\d+)\s*\|\s*(?P<wallet>0x[a-fA-F0-9]{4,}(?:\.\.\.)?[a-fA-F0-9]{4,})",
    re.IGNORECASE,
)
SIGNAL_SIDE_RE = re.compile(r"\b(?P<side>BUY|SELL)\s+(?P<outcome>[A-Za-z][A-Za-z0-9_ ./'-]{0,60})", re.IGNORECASE)
MARKET_FAMILY_RULES = (
    ("crypto", re.compile(r"\b(bitcoin|btc|ethereum|eth|solana|sol\b|xrp|doge|crypto|token)\b", re.IGNORECASE)),
    (
        "sports",
        re.compile(
            r"\b(nba|nfl|nhl|mlb|ufc|fifa|soccer|football|tennis|serie|lazio|premier|champions|game|match)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "politics",
        re.compile(r"\b(trump|biden|election|senate|congress|president|mayor|governor|poll)\b", re.IGNORECASE),
    ),
    ("macro", re.compile(r"\b(fed|rate|inflation|cpi|gdp|unemployment|recession|tariff)\b", re.IGNORECASE)),
    (
        "geopolitics",
        re.compile(
            r"\b(israel|hezbollah|iran|russia|ukraine|china|gaza|war|ceasefire|peace|deal|nuclear)\b",
            re.IGNORECASE,
        ),
    ),
    ("culture", re.compile(r"\b(oscar|grammy|movie|album|song|tiktok|youtube|streamer)\b", re.IGNORECASE)),
    (
        "company",
        re.compile(r"\b(tesla|apple|nvidia|openai|xai|meta|google|microsoft|spacex|stock)\b", re.IGNORECASE),
    ),
)
ENTRY_PRICE_BANDS = (
    (0.04, "lt_0.04"),
    (0.20, "0.04_0.20"),
    (0.40, "0.20_0.40"),
    (0.60, "0.40_0.60"),
    (0.80, "0.60_0.80"),
    (0.90, "0.80_0.90"),
)
KREO_MARKET_SLUG_RE = re.compile(r"\bhttps?://t\.me/KreoPolyBot\?start=slug_([A-Za-z0-9_.~%/-]+)", re.IGNORECASE)
KREO_COPYTRADE_RE = re.compile(r"\bhttps?://t\.me/KreoPolyBot\?start=ct_([A-Za-z0-9_.~%/-]+)", re.IGNORECASE)
POLYMARKET_EVENT_URL_RE = re.compile(r"\bhttps?://(?:www\.)?polymarket\.com/event/([^\s]+)", re.IGNORECASE)
AI1000X_MARKET_RE = re.compile(r"📍\s*(?P<title>.+?)\s*(?:🎯\s*)?动作[:：]", re.IGNORECASE)
AI1000X_ACTION_RE = re.compile(
    r"(?:🎯\s*)?动作[:：]\s*(?P<verb>买入|卖出|BUY|SELL)\s+(?P<outcome>[^├└\n]+)",
    re.IGNORECASE,
)
AI1000X_NAME_RE = re.compile(r"名称[:：]\s*(?P<name>.+?)\s*(?:├|└|Smart Score|回测|胜率|📋|⚠️|$)")
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
    parser.add_argument("--telegram-signal-limit", type=int, default=300)
    parser.add_argument("--telegram-channel-name", default=",".join(DEFAULT_TELEGRAM_CHANNELS))
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
    parser.add_argument("--real-wallet-take-profit-pct", type=float, default=2.0)
    parser.add_argument("--real-wallet-take-profit-usdc", type=float, default=0.05)
    parser.add_argument("--real-wallet-stop-loss-pct", type=float, default=4.0)
    parser.add_argument("--real-wallet-trailing-stop-pct", type=float, default=2.0)
    parser.add_argument("--real-wallet-max-position-usdc", type=float, default=5.0)
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


def market_family(*parts: Any) -> str:
    text = " ".join(str(part or "") for part in parts if part is not None)
    for family, pattern in MARKET_FAMILY_RULES:
        if pattern.search(text):
            return family
    return "other"


def entry_price_band(value: Any) -> str:
    price = safe_number(value, -1.0)
    if price < 0:
        return "unknown"
    for limit, label in ENTRY_PRICE_BANDS:
        if price < limit:
            return label
    return "gt_0.90"


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
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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


def parse_telegram_channels(value: Any, fallback: list[str] | None = None) -> list[str]:
    fallback_channels = list(fallback or DEFAULT_TELEGRAM_CHANNELS)
    raw_parts: list[str] = []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            raw_parts.extend(re.split(r"[,;|\n，、]+", str(item or "")))
    else:
        raw_parts = re.split(r"[,;|\n，、]+", str(value or ""))
    channels: list[str] = []
    for part in raw_parts:
        cleaned = " ".join(str(part or "").strip().split())
        if cleaned and cleaned not in channels:
            channels.append(cleaned)
    return channels or fallback_channels


def normalize_channel_title(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def channel_title_matches(title: Any, channel_names: list[str]) -> bool:
    title_norm = normalize_channel_title(title)
    if not title_norm:
        return False
    for channel_name in channel_names:
        channel_norm = normalize_channel_title(channel_name)
        if channel_norm and (channel_norm in title_norm or title_norm in channel_norm):
            return True
    return False


def matching_channel_label(title: Any, channel_names: list[str]) -> str:
    title_text = " ".join(str(title or "").strip().split())
    if title_text and channel_title_matches(title_text, channel_names):
        return title_text
    return title_text or (channel_names[0] if channel_names else "")


def read_telegram_wallets(path_text: str, channel_names: list[str]) -> dict[str, Any]:
    path_text = path_text.strip()
    primary_channel = channel_names[0] if channel_names else ""
    result = {
        "channelName": primary_channel,
        "channelNames": channel_names,
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
        signals.extend(extract_telegram_signals([text], "telegram_export", primary_channel))
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
        return float(match.group(1).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def normalize_kreo_market_slug(value: str) -> str:
    raw = urllib.parse.unquote(str(value or "").strip())
    if raw.startswith("predictmon--"):
        raw = raw[len("predictmon--") :]
    return raw.strip().strip("/")


def extract_kreo_context(text: str) -> dict[str, Any]:
    market_slugs: list[str] = []
    market_urls: list[str] = []
    for match in KREO_MARKET_SLUG_RE.finditer(text):
        raw_slug = urllib.parse.unquote(match.group(1))
        market_slug = normalize_kreo_market_slug(raw_slug)
        if market_slug and market_slug not in market_slugs:
            market_slugs.append(market_slug)
        url = match.group(0)
        if url not in market_urls:
            market_urls.append(url)
    copy_urls = []
    for match in KREO_COPYTRADE_RE.finditer(text):
        url = match.group(0)
        if url not in copy_urls:
            copy_urls.append(url)
    polymarket_urls: list[str] = []
    for match in POLYMARKET_EVENT_URL_RE.finditer(text):
        raw_path = match.group(1).split("?", 1)[0].strip("/")
        segments = [urllib.parse.unquote(segment) for segment in raw_path.split("/") if segment]
        if segments:
            market_slug = normalize_kreo_market_slug(segments[-1])
            if market_slug and market_slug not in market_slugs:
                market_slugs.append(market_slug)
        url = match.group(0)
        if url not in polymarket_urls:
            polymarket_urls.append(url)
    context: dict[str, Any] = {}
    if market_slugs:
        context["marketSlug"] = market_slugs[0]
        context["marketSlugs"] = market_slugs[:5]
    if market_urls:
        context["kreoTradeUrl"] = market_urls[0]
    if copy_urls:
        context["kreoCopytradeUrl"] = copy_urls[0]
    if polymarket_urls:
        context["polymarketMarketUrl"] = polymarket_urls[0]
    return context


def extract_ai1000x_signal(text: str, source: str, channel_name: str, extra: dict[str, Any]) -> dict[str, Any] | None:
    action = AI1000X_ACTION_RE.search(text)
    wallet = re.search(r"钱包[:：]\s*(0x[a-fA-F0-9]{40})", text, re.IGNORECASE)
    if not action or not wallet:
        return None
    verb = action.group("verb").strip().upper()
    side = "BUY" if verb in {"买入", "BUY"} else "SELL" if verb in {"卖出", "SELL"} else ""
    market_match = AI1000X_MARKET_RE.search(text)
    market_title = " ".join((market_match.group("title") if market_match else "").split())
    name_match = AI1000X_NAME_RE.search(text)
    user_name = " ".join((name_match.group("name") if name_match else "").split())
    wallet_value = wallet.group(1).lower()
    if not user_name:
        user_name = wallet_value[:10]
    price = first_regex_number(r"信号价[:：]\s*([+$0-9,.]+)", text)
    price_cents = None
    if price is not None:
        price_cents = round4(price * 100.0 if price <= 1.0 else price)
    amount = first_regex_number(r"金额[:：]\s*([+$0-9,.]+)", text)
    smart_score = first_regex_number(r"Smart Score[:：]\s*([0-9.]+)", text)
    backtest_pnl = first_regex_number(r"回测\s*PnL[:：]\s*([+\-$0-9,.]+)", text)
    win_rate = first_regex_number(r"胜率[:：]\s*([0-9.]+)%", text)
    signal = {
        "source": source,
        "channelName": channel_name,
        "userName": user_name[:100],
        "rank": 0,
        "wallet": wallet_value,
        "walletPreview": "",
        "side": side,
        "outcome": " ".join(action.group("outcome").split())[:80],
        "amountUSDC": round4(amount) if amount is not None else None,
        "priceCents": price_cents,
        "textPreview": text[:360],
        "marketTitle": market_title[:180],
        "smartScore": round4(smart_score) if smart_score is not None else None,
        "backtestPnlUSDC": round4(backtest_pnl) if backtest_pnl is not None else None,
        "winRatePct": round4(win_rate) if win_rate is not None else None,
    }
    signal.update(extract_kreo_context(text))
    if market_title and "marketSlug" not in signal:
        signal["marketTitle"] = market_title[:180]
    if extra:
        signal.update(extra)
    return signal


def extract_telegram_signals(
    fragments: list[str],
    source: str,
    channel_name: str,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    base_extra = dict(extra or {})
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
            signal = {
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
            if base_extra:
                signal.update(base_extra)
            signals.append(signal)
        ai_signal = extract_ai1000x_signal(text, source, channel_name, base_extra)
        if ai_signal:
            key = (
                "ai1000x",
                str(ai_signal.get("messageId") or ""),
                str(ai_signal.get("wallet") or ""),
                str(ai_signal.get("marketSlug") or ai_signal.get("marketTitle") or ""),
                str(ai_signal.get("side") or ""),
                str(ai_signal.get("outcome") or ""),
            )
            if key not in seen:
                seen.add(key)
                signals.append(ai_signal)
    return signals[:100]


def resolve_signal_wallet_previews(signals: list[dict[str, Any]], wallets: list[str]) -> list[dict[str, Any]]:
    full_wallets = [str(wallet or "").strip().lower() for wallet in wallets if WALLET_RE.fullmatch(str(wallet or ""))]
    resolved: list[dict[str, Any]] = []
    for signal in signals:
        row = dict(signal)
        if row.get("wallet"):
            resolved.append(row)
            continue
        preview = str(row.get("walletPreview") or "").strip()
        match = re.match(r"^(0x[a-fA-F0-9]{4,})\.\.\.([a-fA-F0-9]{4,})$", preview)
        if not match:
            resolved.append(row)
            continue
        prefix = match.group(1).lower()
        suffix = match.group(2).lower()
        matches = [wallet for wallet in full_wallets if wallet.startswith(prefix) and wallet.endswith(suffix)]
        if len(matches) == 1:
            row["wallet"] = matches[0]
        resolved.append(row)
    return resolved


def read_telegram_bot_updates(env_path: str, channel_names: list[str], limit: int, timeout: float) -> dict[str, Any]:
    values = read_env_values(env_path)
    token = values.get("QG_TELEGRAM_BOT_TOKEN") or values.get("TELEGRAM_BOT_TOKEN") or ""
    result = {
        "configured": bool(token),
        "mode": "telegram_bot_api_readonly",
        "active": False,
        "envPath": env_path,
        "channelName": channel_names[0] if channel_names else "",
        "channelNames": channel_names,
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
        if channel_names and title and not channel_title_matches(title, channel_names):
            continue
        channel_label = matching_channel_label(title, channel_names)
        matched += 1
        wallets.update(item.lower() for item in WALLET_RE.findall(text))
        signals.extend(extract_telegram_signals(fragments, "telegram_bot_api", channel_label))
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
    channel_names: list[str],
    limit: int,
    signal_limit: int,
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
        or ",".join(channel_names)
    )
    entity_hints = parse_telegram_channels(entity_hint, channel_names)
    channel_names = parse_telegram_channels([*channel_names, *entity_hints], channel_names)
    result = {
        "configured": bool(api_id and api_hash),
        "mode": "telegram_telethon_user_session_readonly",
        "active": False,
        "envPath": env_path,
        "sessionPath": session,
        "entityHint": entity_hint,
        "entityHints": entity_hints,
        "channelName": channel_names[0] if channel_names else "",
        "channelNames": channel_names,
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
        matched_entities: list[tuple[Any, str]] = []
        seen_entities: set[str] = set()
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

            def entity_key(entity: Any) -> str:
                for attr in ("id", "channel_id", "user_id"):
                    value = getattr(entity, attr, None)
                    if value is not None:
                        return f"{attr}:{value}"
                return repr(entity)

            def add_entity(entity: Any, title_hint: str) -> None:
                key = entity_key(entity)
                if key in seen_entities:
                    return
                seen_entities.add(key)
                title = str(getattr(entity, "title", "") or getattr(entity, "username", "") or title_hint)
                matched_entities.append((entity, title))
                if title:
                    matched_dialogs.append(title)

            for hint in entity_hints:
                try:
                    add_entity(await client.get_entity(hint), hint)
                except Exception:
                    continue
            async for dialog in client.iter_dialogs(limit=500):
                title = str(getattr(dialog, "name", "") or "")
                if channel_title_matches(title, entity_hints) or channel_title_matches(title, channel_names):
                    add_entity(dialog.entity, title)
            if not matched_entities:
                return {
                    "ok": False,
                    "error": "telethon_channel_not_found",
                    "wallets": [],
                    "signals": [],
                    "messagesRead": 0,
                    "matchedDialogs": matched_dialogs,
                    "signalPreviews": [],
                }
            messages_read = 0
            signals: list[dict[str, Any]] = []
            per_entity_limit = max(1, min(2000, int(limit)))
            for entity, title in matched_entities:
                channel_label = matching_channel_label(title, channel_names)
                async for message in client.iter_messages(entity, limit=per_entity_limit):
                    messages_read += 1
                    text = str(getattr(message, "raw_text", "") or "")
                    fragments = [text]
                    button_fragments: list[str] = []
                    try:
                        for row in getattr(message, "buttons", None) or []:
                            for button in row or []:
                                label = str(getattr(button, "text", "") or "")
                                url = str(getattr(button, "url", "") or "")
                                if label:
                                    button_fragments.append(label)
                                if url:
                                    button_fragments.append(url)
                    except Exception:
                        button_fragments = []
                    fragments.extend(button_fragments)
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
                    signal_context = extract_kreo_context(joined)
                    signal_context.update(
                        {
                            "channelName": channel_label,
                            "messageId": getattr(message, "id", None),
                            "messageDate": str(getattr(message, "date", "") or ""),
                        }
                    )
                    signals.extend(extract_telegram_signals(fragments, "telegram_telethon", channel_label, signal_context))
                    if found or "polymarket" in joined.lower() or "wallet" in joined.lower() or "钱包" in joined:
                        previews.append(
                            {
                                "channelName": channel_label,
                                "messageId": getattr(message, "id", None),
                                "date": str(getattr(message, "date", "") or ""),
                                "wallets": sorted(set(found))[:10],
                                "marketSlug": signal_context.get("marketSlug") or "",
                                "textPreview": " ".join(joined.split())[:260],
                            }
                        )
            return {
                "ok": True,
                "error": "",
                "wallets": sorted(wallets),
                "signals": signals[: max(1, min(1000, int(signal_limit)))],
                "messagesRead": messages_read,
                "matchedDialogs": sorted(set(matched_dialogs)),
                "signalPreviews": previews[:20],
            }
        finally:
            await client.disconnect()

    try:
        collected = asyncio.run(
            asyncio.wait_for(collect(), timeout=max(5.0, float(timeout) * max(2.0, len(channel_names) * 2.0)))
        )
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
    channel_names = parse_telegram_channels(args.telegram_channel_name)
    export = read_telegram_wallets(args.telegram_export, channel_names)
    bot = read_telegram_bot_updates(
        args.telegram_bot_env,
        channel_names,
        args.telegram_bot_updates_limit,
        args.request_timeout,
    )
    telethon_env = args.telegram_telethon_env or args.telegram_bot_env
    telethon = read_telegram_telethon_history(
        telethon_env,
        args.telegram_telethon_session,
        channel_names,
        args.telegram_telethon_limit,
        args.telegram_signal_limit,
        args.request_timeout,
    )
    sources = (export, bot, telethon)
    wallets = sorted(set(str(item).lower() for source in sources for item in (source.get("wallets") or [])))
    signal_limit = max(1, min(1000, int(args.telegram_signal_limit)))
    signals = [signal for source in sources for signal in (source.get("signals") or []) if isinstance(signal, dict)]
    signals = resolve_signal_wallet_previews(signals, wallets)
    wallets = sorted(set(wallets) | {str(signal.get("wallet") or "").lower() for signal in signals if signal.get("wallet")})
    all_channel_names = parse_telegram_channels(
        [
            *channel_names,
            *(telethon.get("channelNames") or []),
            *(telethon.get("matchedDialogs") or []),
        ],
        channel_names,
    )
    configured = bool(export.get("configured") or bot.get("configured") or telethon.get("configured"))
    errors = [str(item.get("error")) for item in sources if item.get("error")]
    return {
        "channelName": all_channel_names[0] if all_channel_names else "",
        "channelNames": all_channel_names,
        "configured": configured,
        "mode": "telegram_export_bot_or_telethon_readonly",
        "active": bool(wallets or signals),
        "wallets": wallets,
        "walletCount": len(wallets),
        "signals": signals[:signal_limit],
        "signalCount": len(signals[:signal_limit]),
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
    recent_pnl = safe_number(stats.get("realizedPnl"))
    telegram_sourced = "telegram_channel" in entry.get("sourceKinds", set())
    latest_ts = max(latest_activity_ts(activity), max((safe_number(row.get("timestamp")) for row in positions), default=0.0))
    days = recency_days(latest_ts)
    score = 0.0
    score += min(25.0, math.log1p(max(month_pnl, 0.0)) / math.log1p(1_000_000.0) * 25.0)
    score += min(12.0, math.log1p(max(week_pnl, 0.0)) / math.log1p(250_000.0) * 12.0)
    score += min(12.0, math.log1p(max(all_pnl, 0.0)) / math.log1p(2_500_000.0) * 12.0)
    score += min(8.0, math.log1p(max(month_vol, 0.0)) / math.log1p(10_000_000.0) * 8.0)
    score += min(12.0, math.log1p(max(recent_pnl, 0.0)) / math.log1p(25_000.0) * 12.0)
    if pf:
        score += min(14.0, max(0.0, (pf - 1.0) * 9.0))
    if win_rate:
        score += min(10.0, max(0.0, (win_rate - 45.0) * 0.55))
    score += min(8.0, closed / 30.0 * 8.0)
    if days is not None:
        score += 8.0 if days <= 3 else 6.0 if days <= 7 else 3.0 if days <= 21 else 0.0
    if positions:
        score += 5.0
    if telegram_sourced:
        score += 4.0
    if entry.get("verifiedBadge"):
        score += 2.0

    blockers: list[str] = []
    warnings: list[str] = []
    if month_pnl <= 0 and week_pnl <= 0 and all_pnl <= 0 and not (telegram_sourced and recent_pnl > 0):
        blockers.append("leaderboard_pnl_not_positive")
    if closed < 8:
        warnings.append("closed_sample_thin")
    if pf and pf < 1.05:
        warnings.append("recent_closed_pf_below_1_05")
    if days is None or days > 21:
        blockers.append("trader_activity_stale")
    if not positions:
        warnings.append("no_current_positions_to_shadow")
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


def resolve_isolated_clob_runtime(runtime_dir: Path, dashboard_dir: Path) -> tuple[dict[str, Any], str]:
    explicit = os.environ.get("QG_POLYMARKET_ISOLATED_CLOB_STATUS_PATH", "")
    candidates: list[Path] = []
    if explicit.strip():
        candidates.append(Path(explicit).expanduser())
    isolated_root = os.environ.get("QG_POLYMARKET_ISOLATED_CLOB_ROOT", "")
    if isolated_root.strip():
        candidates.append(Path(isolated_root).expanduser() / ISOLATED_CLOB_RUNTIME_NAME)
    candidates.extend([
        runtime_dir / ISOLATED_CLOB_RUNTIME_NAME,
        dashboard_dir / ISOLATED_CLOB_RUNTIME_NAME,
    ])
    for path in candidates:
        payload = read_optional_json(path)
        if payload:
            return payload, str(path)
    return {}, str(candidates[0]) if candidates else ""


def wallet_runtime_preflight(runtime_dir: Path, dashboard_dir: Path) -> dict[str, Any]:
    real_switch = env_bool("QG_POLYMARKET_REAL_EXECUTION")
    kill_switch_off = str(os.environ.get("QG_POLYMARKET_CANARY_KILL_SWITCH", "true")).strip().lower() == "false"
    adapter = os.environ.get("QG_POLYMARKET_WALLET_ADAPTER", "")
    isolated_runtime, isolated_runtime_path = resolve_isolated_clob_runtime(runtime_dir, dashboard_dir)
    isolated_adapter = isolated_runtime.get("adapter") if isinstance(isolated_runtime.get("adapter"), dict) else {}
    isolated_clob = isolated_runtime.get("clob") if isinstance(isolated_runtime.get("clob"), dict) else {}
    isolated_prepared = bool(isolated_runtime.get("runtimePrepared"))
    isolated_adapter_ok = isolated_adapter.get("name") == "isolated_clob" and bool(isolated_adapter.get("configured"))
    isolated_host_ok = bool(isolated_clob.get("hostConfigured"))
    checks = {
        "realExecutionSwitch": real_switch,
        "killSwitchOff": kill_switch_off,
        "walletAdapterIsolatedClob": adapter == "isolated_clob" or (isolated_prepared and isolated_adapter_ok),
        "privateKeyConfigured": bool(os.environ.get("QG_POLYMARKET_PRIVATE_KEY")),
        "clobHostConfigured": bool(os.environ.get("QG_POLYMARKET_CLOB_HOST")) or (isolated_prepared and isolated_host_ok),
        "isolatedRuntimePrepared": isolated_prepared,
        "isolatedRuntimeStatus": isolated_runtime.get("status", "") if isolated_runtime else "",
        "isolatedRuntimePath": isolated_runtime_path,
        "isolatedRuntimeRoot": isolated_runtime.get("isolatedRoot", "") if isolated_runtime else "",
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
    quality_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested = str_to_bool(args.real_wallet_enabled)
    auto_unlock = str_to_bool(args.real_wallet_auto_unlock)
    require_telegram = str_to_bool(args.real_wallet_require_telegram)
    runtime = wallet_runtime_preflight(Path(args.runtime_dir), Path(args.dashboard_dir) if args.dashboard_dir else Path(args.runtime_dir))
    shadow = validation.get("shadowReplay") if isinstance(validation.get("shadowReplay"), dict) else {}
    walk_forward = validation.get("walkForward") if isinstance(validation.get("walkForward"), dict) else {}
    gate = quality_gate or {}
    runtime_blockers = [str(item) for item in runtime.get("blockers") or []]
    blockers: list[str] = []
    if not requested:
        blockers.append("real_wallet_not_requested")
    if not auto_unlock:
        blockers.append("autonomous_unlock_disabled")
    if require_telegram and not telegram_active:
        blockers.append("telegram_source_not_active")

    global_evidence_blockers: list[str] = []
    if not shadow.get("passed"):
        global_evidence_blockers.append("shadow_replay_not_validated")
    if not walk_forward.get("passed"):
        global_evidence_blockers.append("walk_forward_not_validated")

    promoted_sources = [str(item) for item in gate.get("promotedSources") or [] if str(item)]
    promoted_source_traders = [str(item) for item in gate.get("promotedSourceTraders") or [] if str(item)]
    promoted_micro_buckets = safe_int(gate.get("promotedCompositeBucketCount"))
    weak_sources = [str(item) for item in gate.get("weakSources") or [] if str(item)]
    source_scoped_source_traders = [
        key
        for key in promoted_source_traders
        if any(key.startswith(f"{source}:") for source in promoted_sources)
        and not any(key.startswith(f"{source}:") for source in weak_sources)
    ]
    source_scoped_gate_passed = bool(
        gate.get("active")
        and promoted_sources
        and promoted_micro_buckets > 0
    )
    global_gate_passed = not global_evidence_blockers
    if not (global_gate_passed or source_scoped_gate_passed):
        blockers.extend(global_evidence_blockers)
    blockers.extend(runtime_blockers)

    evidence_gate_passed = requested and auto_unlock and (not require_telegram or telegram_active) and (
        global_gate_passed or source_scoped_gate_passed
    )
    execution_allowed = evidence_gate_passed and not runtime_blockers
    if execution_allowed and source_scoped_gate_passed and not global_gate_passed:
        status = "AUTONOMOUS_SOURCE_SCOPED_MICRO_LIVE_ALLOWED"
    elif execution_allowed:
        status = "AUTONOMOUS_REAL_WALLET_ALLOWED"
    elif requested and evidence_gate_passed:
        status = "AUTONOMOUS_SOURCE_SCOPED_MICRO_LIVE_BLOCKED_BY_RUNTIME"
    elif requested:
        status = "AUTONOMOUS_REAL_WALLET_BLOCKED_BY_EVIDENCE_GATE"
    else:
        status = "CONFIGURED_DISABLED"
    warnings: list[str] = []
    if source_scoped_gate_passed and not global_gate_passed:
        if not shadow.get("passed"):
            warnings.append("global_shadow_replay_not_validated_but_source_scope_promoted")
        if not walk_forward.get("passed"):
            warnings.append("global_walk_forward_not_validated_but_source_scope_promoted")
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
        "strategyEvidenceGatePassed": evidence_gate_passed,
        "globalEvidenceGatePassed": global_gate_passed,
        "sourceScopedMicroLiveGatePassed": source_scoped_gate_passed,
        "sourceScopedMicroLiveGate": {
            "active": source_scoped_gate_passed,
            "mode": "PROMOTED_SOURCE_AND_PROMOTED_TRADER_MICRO_BUCKET",
            "promotedSources": promoted_sources,
            "promotedSourceTraders": source_scoped_source_traders,
            "weakSources": weak_sources,
            "promotedCompositeBucketCount": promoted_micro_buckets,
            "requiresSignalPositionMatch": True,
            "ignoresQuarantinedSources": True,
        },
        "takeProfitPct": round(args.real_wallet_take_profit_pct, 4),
        "takeProfitUSDC": round(args.real_wallet_take_profit_usdc, 4),
        "stopLossPct": round(args.real_wallet_stop_loss_pct, 4),
        "trailingStopPct": round(args.real_wallet_trailing_stop_pct, 4),
        "maxPositionUSDC": round(args.real_wallet_max_position_usdc, 4),
        "maxDailyLossUSDC": round(args.real_wallet_max_daily_loss_usdc, 4),
        "maxOpenPositions": max(1, int(args.real_wallet_max_open_positions)),
        "minEntryPrice": round(args.real_wallet_min_entry_price, 4),
        "maxEntryPrice": round(args.real_wallet_max_entry_price, 4),
        "hardBlockers": blockers,
        "evidenceBlockers": [] if global_gate_passed or source_scoped_gate_passed else global_evidence_blockers,
        "runtimeBlockers": runtime_blockers,
        "warnings": warnings,
        "validation": validation,
        "runtimePreflight": runtime,
        "autoUnlockCriteria": [
            "Telegram 来源可读并能提取钱包/信号",
            f"全局 shadow replay >= {int(args.min_shadow_replay_trades)} 笔且 PF >= {float(args.min_shadow_profit_factor):.2f} 且净 PnL > 0，或单一来源桶已晋级且有晋级交易员/盘口微桶",
            f"全局 walk-forward >= {int(args.min_walk_forward_batches)} 批且 pass rate >= {float(args.min_walk_forward_pass_rate_pct):.0f}%，或启用来源/交易员桶独立 micro-live",
            "真实钱包 runtime 配置齐全、kill switch 关闭、isolated_clob adapter 可用",
            "每笔订单必须带 TP/SL、追踪止损、单笔上限、日亏损上限和最大持仓数",
        ],
        "nextAction": (
            "系统会自动判断是否放开真实钱包；全局通过时可整体 micro-live，"
            "来源桶通过时只允许该来源且匹配晋级交易员/盘口桶的逐笔候选。"
        ),
    }


def bucket_rows_by_key(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("bucketKey") or "").strip().lower(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("bucketKey") or "").strip()
    }


def normalized_bucket_set(payload: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in payload.get(key) or [] if str(item).strip()}


def source_key_from_signal(signal: dict[str, Any]) -> str:
    signal_source = str(signal.get("source") or "telegram_channel").strip().lower()
    signal_channel = str(signal.get("channelName") or "").strip().lower()
    return f"{signal_source}:{signal_channel}" if signal_channel else signal_source


def normalize_match_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = urllib.parse.unquote(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_slug_text(value: Any) -> str:
    text = urllib.parse.unquote(str(value or "").strip().strip("/").lower())
    if text.startswith("predictmon--"):
        text = text[len("predictmon--") :]
    return text


def signal_matches_position(signal: dict[str, Any], position: dict[str, Any]) -> bool:
    signal_slugs = [signal.get("marketSlug")]
    if isinstance(signal.get("marketSlugs"), list):
        signal_slugs.extend(signal.get("marketSlugs") or [])
    position_slugs = [position.get("slug"), position.get("eventSlug")]
    signal_slug_set = {normalize_slug_text(item) for item in signal_slugs if str(item or "").strip()}
    position_slug_set = {normalize_slug_text(item) for item in position_slugs if str(item or "").strip()}
    slug_match = bool(signal_slug_set and position_slug_set and signal_slug_set.intersection(position_slug_set))
    if not slug_match:
        signal_title = normalize_match_text(signal.get("marketTitle") or signal.get("matchedQuestion"))
        position_title = normalize_match_text(position.get("title"))
        slug_match = bool(signal_title and position_title and (signal_title in position_title or position_title in signal_title))
    if not slug_match:
        return False
    signal_outcome = normalize_match_text(signal.get("outcome"))
    position_outcome = normalize_match_text(position.get("outcome"))
    return not signal_outcome or not position_outcome or signal_outcome == position_outcome


def candidate_source_attribution(trader: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    trader_name = str(trader.get("userName") or trader.get("proxyWallet") or "").strip().lower()
    matched_signals: list[dict[str, Any]] = []
    fallback_signals: list[dict[str, Any]] = []
    for signal in trader.get("telegramSignals") or []:
        if not isinstance(signal, dict):
            continue
        source_key = source_key_from_signal(signal)
        if not source_key:
            continue
        if signal_matches_position(signal, position):
            matched_signals.append(signal)
        fallback_signals.append(signal)
    source_signals = matched_signals or fallback_signals
    source_keys = sorted({source_key_from_signal(signal) for signal in source_signals if source_key_from_signal(signal)})
    source_trader_keys = sorted({f"{source}:{trader_name}" for source in source_keys if trader_name})
    compact_matches = []
    for signal in matched_signals[:3]:
        compact_matches.append(
            {
                "source": signal.get("source", ""),
                "channelName": signal.get("channelName", ""),
                "messageDate": signal.get("messageDate", ""),
                "marketSlug": signal.get("marketSlug", ""),
                "outcome": signal.get("outcome", ""),
            }
        )
    return {
        "signalPositionMatched": bool(matched_signals),
        "sourceKeys": source_keys,
        "sourceTraderKeys": source_trader_keys,
        "matchedSignals": compact_matches,
    }


def composite_traders(keys: set[str]) -> set[str]:
    traders: set[str] = set()
    for key in keys:
        trader, _, _ = key.partition(":")
        if trader:
            traders.add(trader)
    return traders


def replay_quality_gate(shadow_replay: dict[str, Any]) -> dict[str, Any]:
    buckets = shadow_replay.get("qualityBuckets") if isinstance(shadow_replay.get("qualityBuckets"), dict) else {}
    quarantine = buckets.get("quarantine") if isinstance(buckets.get("quarantine"), dict) else {}
    promotions = buckets.get("promotions") if isinstance(buckets.get("promotions"), dict) else {}
    traders = normalized_bucket_set(quarantine, "traders")
    sources = normalized_bucket_set(quarantine, "sources")
    source_traders = normalized_bucket_set(quarantine, "sourceTraders")
    market_families = normalized_bucket_set(quarantine, "marketFamilies")
    entry_price_bands = normalized_bucket_set(quarantine, "entryPriceBands")
    trader_market_families = normalized_bucket_set(quarantine, "traderMarketFamilies")
    trader_entry_price_bands = normalized_bucket_set(quarantine, "traderEntryPriceBands")
    promoted_sources = normalized_bucket_set(promotions, "sources")
    promoted_source_traders = normalized_bucket_set(promotions, "sourceTraders")
    promoted_market_families = normalized_bucket_set(promotions, "marketFamilies")
    promoted_entry_price_bands = normalized_bucket_set(promotions, "entryPriceBands")
    promoted_trader_market_families = normalized_bucket_set(promotions, "traderMarketFamilies")
    promoted_trader_entry_price_bands = normalized_bucket_set(promotions, "traderEntryPriceBands")
    micro_policy = buckets.get("microScalpPolicy") if isinstance(buckets.get("microScalpPolicy"), dict) else {}
    has_micro_buckets = bool(
        buckets.get("byMarketFamily")
        or buckets.get("byEntryPriceBand")
        or buckets.get("byTraderMarketFamily")
        or buckets.get("byTraderEntryPriceBand")
    )
    promoted_composite_traders = composite_traders(promoted_trader_market_families | promoted_trader_entry_price_bands)
    return {
        "active": bool(buckets),
        "quarantinedTraders": sorted(traders),
        "weakSources": sorted(sources),
        "quarantinedSourceTraders": sorted(source_traders),
        "quarantinedMarketFamilies": sorted(market_families),
        "quarantinedEntryPriceBands": sorted(entry_price_bands),
        "quarantinedTraderMarketFamilies": sorted(trader_market_families),
        "quarantinedTraderEntryPriceBands": sorted(trader_entry_price_bands),
        "promotedSources": sorted(promoted_sources),
        "promotedSourceTraders": sorted(promoted_source_traders),
        "promotedMarketFamilies": sorted(promoted_market_families),
        "promotedEntryPriceBands": sorted(promoted_entry_price_bands),
        "promotedTraderMarketFamilies": sorted(promoted_trader_market_families),
        "promotedTraderEntryPriceBands": sorted(promoted_trader_entry_price_bands),
        "promotedCompositeTraders": sorted(promoted_composite_traders),
        "hasMicroBuckets": has_micro_buckets,
        "realWalletRequiresPromotedCompositeBucket": bool(
            micro_policy.get("realWalletRequiresPromotedCompositeBucket", has_micro_buckets)
        ),
        "promotedCompositeBucketCount": safe_int(micro_policy.get("promotedCompositeBucketCount")),
        "weakBucketCount": safe_int(quarantine.get("weakBucketCount")),
        "byTrader": bucket_rows_by_key(buckets.get("byTrader")),
        "bySource": bucket_rows_by_key(buckets.get("bySource")),
        "bySourceTrader": bucket_rows_by_key(buckets.get("bySourceTrader")),
        "byMarketFamily": bucket_rows_by_key(buckets.get("byMarketFamily")),
        "byEntryPriceBand": bucket_rows_by_key(buckets.get("byEntryPriceBand")),
        "byTraderMarketFamily": bucket_rows_by_key(buckets.get("byTraderMarketFamily")),
        "byTraderEntryPriceBand": bucket_rows_by_key(buckets.get("byTraderEntryPriceBand")),
    }


def apply_replay_quality_gate(traders: list[dict[str, Any]], gate: dict[str, Any]) -> list[dict[str, Any]]:
    if not gate.get("active"):
        return traders
    promoted_override_blockers = {
        "leaderboard_pnl_not_positive",
        "recent_closed_pf_below_1_05",
        "recent_closed_pnl_not_positive",
    }
    quarantined_traders = set(gate.get("quarantinedTraders") or [])
    weak_sources = set(gate.get("weakSources") or [])
    source_traders = set(gate.get("quarantinedSourceTraders") or [])
    promoted_composite_traders = set(gate.get("promotedCompositeTraders") or [])
    by_trader = gate.get("byTrader") if isinstance(gate.get("byTrader"), dict) else {}
    for trader in traders:
        name = str(trader.get("userName") or "").strip().lower()
        sources = [str(item).strip().lower() for item in trader.get("sourceKinds") or []]
        for signal in trader.get("telegramSignals") or []:
            if not isinstance(signal, dict):
                continue
            signal_source = str(signal.get("source") or "telegram_channel").strip().lower()
            signal_channel = str(signal.get("channelName") or "").strip().lower()
            source_key = f"{signal_source}:{signal_channel}" if signal_channel else signal_source
            if source_key and source_key not in sources:
                sources.append(source_key)
        bucket = by_trader.get(name) if name else None
        if bucket:
            trader["copyReplayQuality"] = {
                key: bucket.get(key)
                for key in (
                    "status",
                    "samples",
                    "wins",
                    "losses",
                    "netPnlUSDC",
                    "profitFactor",
                    "winRatePct",
                    "action",
                )
            }
        source_trader_quarantined = any(f"{source}:{name}" in source_traders for source in sources if name)
        has_promoted_micro_bucket = name in promoted_composite_traders
        blockers = [str(item) for item in trader.get("blockers") or []]
        remaining_blockers = [item for item in blockers if item not in promoted_override_blockers]
        if (
            has_promoted_micro_bucket
            and not trader.get("eligibleForShadowCopy")
            and safe_int(trader.get("currentPositionCount")) > 0
            and not remaining_blockers
        ):
            trader["eligibleForShadowCopy"] = True
            trader.setdefault("warnings", []).append("copy_replay_promoted_micro_bucket_overrides_broad_score")
        if (name in quarantined_traders or source_trader_quarantined) and not has_promoted_micro_bucket:
            trader["eligibleForShadowCopy"] = False
            trader.setdefault("blockers", []).append("copy_replay_trader_bucket_quarantined")
        elif name in quarantined_traders or source_trader_quarantined:
            trader.setdefault("warnings", []).append("copy_replay_broad_bucket_weak_but_micro_bucket_promoted")
        if weak_sources and any(source in weak_sources for source in sources):
            trader.setdefault("warnings", []).append("copy_replay_source_bucket_weak")
    return traders


def compact_bucket_evidence(bucket: dict[str, Any] | None) -> dict[str, Any]:
    if not bucket:
        return {}
    return {
        key: bucket.get(key)
        for key in (
            "bucketType",
            "bucketKey",
            "status",
            "samples",
            "wins",
            "losses",
            "netPnlUSDC",
            "profitFactor",
            "winRatePct",
            "action",
        )
    }


def candidate_micro_scalp_suitability(
    trader: dict[str, Any],
    position: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    family = market_family(position.get("title"), position.get("slug"), position.get("eventSlug"))
    band = entry_price_band(position.get("curPrice"))
    trader_name = str(trader.get("userName") or trader.get("proxyWallet") or "").strip().lower()
    trader_family_key = f"{trader_name}:{family}" if trader_name else f"unknown:{family}"
    trader_band_key = f"{trader_name}:{band}" if trader_name else f"unknown:{band}"
    source_attribution = candidate_source_attribution(trader, position)
    if not gate.get("active") or not gate.get("hasMicroBuckets"):
        return {
            "status": "NOT_ACTIVE",
            "action": "collect_shadow_samples",
            "marketFamily": family,
            "entryPriceBand": band,
            "traderMarketFamilyKey": trader_family_key,
            "traderEntryPriceBandKey": trader_band_key,
            "sourceAttribution": source_attribution,
            "realWalletEligibleByMicroBucket": False,
            "blockers": [],
            "warnings": ["copy_replay_micro_buckets_not_ready"],
            "bucketEvidence": {},
        }

    promoted_family = family in set(gate.get("promotedMarketFamilies") or [])
    promoted_band = band in set(gate.get("promotedEntryPriceBands") or [])
    promoted_trader_family = trader_family_key in set(gate.get("promotedTraderMarketFamilies") or [])
    promoted_trader_band = trader_band_key in set(gate.get("promotedTraderEntryPriceBands") or [])
    quarantined_family = family in set(gate.get("quarantinedMarketFamilies") or [])
    quarantined_band = band in set(gate.get("quarantinedEntryPriceBands") or [])
    quarantined_trader_family = trader_family_key in set(gate.get("quarantinedTraderMarketFamilies") or [])
    quarantined_trader_band = trader_band_key in set(gate.get("quarantinedTraderEntryPriceBands") or [])
    promoted_sources = set(gate.get("promotedSources") or [])
    promoted_source_traders = set(gate.get("promotedSourceTraders") or [])
    weak_sources = set(gate.get("weakSources") or [])
    quarantined_source_traders = set(gate.get("quarantinedSourceTraders") or [])
    candidate_sources = set(source_attribution.get("sourceKeys") or [])
    candidate_source_traders = set(source_attribution.get("sourceTraderKeys") or [])
    promoted_source = bool(candidate_sources.intersection(promoted_sources))
    source_quarantined = bool(candidate_sources.intersection(weak_sources) or candidate_source_traders.intersection(quarantined_source_traders))
    promoted_source_trader = bool(candidate_source_traders.intersection(promoted_source_traders)) and promoted_source and not source_quarantined
    source_promoted = promoted_source or promoted_source_trader
    price_path_promoted = promoted_trader_band and not quarantined_family
    composite_promoted = promoted_trader_family or price_path_promoted
    composite_quarantined = quarantined_trader_family or quarantined_trader_band
    blockers: list[str] = []
    warnings: list[str] = []
    requires_promoted_source = bool(promoted_sources or promoted_source_traders or weak_sources or quarantined_source_traders)
    if requires_promoted_source and not source_attribution.get("signalPositionMatched"):
        blockers.append("copy_replay_signal_position_not_matched")
    if source_quarantined and not source_promoted:
        blockers.append("copy_replay_source_bucket_quarantined")
    elif source_quarantined:
        warnings.append("copy_replay_source_bucket_weak_but_source_trader_promoted")
    if requires_promoted_source and not source_promoted:
        blockers.append("copy_replay_source_bucket_not_promoted")
    if composite_quarantined:
        blockers.append("copy_replay_micro_bucket_quarantined")
    if gate.get("realWalletRequiresPromotedCompositeBucket") and not composite_promoted:
        blockers.append("copy_replay_micro_bucket_not_promoted")
    if quarantined_family and not promoted_trader_family:
        blockers.append("copy_replay_market_family_bucket_quarantined")
    elif quarantined_family:
        warnings.append("copy_replay_broad_market_bucket_weak_but_trader_market_promoted")
    if quarantined_band and not promoted_trader_band:
        blockers.append("copy_replay_entry_price_band_bucket_quarantined")
    elif quarantined_band:
        warnings.append("copy_replay_broad_price_bucket_weak_but_trader_price_promoted")

    bucket_evidence = {
        "source": [
            compact_bucket_evidence((gate.get("bySource") or {}).get(key))
            for key in sorted(candidate_sources)
            if (gate.get("bySource") or {}).get(key)
        ],
        "sourceTrader": [
            compact_bucket_evidence((gate.get("bySourceTrader") or {}).get(key))
            for key in sorted(candidate_source_traders)
            if (gate.get("bySourceTrader") or {}).get(key)
        ],
        "marketFamily": compact_bucket_evidence((gate.get("byMarketFamily") or {}).get(family)),
        "entryPriceBand": compact_bucket_evidence((gate.get("byEntryPriceBand") or {}).get(band)),
        "traderMarketFamily": compact_bucket_evidence((gate.get("byTraderMarketFamily") or {}).get(trader_family_key)),
        "traderEntryPriceBand": compact_bucket_evidence((gate.get("byTraderEntryPriceBand") or {}).get(trader_band_key)),
    }
    status = "PROMOTABLE" if composite_promoted and not composite_quarantined else "QUARANTINE" if blockers else "COLLECTING"
    action = "allow_micro_live_candidate" if status == "PROMOTABLE" else "shadow_only_collect_more_evidence"
    return {
        "status": status,
        "action": action,
        "marketFamily": family,
        "entryPriceBand": band,
        "traderMarketFamilyKey": trader_family_key,
        "traderEntryPriceBandKey": trader_band_key,
        "sourceAttribution": source_attribution,
        "sourcePromoted": source_promoted,
        "promotedSource": promoted_source,
        "promotedSourceTrader": promoted_source_trader,
        "sourceQuarantined": source_quarantined,
        "promotedMarketFamily": promoted_family,
        "promotedEntryPriceBand": promoted_band,
        "promotedTraderMarketFamily": promoted_trader_family,
        "promotedTraderEntryPriceBand": promoted_trader_band,
        "pricePathPromoted": price_path_promoted,
        "realWalletEligibleByMicroBucket": status == "PROMOTABLE",
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": warnings,
        "bucketEvidence": bucket_evidence,
    }


def candidate_risk_plan(
    position: dict[str, Any],
    policy: dict[str, Any],
    extra_blockers: list[str] | None = None,
) -> dict[str, Any]:
    entry = safe_number(position.get("curPrice"))
    tp_pct = safe_number(policy.get("takeProfitPct"), 2.0)
    tp_usdc = safe_number(policy.get("takeProfitUSDC"), 0.0)
    sl_pct = safe_number(policy.get("stopLossPct"), 4.0)
    take_profit = min(0.99, entry * (1.0 + tp_pct / 100.0)) if entry > 0 else 0.0
    stop_loss = max(0.01, entry * (1.0 - sl_pct / 100.0)) if entry > 0 else 0.0
    entry_ok = (
        entry >= safe_number(policy.get("minEntryPrice"), 0.04)
        and entry <= safe_number(policy.get("maxEntryPrice"), 0.90)
    )
    blockers = list(policy.get("hardBlockers") or []) + ([] if entry_ok else ["entry_price_outside_policy_band"])
    blockers.extend(extra_blockers or [])
    blockers = list(dict.fromkeys(blockers))
    real_wallet_eligible = bool(policy.get("realWalletExecutionAllowed")) and not blockers
    return {
        "mode": "AUTONOMOUS_BRACKET_EXIT_GATE",
        "entryReferencePrice": round(entry, 4),
        "takeProfitPct": policy.get("takeProfitPct"),
        "takeProfitUSDC": round(tp_usdc, 4),
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
    quality_gate: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    gate = quality_gate or {}
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
            micro_suitability = candidate_micro_scalp_suitability(trader, position, gate)
            risk_plan = candidate_risk_plan(position, policy, micro_suitability.get("blockers") or [])
            risk_plan["microScalpStatus"] = micro_suitability.get("status")
            risk_plan["microScalpWarnings"] = micro_suitability.get("warnings") or []
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
                    "marketFamily": micro_suitability.get("marketFamily"),
                    "entryPriceBand": micro_suitability.get("entryPriceBand"),
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
                    "microScalpSuitability": micro_suitability,
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
            wallet_signals = signals_by_wallet[wallet]
            bucket.setdefault("telegramSignals", []).extend(wallet_signals[:10])
            first_signal = wallet_signals[0]
            if first_signal.get("userName") and not bucket.get("userName"):
                bucket["userName"] = first_signal.get("userName")
            if first_signal.get("rank") and not bucket.get("telegramRank"):
                bucket["telegramRank"] = first_signal.get("rank")

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
            1 if "telegram_channel" in item.get("sourceKinds", set()) else 0,
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
    quality_gate = replay_quality_gate(shadow_replay)
    policy = wallet_risk_policy(args, bool(telegram.get("active")), validation, quality_gate)
    traders = apply_replay_quality_gate(traders, quality_gate)
    shadow_candidates = build_shadow_candidates(traders, args.min_current_value, policy, quality_gate)
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
            "telegramSignalLimit": args.telegram_signal_limit,
        },
        "walletRiskPolicy": policy,
        "copyReplayQualityGate": {
            key: value
            for key, value in quality_gate.items()
            if not key.startswith("by")
        },
        "summary": {
            "leaderboardRows": leaderboard_rows,
            "candidateWallets": len(wallet_map),
            "rankedTraders": len(traders),
            "eligibleTraders": eligible_count,
            "telegramWallets": safe_int(telegram.get("walletCount")),
            "telegramSignals": safe_int(telegram.get("signalCount")),
            "currentPositions": sum(safe_int(row.get("currentPositionCount")) for row in traders),
            "shadowCandidates": len(shadow_candidates),
            "replayQuarantinedTraders": len(quality_gate.get("quarantinedTraders") or []),
            "replayWeakSources": len(quality_gate.get("weakSources") or []),
            "topTrader": (traders[0].get("userName") or traders[0].get("proxyWallet")) if traders else "",
            "topScore": traders[0].get("copyScore") if traders else 0,
            "walletRiskPolicyStatus": policy.get("status"),
            "realWalletExecutionAllowed": policy.get("realWalletExecutionAllowed"),
            "humanApprovalRequired": False,
            "realWalletCandidates": real_wallet_candidate_count,
            "replayPromotedMicroBuckets": quality_gate.get("promotedCompositeBucketCount", 0),
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
