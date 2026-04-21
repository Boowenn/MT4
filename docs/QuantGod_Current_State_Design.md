# QuantGod 当前设计与实现状态设计书

更新时间: 2026-04-21  
适用版本: `QuantGod-v2.7-fast-exit`  
当前文档定位: 作为项目的“现状总设计书”，区分已经落地的能力、部分落地的能力、以及尚未实现的能力。后续如 README、零散方案、聊天记录与本文件冲突，以本文件和当前代码行为为准。

## 1. 文档目标

这份文档解决三个问题:

1. 当前项目到底已经实现了什么。
2. 哪些能力只是雏形，哪些能力还没有真正落地。
3. 现在的数据规模够支撑到哪一层，下一步应该按什么顺序做。

当前项目已经不再只是“5 个策略 + 一个 dashboard”。
它已经具备了研究型闭环的第一层基础设施:

- 虚拟小资金研究账户
- 多策略并行执行
- 研究快出场加速样本回收
- 基于最近已平仓样本的保护型自适应
- 信号级原始特征日志
- 机会标签机会评估
- 周期性策略评估快照
- dashboard 可视化联动

但它还没有进入“可信自动调参”或“真正模型自学习”阶段。

## 2. 当前项目架构

### 2.1 执行层

- EA 主程序: `MQL4/Experts/QuantGod_MultiStrategy.mq4`
- 公共工具层: `MQL4/Include/QuantEngine.mqh`

职责:

- 管理双品种 `EURUSD, USDJPY`
- 执行 5 个策略
- 输出 dashboard JSON
- 记录交易、信号、机会标签、自适应状态、评估报表
- 在研究模式下用虚拟净值评估真实 demo 执行结果

### 2.2 展示层

- 仪表盘页面: `Dashboard/QuantGod_Dashboard.html`
- 本地静态服务: `Dashboard/dashboard_server.js`

职责:

- 本地读取 `QuantGod_Dashboard.json`
- 补充加载 `QuantGod_StrategyEvaluationReport.csv`
- 补充加载 `QuantGod_OpportunityLabels.csv`
- 显示 regime、adaptive 状态、机会标签统计、策略评估卡片

### 2.3 数据层

当前运行目录在 MT4 本地:

- `MQL4/Files/QuantGod_Dashboard.json`
- `MQL4/Files/QuantGod_TradeJournal.csv`
- `MQL4/Files/QuantGod_BalanceHistory.csv`
- `MQL4/Files/QuantGod_EquitySnapshots.csv`
- `MQL4/Files/QuantGod_SignalLog.csv`
- `MQL4/Files/QuantGod_SignalOpportunityQueue.csv`
- `MQL4/Files/QuantGod_OpportunityLabels.csv`
- `MQL4/Files/QuantGod_AdaptiveStateHistory.csv`
- `MQL4/Files/QuantGod_StrategyEvaluationReport.csv`

### 2.4 可选云层

- `cloudflare/`
- `Dashboard/cloud_sync_uploader.js`
- `Dashboard/cloud_sync_uploader.ps1`

结论:

- 云同步已经具备可选能力。
- 当前默认工作流仍然是本地优先，不依赖云端。

## 3. 当前运行快照

以下数据基于本地运行文件的统一快照:

- 时间: `2026.04.21 14:45:48` 本地
- Build: `QuantGod-v2.7-fast-exit`
- 模式: `virtual_research`
- 观察品种: `EURUSD,USDJPY`
- 当前持仓: 2 笔
- 已平仓样本: 24 笔
- `SignalLog` 行数: 465
- `OpportunityLabels` 行数: 6
- `StrategyEvaluationReport` 行数: 10

### 3.1 按策略的已平仓样本

| 策略 | 已平仓 | 胜率 | 研究净收益 |
|---|---:|---:|---:|
| `MA_Cross` | 2 | 50.0% | 0.01 |
| `RSI_Reversal` | 15 | 40.0% | -0.14 |
| `MACD_Divergence` | 7 | 28.6% | -0.01 |
| `BB_Triple` | 0 | 0.0% | 0.00 |
| `SR_Breakout` | 0 | 0.0% | 0.00 |

### 3.2 按策略 x 品种的已平仓样本

