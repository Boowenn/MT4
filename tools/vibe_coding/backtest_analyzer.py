"""AI-style analyzer for Vibe Coding backtest results."""

from __future__ import annotations

from .config import phase3_vibe_safety
from .strategy_registry import utc_now


class BacktestAnalyzer:
    """Produces deterministic analysis with optional LLM-ready structure."""

    def analyze(self, strategy_id: str, backtest_result: dict) -> dict:
        metrics = backtest_result.get("metrics", {}) if isinstance(backtest_result, dict) else {}
        trades = int(metrics.get("trades") or 0)
        pf = float(metrics.get("profit_factor") or 0.0)
        win_rate = float(metrics.get("win_rate") or 0.0)
        net_pips = float(metrics.get("net_pips") or 0.0)
        strengths: list[str] = []
        weaknesses: list[str] = []
        recommendations: list[str] = []

        if trades >= 20:
            strengths.append("sample size is usable for a first research pass")
        else:
            weaknesses.append("sample size is too small; run a longer backtest before trusting the result")
            recommendations.append("increase days or test multiple symbols/timeframes")
        if pf >= 1.3:
            strengths.append("profit factor is above the first-pass threshold")
        elif pf > 0:
            weaknesses.append("profit factor is below a robust promotion threshold")
            recommendations.append("tighten entry filters or improve exit logic before ParamLab review")
        else:
            weaknesses.append("no positive profit-factor evidence yet")
            recommendations.append("check whether the generated entry condition is too rare or inverted")
        if win_rate >= 0.5:
            strengths.append("win rate is at least 50% in the local research run")
        else:
            weaknesses.append("win rate is below 50%; risk/reward must compensate before governance review")
        if net_pips <= 0:
            recommendations.append("do not route this strategy to ParamLab promotion; iterate in Vibe Coding first")
        else:
            recommendations.append("send to ParamLab only as a tester-only candidate, never directly to live")

        readiness = "reject_or_iterate"
        if trades >= 20 and pf >= 1.3 and net_pips > 0:
            readiness = "paramlab_candidate"
        elif trades >= 10 and net_pips > 0:
            readiness = "needs_more_evidence"

        return {
            "ok": True,
            "schema": "quantgod.vibe_backtest_analysis.v1",
            "generatedAt": utc_now(),
            "strategy_id": strategy_id,
            "readiness": readiness,
            "summary": f"{trades} trades, PF={pf:.2f}, win_rate={win_rate:.1%}, net={net_pips:.1f} pips.",
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "governance_note": "Advisory only: must pass backtest → ParamLab → Governance → Version Gate → manual authorization before live consideration.",
            "safety": phase3_vibe_safety(),
        }
