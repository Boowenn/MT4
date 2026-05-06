from __future__ import annotations

from typing import Any, Dict, List


HARD_BLOCK_TOKENS = (
    "NEWS",
    "SPREAD",
    "SESSION",
    "COOLDOWN",
    "STARTUP",
    "KILL",
    "FALLBACK",
    "RUNTIME",
    "FASTLANE",
    "CAPACITY",
    "MARGIN",
)

TACTICAL_TOKENS = (
    "NO_CROSS",
    "WAIT",
    "BAR",
    "TACTICAL",
    "RSI",
    "CONFIRM",
    "PULLBACK",
)


def classify_gates(sample: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join(str(item or "") for item in (
        sample.get("blockReason"),
        sample.get("status"),
        sample.get("exitReason"),
    )).upper()
    raw = sample.get("raw") if isinstance(sample.get("raw"), dict) else {}
    hard: List[str] = []
    tactical: List[str] = []
    for token in HARD_BLOCK_TOKENS:
        if token in text:
            hard.append(token)
    for token in TACTICAL_TOKENS:
        if token in text:
            tactical.append(token)
    for key, token in (
        ("sessionAllowed", "SESSION"),
        ("spreadAllowed", "SPREAD"),
        ("newsAllowed", "NEWS"),
        ("cooldownAllowed", "COOLDOWN"),
        ("startupGuardAllowed", "STARTUP"),
        ("positionCapacityAllowed", "CAPACITY"),
    ):
        if raw.get(key) is False and token not in hard:
            hard.append(token)
    return {
        "hardBlockers": sorted(set(hard)),
        "tacticalBlockers": sorted(set(tactical)),
        "hardGatePass": not hard,
        "tacticalGatePass": not tactical,
        "note": "session/spread/news/cooldown/runtime 等硬门禁不会在 relaxed_entry_v1 中放宽。",
    }

