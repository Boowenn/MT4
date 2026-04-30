#!/usr/bin/env python3
"""QuantGod MT5 read-only monitor for macOS/Codex automation.

The script only reads local evidence files and read-only dashboard APIs. It
never starts MT5, Strategy Tester, ParamLab run-terminal, or any live mutation
path.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MT5_PREFIX = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5"
DEFAULT_MT5_ROOT = DEFAULT_MT5_PREFIX / "drive_c/Program Files/MetaTrader 5"
DEFAULT_LIVE_PRESET = REPO_ROOT / "MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set"
REQUIRED_FILES = [
    "QuantGod_Dashboard.json",
    "QuantGod_MT5_ShadowStatus.txt",
    "QuantGod_TradeJournal.csv",
    "QuantGod_CloseHistory.csv",
    "QuantGod_TradeOutcomeLabels.csv",
    "QuantGod_TradeEventLinks.csv",
    "QuantGod_ShadowSignalLedger.csv",
    "QuantGod_ShadowOutcomeLedger.csv",
    "QuantGod_ShadowCandidateLedger.csv",
    "QuantGod_ShadowCandidateOutcomeLedger.csv",
    "QuantGod_BacktestSummary.json",
    "QuantGod_ParamLabStatus.json",
    "QuantGod_ParamLabResults.json",
    "QuantGod_ParamLabReportWatcher.json",
    "QuantGod_MT5ResearchStats.json",
    "QuantGod_MT5BackendBacktest.json",
    "QuantGod_GovernanceAdvisor.json",
    "QuantGod_MT5PendingOrderWorker.json",
]
PROTECTED_KEYWORDS = [
    "RSI_TIME_STOP",
    "RSI_FAILFAST",
    "routeProtect=RSI_FAST",
    "RSI H1 SELL blocked",
    "BlockSellInUptrend",
    "legacy route live switch disabled",
    "MA_Cross live switch disabled",
    "non-RSI legacy live authorization lock disabled",
    "STARTUP_GUARD",
]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def resolve_repo_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def is_mac_import_snapshot_dir(path: Path) -> bool:
    return "/runtime/mac_import/mt5_files_snapshot" in path.as_posix()


def resolve_runtime_dir(path: Path) -> Path:
    source_mode = os.environ.get("QG_MAC_RUNTIME_SOURCE", "auto").strip().lower()
    mt5_files = DEFAULT_MT5_ROOT / "MQL5/Files"
    if mt5_files.exists() and (
        source_mode == "mt5"
        or (source_mode == "auto" and is_mac_import_snapshot_dir(path))
    ):
        return mt5_files
    return path


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as exc:  # noqa: BLE001 - monitor reports parse failures.
        return None, str(exc)


def read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.count("\x00") > max(8, len(text) // 10):
            continue
        return text
    return raw.decode("utf-8", errors="replace")


def suspicious_evidence(path: Path) -> bool:
    text = read_text(path, max_bytes=200_000).lower()
    needles = [
        "ignore previous instructions",
        "system prompt",
        "you are now",
        "force enable",
        "override news block",
        "解除 cooldown",
        "放宽 gate",
        "强制 session",
        "修改 live preset",
        "请立即下单",
        "请立即平仓",
        "必须下单",
        "必须平仓",
    ]
    return any(needle in text for needle in needles)


def mtime_age_seconds(path: Path, now_ts: float) -> float:
    return max(0.0, now_ts - path.stat().st_mtime)


def get_nested(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        cur: Any = row
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool_text(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_set_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def preset_drift(values: dict[str, str]) -> list[str]:
    checks: list[tuple[str, str, str]] = [
        ("Watchlist", "eq", "USDJPY"),
        ("EnablePilotMA", "bool_false", ""),
        ("EnablePilotRsiH1Live", "bool_true", ""),
        ("EnablePilotBBH1Live", "bool_false", ""),
        ("EnablePilotMacdH1Live", "bool_false", ""),
        ("EnablePilotSRM15Live", "bool_false", ""),
        ("EnableNonRsiLegacyLiveAuthorization", "bool_false", ""),
        ("NonRsiLegacyLiveAuthorizationTag", "eq", ""),
        ("PilotRsiFailFastCloseOnMaxLoss", "bool_true", ""),
    ]
    drifts: list[str] = []
    for key, mode, expected in checks:
        actual = values.get(key, "")
        if mode == "eq" and actual != expected:
            drifts.append(f"PRESET_DRIFT:{key}")
        elif mode == "bool_true" and not as_bool_text(actual):
            drifts.append(f"PRESET_DRIFT:{key}")
        elif mode == "bool_false" and as_bool_text(actual):
            drifts.append(f"PRESET_DRIFT:{key}")
    numeric_checks = [
        ("PilotLotSize", "eq", 0.01),
        ("PilotMaxTotalPositions", "eq", 1.0),
        ("PilotNewsHighImpactPreBlockMinutes", "min", 60.0),
        ("PilotMaxFloatingLossUSC", "max", 30.0),
        ("PilotMaxRealizedLossDayUSC", "max", 60.0),
    ]
    for key, mode, expected in numeric_checks:
        actual = as_float(values.get(key), float("nan"))
        if mode == "eq" and abs(actual - expected) > 1e-9:
            drifts.append(f"PRESET_DRIFT:{key}")
        elif mode == "min" and actual < expected:
            drifts.append(f"PRESET_DRIFT:{key}")
        elif mode == "max" and actual > expected:
            drifts.append(f"PRESET_DRIFT:{key}")
    return drifts


def normalize_canonical(symbol: str) -> str:
    clean = re.sub(r"[^A-Za-z]", "", str(symbol or "")).upper()
    for suffix in ("RAW", "C", "M", "PRO"):
        if clean.endswith(suffix) and len(clean) > len(suffix) + 3:
            clean = clean[: -len(suffix)]
    return clean


def parse_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = read_text(path)
    try:
        return list(csv.DictReader(text.splitlines()))
    except csv.Error:
        return []


def is_today(value: str, today: datetime) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    candidates = [text[:10], text.replace(".", "-")[:10]]
    return any(part == today.strftime("%Y-%m-%d") for part in candidates)


def close_history_summary(path: Path, today: datetime) -> tuple[int, float, dict[str, float]]:
    rows = [row for row in parse_csv(path) if is_today(row.get("CloseTime", ""), today)]
    grouped: dict[str, float] = defaultdict(float)
    total = 0.0
    for row in rows:
        pnl = as_float(row.get("NetProfit"), 0.0)
        total += pnl
        key = f"{row.get('Strategy') or '--'}/{row.get('EntryRegime') or '--'}"
        grouped[key] += pnl
    return len(rows), round(total, 2), {k: round(v, 2) for k, v in grouped.items()}


def query_json(url: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def scan_logs(log_dir: Path, today: datetime) -> tuple[Counter[str], list[str]]:
    counts: Counter[str] = Counter()
    failures: list[str] = []
    if not log_dir.exists():
        return counts, failures
    today_key = today.strftime("%Y%m%d")
    for path in sorted(log_dir.glob("*.log")):
        if today_key not in path.name and datetime.fromtimestamp(path.stat().st_mtime, JST).date() != today.date():
            continue
        text = read_text(path, max_bytes=5_000_000)
        for key in PROTECTED_KEYWORDS:
            counts[key] += text.count(key)
        for match in re.finditer(r"pilot order failed.*?retcode[=: ]+([0-9]+)", text, flags=re.I):
            failures.append(match.group(1))
    return counts, failures


def scan_trade_permission_logs(log_dir: Path, today: datetime) -> list[str]:
    alerts: list[str] = []
    if not log_dir.exists():
        return alerts
    today_key = today.strftime("%Y%m%d")
    for path in sorted(log_dir.glob("*.log")):
        if today_key not in path.name and datetime.fromtimestamp(path.stat().st_mtime, JST).date() != today.date():
            continue
        text = read_text(path, max_bytes=5_000_000)
        if re.search(r"trading has been disabled\s*-\s*investor mode", text, flags=re.I):
            alerts.append("ACCOUNT_INVESTOR_MODE")
        if re.search(r"\[Trade disabled\]", text, flags=re.I):
            alerts.append("BROKER_TRADE_DISABLED")
    return sorted(set(alerts))


def news_isolation(now: datetime, dashboard: dict[str, Any] | None, shadow_text: str) -> list[str]:
    windows = [
        ("FOMC", datetime(2026, 4, 30, 3, 0, tzinfo=JST), datetime(2026, 4, 30, 2, 30, tzinfo=JST), datetime(2026, 4, 30, 4, 30, tzinfo=JST)),
        ("US GDP + Core PCE", datetime(2026, 4, 30, 21, 30, tzinfo=JST), datetime(2026, 4, 30, 21, 0, tzinfo=JST), datetime(2026, 4, 30, 23, 0, tzinfo=JST)),
    ]
    reminders: list[str] = []
    automated = get_nested(dashboard or {}, "runtime.automatedTradingEnabled", "automatedTradingEnabled")
    shadow_ok = bool(re.search(r"SHADOW|READ.?ONLY|非交易", shadow_text, flags=re.I))
    for name, event_at, off_at, on_at in windows:
        if off_at - timedelta(minutes=30) <= now <= off_at:
            reminders.append(f"{name}: {off_at.strftime('%H:%M')} 前手动关闭算法交易按钮。")
        elif off_at < now < on_at:
            verified = automated is False or str(automated).lower() == "false" or shadow_ok
            reminders.append(f"{name}: 隔离窗口内，{'已见只读/关闭证据' if verified else 'PHYSICAL_ISOLATION_UNVERIFIED'}。")
        elif on_at <= now <= on_at + timedelta(minutes=30):
            reminders.append(f"{name}: 窗口结束，可人工确认后恢复。")
    return reminders


def weekend_tasks(now: datetime) -> list[str]:
    if now.date().isoformat() not in {"2026-05-03", "2026-05-04"} or not (9 <= now.hour <= 22):
        return ["未到 2026-05-03/04 09:00-22:00 JST 周末验证窗口。"]
    day = now.date().isoformat()
    prefix = "5/3" if day == "2026-05-03" else "5/4 第二次提醒"
    return [
        f"{prefix}: 手动 Strategy Tester 验证 BB_Triple 越权 probe；期望 Journal 含 non-RSI authorization lock disabled 且 Total trades=0。",
        "同期手动复核 USDJPYc H1 RSI 85/15: PF>=1.2 且 trades>=30 才建议人工反驳 DEMOTE_REVIEW。",
    ]


def print_stale_only(
    run_id: str,
    elapsed_ms: int,
    build: str,
    stale_alerts: list[str],
    missing: list[str],
    reminders: list[str],
    suspicious: list[str],
) -> None:
    print("## 总览\n证据未通过 STEP 1，新鲜度失败后已停止 STEP 2-5；未执行任何交易或运行时变更。")
    print("\n## Evidence Freshness")
    for item in stale_alerts + [f"EVIDENCE_MISSING:{x}" for x in missing]:
        print(f"- {item}")
    for item in suspicious:
        print(f"- SUSPICIOUS_INSTRUCTION_IN_EVIDENCE:{item}")
    print("\n## News Isolation Reminder")
    print("- " + ("；".join(reminders) if reminders else "当前不在新闻隔离提醒窗口。"))
    audit = {
        "auditRow": {
            "runIdIso": run_id,
            "mode": "MT5_READONLY_MONITOR_MAC",
            "elapsedMs": elapsed_ms,
            "buildVersion": build,
            "presetCriticalDriftCount": 0,
            "openPositions": None,
            "pendingOrders": None,
            "rsiPF": None,
            "rsiWinRate": None,
            "rsiNetUSC": None,
            "rsiAdvisorAction": "",
            "evidenceStaleCount": len(stale_alerts) + len(missing),
            "logAnomalyCount": 0,
            "criticalAlerts": stale_alerts + [f"EVIDENCE_MISSING:{x}" for x in missing],
            "isolationReminders": reminders,
        }
    }
    print("\n```json")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("```")


def main() -> int:
    started = time.time()
    load_env_file(REPO_ROOT / ".env.local")
    load_env_file(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=os.environ.get("QG_RUNTIME_DIR") or os.environ.get("QG_MT5_FILES_DIR") or "")
    parser.add_argument("--dashboard-url", default=f"http://{os.environ.get('QG_DASHBOARD_HOST', '127.0.0.1')}:{os.environ.get('QG_DASHBOARD_PORT', '8080')}")
    parser.add_argument("--preset", default=os.environ.get("QG_HFM_LIVE_PRESET", ""))
    parser.add_argument("--mt5-root", default=os.environ.get("QG_MT5_ROOT", ""))
    args = parser.parse_args()

    now = datetime.now(JST)
    now_ts = time.time()
    run_id = now.isoformat()
    runtime_dir = resolve_runtime_dir(resolve_repo_path(args.runtime_dir, REPO_ROOT / "Dashboard"))
    mt5_root = resolve_repo_path(args.mt5_root, DEFAULT_MT5_ROOT)
    preset = resolve_repo_path(args.preset, DEFAULT_LIVE_PRESET)
    if not preset.exists():
        wine_preset = mt5_root / "MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set"
        preset = wine_preset if wine_preset.exists() else preset

    paths = {name: runtime_dir / name for name in REQUIRED_FILES}
    missing = [name for name, path in paths.items() if not path.exists()]
    suspicious = [name for name, path in paths.items() if path.exists() and suspicious_evidence(path)]
    dashboard_path = paths["QuantGod_Dashboard.json"]
    dashboard, dashboard_error = read_json(dashboard_path) if dashboard_path.exists() else (None, "missing")
    build = str(get_nested(dashboard or {}, "dashboardBuild", "build", "version", "buildVersion", default=""))
    shadow_text = read_text(paths["QuantGod_MT5_ShadowStatus.txt"])
    reminders = news_isolation(now, dashboard, shadow_text)

    stale_alerts: list[str] = []
    if not dashboard_path.exists():
        stale_alerts.append("EVIDENCE_MISSING:QuantGod_Dashboard.json")
    elif dashboard_error:
        stale_alerts.append(f"EVIDENCE_PARSE_FAIL:QuantGod_Dashboard.json:{dashboard_error}")
    else:
        age = mtime_age_seconds(dashboard_path, now_ts)
        if age >= 60:
            stale_alerts.append(f"EVIDENCE_STALE_DASHBOARD:{int(age)}s")

    gov_path = paths["QuantGod_GovernanceAdvisor.json"]
    gov, gov_error = read_json(gov_path) if gov_path.exists() else (None, "missing")
    advisor_stale = False
    if gov_path.exists() and mtime_age_seconds(gov_path, now_ts) >= 24 * 3600:
        advisor_stale = True
    if stale_alerts:
        print_stale_only(run_id, int((time.time() - started) * 1000), build, stale_alerts, missing, reminders, suspicious)
        return 0

    critical: list[str] = []
    version_match = re.search(r"QuantGod-v(\d+)\.(\d+)-mt5-([A-Za-z0-9_-]+)", build)
    if not version_match:
        critical.append("BUILD_PARSE_FAIL")
    else:
        major, minor, feature = int(version_match.group(1)), int(version_match.group(2)), version_match.group(3)
        if major < 3 or (major == 3 and minor <= 14):
            critical.append("BUILD_DOWNGRADE_DETECTED")
        elif major == 3 and minor < 17:
            critical.append("BUILD_BELOW_MIN_V3_17")
        if major == 3 and minor == 17 and "startup-entry-guard" not in feature:
            critical.append("BUILD_MISSING_STARTUP_ENTRY_GUARD")

    if not preset.exists():
        critical.append("PRESET_READ_FAILED")
        preset_values: dict[str, str] = {}
    else:
        preset_values = parse_set_file(preset)
        critical.extend(preset_drift(preset_values))
    if any(item.startswith("PRESET_DRIFT") or item == "PRESET_READ_FAILED" for item in critical):
        elapsed = int((time.time() - started) * 1000)
        print("## 总览\nSTEP 2 发现 preset/build critical，已按规则停止后续检查；未执行任何交易或运行时变更。")
        print("\n## Evidence Freshness\n- Dashboard fresh OK\n- Governance " + ("EVIDENCE_STALE_ADVISOR best-effort" if advisor_stale or gov_error else "fresh OK"))
        print("\n## Critical Drifts")
        for item in critical:
            print(f"- {item}")
        print("\n## News Isolation Reminder\n- " + ("；".join(reminders) if reminders else "当前不在新闻隔离提醒窗口。"))
        print("\n```json")
        print(json.dumps({"auditRow": {"runIdIso": run_id, "mode": "MT5_READONLY_MONITOR_MAC", "elapsedMs": elapsed, "buildVersion": build, "presetCriticalDriftCount": len(critical), "openPositions": None, "pendingOrders": None, "rsiPF": None, "rsiWinRate": None, "rsiNetUSC": None, "rsiAdvisorAction": "", "evidenceStaleCount": int(advisor_stale), "logAnomalyCount": 0, "criticalAlerts": critical, "isolationReminders": reminders}}, ensure_ascii=False, indent=2))
        print("```")
        return 0

    open_positions = list(get_nested(dashboard or {}, "openPositions", "openTrades", default=[]) or [])
    pending_orders = list(get_nested(dashboard or {}, "pendingOrders", default=[]) or [])
    sanity_alerts: list[str] = []
    if len(open_positions) > 1:
        sanity_alerts.append("POSITION_LIMIT_VIOLATION")
    canonical_counts: Counter[str] = Counter()
    for pos in open_positions:
        ticket = str(get_nested(pos, "ticket", "Ticket", "positionId", default="?"))
        symbol = str(get_nested(pos, "symbol", "Symbol", default=""))
        canonical_counts[normalize_canonical(symbol)] += 1
        volume = as_float(get_nested(pos, "volume", "lots", "Volume", default=0.0))
        if abs(volume - 0.01) > 1e-9:
            sanity_alerts.append(f"VOLUME_DRIFT:{ticket}")
        sl = as_float(get_nested(pos, "sl", "stopLoss", "SL", default=0.0))
        tp = as_float(get_nested(pos, "tp", "takeProfit", "TP", default=0.0))
        if sl == 0.0 or tp == 0.0:
            sanity_alerts.append(f"MISSING_SL_TP:{ticket}")
        magic = str(get_nested(pos, "magic", "Magic", default=""))
        comment = str(get_nested(pos, "comment", "Comment", default="")).lower()
        if magic not in {"520001", "520001.0"} and "manual" not in comment and "safety" not in comment:
            sanity_alerts.append(f"UNKNOWN_MAGIC:{ticket}")
    for canonical, count in canonical_counts.items():
        if canonical and count > 1:
            sanity_alerts.append(f"CANONICAL_DUPLICATE:{canonical}")
    for order in pending_orders:
        sanity_alerts.append(f"UNEXPECTED_PENDING:{get_nested(order, 'ticket', 'order', default='?')}")

    worker, _ = read_json(paths["QuantGod_MT5PendingOrderWorker.json"]) if paths["QuantGod_MT5PendingOrderWorker.json"].exists() else ({}, None)
    if worker:
        safety = worker.get("safety") if isinstance(worker.get("safety"), dict) else {}
        dry_run = get_nested(worker, "dryRun", "summary.dryRun", "safety.dryRun", default=True)
        kill = get_nested(worker, "killSwitch", "safety.killSwitch", default=True)
        order_send = get_nested(worker, "orderSendAllowed", "safety.orderSendAllowed", default=False)
        if dry_run is not True or kill is not True or order_send is not False:
            sanity_alerts.append("PENDING_WORKER_ARMED")
        _ = safety

    log_counts, order_failures = scan_logs(mt5_root / "MQL5/Logs", now)
    log_alerts = [f"ORDER_SEND_FAILURE:{code}" for code in order_failures]
    log_alerts.extend(scan_trade_permission_logs(mt5_root / "logs", now))
    for key, count in log_counts.items():
        if count > 5 and key in {"RSI_TIME_STOP", "RSI_FAILFAST"}:
            log_alerts.append(f"LOG_ANOMALY:{key}:{count}")
    candidate_rows = parse_csv(paths["QuantGod_ShadowCandidateLedger.csv"])
    today_non_rsi_candidate = any(
        is_today(row.get("Time") or row.get("generatedAt") or row.get("EventTime") or "", now)
        and str(row.get("Strategy") or row.get("strategy") or "").upper() in {"BB_TRIPLE", "MACD_DIVERGENCE", "SR_BREAKOUT"}
        for row in candidate_rows
    )
    if today_non_rsi_candidate and log_counts["non-RSI legacy live authorization lock disabled"] == 0:
        log_alerts.append("AUTH_LOCK_NEVER_TRIGGERED")

    close_count, close_net, grouped = close_history_summary(paths["QuantGod_CloseHistory.csv"], now)
    route_lines: list[str] = []
    rsi_pf = rsi_wr = rsi_net = None
    rsi_action = ""
    if gov and not advisor_stale:
        for row in gov.get("routeDecisions", [])[:8]:
            live_forward = row.get("liveForward") if isinstance(row.get("liveForward"), dict) else {}
            action = str(row.get("recommendedAction") or "")
            key = str(row.get("key") or "")
            if action == "DEMOTE_LIVE":
                critical.append(f"DEMOTE_LIVE:{key}")
            if key == "RSI_Reversal":
                rsi_pf = as_float(live_forward.get("profitFactor"), 0.0)
                rsi_wr = as_float(live_forward.get("winRatePct"), 0.0)
                rsi_net = as_float(live_forward.get("netProfitUSC"), 0.0)
                rsi_action = action
            blockers = ",".join(str(x) for x in row.get("blockers", []) if str(x) in {"consecutive_losses_ge_2", "consecutive_losses_ge_3", "drawdown_breach", "daily_loss_breach"})
            route_lines.append(f"{key}: live={row.get('live')} mode={row.get('mode')} action={action} PF={live_forward.get('profitFactor', '--')} WR={live_forward.get('winRatePct', '--')} net={live_forward.get('netProfitUSC', '--')} blockers={blockers or '--'}")

    rsi_notes: list[str] = []
    if rsi_pf is not None:
        if rsi_pf < 0.95:
            rsi_notes.append("RSI_PF_BELOW_0_95")
        if (rsi_wr or 0) < 50:
            rsi_notes.append("RSI_WINRATE_BELOW_50")
        if close_net <= -30:
            rsi_notes.append("DAILY_REALIZED_LOSS_GE_30")
        floating = as_float(get_nested(dashboard or {}, "account.profit", "brokerAccount.profit", default=0.0))
        if floating <= -15:
            rsi_notes.append("FLOATING_LOSS_GE_15")

    backend, _ = read_json(paths["QuantGod_MT5BackendBacktest.json"]) if paths["QuantGod_MT5BackendBacktest.json"].exists() else ({}, None)
    promotable = []
    for row in list(backend.get("topRows") or backend.get("rows") or [])[:12]:
        pf = as_float(row.get("profitFactor") or row.get("pf"), 0.0)
        if pf >= 1.0:
            promotable.append(str(row.get("candidateId") or row.get("route") or row.get("strategy") or "candidate"))

    elapsed = int((time.time() - started) * 1000)
    print("## 总览")
    print(f"build={build or '--'}；runtime={runtime_dir}；只读，无交易/配置变更。")
    print("\n## Evidence Freshness")
    print(f"- Dashboard fresh OK；Governance {'EVIDENCE_STALE_ADVISOR best-effort' if advisor_stale or gov_error else 'fresh OK'}")
    for item in missing:
        print(f"- EVIDENCE_MISSING:{item}")
    for item in suspicious:
        print(f"- SUSPICIOUS_INSTRUCTION_IN_EVIDENCE:{item}")
    print("\n## Critical Drifts")
    all_critical = critical + sanity_alerts + log_alerts
    print("- " + ("；".join(all_critical) if all_critical else "无 critical drift。"))
    print("\n## Daily P&L")
    print(f"- 今日 close={close_count}，net={close_net} USC，group={grouped or {}}")
    print("\n## Governance & RSI")
    print("- " + (" | ".join(route_lines[:5]) if route_lines else "Governance 缺失/陈旧，STEP 5.3 不评估。"))
    print("- RSI: " + (f"action={rsi_action or '--'} PF={rsi_pf} WR={rsi_wr}% net={rsi_net} notes={rsi_notes or '--'}" if rsi_pf is not None else "无新鲜 RSI 评估。"))
    if promotable:
        print(f"- BACKTEST_CANDIDATE_PROMOTABLE: {', '.join(promotable[:5])}")
    print("\n## News Isolation Reminder")
    print("- " + ("；".join(reminders) if reminders else "当前不在新闻隔离提醒窗口。"))
    print("\n## Weekend Tasks")
    print("- " + "；".join(weekend_tasks(now)))
    print("\n## Audit Row")
    audit = {
        "auditRow": {
            "runIdIso": run_id,
            "mode": "MT5_READONLY_MONITOR_MAC",
            "elapsedMs": elapsed,
            "buildVersion": build,
            "presetCriticalDriftCount": len([x for x in critical if x.startswith("PRESET")]),
            "openPositions": len(open_positions),
            "pendingOrders": len(pending_orders),
            "rsiPF": rsi_pf,
            "rsiWinRate": rsi_wr,
            "rsiNetUSC": rsi_net,
            "rsiAdvisorAction": rsi_action,
            "evidenceStaleCount": int(advisor_stale) + len(missing),
            "logAnomalyCount": len([x for x in log_alerts if x.startswith("LOG_ANOMALY")]),
            "criticalAlerts": all_critical,
            "isolationReminders": reminders,
        }
    }
    print("```json")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
