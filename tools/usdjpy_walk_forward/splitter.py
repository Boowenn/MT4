from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from .schema import SEGMENTS


def _parse_time(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
        text.replace(".", "-"),
        text.replace(".", "-").replace(" ", "T"),
    ]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).timestamp()
        except ValueError:
            continue
    return None


def sort_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    indexed = []
    for index, event in enumerate(events):
        indexed.append((_parse_time(event.get("timestamp")), index, event))
    indexed.sort(key=lambda item: (item[0] is None, item[0] if item[0] is not None else item[1], item[1]))
    return [item[2] for item in indexed]


def split_events(events: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    ordered = sort_events(events)
    count = len(ordered)
    if count == 0:
        return {segment: [] for segment in SEGMENTS}
    train_end = max(1, int(round(count * 0.60)))
    validation_end = max(train_end + 1, int(round(count * 0.80))) if count >= 3 else count
    validation_end = min(validation_end, count)
    if count >= 3 and validation_end == count:
        validation_end = count - 1
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "forward": ordered[validation_end:],
    }