| 策略 | 品种 | 已平仓 | 研究净收益 |
|---|---|---:|---:|
| `MA_Cross` | `EURUSD` | 1 | 0.00 |
| `MA_Cross` | `USDJPY` | 1 | 0.01 |
| `RSI_Reversal` | `EURUSD` | 8 | -0.07 |
| `RSI_Reversal` | `USDJPY` | 7 | -0.07 |
| `MACD_Divergence` | `EURUSD` | 5 | 0.01 |
| `MACD_Divergence` | `USDJPY` | 2 | -0.02 |

结论:

- 当前只有 `RSI_Reversal` 和 `MACD_Divergence` 有初步样本。
- `MA_Cross` 只有预热级样本。
- `BB_Triple` 和 `SR_Breakout` 仍然没有平仓样本。
- 当前数据量只够做“保护性节流”，不够做“可信参数迭代”。

### 3.3 按策略的信号级样本

| 策略 | `SignalLog` 行数 | 已覆盖 regime |
|---|---:|---|
| `MA_Cross` | 9 | `RANGE / TRANSITION / TREND_EXP / TREND_EXP_DOWN / TREND_EXP_UP` |
| `RSI_Reversal` | 441 | `RANGE_HIGHVOL / TRANSITION` |
| `BB_Triple` | 3 | `RANGE_HIGHVOL / TRANSITION` |
| `MACD_Divergence` | 3 | `RANGE_HIGHVOL / TRANSITION` |
| `SR_Breakout` | 9 | `RANGE / TRANSITION / TREND_EXP / TREND_EXP_DOWN / TREND_EXP_UP` |

结论:

- 信号级数据已经开始积累。
- 但结构非常不均衡，当前绝大多数信号行来自 `RSI_Reversal`。
- 这意味着“有日志”不等于“有平衡训练集”。

### 3.4 按策略的机会标签

| 策略 | 标签数 | 有方向标签数 | Bias 命中 | Bias 命中率 |
|---|---:|---:|---:|---:|
| `MA_Cross` | 1 | 1 | 1 | 100.0% |
| `BB_Triple` | 2 | 2 | 1 | 50.0% |
| `MACD_Divergence` | 2 | 0 | 0 | 0.0% |
| `SR_Breakout` | 1 | 1 | 0 | 0.0% |
| `RSI_Reversal` | 0 | 0 | 0 | 0.0% |

结论:

- `OpportunityLabels` 功能已经打通。
- 但总体样本量还非常小，当前更适合用于 dashboard 观察，不适合直接驱动策略升级。

## 4. 已实现的能力

本节只写“代码里确实存在并正在运行”的能力。

### 4.1 多策略并行研究框架

状态: 已实现

当前有 5 个策略:

- `MA_Cross`
- `RSI_Reversal`
- `BB_Triple`
- `MACD_Divergence`
- `SR_Breakout`

特点:

- 双品种并行
- M15 / H1 混合节奏
- 每个策略有独立输入参数与 MagicNumber
- dashboard 可以按策略与按品种展示运行状态

### 4.2 虚拟研究账户

状态: 已实现

当前系统不是直接用真实 demo 账户余额来判断研究收益，而是:

- 用固定 `0.01` demo 手数执行
- 用虚拟账户余额估算研究收益与回撤
- 旧仓可以通过 `IgnoreLegacyTradesInVirtualStats` 排除

意义:

- 这让当前系统能在极小风险下快速积累样本。
- 这是研究闭环能成立的基础。

### 4.3 研究快出场

状态: 已实现

当前已有研究模式专用快出场机制:

- `ResearchTargetRR`
- `ResearchBreakEvenRR`
- `ResearchBreakEvenLockPips`
- `ResearchMaxHoldMinutes_M15`
- `ResearchMaxHoldMinutes_H1`
- `ResearchMaxHoldMinutes_H4`

作用:

- 不是为了追求最优收益。
- 而是为了更快形成平仓样本，提升研究阶段的数据积累速度。

### 4.4 保护型自适应闭环

状态: 已实现

当前已实现的是“保护型自适应”，不是“自动调参型自学习”。

现有 adaptive 规则:

- `WARMUP`: 总样本未达到 `AdaptiveMinClosedTrades`
- `CAUTION`: 样本显示质量偏弱，风险降到 `AdaptiveLowRiskScale`
- `COOLDOWN`: 达到硬暂停条件后进入冷却期，策略停开新仓
- `RETEST`: 冷却窗口结束后低风险复测
- `NORMAL`: 正常运行
- `BOOST`: 达到强势门槛后升到 `AdaptiveHighRiskScale`

当前默认阈值:

