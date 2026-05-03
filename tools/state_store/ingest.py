"""Evidence ingestion for the QuantGod P2-3 SQLite state layer."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence

from .config import StateStoreConfig, unique_existing_dirs
from .db import StateStore, utc_now_iso
from .safety import assert_state_store_safety, safety_payload

SOURCE_ALL = "all"
SUPPORTED_SOURCES = (
    "events",
    "ai-analysis",
    "vibe",
    "notifications",
    "api-contract",
    "frontend-dist",
)

AI_JSON_PATTERNS = (
    "**/QuantGod_AIAnalysis*.json",
    "**/QuantGod_AiAnalysis*.json",
    "**/*ai_analysis*.json",
    "**/*AIAnalysis*.json",
)
AI_CSV_PATTERNS = (
    "**/QuantGod_AIAnalysis*.csv",
    "**/QuantGod_AiAnalysis*.csv",
    "**/*ai_analysis*.csv",
    "**/*AIAnalysis*.csv",
)
VIBE_JSON_PATTERNS = (
    "**/QuantGod_Vibe*.json",
    "**/*vibe*.json",
    "**/*Vibe*.json",
)
VIBE_CSV_PATTERNS = (
    "**/QuantGod_Vibe*.csv",
    "**/*vibe*.csv",
    "**/*Vibe*.csv",
)
NOTIFY_JSON_PATTERNS = (
    "**/QuantGod_Notification*.json",
    "**/QuantGod_Notify*.json",
    "**/*notification*.json",
    "**/*notify*.json",
)
NOTIFY_CSV_PATTERNS = (
    "**/QuantGod_Notification*.csv",
    "**/QuantGod_Notify*.csv",
    "**/*notification*.csv",
    "**/*notify*.csv",
)
EVENT_PATTERNS = (
    "QuantGod_*.json",
    "QuantGod_*.csv",
)

SKIP_DIR_NAMES = {".git", ".venv", "venv", "node_modules", "__pycache__", "vue-dist"}
MAX_FILES_PER_SOURCE = 250
MAX_EVENT_FILES = 150


def expand_sources(sources: Sequence[str] | None) -> List[str]:
    if not sources:
        return list(SUPPORTED_SOURCES)
    normalized: list[str] = []
    for raw in sources:
        for part in str(raw or "").split(","):
            value = part.strip().lower()
            if not value:
                continue
            if value == SOURCE_ALL:
                return list(SUPPORTED_SOURCES)
            if value not in SUPPORTED_SOURCES:
                raise ValueError(f"Unsupported state ingest source: {value}")
            if value not in normalized:
                normalized.append(value)
    return normalized or list(SUPPORTED_SOURCES)


def ingest_sources(config: StateStoreConfig, sources: Sequence[str] | None = None) -> Dict[str, Any]:
    assert_state_store_safety()
    selected = expand_sources(sources)
    store = StateStore(config)
    store.init()
    started_at = utc_now_iso()
    run_id = stable_id("ingest", started_at, ",".join(selected))
    counts: Dict[str, int] = {source: 0 for source in selected}
    error = ""
    status = "ok"

    try:
        for source in selected:
            if source == "events":
                counts[source] = ingest_event_file_index(store, config)
            elif source == "ai-analysis":
                counts[source] = ingest_ai_analysis(store, config)
            elif source == "vibe":
                counts[source] = ingest_vibe(store, config)
            elif source == "notifications":
                counts[source] = ingest_notifications(store, config)
            elif source == "api-contract":
                counts[source] = ingest_api_contract(store, config)
            elif source == "frontend-dist":
                counts[source] = ingest_frontend_dist(store, config)
    except Exception as exc:  # pragma: no cover - defensive run ledger capture
        status = "failed"
        error = str(exc)
        raise
    finally:
        finished_at = utc_now_iso()
        store.insert_ingest_run(
            {
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "sources": selected,
                "counts": counts,
                "error": error,
            }
        )

    return {
        "ok": True,
        "runId": run_id,
        "startedAt": started_at,
        "finishedAt": utc_now_iso(),
        "sources": selected,
        "counts": counts,
        "safety": safety_payload(),
    }


def ingest_ai_analysis(store: StateStore, config: StateStoreConfig) -> int:
    count = 0
    for path, payload in iter_json_payloads(config, AI_JSON_PATTERNS):
        for index, record in enumerate(extract_records(payload)):
            run_id = first_text(record, "runId", "run_id", "id", "analysisId", "analysis_id") or stable_id("ai", path, index, record)
            store.upsert_ai_analysis_run(
                {
                    "run_id": run_id,
                    "status": first_text(record, "status", "result", "decision") or "recorded",
                    "symbol": first_text(record, "symbol", "Symbol", "ticker", "instrument"),
                    "route": first_text(record, "route", "strategy", "Strategy"),
                    "provider": first_text(record, "provider", "aiProvider", "vendor"),
                    "model": first_text(record, "model", "modelName", "llm"),
                    "advisory_only": True,
                    "generated_at": first_time(record, path),
                    "source_path": str(path),
                    "payload": record,
                }
            )
            store.upsert_event(evidence_event("AI_ANALYSIS_RUN", "ai-analysis", path, run_id, record))
            count += 1
    for path, row in iter_csv_rows(config, AI_CSV_PATTERNS):
        run_id = first_text(row, "runId", "run_id", "id", "analysisId") or stable_id("ai-csv", path, row)
        store.upsert_ai_analysis_run(
            {
                "run_id": run_id,
                "status": first_text(row, "status", "result", "decision") or "recorded",
                "symbol": first_text(row, "symbol", "Symbol", "ticker", "instrument"),
                "route": first_text(row, "route", "strategy", "Strategy"),
                "provider": first_text(row, "provider", "aiProvider", "vendor"),
                "model": first_text(row, "model", "modelName", "llm"),
                "advisory_only": True,
                "generated_at": first_time(row, path),
                "source_path": str(path),
                "payload": row,
            }
        )
        store.upsert_event(evidence_event("AI_ANALYSIS_RUN", "ai-analysis", path, run_id, row))
        count += 1
    return count


def ingest_vibe(store: StateStore, config: StateStoreConfig) -> int:
    count = 0
    for path, payload in iter_json_payloads(config, VIBE_JSON_PATTERNS):
        records = extract_records(payload)
        for index, record in enumerate(records):
            kind = str(first_text(record, "kind", "type", "recordType") or "").lower()
            is_backtest = "backtest" in kind or any(key in record for key in ("backtestId", "backtest_id", "metrics", "equityCurve"))
            if is_backtest:
                run_id = first_text(record, "runId", "run_id", "backtestId", "backtest_id", "id") or stable_id("vibe-backtest", path, index, record)
                store.upsert_vibe_backtest_run(
                    {
                        "run_id": run_id,
                        "strategy_id": first_text(record, "strategyId", "strategy_id", "id"),
                        "status": first_text(record, "status") or "recorded",
                        "generated_at": first_time(record, path),
                        "source_path": str(path),
                        "payload": record,
                    }
                )
                store.upsert_event(evidence_event("VIBE_BACKTEST_RUN", "vibe", path, run_id, record))
            else:
                strategy_id = first_text(record, "strategyId", "strategy_id", "id", "name") or stable_id("vibe-strategy", path, index, record)
                store.upsert_vibe_strategy(
                    {
                        "strategy_id": strategy_id,
                        "name": first_text(record, "name", "strategyName", "title") or strategy_id,
                        "version": first_text(record, "version", "strategyVersion"),
                        "status": first_text(record, "status") or "recorded",
                        "research_only": True,
                        "generated_at": first_time(record, path),
                        "source_path": str(path),
                        "payload": record,
                    }
                )
                store.upsert_event(evidence_event("VIBE_STRATEGY", "vibe", path, strategy_id, record))
            count += 1
    for path, row in iter_csv_rows(config, VIBE_CSV_PATTERNS):
        strategy_id = first_text(row, "strategyId", "strategy_id", "id", "name") or stable_id("vibe-csv", path, row)
        store.upsert_vibe_strategy(
            {
                "strategy_id": strategy_id,
                "name": first_text(row, "name", "strategyName", "title") or strategy_id,
                "version": first_text(row, "version", "strategyVersion"),
                "status": first_text(row, "status") or "recorded",
                "research_only": True,
                "generated_at": first_time(row, path),
                "source_path": str(path),
                "payload": row,
            }
        )
        store.upsert_event(evidence_event("VIBE_STRATEGY", "vibe", path, strategy_id, row))
        count += 1
    return count


def ingest_notifications(store: StateStore, config: StateStoreConfig) -> int:
    count = 0
    for path, payload in iter_json_payloads(config, NOTIFY_JSON_PATTERNS):
        for index, record in enumerate(extract_records(payload)):
            event_id = first_text(record, "eventId", "event_id", "id", "messageId") or stable_id("notify", path, index, record)
            store.upsert_notification_event(
                {
                    "event_id": event_id,
                    "event_type": first_text(record, "eventType", "event_type", "type") or "NOTIFICATION",
                    "channel": first_text(record, "channel", "target") or "telegram",
                    "status": first_text(record, "status", "deliveryStatus") or "recorded",
                    "push_only": True,
                    "generated_at": first_time(record, path),
                    "source_path": str(path),
                    "payload": record,
                }
            )
            store.upsert_event(evidence_event("NOTIFICATION_EVENT", "notifications", path, event_id, record))
            count += 1
    for path, row in iter_csv_rows(config, NOTIFY_CSV_PATTERNS):
        event_id = first_text(row, "eventId", "event_id", "id", "messageId") or stable_id("notify-csv", path, row)
        store.upsert_notification_event(
            {
                "event_id": event_id,
                "event_type": first_text(row, "eventType", "event_type", "type") or "NOTIFICATION",
                "channel": first_text(row, "channel", "target") or "telegram",
                "status": first_text(row, "status", "deliveryStatus") or "recorded",
                "push_only": True,
                "generated_at": first_time(row, path),
                "source_path": str(path),
                "payload": row,
            }
        )
        store.upsert_event(evidence_event("NOTIFICATION_EVENT", "notifications", path, event_id, row))
        count += 1
    return count


def ingest_api_contract(store: StateStore, config: StateStoreConfig) -> int:
    path = config.docs_contract_path
    if not path or not path.exists():
        return 0
    payload = read_json(path)
    endpoint_count = 0
    for group in payload.get("endpointGroups", []) if isinstance(payload, dict) else []:
        endpoints = group.get("endpoints", []) if isinstance(group, dict) else []
        endpoint_count += len(endpoints) if isinstance(endpoints, list) else 0
    contract_id = stable_id("api-contract", path, payload.get("schemaVersion") if isinstance(payload, dict) else "", endpoint_count)
    store.upsert_api_contract_version(
        {
            "contract_id": contract_id,
            "schema_version": str(payload.get("schemaVersion", "")) if isinstance(payload, dict) else "",
            "project": payload.get("project", "QuantGod") if isinstance(payload, dict) else "QuantGod",
            "reviewed_at": payload.get("lastReviewed", "") if isinstance(payload, dict) else "",
            "endpoint_count": endpoint_count,
            "source_path": str(path),
            "payload": payload,
        }
    )
    store.upsert_event(evidence_event("API_CONTRACT_VERSION", "api-contract", path, contract_id, payload if isinstance(payload, dict) else {}))
    return 1


def ingest_frontend_dist(store: StateStore, config: StateStoreConfig) -> int:
    vue_dist = config.dashboard_dir / "vue-dist"
    if not vue_dist.exists() or not vue_dist.is_dir():
        return 0
    candidates = [
        vue_dist / "asset-manifest.json",
        vue_dist / "manifest.json",
        vue_dist / "qg-frontend-release.json",
        vue_dist / "index.html",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            stat = path.stat()
            if path.suffix.lower() == ".json":
                payload: Any = read_json(path)
            else:
                payload = {
                    "fileName": path.name,
                    "size": stat.st_size,
                    "mtimeIso": mtime_iso(path),
                }
            release_id = first_text(payload, "releaseId", "release_id", "buildId", "commit", "frontendCommit") if isinstance(payload, dict) else ""
            release_id = release_id or stable_id("frontend-dist", path, stat.st_size, int(stat.st_mtime))
            store.upsert_frontend_dist_release(
                {
                    "release_id": release_id,
                    "frontend_commit": first_text(payload, "commit", "frontendCommit", "gitCommit") if isinstance(payload, dict) else "",
                    "build_time": first_text(payload, "buildTime", "builtAt", "generatedAt") if isinstance(payload, dict) else mtime_iso(path),
                    "source_path": str(path),
                    "payload": payload,
                }
            )
            store.upsert_event(evidence_event("FRONTEND_DIST_RELEASE", "frontend-dist", path, release_id, payload if isinstance(payload, dict) else {}))
            return 1
    return 0


def ingest_event_file_index(store: StateStore, config: StateStoreConfig) -> int:
    roots = unique_existing_dirs([config.runtime_dir, config.dashboard_dir])
    files: list[Path] = []
    for root in roots:
        for pattern in EVENT_PATTERNS:
            files.extend(path for path in root.glob(pattern) if path.is_file())
    files = sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)[:MAX_EVENT_FILES]
    for path in files:
        stat = path.stat()
        payload = {
            "fileName": path.name,
            "size": stat.st_size,
            "mtimeIso": mtime_iso(path),
            "suffix": path.suffix.lower(),
        }
        event_id = stable_id("evidence-file", path, stat.st_size, int(stat.st_mtime))
        store.upsert_event(evidence_event("EVIDENCE_FILE_SEEN", "events", path, event_id, payload))
    return len(files)


def iter_json_payloads(config: StateStoreConfig, patterns: Sequence[str]) -> Iterator[tuple[Path, Any]]:
    for path in find_files(config, patterns):
        try:
            yield path, read_json(path)
        except (OSError, json.JSONDecodeError):
            continue


def iter_csv_rows(config: StateStoreConfig, patterns: Sequence[str]) -> Iterator[tuple[Path, Dict[str, str]]]:
    for path in find_files(config, patterns):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    yield path, dict(row)
        except OSError:
            continue


def find_files(config: StateStoreConfig, patterns: Sequence[str]) -> List[Path]:
    roots = unique_existing_dirs(
        [
            config.runtime_dir,
            config.dashboard_dir,
            config.repo_root / "archive",
            config.repo_root / "runtime",
            config.repo_root / "tools",
            config.repo_root / "docs",
        ]
    )
    found: list[Path] = []
    for root in roots:
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file() or should_skip(path):
                    continue
                found.append(path.resolve())
    unique = sorted(set(found), key=lambda item: item.stat().st_mtime, reverse=True)
    return unique[:MAX_FILES_PER_SOURCE]


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item if isinstance(item, dict) else {"value": item} for item in payload]
    if not isinstance(payload, dict):
        return [{"value": payload}]
    for key in (
        "runs",
        "history",
        "reports",
        "records",
        "items",
        "events",
        "notifications",
        "strategies",
        "backtests",
        "data",
        "rows",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"value": item} for item in value]
    return [payload]


def first_text(data: Mapping[str, Any] | Any, *keys: str) -> str:
    if not isinstance(data, Mapping):
        return ""
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text[:500]
    return ""


def first_time(data: Mapping[str, Any] | Any, path: Path) -> str:
    text = first_text(
        data,
        "generatedAt",
        "generated_at",
        "createdAt",
        "created_at",
        "timestamp",
        "time",
        "Time",
        "date",
        "Date",
    )
    if text:
        return normalize_time(text)
    return mtime_iso(path)


def normalize_time(value: str) -> str:
    text = str(value).strip()
    if not text:
        return utc_now_iso()
    if text.endswith("Z") and "T" in text:
        return text
    if text.isdigit():
        numeric = int(text)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        return datetime.fromtimestamp(numeric, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
            return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return text


def mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, Path):
            text = str(part.resolve())
        else:
            text = json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
        digest.update(text.encode("utf-8", errors="replace"))
        digest.update(b"\x1f")
    return digest.hexdigest()[:24]


def evidence_event(event_type: str, source: str, path: Path, entity_id: str, payload: Mapping[str, Any] | Dict[str, Any]) -> Dict[str, Any]:
    event_id = stable_id(event_type, source, path, entity_id)
    symbol = first_text(payload, "symbol", "Symbol", "ticker")
    route = first_text(payload, "route", "strategy", "Strategy")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "source": source,
        "source_path": str(path),
        "entity_id": entity_id,
        "symbol": symbol,
        "route": route,
        "severity": first_text(payload, "severity") or "info",
        "occurred_at": first_time(payload, path),
        "payload": dict(payload),
    }
