from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            # Accept both seconds and milliseconds.
            raw = float(value)
            if raw > 10_000_000_000:
                raw = raw / 1000.0
            return datetime.fromtimestamp(raw, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
        text.replace(" ", "T").replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def snapshot_timestamp(snapshot: dict[str, Any]) -> datetime | None:
    for key in ("generatedAt", "generatedAtIso", "timeIso", "timestamp"):
        parsed = parse_timestamp(snapshot.get(key))
        if parsed is not None:
            return parsed
    current_price = snapshot.get("current_price") or snapshot.get("currentPrice")
    if isinstance(current_price, dict):
        for key in ("timeIso", "time", "timestamp"):
            parsed = parse_timestamp(current_price.get(key))
            if parsed is not None:
                return parsed
    return None


def freshness_report(snapshot: dict[str, Any], *, max_age_seconds: int) -> dict[str, Any]:
    ts = snapshot_timestamp(snapshot)
    now = utc_now()
    if ts is None:
        return {
            "fresh": False,
            "ageSeconds": None,
            "timestampIso": None,
            "maxAgeSeconds": max_age_seconds,
            "reason": "missing_runtime_timestamp",
        }
    age = max(0, int((now - ts).total_seconds()))
    if max_age_seconds <= 0:
        return {
            "fresh": True,
            "ageSeconds": age,
            "timestampIso": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "maxAgeSeconds": max_age_seconds,
            "reason": "freshness_check_disabled",
        }
    fresh = age <= max_age_seconds
    return {
        "fresh": fresh,
        "ageSeconds": age,
        "timestampIso": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "maxAgeSeconds": max_age_seconds,
        "reason": "fresh" if fresh else "stale_runtime_snapshot",
    }