- 窗口样本: 12 笔
- 激活闭环最低总样本: 6 笔
- 允许硬暂停最低总样本: 20 笔
- 允许风险放大最低总样本: 50 笔
- 暂停候选条件: 最近窗口净收益 < 0 且 `AvgNet <= -0.01` 或 `PF <= 0.90`
- 强势放大条件: 净收益 > 0 且 `AvgNet >= 0.03` 且 `PF >= 1.35` 且 `WinRate >= 55%`

重要说明:

- adaptive 当前是按“策略全局”聚合，不是按“策略 x 品种”独立聚合。
- 也就是说 `RSI_Reversal` 的自适应状态是 EURUSD 和 USDJPY 共用的。

### 4.5 SignalLog 信号级原始特征日志

状态: 已实现

当前 `QuantGod_SignalLog.csv` 已经记录:

- 时间
- 品种
- 策略
- 周期
- regime
- adaptive state
- risk multiplier
- trading status
- signal status
- signal reason
- signal score
- buy / sell score
- spread / ATR / ADX / 布林宽度
- OHLC / bar range / bar body / close delta
- RSI / EMA / TrendMA
- MACD
- 成交量与 volume ratio
- support / resistance 距离
- 当前持仓数
- 当前研究余额 / 权益 / 回撤
- detail 文本

结论:

- “信号级原始特征列”已经落地。
- 这一步已经超过了早期只有成交日志的阶段。

### 4.6 regime 标签

状态: 已实现

当前 regime 已经不是空概念，已经进入:

- `SignalLog`
- `OpportunityLabels`
- `StrategyEvaluationReport`
- `QuantGod_Dashboard.json`
- dashboard 页面展示

当前 regime 是内嵌字段，不是单独的 `QuantGod_RegimeLog.csv`。

### 4.7 Opportunity Labels 机会标签

状态: 已实现

当前链路:

1. 信号评估时，把可观察事件写入 `QuantGod_SignalOpportunityQueue.csv`
2. 到达 horizon 后，异步写入 `QuantGod_OpportunityLabels.csv`
3. dashboard 聚合最近 N 条机会标签，显示:
   - Bias 命中率
   - Best-side 偏离
   - Avg Long / Short close pips

当前机会标签包含:

- `LongClosePips`
- `ShortClosePips`
- `LongMFEPips`
- `LongMAEPips`
- `ShortMFEPips`
- `ShortMAEPips`
- `DirectionalOutcome`
- `BestOpportunity`

### 4.8 AdaptiveStateHistory

状态: 已实现

当前只有在 adaptive 状态变化时才写历史，不是每次刷新都写。

这意味着它适合回答:

- 策略什么时候进入 `CAUTION`
- 什么时候恢复 `NORMAL`
- 什么时候进入 `COOLDOWN`

但它不适合直接当作完整的连续时间序列。

### 4.9 StrategyEvaluationReport

状态: 已实现

当前 `QuantGod_StrategyEvaluationReport.csv` 是周期性快照报表，包含:

- symbol
- strategy
- timeframe
- regime
- adaptive state
- risk multiplier
- signal status / score / reason
- closed trades
- win rate
- profit factor
- avg net
- net profit
- spread / ATR / ADX / BBWidth
- last eval time
- last closed time

这已经是“周期性策略评估报表”的实现版本。

### 4.10 dashboard 联动展示

状态: 已实现

当前 dashboard 已显示:

- 研究账户权益与回撤
- 品种级状态
- strategy 卡片
- 当前 regime
- adaptive 状态与风险倍率
- opportunity label 汇总
- 策略评估卡片

最近已完成的前端工作:

- 机会标签汇总接入 dashboard
- 策略评估区改为卡片式布局
- regime 与策略评估表已直接显示在前端

## 5. 部分实现的能力

这些能力不是“完全没有”，但还没有达到最终设计目标。

### 5.1 周期性评估报表

状态: 部分实现

已实现:

- 周期性 CSV 快照报表
- dashboard 可视化读取

未实现:

- 周报 / 日报级汇总文档
- 长窗口对比
- 自动生成“调参候选”
- 按 regime 的滚动统计摘要

### 5.2 自学习数据层

状态: 部分实现

已实现:

- 原始特征日志
- regime
- adaptive state
- opportunity labels

未实现:

- 交易标签与信号事件的强关联主键
- 同一信号从“评估 -> 下单 -> 平仓结果”的完整生命周期拼接
- 标准化布尔条件列

说明:

