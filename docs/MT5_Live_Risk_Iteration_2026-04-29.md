# MT5 live risk iteration - 2026-04-29

## 触发原因

HFM 只读快照显示 MT5 pilot 已进入连续亏损冷却：`MA_Cross`、`RSI_Reversal`、`BB_Triple`、`MACD_Divergence`、`SR_Breakout` 均显示 `COOLDOWN`，原因是 `Consecutive loss pause active`。这不是前端误报，而是 EA 风控已经暂停新开仓。

两份改进报告把主要问题指向四处：

- `USDJPY RSI_Reversal H1` 仍是唯一有正样本的路线，但 live 出场太慢，曾出现盈利后拖到亏损、隔夜 swap、长持仓。
- `EURUSDc` 的 MA / BB 样本继续拖累组合，短期不应再参与 live pilot。
- 新闻过滤 10/5 分钟太短，FOMC 这类高冲击事件前后窗口不足。
- 2026-04-27 曾出现 `BB_Triple` 真实成交，当前 preset 已关闭，但下单函数缺少最后一层路线开关复核。

## 本分支改动

1. Live preset 降风险：
   - `Watchlist=USDJPY`
   - `EnablePilotMA=false`
   - `EnablePilotRsiH1Live=true`
   - `EnablePilotBBH1Live=false`
   - `EnablePilotMacdH1Live=false`
   - `EnablePilotSRM15Live=false`

2. RSI 参数收紧：
   - `PilotRsiOverbought=85`
   - `PilotRsiOversold=15`
   - `PilotRsiBandTolerancePct=0.006`

3. RSI 出场保护：
   - `PilotRsiFailFastCloseOnMaxLoss=true`
   - 新增 `EnablePilotRsiTimeStopProtect=true`
   - 新增 `PilotRsiMaxHoldMinutes=90`
   - 新增 `PilotRsiCloseOnServerDayChange=true`
   - 日志证据标记：`routeProtect=RSI_TIME_STOP`

4. RSI 入场过滤：
   - SELL 在 `TREND_UP` / `TREND_EXP_UP` 中禁止。
   - `RANGE_TIGHT` 仅允许 BUY，禁止 SELL。

5. 新闻过滤保守化：
   - 常规 pre/post block 调整为 30/30 分钟。
   - 高冲击事件 pre block 60 分钟。
   - bias 窗口 60 分钟。

6. 下单二次防线：
   - `SendPilotMarketOrder()` 现在会再次检查 `IsPilotLiveMode()`。
   - `MA_Cross` 必须 `EnablePilotMA=true`。
   - legacy routes 必须各自 live switch 为 true。

7. 研究账本修复：
   - shadow ledger 对没有方向的观察样本不再全部写 `NO_DIRECTION`。
   - 现在会保留 `LONG_OPPORTUNITY` / `SHORT_OPPORTUNITY` / `NEUTRAL_OPPORTUNITY`，方便后端统计真实机会方向。

## BB_Triple 事件复盘

只读 CloseHistory 显示 2026-04-27 有一笔 `QG_BB_Triple_MT5_SELL` EURUSDc 真实成交，净亏损约 -1.35 USC。Git 证据显示当日曾短暂把 legacy live routes 打开，随后又关闭。因此本分支不假设一定是代码绕过，但补了“下单函数最后一层 live switch 复核”，避免以后 preset 或流程漂移导致候选路线误下单。

## 仍需人工确认

这些改动先留在分支中验证，不自动部署到 HFM live terminal。上线前需要：

- 编译 EA。
- 复制新 `.ex5` 和 live preset 到 HFM。
- 重载 EA。
- 确认日志出现新 build：`QuantGod-v3.15-mt5-live-risk-iteration`。
- 后续重点观察：`routeProtect=RSI_TIME_STOP`、`routeProtect=RSI_FAILFAST`、`RSI H1 SELL blocked`、`legacy route live switch disabled`。
