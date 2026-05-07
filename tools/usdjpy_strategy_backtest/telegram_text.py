from __future__ import annotations

from typing import Any, Dict


def _fmt(value: Any, default: str = "—") -> str:
    if value in (None, ""):
        return default
    return str(value)


def backtest_to_chinese_text(payload: Dict[str, Any]) -> str:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else payload
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    lines = [
        "【QuantGod Strategy JSON 回测报告】",
        "",
        f"品种：{_fmt(report.get('symbol'), 'USDJPYc')}",
        f"策略：{_fmt(report.get('strategyFamily'))} / {_fmt(report.get('direction'))}",
        f"周期：{_fmt(report.get('timeframe'), 'H1')}",
        f"样本：K线 {_fmt(report.get('barCount'), '0')} / 交易 {_fmt(metrics.get('tradeCount'), '0')}",
        "",
        "核心指标：",
        f"- 净 R：{_fmt(metrics.get('netR'), '0')}",
        f"- Profit Factor：{_fmt(metrics.get('profitFactor'), '0')}",
        f"- 胜率：{_fmt(metrics.get('winRate'), '0')}%",
        f"- 最大回撤 R：{_fmt(metrics.get('maxDrawdownR'), '0')}",
        f"- Sharpe：{_fmt(metrics.get('sharpe'), '0')}",
        f"- Sortino：{_fmt(metrics.get('sortino'), '0')}",
        "",
        f"结论：{_fmt(report.get('reasonZh'), '等待回测数据')}",
        "",
        "安全边界：本回测只读取 Strategy JSON 和 USDJPY SQLite K线。",
        "不会下单、不会平仓、不会撤单、不会修改 live preset。",
    ]
    return "\n".join(lines)

