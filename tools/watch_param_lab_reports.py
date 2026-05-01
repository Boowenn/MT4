#!/usr/bin/env python3
"""Watch ParamLab Strategy Tester reports and update the result ledger.

This is a file-only bridge between Strategy Tester output and the QuantGod
governance loop. It discovers reports in ParamLab archives, parses tester
metrics, writes the same ParamLab result ledger used by Version Promotion Gate,
and records watcher state for the dashboard. It never launches MT5, never
mutates the HFM live preset, and never touches a broker/order path.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_param_lab_results import (
    LEDGER_NAME,
    PLAN_NAME,
    RESULTS_NAME,
    STATUS_NAME,
    annotate_plan,
    parse_report,
    read_json,
    reusable_task_metrics,
    score_result,
    top_results_by_route,
    write_csv,
    write_json,
)


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
AUTO_SCHEDULER_NAME = "QuantGod_ParamLabAutoScheduler.json"
WATCHER_NAME = "QuantGod_ParamLabReportWatcher.json"
WATCHER_LEDGER_NAME = "QuantGod_ParamLabReportWatcherLedger.csv"
REPORT_EXTENSIONS = {".html", ".htm", ".xml"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch QuantGod ParamLab Strategy Tester reports.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--archive-root", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--scheduler", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--watcher-output", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--watcher-ledger", default="")
    parser.add_argument("--scan-root", action="append", default=[], help="Extra report root to scan.")
    parser.add_argument("--min-trades", type=int, default=10)
    return parser.parse_args()


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(str(value).strip())
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value)
    return int(number) if number is not None else default


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def iso_from_mtime(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def normalize_report_path(raw: Any, repo_root: Path) -> Path | None:
    text = str(raw or "").strip().strip('"')
    if not text:
        return None
    text = text.replace("/", "\\")
    text = text.replace("archive\\param_lab_runs\\", "archive\\param-lab\\runs\\")
    text = text.replace("archive\\param_lab\\runs\\", "archive\\param-lab\\runs\\")
    path = Path(text)
    if not path.is_absolute():
        path = repo_root / path
    return path


def report_exists(path: Path | None) -> bool:
    try:
        return bool(path and path.exists() and path.is_file() and path.stat().st_size > 0)
    except OSError:
        return False


def discover_report_files(roots: list[Path]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in REPORT_EXTENSIONS and report_exists(root):
            discovered[str(root.resolve()).lower()] = root
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in REPORT_EXTENSIONS and report_exists(path):
                discovered[str(path.resolve()).lower()] = path
    return sorted(discovered.values(), key=lambda item: str(item).lower())


def add_metadata_from_task(metadata: dict[str, dict[str, Any]], task: dict[str, Any]) -> None:
    candidate_id = str(task.get("candidateId") or task.get("proposalId") or task.get("candidateVersionId") or "").strip()
    if not candidate_id:
        return
    existing = metadata.setdefault(candidate_id, {})
    for key in (
        "candidateId",
        "routeKey",
        "strategy",
        "symbol",
        "timeframe",
        "variant",
        "score",
        "rank",
        "parameterSummary",
        "presetName",
        "configPath",
        "presetPath",
    ):
        if task.get(key) not in (None, "") and existing.get(key) in (None, ""):
            existing[key] = task.get(key)


def build_candidate_metadata(plan: dict[str, Any], scheduler: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for route_plan in safe_list(plan.get("routePlans")):
        route_plan = safe_dict(route_plan)
        for candidate in safe_list(route_plan.get("candidates")):
            candidate = safe_dict(candidate)
            if route_plan.get("routeKey") and not candidate.get("routeKey"):
                candidate = {**candidate, "routeKey": route_plan.get("routeKey")}
            add_metadata_from_task(metadata, candidate)
    for task in safe_list(plan.get("backtestTasks")):
        add_metadata_from_task(metadata, safe_dict(task))
    for key in ("selectedTasks", "backtestTasks"):
        for task in safe_list(scheduler.get(key)):
            add_metadata_from_task(metadata, safe_dict(task))
    for status in statuses:
        for task in safe_list(status.get("tasks")):
            add_metadata_from_task(metadata, safe_dict(task))
    return metadata


def report_candidates_from_file(path: Path, candidate_ids: list[str]) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    for candidate_id in sorted(candidate_ids, key=len, reverse=True):
        value = candidate_id.lower()
        if stem == value or value in name:
            return candidate_id
    return ""


def index_report_files(paths: list[Path], candidate_ids: list[str]) -> tuple[dict[str, list[Path]], dict[str, Path]]:
    by_candidate: dict[str, list[Path]] = {}
    by_stem: dict[str, Path] = {}
    for path in paths:
        by_stem.setdefault(path.stem.lower(), path)
        candidate_id = report_candidates_from_file(path, candidate_ids)
        if candidate_id:
            by_candidate.setdefault(candidate_id, []).append(path)
    for rows in by_candidate.values():
        rows.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return by_candidate, by_stem


def alternate_report_paths(path: Path | None) -> list[Path]:
    if not path:
        return []
    alternates = [path]
    for suffix in REPORT_EXTENSIONS:
        alternates.append(path.with_suffix(suffix))
    seen: set[str] = set()
    output: list[Path] = []
    for item in alternates:
        key = str(item).lower()
        if key not in seen:
            output.append(item)
            seen.add(key)
    return output


def resolve_report_path(
    *,
    candidate_id: str,
    expected_path: Path | None,
    report_by_candidate: dict[str, list[Path]],
    report_by_stem: dict[str, Path],
) -> tuple[Path | None, str]:
    for path in alternate_report_paths(expected_path):
        if report_exists(path):
            return path, "expected_path"
    if expected_path:
        by_stem = report_by_stem.get(expected_path.stem.lower())
        if report_exists(by_stem):
            return by_stem, "stem_match"
    for path in report_by_candidate.get(candidate_id, []):
        if report_exists(path):
            return path, "candidate_filename"
    return expected_path, "pending_expected_path" if expected_path else "pending_no_path"


def load_status_documents(runtime_status_path: Path, archive_root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if runtime_status_path.exists():
        status = read_json(runtime_status_path)
        if status:
            status["_statusPath"] = str(runtime_status_path)
            status["_statusSource"] = "runtime_status"
            documents.append(status)
    if archive_root.exists():
        for status_path in sorted(archive_root.glob(f"*/{STATUS_NAME}")):
            status = read_json(status_path)
            if status:
                status["_statusPath"] = str(status_path)
                status["_statusSource"] = "archive_status"
                documents.append(status)
    return documents


def add_task_record(records: list[dict[str, Any]], source: str, task: dict[str, Any], repo_root: Path, status: dict[str, Any] | None = None) -> None:
    candidate_id = str(task.get("candidateId") or task.get("candidateVersionId") or task.get("proposalId") or "").strip()
    if not candidate_id:
        return
    status_doc = status or {}
    report_path = (
        task.get("reportPath")
        or task.get("existingReportPath")
        or task.get("reportPathHint")
        or safe_dict(task.get("resultEvidence")).get("reportPath")
    )
    records.append({
        "source": source,
        "runId": status_doc.get("runId", task.get("runId", "")),
        "runMode": status_doc.get("mode", task.get("runMode", "")),
        "runGeneratedAtIso": status_doc.get("generatedAtIso", task.get("runGeneratedAtIso", "")),
        "statusPath": status_doc.get("_statusPath", ""),
        "candidateId": candidate_id,
        "routeKey": task.get("routeKey") or task.get("strategy") or "",
        "symbol": task.get("symbol", ""),
        "timeframe": task.get("timeframe", ""),
        "variant": task.get("variant", ""),
        "score": task.get("score", task.get("rankScore", "")),
        "rank": task.get("rank", task.get("routeRank", "")),
        "configPath": task.get("configPath", task.get("existingConfigPath", "")),
        "presetPath": task.get("presetPath", ""),
        "reportPath": normalize_report_path(report_path, repo_root),
        "existingStatus": task.get("status", task.get("existingTaskStatus", "")),
        "artifactDir": task.get("artifactDir", ""),
        "agentFilesCopied": task.get("agentFilesCopied", False),
        "metrics": task.get("metrics") if isinstance(task.get("metrics"), dict) else {},
    })


def build_known_records(
    repo_root: Path,
    plan: dict[str, Any],
    scheduler: dict[str, Any],
    status_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for status in status_docs:
        for task in safe_list(status.get("tasks")):
            add_task_record(records, str(status.get("_statusSource") or "status"), safe_dict(task), repo_root, status)
    for task in safe_list(plan.get("backtestTasks")):
        add_task_record(records, "param_plan_task", safe_dict(task), repo_root)
    for key in ("selectedTasks", "backtestTasks"):
        for task in safe_list(scheduler.get(key)):
            add_task_record(records, f"auto_scheduler_{key}", safe_dict(task), repo_root)

    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_order = {
        "archive_status": 1,
        "runtime_status": 2,
        "param_plan_task": 3,
        "auto_scheduler_selectedTasks": 4,
        "auto_scheduler_backtestTasks": 5,
    }
    for record in records:
        key = (
            str(record.get("candidateId") or ""),
            str(record.get("runId") or ""),
            str(record.get("reportPath") or ""),
        )
        existing = deduped.get(key)
        if not existing or source_order.get(str(record.get("source")), 99) < source_order.get(str(existing.get("source")), 99):
            deduped[key] = record
    return list(deduped.values())


def fill_from_metadata(record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    merged = dict(record)
    for key in ("routeKey", "strategy", "symbol", "timeframe", "variant", "score", "rank", "parameterSummary", "presetName"):
        if merged.get(key) in (None, "") and metadata.get(key) not in (None, ""):
            merged[key] = metadata.get(key)
    return merged


def result_from_record(
    record: dict[str, Any],
    metadata: dict[str, Any],
    report_path: Path | None,
    match_type: str,
    min_trades: int,
) -> dict[str, Any]:
    enriched = fill_from_metadata(record, metadata)
    if report_exists(report_path):
        metrics = parse_report(report_path)
    else:
        metrics = reusable_task_metrics(enriched) or {
            "reportExists": False,
            "parseStatus": "PENDING_REPORT",
            "closedTrades": None,
            "netProfit": None,
            "profitFactor": None,
            "winRate": None,
            "maxDrawdown": None,
            "relativeDrawdownPct": None,
        }
    score, grade, readiness, blockers = score_result(metrics, min_trades)
    status = metrics.get("parseStatus") or "PENDING_REPORT"
    return {
        "runId": enriched.get("runId", ""),
        "runMode": enriched.get("runMode", ""),
        "runGeneratedAtIso": enriched.get("runGeneratedAtIso", ""),
        "candidateId": enriched.get("candidateId", ""),
        "routeKey": enriched.get("routeKey", ""),
        "symbol": enriched.get("symbol", ""),
        "timeframe": enriched.get("timeframe", ""),
        "variant": enriched.get("variant", ""),
        "configPath": str(enriched.get("configPath") or ""),
        "reportPath": str(report_path or enriched.get("reportPath") or ""),
        "presetPath": str(enriched.get("presetPath") or ""),
        "status": status,
        "resultScore": score,
        "grade": grade,
        "promotionReadiness": readiness,
        "blockers": blockers,
        "metrics": metrics,
        "watcher": {
            "source": enriched.get("source", ""),
            "matchType": match_type,
            "reportDiscovered": bool(metrics.get("reportExists")),
            "reportModifiedAtIso": iso_from_mtime(report_path if report_exists(report_path) else None),
            "statusPath": enriched.get("statusPath", ""),
        },
    }


def previous_parsed_candidates(results_doc: dict[str, Any]) -> set[str]:
    parsed: set[str] = set()
    for row in safe_list(results_doc.get("results")):
        row = safe_dict(row)
        candidate_id = str(row.get("candidateId") or "")
        if candidate_id and safe_dict(row.get("metrics")).get("reportExists"):
            parsed.add(candidate_id)
    return parsed


def infer_run_id_from_path(path: Path, archive_root: Path) -> str:
    try:
        relative = path.relative_to(archive_root)
        if relative.parts:
            return relative.parts[0]
    except ValueError:
        pass
    return ""


def append_orphan_reports(
    *,
    results: list[dict[str, Any]],
    used_reports: set[str],
    report_files: list[Path],
    candidate_metadata: dict[str, dict[str, Any]],
    archive_root: Path,
    min_trades: int,
) -> int:
    orphan_count = 0
    candidate_ids = list(candidate_metadata.keys())
    for path in report_files:
        key = str(path.resolve()).lower()
        if key in used_reports:
            continue
        candidate_id = report_candidates_from_file(path, candidate_ids)
        if not candidate_id:
            continue
        metadata = candidate_metadata.get(candidate_id, {})
        record = {
            "source": "orphan_report",
            "runId": infer_run_id_from_path(path, archive_root),
            "runMode": "STRATEGY_TESTER_REPORT_DISCOVERED",
            "candidateId": candidate_id,
            "reportPath": path,
        }
        results.append(result_from_record(record, metadata, path, "orphan_candidate_filename", min_trades))
        used_reports.add(key)
        orphan_count += 1
    return orphan_count


def best_results_by_candidate(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for result in results:
        candidate_id = str(result.get("candidateId") or "")
        if not candidate_id:
            continue
        previous = best.get(candidate_id)
        if previous is None or float(result.get("resultScore") or 0) > float(previous.get("resultScore") or 0):
            best[candidate_id] = result
    return best


def annotate_auto_scheduler(scheduler_path: Path, scheduler: dict[str, Any], results: list[dict[str, Any]]) -> None:
    if not scheduler:
        return
    best = best_results_by_candidate(results)
    for key in ("selectedTasks", "backtestTasks"):
        for task in safe_list(scheduler.get(key)):
            task = safe_dict(task)
            result = best.get(str(task.get("candidateId") or ""))
            if not result:
                continue
            task["resultStatus"] = result.get("status")
            task["resultScore"] = result.get("resultScore")
            task["resultGrade"] = result.get("grade")
            task["promotionReadiness"] = result.get("promotionReadiness")
            task["metrics"] = result.get("metrics", {})
            task["resolvedReportPath"] = result.get("reportPath", "")
            task["reportWatcherMatchType"] = safe_dict(result.get("watcher")).get("matchType", "")
    scheduler["paramLabReportWatcherLatest"] = {
        "generatedAtIso": datetime.now(timezone.utc).isoformat(),
        "resultCount": len(results),
        "parsedReportCount": sum(1 for item in results if safe_dict(item.get("metrics")).get("reportExists")),
    }
    write_json(scheduler_path, scheduler)


def write_result_ledger(path: Path, results: list[dict[str, Any]], generated_at: str) -> None:
    rows = []
    for item in results:
        metrics = safe_dict(item.get("metrics"))
        watcher = safe_dict(item.get("watcher"))
        rows.append({
            "GeneratedAtIso": generated_at,
            "RunId": item.get("runId", ""),
            "CandidateId": item.get("candidateId", ""),
            "RouteKey": item.get("routeKey", ""),
            "Symbol": item.get("symbol", ""),
            "Timeframe": item.get("timeframe", ""),
            "Variant": item.get("variant", ""),
            "Status": item.get("status", ""),
            "ResultScore": item.get("resultScore", ""),
            "Grade": item.get("grade", ""),
            "PromotionReadiness": item.get("promotionReadiness", ""),
            "ClosedTrades": metrics.get("closedTrades"),
            "ProfitFactor": metrics.get("profitFactor"),
            "WinRate": metrics.get("winRate"),
            "NetProfit": metrics.get("netProfit"),
            "MaxDrawdown": metrics.get("maxDrawdown"),
            "RelativeDrawdownPct": metrics.get("relativeDrawdownPct"),
            "Blockers": "/".join(item.get("blockers") or []),
            "WatcherSource": watcher.get("source", ""),
            "WatcherMatchType": watcher.get("matchType", ""),
            "ReportModifiedAtIso": watcher.get("reportModifiedAtIso", ""),
            "ReportPath": item.get("reportPath", ""),
        })
    write_csv(path, rows, [
        "GeneratedAtIso",
        "RunId",
        "CandidateId",
        "RouteKey",
        "Symbol",
        "Timeframe",
        "Variant",
        "Status",
        "ResultScore",
        "Grade",
        "PromotionReadiness",
        "ClosedTrades",
        "ProfitFactor",
        "WinRate",
        "NetProfit",
        "MaxDrawdown",
        "RelativeDrawdownPct",
        "Blockers",
        "WatcherSource",
        "WatcherMatchType",
        "ReportModifiedAtIso",
        "ReportPath",
    ])


def write_watcher_ledger(path: Path, results: list[dict[str, Any]], generated_at: str) -> None:
    rows = []
    for item in results:
        metrics = safe_dict(item.get("metrics"))
        watcher = safe_dict(item.get("watcher"))
        rows.append({
            "GeneratedAtIso": generated_at,
            "CandidateId": item.get("candidateId", ""),
            "RouteKey": item.get("routeKey", ""),
            "Status": item.get("status", ""),
            "Grade": item.get("grade", ""),
            "ReportDiscovered": str(bool(metrics.get("reportExists"))).lower(),
            "MatchType": watcher.get("matchType", ""),
            "Source": watcher.get("source", ""),
            "ReportModifiedAtIso": watcher.get("reportModifiedAtIso", ""),
            "ReportPath": item.get("reportPath", ""),
        })
    write_csv(path, rows, [
        "GeneratedAtIso",
        "CandidateId",
        "RouteKey",
        "Status",
        "Grade",
        "ReportDiscovered",
        "MatchType",
        "Source",
        "ReportModifiedAtIso",
        "ReportPath",
    ])


def build_report_watcher(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_root = Path(args.repo_root)
    runtime_dir = Path(args.runtime_dir)
    archive_root = Path(args.archive_root) if args.archive_root else repo_root / "archive" / "param-lab" / "runs"
    plan_path = Path(args.plan) if args.plan else runtime_dir / PLAN_NAME
    scheduler_path = Path(args.scheduler) if args.scheduler else runtime_dir / AUTO_SCHEDULER_NAME
    output_path = Path(args.output) if args.output else runtime_dir / RESULTS_NAME
    watcher_path = Path(args.watcher_output) if args.watcher_output else runtime_dir / WATCHER_NAME
    ledger_path = Path(args.ledger) if args.ledger else runtime_dir / LEDGER_NAME
    watcher_ledger_path = Path(args.watcher_ledger) if args.watcher_ledger else runtime_dir / WATCHER_LEDGER_NAME

    plan = read_json(plan_path)
    scheduler = read_json(scheduler_path)
    previous_results = read_json(output_path)
    previous_parsed = previous_parsed_candidates(previous_results)
    status_docs = load_status_documents(runtime_dir / STATUS_NAME, archive_root)
    metadata = build_candidate_metadata(plan, scheduler, status_docs)
    known_records = build_known_records(repo_root, plan, scheduler, status_docs)
    candidate_ids = sorted(metadata.keys())

    scan_roots = [archive_root, repo_root / "archive" / "param-lab"]
    scan_roots.extend(Path(root) for root in args.scan_root if str(root).strip())
    report_files = discover_report_files(scan_roots)
    report_by_candidate, report_by_stem = index_report_files(report_files, candidate_ids)

    results: list[dict[str, Any]] = []
    used_reports: set[str] = set()
    for record in known_records:
        candidate_id = str(record.get("candidateId") or "")
        report_path, match_type = resolve_report_path(
            candidate_id=candidate_id,
            expected_path=record.get("reportPath"),
            report_by_candidate=report_by_candidate,
            report_by_stem=report_by_stem,
        )
        metadata_row = metadata.get(candidate_id, {})
        result = result_from_record(record, metadata_row, report_path, match_type, args.min_trades)
        results.append(result)
        if report_exists(report_path):
            used_reports.add(str(report_path.resolve()).lower())

    orphan_count = append_orphan_reports(
        results=results,
        used_reports=used_reports,
        report_files=report_files,
        candidate_metadata=metadata,
        archive_root=archive_root,
        min_trades=args.min_trades,
    )

    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for result in results:
        report_key = str(result.get("reportPath") or "")
        key = (
            str(result.get("candidateId") or ""),
            report_key or str(result.get("runId") or ""),
            "report" if report_key else "run",
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = result
            continue
        existing_has_report = safe_dict(existing.get("metrics")).get("reportExists")
        result_has_report = safe_dict(result.get("metrics")).get("reportExists")
        if result_has_report and not existing_has_report:
            deduped[key] = result
        elif result_has_report == existing_has_report and float(result.get("resultScore") or 0) > float(existing.get("resultScore") or 0):
            deduped[key] = result
    results = list(deduped.values())
    results.sort(key=lambda item: (
        str(item.get("routeKey")),
        0 if safe_dict(item.get("metrics")).get("reportExists") else 1,
        -float(item.get("resultScore") or 0),
        str(item.get("candidateId")),
    ))

    top_by_route = top_results_by_route(results)
    parsed = sum(1 for item in results if safe_dict(item.get("metrics")).get("reportExists"))
    malformed = sum(1 for item in results if str(item.get("status")) == "REPORT_FOUND_UNPARSED")
    pending = len(results) - parsed
    promotion_ready = sum(1 for item in results if item.get("promotionReadiness") == "PROMOTION_REVIEW_READY")
    newly_parsed = sum(
        1 for item in results
        if str(item.get("candidateId") or "") not in previous_parsed
        and safe_dict(item.get("metrics")).get("reportExists")
    )
    generated_at = datetime.now(timezone.utc).isoformat()

    output = {
        "schemaVersion": 2,
        "source": "QuantGod ParamLab Report Watcher",
        "generatedAtIso": generated_at,
        "runtimeDir": str(runtime_dir),
        "archiveRoot": str(archive_root),
        "mode": "REPORT_WATCHER_RESULT_LEDGER",
        "summary": {
            "statusDocumentCount": len(status_docs),
            "knownTaskCount": len(known_records),
            "reportFileCount": len(report_files),
            "discoveredReportCount": parsed,
            "parsedReportCount": parsed,
            "malformedReportCount": malformed,
            "pendingReportCount": pending,
            "orphanReportCount": orphan_count,
            "newlyParsedReportCount": newly_parsed,
            "resultCount": len(results),
            "promotionReadyCount": promotion_ready,
            "topRouteCount": len(top_by_route),
            "runTerminal": False,
            "livePresetMutation": False,
        },
        "topByRoute": top_by_route,
        "results": results,
        "hardGuards": [
            "No terminal is launched by the report watcher.",
            "No live preset is mutated.",
            "No broker connection or OrderSend path is touched.",
            "Only Strategy Tester report files are parsed into advisory result evidence.",
        ],
        "nextOperatorSteps": [
            "Run authorized Strategy Tester tasks only when allowed, then rerun this watcher.",
            "Use parsed PF, win rate, net profit, trades, and drawdown as version evidence.",
            "Keep pending or malformed reports out of promotion evidence.",
        ],
    }

    watcher = {
        "schemaVersion": 1,
        "source": "QuantGod ParamLab Report Watcher",
        "generatedAtIso": generated_at,
        "runtimeDir": str(runtime_dir),
        "archiveRoot": str(archive_root),
        "mode": "FILE_ONLY_REPORT_WATCHER",
        "summary": output["summary"],
        "scanRoots": [str(root) for root in scan_roots],
        "reportFiles": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "modifiedAtIso": iso_from_mtime(path),
                "matchedCandidateId": report_candidates_from_file(path, candidate_ids),
            }
            for path in report_files
        ],
        "watchedResults": results,
        "hardGuards": output["hardGuards"],
    }

    write_json(output_path, output)
    write_json(watcher_path, watcher)
    write_result_ledger(ledger_path, results, generated_at)
    write_watcher_ledger(watcher_ledger_path, results, generated_at)
    if plan:
        annotate_plan(plan, results, plan_path)
    annotate_auto_scheduler(scheduler_path, scheduler, results)
    return output, watcher


def main() -> int:
    args = parse_args()
    try:
        output, watcher = build_report_watcher(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    summary = output["summary"]
    watcher_path = Path(args.watcher_output) if args.watcher_output else Path(args.runtime_dir) / WATCHER_NAME
    output_path = Path(args.output) if args.output else Path(args.runtime_dir) / RESULTS_NAME
    print(f"Wrote {watcher_path}")
    print(f"Wrote {output_path}")
    print(
        "ParamLab report watcher: "
        f"tasks={summary['knownTaskCount']} reports={summary['reportFileCount']} "
        f"parsed={summary['parsedReportCount']} pending={summary['pendingReportCount']} "
        f"new={summary['newlyParsedReportCount']} malformed={summary['malformedReportCount']}"
    )
    print(
        "Guards: "
        f"runTerminal={summary['runTerminal']} livePresetMutation={summary['livePresetMutation']} "
        f"scanRoots={len(watcher.get('scanRoots') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