当前 `Detail` 字段里已经有类似 `cross=Y trend=N` 这类半结构化信息，但仍是文本，不是规则列。
这意味着“可看懂”已经实现，但“可直接喂模型/规则分析器”还没有完全标准化。

### 5.3 自适应闭环

状态: 部分实现

已实现:

- 最近窗口样本统计
- 自动降风险
- 自动暂停
- 自动恢复低风险复测
- 自动风险放大

未实现:

- 按品种独立 adaptive
- 按 regime 独立 adaptive
- 组合层风险预算联动
- drawdown slope / MAE / MFE 等更丰富的控制因子

### 5.4 dashboard 作为研究控制台

状态: 部分实现

已实现:

- 观测层
- 诊断层
- 报表层

未实现:

- 参数候选审批界面
- walk-forward 结果展示
- canary / rollback 面板
- 每策略数据门槛进度条

## 6. 尚未实现的关键能力

这些能力如果没有补上，就不能把系统定义为“可信自学习”。

### 6.1 自动参数迭代

状态: 未实现

当前没有:

- 参数候选搜索器
- 参数替换器
- 自动回写 EA 参数
- 参数版本记录
- 参数回滚机制

结论:

- 现在系统不会自动优化参数。
- 现在的 adaptive 只会调风险和启停，不会改策略参数。

### 6.2 walk-forward / OOS

状态: 未实现

当前没有:

- 训练窗
- 验证窗
- 前向窗
- 连续 OOS 通过逻辑

结论:

- 当前报表仍然是“运行时观察 + 最近窗口统计”。
- 还不是正式的 walk-forward 研究框架。

### 6.3 canary / rollback

状态: 未实现

当前没有:

- 新参数灰度上线
- 观察期自动回退
- 参数版本切换日志

### 6.4 交易标签闭环

状态: 未实现

当前虽然有 `TradeJournal.csv`，但还没有把单笔交易结果严格回挂到对应的信号事件。

缺失点:

- `Signal EventId -> Order -> Close Result` 的主链路
- 每次下单信号的真实平仓标签
- 每次没下单信号的机会标签与后验结果统一聚合

### 6.5 真正的模型学习层

状态: 未实现

当前没有:

- signal quality model
- regime classifier model
- strategy router
- entry filter model
- 自动训练 pipeline

## 7. 现在系统真正具备的能力边界

一句话结论:

当前系统已经具备“保护型自适应研究平台”，但还不具备“可信自动调参平台”，更不具备“机器学习自学习平台”。

### 7.1 现在能做什么

- 自动积累结构化样本
- 自动记录信号级特征
- 自动打机会标签
- 自动识别明显弱势策略
- 自动降风险或暂停
- 自动把状态输出到 dashboard

### 7.2 现在不能做什么

- 自动改参数并保证可靠
- 自动做 walk-forward
- 自动回滚错误参数
- 基于足够样本训练出稳定模型
- 对每个策略在每个品种、每个 regime 下做可信比较

## 8. 当前按策略状态判断

### 8.1 `MA_Cross`

当前状态: `WARMUP`

- 已平仓 2 笔
- 样本远不足
- signal log 已覆盖多个 regime
- 说明它“有评估覆盖”，但“没有成交覆盖”

结论:

- 可继续观察
- 不可做任何参数决策

### 8.2 `RSI_Reversal`

当前状态: `CAUTION`

- 已平仓 15 笔
- adaptive 风险已降到 `0.75x`
- 是目前样本最多的策略
- 但净收益和 PF 仍偏弱

结论:

- 它已经能进入保护型 adaptive
- 但还没有达到可信保留/淘汰判断门槛

### 8.3 `BB_Triple`

当前状态: `WARMUP`

- 已有少量 signal log
- 已有机会标签
- 还没有平仓样本

结论:

- 数据链路通了
- 交易样本没起来

### 8.4 `MACD_Divergence`

当前状态: `NORMAL`

- 已平仓 7 笔
- adaptive 当前显示 `NORMAL`
- 但总体样本仍明显偏少

结论:

- 现在的 `NORMAL` 只能理解为“未触发保护阈值”
- 不能理解为“策略已经被证明可靠”

### 8.5 `SR_Breakout`

当前状态: `WARMUP`

- 已有少量 signal log
- 已有机会标签
- 还没有平仓样本

结论:

- 与 `BB_Triple` 类似，仍停留在研究早期

## 9. 为什么现在仍不够做可信自学习

核心不是“完全没数据”，而是“数据层级还不够高、覆盖还不够均匀”。

