from __future__ import annotations

from typing import Any

def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "0.0%"

def _num(value: Any) -> str:
    try:
        return f"{float(value):+.3f}"
    except Exception:
        return "0.000"

def direction_cn(value: str | None) -> str:
    if value == "LONG":
        return "买入观察"
    if value == "SHORT":
        return "卖出观察"
    return "观望"

def state_cn(value: str | None) -> str:
    mapping = {
        "ACTIVE_SHADOW_OK": "允许影子观察",
        "WATCH_ONLY": "仅观察",
        "INSUFFICIENT_DATA": "样本不足",
        "PAUSED": "暂停",
        "NO_ROUTE": "无有效路线",
    }
    return mapping.get(str(value or ""), str(value or "未知"))

def build_policy_telegram_text(policy: dict[str, Any], symbol: str | None = None, max_routes: int = 5) -> str:
    routes = policy.get("routes", [])
    if symbol:
        routes = [r for r in routes if str(r.get("symbol", "")).upper() == symbol.upper()]
    gates = policy.get("entryGates", [])
    if symbol:
        gates = [g for g in gates if str(g.get("symbol", "")).upper() == symbol.upper()]
    plans = policy.get("dynamicSltpPlans", [])
    if symbol:
        plans = [p for p in plans if str(p.get("symbol", "")).upper() == symbol.upper()]

    quality = policy.get("dataQuality", {})
    lines: list[str] = [
        "【QuantGod 自适应策略审查】",
        "",
        f"生成时间：{policy.get('generatedAt', '未知')}",
        f"运行数据：快照 {quality.get('snapshotCount', 0)}；影子/复盘样本 {quality.get('observationCount', 0)}",
        "",
        "策略评分：",
    ]

    if not routes:
        lines.append("暂无足够样本，所有方向仅允许观察复核。")
    for route in routes[:max_routes]:
        lines.append(
            f"- {route.get('symbol')}｜{route.get('strategy')}｜{direction_cn(route.get('direction'))}｜"
            f"{route.get('regime')}｜状态：{state_cn(route.get('state'))}｜"
            f"样本：{route.get('samples')}｜胜率：{_pct(route.get('winRate'))}｜平均R：{_num(route.get('avgScoreR'))}"
        )
        lines.append(f"  原因：{route.get('reason', '无')}")

    if gates:
        lines.extend(["", "入场闸门："])
        for gate in gates[:max_routes]:
            lines.append(f"- {gate.get('symbol')}：{gate.get('conclusion')}；快照新鲜：{'是' if gate.get('runtimeFresh') else '否'}；回退：{'是' if gate.get('fallback') else '否'}")
            for check in gate.get("checks", [])[:4]:
                lines.append(f"  · {check.get('name')}：{'通过' if check.get('passed') else '未通过'}｜{check.get('reason')}")

    if plans:
        lines.extend(["", "动态止盈止损建议："])
        for plan in plans[:max_routes]:
            lines.append(f"- {plan.get('symbol')}｜{plan.get('directionLabel')}｜风险模式：{plan.get('riskMode')}｜依据：{plan.get('basis')}")
            stop = plan.get("initialStop", {})
            lines.append(f"  · {stop.get('label')}：{stop.get('value')}（{stop.get('description')}）")
            for target in plan.get("targets", [])[:3]:
                lines.append(f"  · {target.get('name')}：{target.get('value')}（{target.get('description')}）")

    lines.extend([
        "",
        "安全边界：仅建议、只读、影子评估；不会下单、不会平仓、不会撤单、不会修改实盘 preset。",
    ])
    return "\n".join(lines)
