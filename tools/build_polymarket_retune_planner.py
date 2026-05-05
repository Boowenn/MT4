#!/usr/bin/env python3
"""Build shadow-only Polymarket retune recommendations for QuantGod.

The planner consumes the read-only research bridge output and produces
screenable retune ideas. It never imports the Polymarket runtime, never loads
wallet code, never places orders, and never changes MT5 state.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(r"C:\Program Files\HFM Metatrader 5\MQL5\Files")
DEFAULT_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "Dashboard"
RESEARCH_NAME = "QuantGod_PolymarketResearch.json"
OUTPUT_NAME = "QuantGod_PolymarketRetunePlanner.json"
LEDGER_NAME = "QuantGod_PolymarketRetunePlanner.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--dashboard-dir", default=str(DEFAULT_DASHBOARD_DIR))
    parser.add_argument("--research-path", default="")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return int(value)
    except (TypeError, ValueError):
        return default


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_bucket(item: dict[str, Any]) -> dict[str, Any]:
    closed = safe_int(item.get("closed"))
    wins = safe_int(item.get("wins"))
    pnl = safe_number(item.get("realizedPnl"))
    gross_win = safe_number(item.get("grossWin"))
    gross_loss = safe_number(item.get("grossLoss"))
    pf_raw = item.get("profitFactor")
    pf = None if pf_raw in (None, "") else safe_number(pf_raw)
    win_rate_raw = item.get("winRatePct")
    win_rate = None if win_rate_raw in (None, "") else safe_number(win_rate_raw)
    avg = safe_number(item.get("avgPnl")) if item.get("avgPnl") is not None else (pnl / closed if closed else 0.0)
    return {
        "closed": closed,
        "wins": wins,
        "losses": safe_int(item.get("losses")),
        "realizedPnl": round(pnl, 4),
        "grossWin": round(gross_win, 4),
        "grossLoss": round(gross_loss, 4),
        "profitFactor": pf,
        "winRatePct": win_rate,
        "avgPnl": round(avg, 4),
    }


def infer_family(key: str, scope: str, source: str = "") -> str:
    lowered = f"{key} {scope} {source}".lower()
    if "copy_archive" in lowered or "copy" in lowered:
        return "copy_archive"
    if "edge_filter" in lowered:
        return "edge_filter"
    if "stage2" in lowered or "repeat" in lowered or "delayed" in lowered:
        return "stage2_recheck"
    if "baseline" in lowered:
        return f"baseline_{scope or 'unknown'}"
    return "unknown"


def severity_and_action(metrics: dict[str, Any]) -> tuple[str, str, int]:
    closed = metrics["closed"]
    pnl = metrics["realizedPnl"]
    pf = metrics["profitFactor"]
    win_rate = metrics["winRatePct"]
    if closed < 10:
        return "gray", "COLLECT_SHADOW_ONLY", 20
    score = 50
    if pf is not None:
        score += min(max((pf - 1.0) * 35.0, -35.0), 25.0)
    if win_rate is not None:
        score += min(max((win_rate - 50.0) * 0.65, -30.0), 20.0)
    score += min(max(pnl * 0.18, -25.0), 15.0)
    score_int = max(0, min(100, round(score)))
    if (pf is not None and pf < 0.55) or (win_rate is not None and win_rate < 30) or pnl <= -20:
        return "red", "REBUILD_OR_RETIRE_CURRENT_FILTER", score_int
    if pnl < 0 or (pf is not None and pf < 1.0) or (win_rate is not None and win_rate < 50):
        return "yellow", "RETUNE_SHADOW_ONLY", score_int
    return "green", "KEEP_SHADOW_CANDIDATE_NO_LIVE", score_int


def issue_tags(metrics: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if metrics["closed"] < 10:
        tags.append("sample_too_small")
    if metrics["realizedPnl"] < 0:
        tags.append("negative_realized_pnl")
    if metrics["profitFactor"] is not None and metrics["profitFactor"] < 1:
        tags.append("profit_factor_below_1")
    if metrics["winRatePct"] is not None and metrics["winRatePct"] < 45:
        tags.append("win_rate_low")
    if metrics["avgPnl"] < 0:
        tags.append("negative_avg_pnl")
    return tags or ["no_major_metric_blocker_but_keep_shadow_only"]


def suggestions_for(family: str, scope: str, metrics: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    if family == "copy_archive":
        suggestions.extend(
            [
                "Shadow-only: prune copied traders/signals to those with fresh positive realized PnL and enough settled samples.",
                "Require copied market liquidity/spread sanity before recording a candidate; keep failed copy_archive rows as quarantine evidence.",
                "Split copied evidence by market category and source quality; do not treat sports, politics, macro, crypto, company events, and long-tail markets as one pool.",
            ]
        )
        if metrics["profitFactor"] is not None and metrics["profitFactor"] < 1.05:
            suggestions.append("Do not promote copy archive: require PF >= 1.10 and net positive shadow result after costs first.")
    elif family == "edge_filter":
        suggestions.extend(
            [
                "Shadow-only: raise score/liquidity thresholds and narrow the price band before collecting the next batch.",
                "Keep sports and esports filter families separate; a weak sports filter must not borrow esports evidence.",
                "Add a no-bet blocked reason for low confidence rather than widening the entry band.",
            ]
        )
        if scope == "sports":
            suggestions.append("For sports, test stricter pre-event lead windows and reject low-liquidity late markets.")
        elif scope == "esports":
            suggestions.append("For esports, require series/team context and avoid generic baseline entries.")
    elif family.startswith("baseline"):
        suggestions.extend(
            [
                "Treat baseline rows as control evidence only; do not promote a baseline route.",
                "Use baseline losses to identify which blocker families should get stricter shadow filters.",
            ]
        )
    else:
        suggestions.extend(
            [
                "Keep this group in research-only quarantine until the route is named and isolated.",
                "Add explicit experiment key, market scope, and blocker labels before comparing it with other routes.",
            ]
        )

    if metrics["winRatePct"] is not None and metrics["winRatePct"] < 35:
        suggestions.append("Low win rate: rebuild the selector before testing stake or exit changes.")
    if metrics["realizedPnl"] <= -20:
        suggestions.append("Large negative PnL: retire current params and start a smaller shadow batch with stricter filters.")
    return suggestions


def next_shadow_tests(family: str, scope: str, action: str) -> list[dict[str, str]]:
    if action == "COLLECT_SHADOW_ONLY":
        return [
            {
                "name": "sample_completion_gate",
                "goal": "Collect enough closed shadow samples before judging the route.",
                "mode": "shadow-only",
            }
        ]
    if family == "copy_archive":
        return [
            {
                "name": "copy_archive_all_market_whitelist_v2",
                "goal": "Replay only copied traders/signals with recent positive settled evidence across sports, politics, macro, crypto, company, culture, and long-tail markets; skip stale/illiquid markets.",
                "mode": "shadow-only",
            },
            {
                "name": "copy_archive_market_family_split_v1",
                "goal": "Split copy evidence by market family, signal source, copied trader, and liquidity so one weak category cannot hide inside pooled stats.",
                "mode": "shadow-only",
            },
            {
                "name": "copy_archive_source_quality_fusion_v1",
                "goal": "Fuse Telegram/source history, local radar score, probability band, liquidity, and settlement quality before admitting a copied signal.",
                "mode": "shadow-only",
            },
        ]
    if family == "edge_filter":
        prefix = "sports" if scope == "sports" else "esports"
        return [
            {
                "name": f"{prefix}_edge_filter_strict_score_liquidity_v2",
                "goal": "Raise score/liquidity gates and compare against current shadow baseline.",
                "mode": "shadow-only",
            },
            {
                "name": f"{prefix}_edge_filter_price_band_replay_v2",
                "goal": "Replay narrower price bands without changing live execution.",
                "mode": "shadow-only",
            },
        ]
    return [
        {
            "name": "route_identity_cleanup_v1",
            "goal": "Label this evidence family before any further optimization.",
            "mode": "shadow-only",
        }
    ]


def build_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    key = str(item.get("experimentKey") or "baseline")
    scope = str(item.get("marketScope") or "unknown")
    source = str(item.get("signalSource") or "")
    metrics = metric_bucket(item)
    severity, action, score = severity_and_action(metrics)
    family = infer_family(key, scope, source)
    return {
        "experimentKey": key,
        "routeFamily": family,
        "marketScope": scope,
        "signalSource": source or "unknown",
        "strategyRole": "copy_trading_shadow" if family == "copy_archive" else "autonomous_filter_shadow",
        "operatorLabel": (
            "跟单策略模拟" if family == "copy_archive" else
            "雷达筛选模拟" if family == "edge_filter" else
            "基准/对照样本" if family.startswith("baseline") else
            "未归类研究样本"
        ),
        "severity": severity,
        "score": score,
        "primaryAction": action,
        "shadowOnly": True,
        "liveExecutionAllowed": False,
        "issueTags": issue_tags(metrics),
        "metrics": metrics,
        "filterSuggestions": suggestions_for(family, scope, metrics),
        "nextShadowTests": next_shadow_tests(family, scope, action),
    }


def copy_capital_simulation(metrics: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    cash = safe_number(account.get("accountCash"), 0.0)
    bankroll = safe_number(account.get("bankroll"), 0.0)
    effective_cash = cash if cash > 0 else bankroll
    effective_bankroll = min(cash, bankroll) if cash > 0 and bankroll > 0 else max(cash, bankroll)
    gross_win = abs(safe_number(metrics.get("grossWin"), 0.0))
    gross_loss = abs(safe_number(metrics.get("grossLoss"), 0.0))
    closed = safe_int(metrics.get("closed"))
    exposure_proxy = max(gross_win + gross_loss, float(closed), 1.0)
    ledger_pnl = safe_number(metrics.get("realizedPnl"), 0.0)
    exposure_return = ledger_pnl / exposure_proxy
    cash_scaled_pnl = exposure_return * effective_cash
    bankroll_scaled_pnl = exposure_return * effective_bankroll
    restored_review_eligible = (
        closed >= 200
        and safe_number(metrics.get("profitFactor"), 0.0) >= 1.10
        and safe_number(metrics.get("winRatePct"), 0.0) >= 52.0
        and cash_scaled_pnl > 0
    )
    return {
        "method": "shadow_pnl_normalized_by_absolute_settled_pnl_proxy",
        "accountCashUSDC": round(cash, 6),
        "configuredBankrollUSDC": round(bankroll, 6),
        "effectiveCashUSDC": round(effective_cash, 6),
        "effectiveBankrollUSDC": round(effective_bankroll, 6),
        "shadowLedgerPnlUSDC": round(ledger_pnl, 6),
        "settledExposureProxyUSDC": round(exposure_proxy, 6),
        "estimatedReturnPct": round(exposure_return * 100.0, 4),
        "cashScaledPnlUSDC": round(cash_scaled_pnl, 6),
        "bankrollScaledPnlUSDC": round(bankroll_scaled_pnl, 6),
        "restoreLiveReviewEligible": restored_review_eligible,
        "restoreLiveReviewBlockers": [] if restored_review_eligible else [
            blocker for blocker in [
            "sample_lt_200" if closed < 200 else "",
            "pf_lt_1_10" if safe_number(metrics.get("profitFactor"), 0.0) < 1.10 else "",
            "win_rate_lt_52" if safe_number(metrics.get("winRatePct"), 0.0) < 52.0 else "",
            "cash_scaled_pnl_not_positive" if cash_scaled_pnl <= 0 else "",
            ] if blocker
        ],
        "note": "这是按当前只读资金规模做的 shadow accounting 估算，不会连接钱包、不会恢复真钱执行。",
    }


def copy_source_toolkit() -> list[dict[str, str]]:
    return [
        {
            "source": "Telegram signals",
            "mode": "operator-approved-channel-or-export-only",
            "use": "只读取你授权的频道、机器人推送或导出的历史消息，把信号转成 shadow copy 样本。",
        },
        {
            "source": "Public leaderboards / copied traders",
            "mode": "public-readonly",
            "use": "按历史结算表现、样本数、市场家族和流动性筛选可复制信号。",
        },
        {
            "source": "QuantGod radar / AI score",
            "mode": "local-evidence-fusion",
            "use": "把外部跟单信号与本地雷达评分交叉验证，低置信度只记录为隔离证据。",
        },
        {
            "source": "Manual watchlist",
            "mode": "human-curated-shadow-only",
            "use": "人工加入观察名单后，只跑模拟账本；达到恢复门槛也只进入人工确认。",
        },
    ]


def copy_iteration_plan(
    best: dict[str, Any],
    metrics: dict[str, Any],
    capital_simulation: dict[str, Any],
    needs_retune: bool,
) -> dict[str, Any]:
    experiment = str(best.get("experimentKey") or "copy_archive_shadow")
    scope = str(best.get("marketScope") or "unknown")
    blockers = list(capital_simulation.get("restoreLiveReviewBlockers") or [])
    return {
        "retuneRequired": bool(needs_retune),
        "currentExperimentKey": experiment,
        "currentMarketScope": scope,
        "diagnosis": (
            f"当前最佳跟单样本来自 {scope}，样本 {safe_int(metrics.get('closed'))}，"
            f"PF {safe_number(metrics.get('profitFactor')):.4g}，胜率 {safe_number(metrics.get('winRatePct')):.2f}%，"
            f"账本净值 {safe_number(metrics.get('realizedPnl')):.4g} USDC；"
            + (
                "还不能证明跟单策略有可恢复真钱的稳定 edge。"
                if needs_retune else
                "已达到观察门槛，但真钱恢复仍需人工确认钱包、限额和隔离边界。"
            )
        ),
        "copyUniverse": [
            "sports",
            "esports",
            "politics",
            "macro",
            "crypto",
            "company_events",
            "culture",
            "long_tail",
        ],
        "candidateVariants": [
            {
                "key": "copy_archive_all_market_whitelist_v2",
                "goal": "全市场跟单白名单：只保留近期结算为正、样本充足、流动性达标的来源。",
            },
            {
                "key": "copy_archive_market_family_split_v1",
                "goal": "按市场家族拆账，不允许 sports/esports/politics/crypto 等互相掩盖亏损。",
            },
            {
                "key": "copy_archive_source_quality_fusion_v1",
                "goal": "把 Telegram/公开强账户信号与本地雷达评分、概率区间、成交深度交叉验证。",
            },
            {
                "key": "copy_archive_negative_source_blacklist_v1",
                "goal": "近期负收益或连续错判来源进入冷却黑名单，只保留为隔离证据。",
            },
        ],
        "acceptanceCriteria": [
            "closed >= 200",
            "profitFactor >= 1.10",
            "winRatePct >= 52",
            "cashScaledPnlUSDC > 0",
            "no single market family contributes more than 45% of positive evidence",
        ],
        "capitalResult": {
            "cashScaledPnlUSDC": capital_simulation.get("cashScaledPnlUSDC"),
            "estimatedReturnPct": capital_simulation.get("estimatedReturnPct"),
            "restoreLiveReviewEligible": capital_simulation.get("restoreLiveReviewEligible"),
            "blockers": blockers,
        },
        "nextAction": (
            "生成上述 shadow-only retune 批次；通过前禁止真钱下注、钱包写入或自动恢复执行。"
            if needs_retune else
            "保持 shadow watch；若连续批次仍通过，再进入人工恢复复核。"
        ),
    }


def copy_trading_review(recommendations: list[dict[str, Any]], account: dict[str, Any]) -> dict[str, Any]:
    copy_rows = [row for row in recommendations if row.get("routeFamily") == "copy_archive"]
    copy_rows.sort(key=lambda row: (
        safe_number((row.get("metrics") or {}).get("profitFactor"), -1.0),
        safe_number((row.get("metrics") or {}).get("realizedPnl"), -9999.0),
    ), reverse=True)
    if not copy_rows:
        return {
            "status": "NO_COPY_TRADING_SHADOW_EVIDENCE",
            "active": False,
            "summary": "当前没有跟单策略模拟样本；预测市场只在跑雷达/基准筛选。",
            "bestExperimentKey": "",
            "sourceToolkit": copy_source_toolkit(),
            "nextActions": ["先收集 copy_archive shadow 样本，再比较跟单与自主雷达筛选。"],
        }
    best = copy_rows[0]
    metrics = best.get("metrics") or {}
    pf = safe_number(metrics.get("profitFactor"))
    pnl = safe_number(metrics.get("realizedPnl"))
    closed = safe_int(metrics.get("closed"))
    win_rate = safe_number(metrics.get("winRatePct"))
    needs_retune = best.get("primaryAction") != "KEEP_SHADOW_CANDIDATE_NO_LIVE" or pf < 1.1 or pnl <= 0
    capital_simulation = copy_capital_simulation(metrics, account)
    iteration_plan = copy_iteration_plan(best, metrics, capital_simulation, needs_retune)
    scope = str(best.get("marketScope") or "unknown")
    return {
        "status": "COPY_TRADING_RETUNE_REQUIRED" if needs_retune else "COPY_TRADING_SHADOW_WATCH",
        "operatorStatusLabel": "需要重调跟单筛选" if needs_retune else "跟单模拟观察",
        "active": True,
        "summary": (
            f"正在模拟跟单策略，当前最佳样本来自 {scope}："
            f"样本 {closed}，PF {pf:.4g}，胜率 {win_rate:.2f}%，账本净值 {pnl:.4g} USDC；"
            "下一轮会扩展到全市场模块并重新筛选来源。"
        ),
        "bestExperimentKey": best.get("experimentKey", ""),
        "bestMetrics": metrics,
        "capitalSimulation": capital_simulation,
        "iterationPlan": iteration_plan,
        "sourceToolkit": copy_source_toolkit(),
        "primaryAction": best.get("primaryAction", ""),
        "shadowOnly": True,
        "walletWriteAllowed": False,
        "orderSendAllowed": False,
        "nextActions": [
            "跟单策略继续 shadow-only：可跟任何市场模块，但只复制历史强交易员/强信号，不连接钱包。",
            "先剪掉近期负收益或样本不足的 copied trader，再按市场家族、来源质量和流动性分桶重放。",
            (
                "达到 PF >= 1.10、胜率 >= 52%、样本 >= 200、按当前资金估算净收益为正之前，不进入真钱恢复复核。"
                if not capital_simulation.get("restoreLiveReviewEligible") else
                "跟单结果已达到恢复复核门槛；仍需人工确认钱包、限额、隔离和单笔风险。"
            ),
        ],
    }


def enrich_group(item: dict[str, Any], journal_groups: list[dict[str, Any]]) -> dict[str, Any]:
    key = str(item.get("experimentKey") or "baseline")
    if item.get("marketScope") and item.get("signalSource"):
        return item
    matches = [
        row
        for row in journal_groups
        if str(row.get("sampleType") or "").lower() == "shadow"
        and str(row.get("experimentKey") or "baseline") == key
    ]
    if not matches:
        return item
    best = max(matches, key=lambda row: safe_int(row.get("entries")))
    enriched = dict(item)
    enriched.setdefault("marketScope", best.get("marketScope") or "")
    enriched.setdefault("signalSource", best.get("signalSource") or "")
    if not enriched.get("marketScope"):
        enriched["marketScope"] = best.get("marketScope") or ""
    if not enriched.get("signalSource"):
        enriched["signalSource"] = best.get("signalSource") or ""
    return enriched


def build_plan(research: dict[str, Any]) -> dict[str, Any]:
    groups = list(research.get("experimentGroups") or [])
    journal_groups = research.get("journalGroups") or []
    baseline_groups = [
        row
        for row in journal_groups
        if str(row.get("experimentKey") or "").lower() == "baseline"
        and str(row.get("sampleType") or "").lower() == "shadow"
    ]
    if baseline_groups:
        groups = [row for row in groups if str(row.get("experimentKey") or "").lower() != "baseline"]
    seen = {str(row.get("experimentKey") or "") for row in groups}
    for row in baseline_groups:
        label = f"baseline_{row.get('marketScope') or 'unknown'}_{row.get('signalSource') or 'unknown'}"
        if label in seen:
            continue
        copy_row = dict(row)
        copy_row["experimentKey"] = label
        groups.append(copy_row)
        seen.add(label)

    groups = [enrich_group(item, journal_groups) for item in groups]
    recommendations = [build_recommendation(item) for item in groups]
    recommendations.sort(key=lambda item: ({"red": 0, "yellow": 1, "gray": 2, "green": 3}.get(item["severity"], 9), -item["metrics"]["closed"]))
    account = research.get("accountSnapshot") or {}
    summary = research.get("summary") or {}
    executed = summary.get("executed") or {}
    shadow = summary.get("shadow") or {}
    blockers = list((research.get("governance") or {}).get("blockers") or [])
    if account.get("authState") == "read_only_ok" and safe_number(account.get("accountCash")) < safe_number(account.get("bankroll")):
        blockers.append("polymarket_account_cash_below_bankroll")
    if safe_number(executed.get("realizedPnl")) < 0:
        blockers.append("executed_loss_quarantine")
    if safe_number(shadow.get("realizedPnl")) < 0:
        blockers.append("shadow_recovery_negative")
    copy_review = copy_trading_review(recommendations, account)

    return {
        "generatedAtIso": utc_now_iso(),
        "mode": "POLYMARKET_RETUNE_PLANNER_SHADOW_ONLY",
        "status": "OK",
        "sourceResearchGeneratedAtIso": research.get("generatedAtIso", ""),
        "safety": {
            "shadowOnly": True,
            "placesOrders": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "loadsWallet": False,
            "boundary": "retune recommendations only; no betting, no CLOB orders, no MT5 mutation",
        },
        "decision": "SHADOW_ONLY_RETUNE_NO_BETTING",
        "account": {
            "authState": account.get("authState", "unknown"),
            "authOk": bool(account.get("authOk")),
            "accountCash": account.get("accountCash"),
            "bankroll": account.get("bankroll"),
            "cashVsBankroll": account.get("cashVsBankroll"),
            "openOrderCount": account.get("openOrderCount", 0),
            "funderMasked": account.get("funderMasked", ""),
            "note": "Polymarket account balance is intentionally separate from MT5 equity.",
        },
        "globalBlockers": sorted(set(str(x) for x in blockers if x)),
        "recommendationCounts": {
            "total": len(recommendations),
            "red": sum(1 for item in recommendations if item["severity"] == "red"),
            "yellow": sum(1 for item in recommendations if item["severity"] == "yellow"),
            "green": sum(1 for item in recommendations if item["severity"] == "green"),
            "gray": sum(1 for item in recommendations if item["severity"] == "gray"),
            "copyTrading": sum(1 for item in recommendations if item["routeFamily"] == "copy_archive"),
        },
        "copyTradingReview": copy_review,
        "recommendations": recommendations,
        "nextActions": [
            "Keep all Polymarket retunes shadow-only while executed and shadow evidence are negative.",
            "Start with red/yellow routes: rebuild filters, collect fresh shadow results, then compare by route family.",
            "Do not restore live canary or autonomous betting from this planner; it is a research queue only.",
        ],
    }


def unavailable_plan(reason: str, research_path: Path) -> dict[str, Any]:
    return {
        "generatedAtIso": utc_now_iso(),
        "mode": "POLYMARKET_RETUNE_PLANNER_SHADOW_ONLY",
        "status": "UNAVAILABLE",
        "decision": "SHADOW_ONLY_RETUNE_SOURCE_UNAVAILABLE",
        "sourcePath": str(research_path),
        "error": reason,
        "safety": {
            "shadowOnly": True,
            "placesOrders": False,
            "startsExecutor": False,
            "mutatesMt5": False,
            "loadsWallet": False,
            "boundary": "retune recommendations only; source unavailable",
        },
        "recommendations": [],
        "recommendationCounts": {"total": 0, "red": 0, "yellow": 0, "green": 0, "gray": 0},
        "globalBlockers": [reason],
        "nextActions": ["Generate QuantGod_PolymarketResearch.json first."],
    }


def write_outputs(plan: dict[str, Any], runtime_dir: Path, dashboard_dir: Path | None) -> None:
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    paths = [runtime_dir / OUTPUT_NAME]
    if dashboard_dir:
        paths.append(dashboard_dir / OUTPUT_NAME)
    for path in paths:
        atomic_write_text(path, text)

    rows = []
    for item in plan.get("recommendations") or []:
        metrics = item.get("metrics") or {}
        rows.append(
            {
                "generatedAtIso": plan.get("generatedAtIso", ""),
                "experimentKey": item.get("experimentKey", ""),
                "routeFamily": item.get("routeFamily", ""),
                "marketScope": item.get("marketScope", ""),
                "severity": item.get("severity", ""),
                "score": item.get("score", ""),
                "primaryAction": item.get("primaryAction", ""),
                "closed": metrics.get("closed", 0),
                "winRatePct": metrics.get("winRatePct", ""),
                "profitFactor": metrics.get("profitFactor", ""),
                "realizedPnl": metrics.get("realizedPnl", 0),
                "shadowOnly": item.get("shadowOnly", True),
                "liveExecutionAllowed": item.get("liveExecutionAllowed", False),
            }
        )
    ledger_paths = [runtime_dir / LEDGER_NAME] + ([dashboard_dir / LEDGER_NAME] if dashboard_dir else [])
    for path in ledger_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            fieldnames = [
                "generatedAtIso",
                "experimentKey",
                "routeFamily",
                "marketScope",
                "severity",
                "score",
                "primaryAction",
                "closed",
                "winRatePct",
                "profitFactor",
                "realizedPnl",
                "shadowOnly",
                "liveExecutionAllowed",
            ]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    dashboard_dir = Path(args.dashboard_dir) if args.dashboard_dir else None
    research_path = Path(args.research_path) if args.research_path else runtime_dir / RESEARCH_NAME
    if not research_path.exists() and dashboard_dir and (dashboard_dir / RESEARCH_NAME).exists():
        research_path = dashboard_dir / RESEARCH_NAME
    try:
        research = load_json(research_path)
        plan = build_plan(research)
    except Exception as exc:
        plan = unavailable_plan(f"{type(exc).__name__}: {str(exc)[:220]}", research_path)
    write_outputs(plan, runtime_dir, dashboard_dir)
    counts = plan.get("recommendationCounts") or {}
    print(
        f"{OUTPUT_NAME}: {plan.get('status')} | decision={plan.get('decision')} | "
        f"red={counts.get('red', 0)} yellow={counts.get('yellow', 0)} | runtime={runtime_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
