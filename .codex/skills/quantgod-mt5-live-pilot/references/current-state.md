# 当前状态参考

QuantGod MT5 Live Pilot 当前以只读证据和受控 live pilot 为核心。前端、后端、infra、docs 已拆成四仓库。

## 关键边界

- live pilot 仍由 MT5 EA、preset、session/news/cooldown/order-send guard 控制。
- 前端只展示证据和建议，不直接交易。
- AI/Vibe/Telegram 都不能绕过 Kill Switch 或 authorization lock。
- 每日复盘和今日待办只生成建议、报告和人工复核项。

## 常用证据

- `QuantGod_Dashboard.json`
- `QuantGod_CloseHistory.csv`
- `QuantGod_TradeJournal.csv`
- `QuantGod_GovernanceAdvisor.json`
- `QuantGod_ParamLabStatus.json`
- `QuantGod_MT5PendingOrderWorker.json`
- `MQL5/Logs`
