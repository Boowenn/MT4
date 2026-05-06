from __future__ import annotations

from typing import Any, Dict


def _fmt(value: Any, default: str = "—") -> str:
    if value in (None, ""):
        return default
    return str(value)


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"


def daily_autopilot_v2_to_chinese_text(payload: Dict[str, Any]) -> str:
    morning = payload.get("morningPlan") if isinstance(payload.get("morningPlan"), dict) else {}
    evening = payload.get("eveningReview") if isinstance(payload.get("eveningReview"), dict) else {}
    daily_todo = payload.get("dailyTodo") if isinstance(payload.get("dailyTodo"), dict) else {}
    daily_review = payload.get("dailyReview") if isinstance(payload.get("dailyReview"), dict) else {}
    review_metrics = daily_review.get("metrics") if isinstance(daily_review.get("metrics"), dict) else {}
    live = morning.get("liveLane") if isinstance(morning.get("liveLane"), dict) else {}
    mt5 = morning.get("mt5ShadowLane") if isinstance(morning.get("mt5ShadowLane"), dict) else {}
    mt5_summary = mt5.get("summary") if isinstance(mt5.get("summary"), dict) else {}
    polymarket = morning.get("polymarketShadowLane") if isinstance(morning.get("polymarketShadowLane"), dict) else {}
    poly_summary = polymarket.get("summary") if isinstance(polymarket.get("summary"), dict) else {}
    evening_live = evening.get("liveLane") if isinstance(evening.get("liveLane"), dict) else {}
    evening_mt5 = evening.get("mt5ShadowLane") if isinstance(evening.get("mt5ShadowLane"), dict) else {}
    lines = [
        "【QuantGod 今日自动作战计划】",
        "",
        f"账户模式：{_fmt(morning.get('accountMode'), 'cent')} / {_fmt(morning.get('accountCurrencyUnit'), 'USC')}",
        f"实盘车道：{_fmt(live.get('symbol'), 'USDJPYc')} {_fmt(live.get('strategy'), 'RSI_Reversal')} {_fmt(live.get('direction'), 'LONG')}",
        f"当前阶段：{_fmt(live.get('stageZh') or live.get('stage'))}",
        f"建议阶段仓位：{_num(live.get('stageMaxLot'))} / 最大上限 {_num(live.get('maxLot') or 2.0)}",
        "",
        "MT5 模拟车道：",
        f"- 路线：{_fmt(mt5_summary.get('routeCount'), '0')} 条",
        f"- 快速模拟：{_fmt(mt5_summary.get('fastShadow'), '0')}，测试器：{_fmt(mt5_summary.get('testerOnly'), '0')}，暂停：{_fmt(mt5_summary.get('paused'), '0')}",
        "",
        "Polymarket 模拟车道：",
        f"- 状态：{_fmt(polymarket.get('stageZh') or polymarket.get('stage'))}",
        f"- 模拟 PF：{_fmt(poly_summary.get('shadowProfitFactor'), '0')}，模拟净值：{_fmt(poly_summary.get('shadowNetUSDC'), '0')} USDC",
        "- 只做模拟账本和事件风险，不连接真实钱包。",
        "",
        "今日禁止：",
    ]
    for item in morning.get("todayForbiddenZh") or []:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "Agent 今日待办：",
        f"- 状态：{_fmt(daily_todo.get('status'), 'COMPLETED_BY_AGENT')}；无需人工回灌。",
        f"- 自动推动：{'是' if daily_todo.get('autoAppliedByAgent') else '否'}；回滚：{'是' if daily_todo.get('rollbackTriggered') else '否'}。",
        "",
        "【QuantGod 今日自动复盘】",
        f"Agent 版本：{_fmt(payload.get('agentVersion'), 'v2.4')}",
        f"Live 阶段：{_fmt(evening_live.get('stageZh') or evening_live.get('stage'))}",
        f"是否触发回滚：{'是' if evening_live.get('rollbackTriggered') else '否'}",
        f"净 R：{_fmt(review_metrics.get('netR'), '0')}；最大不利 R：{_fmt(review_metrics.get('maxAdverseR'))}；利润捕获：{_fmt(review_metrics.get('profitCaptureRatio'))}",
        f"错失机会：{_fmt(review_metrics.get('missedOpportunity'), '0')}；早出场改善：{_fmt(review_metrics.get('earlyExit'), '0')}",
        f"MT5 模拟：晋级/强化 {evening_mt5.get('promotedCount', 0)}，暂停 {evening_mt5.get('pausedCount', 0)}，淘汰 {evening_mt5.get('rejectedCount', 0)}",
        f"明日阶段：{_fmt(evening.get('tomorrowStageZh'))}",
        "",
        "安全边界：不会下单、不会平仓、不会撤单、不会修改订单或 live preset；DeepSeek 只解释，不批准越权；机器硬风控和自动回滚不可被取消。",
    ])
    return "\n".join(lines)
