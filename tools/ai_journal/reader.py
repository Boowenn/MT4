"""Read local AI advisory journal records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_JOURNAL_FILE = "QuantGod_AIAdvisoryJournal.jsonl"
DEFAULT_OUTCOME_FILE = "QuantGod_AIAdvisoryOutcomes.jsonl"
DEFAULT_KILL_SWITCH_FILE = "QuantGod_AISignalKillSwitch.json"


def runtime_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir).expanduser().resolve()


def journal_dir(runtime_dir: str | Path) -> Path:
    return runtime_path(runtime_dir) / "journal"


def journal_path(runtime_dir: str | Path) -> Path:
    return journal_dir(runtime_dir) / DEFAULT_JOURNAL_FILE


def outcome_path(runtime_dir: str | Path) -> Path:
    return journal_dir(runtime_dir) / DEFAULT_OUTCOME_FILE


def kill_switch_path(runtime_dir: str | Path) -> Path:
    return journal_dir(runtime_dir) / DEFAULT_KILL_SWITCH_FILE


def read_jsonl(path: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    if limit is not None and limit >= 0:
        return rows[-limit:]
    return rows


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def latest_records(runtime_dir: str | Path, *, limit: int = 20) -> list[dict[str, Any]]:
    return read_jsonl(journal_path(runtime_dir), limit=limit)


def latest_outcomes(runtime_dir: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    return read_jsonl(outcome_path(runtime_dir), limit=limit)


def iter_symbol_records(records: Iterable[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    wanted = str(symbol or "").strip()
    return [row for row in records if str(row.get("symbol") or "").strip() == wanted]