### 9.1 平仓样本仍然偏少

当前最活跃策略也只有 15 笔已平仓。

相比推荐门槛:

- 保护型 adaptive: 每策略 20-30 笔
- 稳定保留/停用判断: 每策略 60-100 笔
- 自动参数迭代: 每策略 100-150 笔 + OOS

当前还只在第一阶段门口。

### 9.2 样本分布不均

当前问题:

- 样本高度集中在 `RSI_Reversal`
- `BB_Triple` / `SR_Breakout` 还没有成交覆盖
- `MACD_Divergence` 有成交，但很薄
- regime 覆盖也不均衡

### 9.3 交易标签主链路没打通

系统已经能回答:

- 当时是什么 regime
- 当时信号强弱如何
- 如果不下单，后面机会如何

但还不能稳定回答:

- 某个具体 signal event 最终平仓结果是什么
- 哪类信号质量高、哪类信号质量低
- 哪类过滤器真正改善了成交质量

## 10. 下一版应当怎么收敛

这里给出建议顺序，按“先把系统理顺，再谈复杂自学习”推进。

### 10.1 P0: 文档和状态统一

目标:

- 以本文件作为项目现状总设计书
- README 只负责安装、启动、入口说明
- 所有新功能先写入“已实现 / 部分实现 / 未实现”矩阵再改代码

### 10.2 P1: 打通交易标签主链路

目标:

- 给每个下单信号保留 `EventId`
- 在平仓后把结果回写成 trade outcome label

新增建议:

- `QuantGod_TradeOutcomeLabels.csv`

最关键字段:

- `EventId`
- `OrderTicket`
- `Strategy`
- `Symbol`
- `EntryDirection`
- `HoldBars`
- `CloseReason`
- `RealizedPips`
- `RealizedR`
- `MFE`
- `MAE`
- `DurationMinutes`

这是下一阶段最值得优先做的事。

### 10.3 P2: 标准化条件列

目标:

- 把 `Detail` 里的半结构化文本拆成标准列

例如:

- `Cond_Cross`
- `Cond_Trend`
- `Cond_Spread`
- `Cond_Distance`
- `Cond_Band`
- `Cond_RSI`
- `Cond_MACD`
- `Cond_Volume`

这样未来不管做规则分析、特征筛选还是模型训练，都会干净很多。

### 10.4 P3: 做策略候选而不是自动调参

目标:

- 先输出“候选参数建议”
- 不要直接自动生效

先做:

- 最近窗口统计
- 按 symbol 分解
- 按 regime 分解
- 给出候选，不自动应用

### 10.5 P4: 上 walk-forward

目标:

- 引入训练窗 / 验证窗 / 前向窗

没有这一步，不要进入自动参数替换。

### 10.6 P5: 小步自动参数迭代

前提:

- 每策略 100-150 笔以上
- 至少 2 个连续 OOS 窗口通过
- 有 canary / rollback

到这一步，系统才算开始具备“可信的策略迭代能力”。

## 11. 当前推荐门槛

### 阶段 A: 保护型 adaptive

- 每策略 20-30 笔已平仓
- 允许降风险 / 暂停 / 恢复
- 不允许自动改参数

### 阶段 B: 稳定统计分析

- 每策略 60-100 笔已平仓
- 每个品种至少 30 笔
- 每个策略至少覆盖趋势 / 震荡 / 高波动三类环境
- 允许输出参数候选

### 阶段 C: 自动参数迭代

- 每策略 100-150 笔已平仓
- 至少两个连续 OOS 窗口通过
- 才允许小步自动替换参数

### 阶段 D: 模型化学习

- 3000-10000 条信号级样本
- 300-500 笔交易级样本
- 具备 trade outcome label
- 具备标准化条件列

## 12. 最终结论

当前 QuantGod 的真实定位应该是:

> 一个已经完成第一层闭环基础设施的 MT4 多策略研究平台。

它已经完成的不是“策略自动优化”，而是“为未来做可信优化准备好数据和控制骨架”。

最准确的状态判断是:

- 已实现: 研究执行、快出场、保护型 adaptive、signal log、机会标签、评估报表、dashboard 联动
- 部分实现: 自学习数据层、周期性评估、研究控制台
- 未实现: trade outcome label、walk-forward、参数候选系统、自动调参、canary/rollback、模型训练层

如果只用一句话总结:

> 现在已经不是一个“只有交易结果的 EA”，但还不是一个“能可信自我进化的策略系统”。
