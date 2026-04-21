//+------------------------------------------------------------------+
//|                                       QuantGod_MultiStrategy.mq4 |
//|                          QuantGod Multi-Strategy Trading Engine   |
//|                              https://github.com/Boowenn/MT4      |
//+------------------------------------------------------------------+
#property copyright "QuantGod Engine v2.0"
#property link      "https://github.com/Boowenn/MT4"
#property version   "2.00"
#property strict

#include "..\\Include\\QuantEngine.mqh"
#include "..\\Include\\WinUser32.mqh"

#import "user32.dll"
int GetAncestor(int hWnd, int gaFlags);
#import

#define GA_ROOT 2
#define MT4_WMCMD_EXPERTS 33020
#define ADAPTIVE_REFRESH_SECONDS 10
#define OPPORTUNITY_LABEL_COLUMNS 27

struct SignalFeatureSnapshot
{
   datetime eventBarTime;
   datetime labelReadyTime;
   int      horizonBars;
   double   refPrice;
   double   open1;
   double   high1;
   double   low1;
   double   close1;
   double   close2;
   double   barRangePips;
   double   barBodyPips;
   double   closeDeltaPips;
   double   spreadPips;
   double   atrPips;
   double   adxValue;
   double   bbUpper;
   double   bbMiddle;
   double   bbLower;
   double   bbWidthPips;
   double   bbPosPct;
   double   rsi2;
   double   rsi14;
   double   emaFast;
   double   emaSlow;
   double   trendMA;
   double   maGapPips;
   double   trendDistancePips;
   double   macdMain;
   double   macdSignal;
   double   macdHist;
   double   volume1;
   double   avgVolume20;
   double   volumeRatio20;
   double   support;
   double   resistance;
   double   supportDistancePips;
   double   resistanceDistancePips;
   string   regime;
};

struct TradeEventLink
{
   string   eventId;
   string   eventKey;
   int      ticket;
   string   strategy;
   string   symbol;
   string   timeframe;
   string   signalStatus;
   string   signalDirection;
   double   signalScore;
   datetime eventTimeServer;
   datetime eventBarTime;
   double   requestedPrice;
   double   stopLoss;
   double   takeProfit;
   double   actualLots;
   double   researchLots;
   string   orderComment;
};

//=== 全局设置 ===
input string   _g0 = "====== 全局设置 ======";
input double   RiskPercent        = 0.04;    // 多策略并行研究：单笔风险进一步压低
input double   MaxDrawdownPercent = 6.0;     // 组合研究模式更紧的回撤保护
input int      MaxTotalTrades     = 4;       // 允许多策略并行，但仍保留组合上限
input bool     UseTradeSession    = false;   // 关闭时段过滤，避免时区干扰
input double   TrailingStopPips   = 0.0;     // 研究模式先关闭追踪止损
input bool     EnableDashboard    = true;    // 导出 dashboard 数据
input string   TradingSymbols     = "EURUSD,USDJPY"; // 研究模式先聚焦双品种
input bool     AutoSelectSymbols  = true;    // 自动加入 Market Watch
input bool     PauseNewEntries    = false;   // 暂停开新仓，只管理已有仓位
input bool     FlattenManagedPositions = false; // 紧急清空当前策略组合仓位
input string   _g1 = "====== 虚拟研究账户 ======";
input bool     UseVirtualResearchAccount = true; // 用虚拟小资金模型评估策略
input double   VirtualStartingBalance = 10.0; // 虚拟起始资金
input double   VirtualRiskPercent = 1.0; // 虚拟账户单笔风险百分比
input double   ResearchExecutionLot = 0.01; // 实际 demo 执行统一微型手数
input bool     IgnoreLegacyTradesInVirtualStats = true; // 旧持仓不计入新研究样本
input string   _g1b = "====== 研究快出场 ======";
input bool     EnableResearchFastExit = true; // 研究模式启用更快的样本闭环
input double   ResearchTargetRR = 0.9; // 将 TP 压缩到 0.9R，优先形成平仓样本
input double   ResearchBreakEvenRR = 0.5; // 浮盈达到 0.5R 后推保护止损
input double   ResearchBreakEvenLockPips = 0.2; // 保本后锁住少量盈利
input int      ResearchMaxHoldMinutes_M15 = 45; // M15 策略最长持仓时间
input int      ResearchMaxHoldMinutes_H1 = 90; // H1 策略最长持仓时间
input int      ResearchMaxHoldMinutes_H4 = 240; // 更高周期最长持仓时间
input string   _g1c = "====== 自适应闭环 ======";
input bool     EnableAdaptiveControl = true; // 根据最近已平仓样本自动启停策略与缩放风险
input int      AdaptiveWindowTrades = 12; // 每个策略统计最近 N 笔平仓样本
input int      AdaptiveMinClosedTrades = 6; // 至少达到该样本量后再启用闭环
input int      AdaptivePauseMinClosedTrades = 20; // 至少达到该样本量后才允许进入硬冷却
input int      AdaptiveBoostMinClosedTrades = 50; // 至少达到该样本量后才允许提高风险
input int      AdaptiveCooldownMinutes = 180; // 低质量策略暂停后的最短冷却时间
input double   AdaptiveDisableAvgNet = -0.01; // 平均单笔收益低于此值时进入暂停候选
input double   AdaptiveDisableProfitFactor = 0.90; // profit factor 低于此值时进入暂停候选
input double   AdaptiveLowRiskScale = 0.75; // 弱势策略/重启试运行时的风险系数
input double   AdaptiveHighRiskScale = 1.25; // 强势策略的风险系数上调
input double   AdaptiveHighAvgNet = 0.03; // 提高风险所需的平均单笔收益
input double   AdaptiveHighProfitFactor = 1.35; // 提高风险所需的 profit factor
input double   AdaptiveHighWinRate = 55.0; // 提高风险所需的胜率
input string   _g1d = "====== SignalLog / Regime / Eval Report ======";
input bool     EnableSignalLog = true; // 记录每次策略判定/信号状态
input bool     EnableStrategyReport = true; // 周期性导出策略评估报表
input bool     EnableAdaptiveStateHistory = true; // 仅在自适应状态变化时写入历史
input bool     EnableOpportunityLabels = true; // 延迟生成固定 horizon 的机会标签
input int      OpportunityLabelIntervalSeconds = 30; // 标签扫描最小间隔
input int      OpportunityHorizonBars_M15 = 4; // M15 机会标签 horizon
input int      OpportunityHorizonBars_H1 = 3; // H1 机会标签 horizon
input int      OpportunityHorizonBars_H4 = 2; // H4 机会标签 horizon
input double   OpportunityNeutralThresholdATR = 0.15; // 低于该 ATR 比例的收益记为中性
input int      StrategyReportIntervalSeconds = 300; // 报表刷新周期
input string   _g2 = "====== Cloud 同步 ======";
input bool     EnableCloudSync = false; // 将 dashboard 数据推送到云端
input string   CloudSyncEndpoint = ""; // 例如 https://your-domain.workers.dev/api/ingest
input string   CloudSyncToken = ""; // 可选 Bearer Token
input int      CloudSyncIntervalSeconds = 30; // 云端推送最小间隔
input int      CloudSyncTimeoutMs = 5000; // WebRequest 超时

//=== 策略1: MA交叉 ===
input string   _s1 = "====== 策略1: MA交叉 ======";
input bool     Enable_MA          = true;    // 启用 MA 交叉策略
input int      MA_FastPeriod      = 9;       // 快线周期
input int      MA_SlowPeriod      = 21;      // 慢线周期
input int      MA_TrendPeriod     = 100;     // 趋势过滤 SMA
input ENUM_TIMEFRAMES MA_Timeframe = PERIOD_M15; // 研究模式：M15 提高样本量
input ENUM_TIMEFRAMES MA_TrendTimeframe = PERIOD_H1; // 用更高周期过滤方向
input int      MA_CrossLookbackBars = 2;     // 只接受最近 2 根K线内的交叉
input double   MA_MaxEntryDistanceATR = 0.35; // 进场不能离快线太远，避免追价
input double   MA_MaxSpreadPips = 1.2;       // 点差过大不进场
input int      MA_Magic           = 10001;   // Magic Number

//=== 策略2: RSI 均值回归 ===
input string   _s2 = "====== 策略2: RSI 均值回归 ======";
input bool     Enable_RSI         = true;    // 并行研究开启
input int      RSI_Period         = 2;       // RSI 周期
input int      RSI_OB             = 80;      // 超买阈值
input int      RSI_OS             = 20;      // 超卖阈值
input ENUM_TIMEFRAMES RSI_Timeframe = PERIOD_H1; // 更活跃：H1
input int      RSI_Magic          = 10002;   // Magic Number

//=== 策略3: BB + RSI + MACD 三重确认 ===
input string   _s3 = "====== 策略3: BB+RSI+MACD 三重确认 ======";
input bool     Enable_BB          = true;    // 并行研究开启
input int      BB_Period          = 20;      // 布林周期
input double   BB_Deviation       = 2.0;     // 布林标准差
input int      BB_RSI_Period      = 14;      // RSI 周期
input int      BB_RSI_OB          = 65;      // RSI 超买
input int      BB_RSI_OS          = 35;      // RSI 超卖
input ENUM_TIMEFRAMES BB_Timeframe = PERIOD_H1; // 更活跃：H1
input int      BB_Magic           = 10003;   // Magic Number

//=== 策略4: MACD 背离 ===
input string   _s4 = "====== 策略4: MACD 背离 ======";
input bool     Enable_MACD        = true;    // 并行研究开启
input int      MACD_Fast          = 12;      // 快线
input int      MACD_Slow          = 26;      // 慢线
input int      MACD_Signal        = 9;       // 信号线
input int      MACD_LookBack      = 24;      // 背离回溯周期
input ENUM_TIMEFRAMES MACD_Timeframe = PERIOD_H1; // 更活跃：H1
input int      MACD_Magic         = 10004;   // Magic Number

//=== 策略5: 支撑阻力突破 ===
input string   _s5 = "====== 策略5: 支撑阻力突破 ======";
input bool     Enable_SR          = true;    // 并行研究开启
input int      SR_LookBack        = 24;      // 更短回溯窗口
input double   SR_BreakPips       = 2.0;     // 更小突破确认
input ENUM_TIMEFRAMES SR_Timeframe = PERIOD_M15; // 更活跃：M15
input int      SR_Magic           = 10005;   // Magic Number


//=== 蜈ｨ螻蜿倬㍼ ===
input bool     AutoEnableTrading  = true;    // Try to turn terminal AutoTrading on

#define STRATEGY_DIAG_COUNT 5
#define MAX_MANAGED_SYMBOLS 8

string gChartSymbol;
string gDashboardSymbol;
string gManagedSymbols[MAX_MANAGED_SYMBOLS];
int    gManagedSymbolCount;
string gSymbol;
int    gDigits;
double gPoint;
int    gTotalSignals;
datetime gLastExport;
datetime gLastStrategyReportExport;
datetime gLastTickTime;
datetime gLastSnapshotLog;
datetime gLastLoggedCloseTime;
int      gLastLoggedCloseTicket;
int      gCurrentDiagSymbolIndex;
int      gLastOrderSendError;
datetime gLastCloudSyncAttempt;
datetime gLastCloudSyncSuccess;
int      gLastCloudSyncHttpCode;
string   gLastCloudSyncStatus;
string   gLastCloudSyncMessage;

string gStrategyDiagStatus[STRATEGY_DIAG_COUNT];
string gStrategyDiagReason[STRATEGY_DIAG_COUNT];
double gStrategyDiagScore[STRATEGY_DIAG_COUNT];
string gManagedDiagStatus[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
string gManagedDiagReason[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
double gManagedDiagScore[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
datetime gStrategyLastBars[STRATEGY_DIAG_COUNT][MAX_MANAGED_SYMBOLS];
string gStrategyLastEvalStatus[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
string gStrategyLastEvalReason[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
double gStrategyLastEvalScore[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
datetime gStrategyLastEvalTime[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
datetime gSignalLogLastWriteTime[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
datetime gSignalLogLastBarTime[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];
string   gSignalLogLastKey[MAX_MANAGED_SYMBOLS][STRATEGY_DIAG_COUNT];

bool     gAdaptiveStrategyActive[STRATEGY_DIAG_COUNT];
double   gAdaptiveRiskMultiplier[STRATEGY_DIAG_COUNT];
int      gAdaptiveTradeCount[STRATEGY_DIAG_COUNT];
int      gAdaptiveSampleCount[STRATEGY_DIAG_COUNT];
int      gAdaptiveWinCount[STRATEGY_DIAG_COUNT];
double   gAdaptiveGrossProfit[STRATEGY_DIAG_COUNT];
double   gAdaptiveGrossLoss[STRATEGY_DIAG_COUNT];
double   gAdaptiveNetProfit[STRATEGY_DIAG_COUNT];
double   gAdaptiveAvgNet[STRATEGY_DIAG_COUNT];
double   gAdaptiveWinRate[STRATEGY_DIAG_COUNT];
double   gAdaptiveProfitFactor[STRATEGY_DIAG_COUNT];
datetime gAdaptiveLastCloseTime[STRATEGY_DIAG_COUNT];
datetime gAdaptiveDisabledUntil[STRATEGY_DIAG_COUNT];
string   gAdaptiveState[STRATEGY_DIAG_COUNT];
string   gAdaptiveReason[STRATEGY_DIAG_COUNT];
datetime gLastAdaptiveRefresh;
int      gLastAdaptiveHistoryTotal;
int      gCurrentEntryStrategyIndex;
int      gSignalEventCounter;
datetime gLastOpportunityLabelScan;
string   gOpportunityProcessedIds[];
int      gOpportunityProcessedCount;

void Strategy_RSI_Reversal_V2();
void Strategy_MACD_Divergence_V2();
void Strategy_SR_Breakout_V2();
int DetectBullishDivergenceV2();
int DetectBearishDivergenceV2();
void ExportBalanceHistoryV2();
bool LoadManagedSymbols();
bool PrepareSymbolContext(string symbol_name);
int GetManagedSymbolIndex(string symbol_name);
bool IsManagedSymbol(string symbol_name);
bool IsManagedMagic(int magic);
string GetManagedSymbolsLabel();
int CountPositionsAllSymbols(int magic);
int GetTickAgeSecondsForSymbol(string symbol_name);
bool IsNewStrategyBar(int strategyIndex, string symbol_name, int timeframe);
int DigitsForSymbolName(string symbol_name);
void FlattenManagedPortfolio();
void ProcessManagedTrading();
void ProcessManagedSymbol(string symbol_name);
void RefreshAllManagedDiagnostics();
string GetTradingStatusForSymbol(string symbol_name);
double NormalizeLotForSymbol(double lots, string symbol_name);
double CalcLotSizeForBalance(double baseBalance, double riskPercent, double slPips, string symbol_name);
bool HasResearchTag(string comment);
double ParseTaggedDouble(string text, string tag);
double GetResearchLotsFromComment(string comment, double actualLots);
double ScaleResearchNet(double actualNet, double actualLots, string comment);
double GetResearchClosedNetProfit();
double GetResearchOpenNetProfit();
double GetResearchBalance();
double GetResearchEquity();
double GetResearchProfit();
double GetResearchDrawdownPercent();
bool CheckResearchDrawdownLimit();
double CalculateManagedLots(double slPips, string symbol_name, double &virtualLots);
string BuildManagedOrderComment(string baseComment, double virtualLots);
string BuildManagedOrderCommentWithEvent(string baseComment, double virtualLots, string eventId);
string BuildCompactEventKey(string eventId, int keyLength);
string BuildVirtualLotsTag(double virtualLots);
string ParseTaggedText(string text, string tag);
double PriceToPips(double priceDistance, string symbol_name);
int GetStrategyTimeframeByMagic(int magic);
int GetStrategyIndexByMagic(int magic);
string GetStrategyNameByIndex(int index);
bool IsStrategyConfiguredEnabled(int index);
void RefreshAdaptiveControl(bool force=false);
bool IsStrategyRuntimeActive(int index);
double GetStrategyRiskMultiplier(int index);
string GetStrategyAdaptiveReason(int index);
string GetStrategyRuntimeLabel(int index);
double ClampAdaptiveRiskScale(double scale);
int GetAdaptiveWindowTradeCount();
int GetAdaptiveMinTradeCount();
int GetAdaptivePauseMinTradeCount();
int GetAdaptiveBoostMinTradeCount();
string BuildAdaptiveSummary(int index);
void AppendAdaptiveStateHistory(int strategyIndex, string prevState, bool prevActive,
                                double prevRiskMultiplier, datetime prevDisabledUntil);
int GetTimeframeSeconds(int timeframe);
int GetOpportunityHorizonBars(int timeframe);
string BuildSignalEventId();
bool BuildSignalFeatureSnapshot(string symbol_name, int timeframe, SignalFeatureSnapshot &snapshot);
bool ShouldQueueOpportunityLabel(string signalStatus);
void AppendOpportunityQueue(string eventId, int strategyIndex, string symbol_name, int timeframe,
                            string signalStatus, string signalDirection, double signalScore,
                            double buyScore, double sellScore, string detail,
                            SignalFeatureSnapshot &snapshot);
void LoadOpportunityLabelState();
bool HasProcessedOpportunityEvent(string eventId);
void RememberProcessedOpportunityEvent(string eventId);
void ProcessOpportunityLabels(bool force=false);
int GetResearchMaxHoldMinutes(int timeframe);
double AdjustTakeProfitPipsForResearch(double desiredTpPips, double slPips, string symbol_name);
bool SafeOrderCloseCurrent(string reason);
void ManageResearchFastExitForSelectedOrder();
void ManageResearchFastExits(string symbol_name);
double GetDisplayedBalance();
double GetDisplayedEquity();
double GetDisplayedProfit();
double GetDisplayedDrawdownPercent();
double GetResearchSymbolFloatingProfit(string symbol_name);
double GetResearchSymbolClosedProfit(string symbol_name, int &closedTrades, int &winTrades, datetime &lastCloseTime);
bool CanSyncToCloud();
bool ReadBinaryFile(string filename, char &data[]);
void RecordCloudSyncResult(string status, int httpCode, string message, bool success);
bool SyncDashboardToCloud(string filename);
string SanitizeCsvText(string value);
int GetStrategyMagicByIndex(int index);
int CountStrategyPositionsForSymbol(int magic, string symbol_name);
int CountManagedPositionsForSymbol(string symbol_name);
void GetStrategyClosedStats(int strategyIndex, string symbol_name, int &closedTrades, int &winTrades,
                            double &netProfit, double &grossProfit, double &grossLoss, datetime &lastCloseTime);
string DetectMarketRegime(string symbol_name, int timeframe, double &atrPips, double &adxValue,
                          double &bbWidthPips, double &spreadPips);
bool ShouldLogSignalEvent(int strategyIndex, string symbol_name, int timeframe, string eventKey,
                          bool transitionOnly=false);
void AppendSignalLog(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                     string signalReason, string signalDirection, double signalScore,
                     double buyScore, double sellScore, string detail);
void AppendSignalLogWithEvent(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                              string signalReason, string signalDirection, double signalScore,
                              double buyScore, double sellScore, string detail, string eventId);
void LogStrategySignal(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                       string signalReason, string signalDirection, double signalScore,
                       double buyScore, double sellScore, string detail);
void LogStrategySignalWithEvent(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                                string signalReason, string signalDirection, double signalScore,
                                double buyScore, double sellScore, string detail, string eventId);
void AppendTradeEventLink(string eventId, int ticket, int strategyIndex, string symbol_name, int timeframe,
                          string signalStatus, string signalDirection, double signalScore,
                          double requestedPrice, double stopLoss, double takeProfit,
                          double actualLots, double researchLots, string orderComment);
bool LoadTradeEventLinks(TradeEventLink &links[], int &linkCount);
int FindTradeEventLinkIndexByTicket(TradeEventLink &links[], int linkCount, int ticket);
int FindTradeEventLinkIndexByEventKey(TradeEventLink &links[], int linkCount, string eventKey);
double GetInitialRiskPipsFromLink(TradeEventLink &link, int orderType, double openPrice, string symbol_name);
string GetTradeOutcomeFromPips(double realizedPips);
string DetectTradeCloseReason(int orderType, double closePrice, double stopLoss, double takeProfit,
                              int durationMinutes, int timeframe, string comment, string symbol_name);
void ExportTradeOutcomeLabels();
void ExportStrategyEvaluationReport(bool force=false);

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   gChartSymbol = Symbol();
   gDashboardSymbol = gChartSymbol;
   gManagedSymbolCount = 0;
   gSymbol = gChartSymbol;
   gDigits = Digits;
   gPoint  = Point;
   gTotalSignals = 0;
   gLastExport = 0;
   gLastStrategyReportExport = 0;
   gCurrentDiagSymbolIndex = -1;
   gLastAdaptiveRefresh = 0;
   gLastAdaptiveHistoryTotal = -1;
   gCurrentEntryStrategyIndex = -1;
   gSignalEventCounter = 0;
   gLastOpportunityLabelScan = 0;
   gOpportunityProcessedCount = 0;
   ArrayResize(gOpportunityProcessedIds, 0);
   for(int initSym = 0; initSym < MAX_MANAGED_SYMBOLS; initSym++)
   {
      for(int initStrat = 0; initStrat < STRATEGY_DIAG_COUNT; initStrat++)
      {
         gSignalLogLastWriteTime[initSym][initStrat] = 0;
         gSignalLogLastBarTime[initSym][initStrat] = 0;
         gSignalLogLastKey[initSym][initStrat] = "";
      }
   }
   LoadManagedSymbols();
   PrepareSymbolContext(gDashboardSymbol);
   gLastTickTime = (datetime)MarketInfo(gDashboardSymbol, MODE_TIME);
   gLastSnapshotLog = 0;
   gLastLoggedCloseTime = 0;
   gLastLoggedCloseTicket = 0;
   gLastCloudSyncAttempt = 0;
   gLastCloudSyncSuccess = 0;
   gLastCloudSyncHttpCode = 0;
   if(!EnableCloudSync)
   {
      gLastCloudSyncStatus = "DISABLED";
      gLastCloudSyncMessage = "Cloud sync is disabled";
   }
   else if(StringLen(CloudSyncEndpoint) < 12)
   {
      gLastCloudSyncStatus = "MISSING_ENDPOINT";
      gLastCloudSyncMessage = "Set CloudSyncEndpoint before enabling cloud sync";
   }
   else
   {
      gLastCloudSyncStatus = "IDLE";
      gLastCloudSyncMessage = "Waiting for next export";
   }

   // 蝗ｾ陦ｨ譏ｾ遉ｺ隶ｾ鄂ｮ
   ChartSetInteger(0, CHART_SHOW_GRID, false);
   Comment("");
   EventSetTimer(5);
   EnsureAutoTradingEnabled();
   RefreshAdaptiveControl(true);
   RefreshAllManagedDiagnostics();

   Print("[QuantGod] Multi-Strategy Engine v2.0 initialized");
   Print("辟ｦ轤ｹ蜩∫ｧ・ ", gDashboardSymbol, " | 逶第而蛻苓｡ｨ: ", GetManagedSymbolsLabel(),
         " | 鬟朱勦: ", RiskPercent, "% | 譛螟ｧ蝗樊彫: ", MaxDrawdownPercent, "%");

   LoadTradeLogState();
   LoadOpportunityLabelState();
   LogAccountSnapshot("INIT");
   gLastSnapshotLog = TimeLocal();
   AuditClosedTrades();
   if(EnableOpportunityLabels)
      ProcessOpportunityLabels(true);
   if(EnableStrategyReport)
      ExportStrategyEvaluationReport(true);
   UpdateChartDisplayV2();
   if(EnableDashboard) ExportDashboardData();

   return INIT_SUCCEEDED;
}

double NormalizeLotForSymbol(double lots, string symbol_name)
{
   double minLot = MarketInfo(symbol_name, MODE_MINLOT);
   double maxLot = MarketInfo(symbol_name, MODE_MAXLOT);
   double lotStep = MarketInfo(symbol_name, MODE_LOTSTEP);
   if(lotStep <= 0)
      lotStep = 0.01;

   lots = MathMax(minLot, MathMin(maxLot, lots));
   lots = MathFloor((lots / lotStep) + 0.000001) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   int lotDigits = 2;
   if(lotStep < 0.01)
      lotDigits = 3;

   return NormalizeDouble(lots, lotDigits);
}

double CalcLotSizeForBalance(double baseBalance, double riskPercent, double slPips, string symbol_name)
{
   if(baseBalance <= 0 || riskPercent <= 0 || slPips <= 0)
      return 0.0;

   double accountRisk = baseBalance * riskPercent / 100.0;
   double tickValue = MarketInfo(symbol_name, MODE_TICKVALUE);
   double tickSize = MarketInfo(symbol_name, MODE_TICKSIZE);
   if(tickValue <= 0 || tickSize <= 0)
      return 0.0;

   double pipValue = tickValue * (0.0001 / tickSize);
   if(StringFind(symbol_name, "JPY") >= 0)
      pipValue = tickValue * (0.01 / tickSize);

   if(pipValue <= 0)
      return 0.0;

   return NormalizeDouble(MathMax(0.0, accountRisk / (slPips * pipValue)), 5);
}

bool HasResearchTag(string comment)
{
   return StringFind(comment, "|v=") >= 0;
}

double ParseTaggedDouble(string text, string tag)
{
   int start = StringFind(text, tag);
   if(start < 0)
      return -1.0;

   string valueText = StringSubstr(text, start + StringLen(tag));
   int stopPos = StringFind(valueText, "|");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   stopPos = StringFind(valueText, "[");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   stopPos = StringFind(valueText, " ");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   return StrToDouble(valueText);
}

string ParseTaggedText(string text, string tag)
{
   int start = StringFind(text, tag);
   if(start < 0)
      return "";

   string valueText = StringSubstr(text, start + StringLen(tag));
   int stopPos = StringFind(valueText, "|");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   stopPos = StringFind(valueText, "[");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   stopPos = StringFind(valueText, " ");
   if(stopPos >= 0)
      valueText = StringSubstr(valueText, 0, stopPos);

   return valueText;
}

double GetResearchLotsFromComment(string comment, double actualLots)
{
   if(!UseVirtualResearchAccount)
      return actualLots;

   double taggedLots = ParseTaggedDouble(comment, "|v=");
   if(taggedLots > 0)
      return taggedLots;

   if(IgnoreLegacyTradesInVirtualStats)
      return 0.0;

   return actualLots;
}

double ScaleResearchNet(double actualNet, double actualLots, string comment)
{
   if(!UseVirtualResearchAccount)
      return actualNet;

   if(actualLots <= 0)
      return 0.0;

   double researchLots = GetResearchLotsFromComment(comment, actualLots);
   if(researchLots <= 0)
      return 0.0;

   return actualNet * (researchLots / actualLots);
}

double GetResearchClosedNetProfit()
{
   if(!UseVirtualResearchAccount)
      return 0.0;

   double closedNet = 0.0;
   for(int i = 0; i < OrdersHistoryTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      closedNet += ScaleResearchNet(actualNet, OrderLots(), OrderComment());
   }

   return closedNet;
}

double GetResearchOpenNetProfit()
{
   if(!UseVirtualResearchAccount)
      return 0.0;

   double openNet = 0.0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      openNet += ScaleResearchNet(actualNet, OrderLots(), OrderComment());
   }

   return openNet;
}

double GetResearchBalance()
{
   if(!UseVirtualResearchAccount)
      return AccountBalance();

   double researchBalance = VirtualStartingBalance + GetResearchClosedNetProfit();
   return MathMax(0.0, researchBalance);
}

double GetResearchEquity()
{
   if(!UseVirtualResearchAccount)
      return AccountEquity();

   double researchEquity = GetResearchBalance() + GetResearchOpenNetProfit();
   return MathMax(0.0, researchEquity);
}

double GetResearchProfit()
{
   if(!UseVirtualResearchAccount)
      return AccountProfit();

   return GetResearchOpenNetProfit();
}

double GetResearchDrawdownPercent()
{
   if(!UseVirtualResearchAccount)
   {
      double balance = AccountBalance();
      double equity = AccountEquity();
      if(balance <= 0)
         return 0.0;
      return MathMax(0.0, (balance - equity) / balance * 100.0);
   }

   double researchBalance = GetResearchBalance();
   double researchEquity = GetResearchEquity();
   if(researchBalance <= 0)
      return (researchEquity <= 0 ? 100.0 : 0.0);

   return MathMax(0.0, (researchBalance - researchEquity) / researchBalance * 100.0);
}

bool CheckResearchDrawdownLimit()
{
   if(!UseVirtualResearchAccount)
      return CheckMaxDrawdown(MaxDrawdownPercent);

   return GetResearchDrawdownPercent() < MaxDrawdownPercent;
}

double CalculateManagedLots(double slPips, string symbol_name, double &virtualLots)
{
   virtualLots = 0.0;
   double riskScale = GetStrategyRiskMultiplier(gCurrentEntryStrategyIndex);

   if(!UseVirtualResearchAccount)
      return CalcLotSize(RiskPercent * riskScale, slPips, symbol_name);

   virtualLots = CalcLotSizeForBalance(GetResearchBalance(), VirtualRiskPercent * riskScale, slPips, symbol_name);

   double executionLot = ResearchExecutionLot * riskScale;
   if(executionLot <= 0)
      executionLot = MarketInfo(symbol_name, MODE_MINLOT);

   return NormalizeLotForSymbol(MathMax(executionLot, MarketInfo(symbol_name, MODE_MINLOT)), symbol_name);
}

string BuildManagedOrderComment(string baseComment, double virtualLots)
{
   if(!UseVirtualResearchAccount)
      return baseComment;

   string tag = "|v=" + DoubleToStr(MathMax(0.0, virtualLots), 5);
   if(StringLen(baseComment) + StringLen(tag) <= 31)
      return baseComment + tag;

   tag = "|v=" + DoubleToStr(MathMax(0.0, virtualLots), 4);
   if(StringLen(baseComment) + StringLen(tag) <= 31)
      return baseComment + tag;

   return baseComment;
}

string BuildCompactEventKey(string eventId, int keyLength)
{
   if(eventId == "")
      return "";

   if(keyLength < 2)
      keyLength = 2;
   if(keyLength > 6)
      keyLength = 6;

   int modulo = 1;
   for(int i = 0; i < keyLength; i++)
      modulo *= 36;

   int hash = 7;
   for(int j = 0; j < StringLen(eventId); j++)
   {
      hash = (hash * 131 + StringGetChar(eventId, j)) % modulo;
      if(hash < 0)
         hash += modulo;
   }

   string alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
   string key = "";
   for(int k = 0; k < keyLength; k++)
   {
      int index = hash % 36;
      key = StringSubstr(alphabet, index, 1) + key;
      hash /= 36;
   }

   return key;
}

string BuildVirtualLotsTag(double virtualLots)
{
   double safeLots = MathMax(0.0, virtualLots);
   string raw = DoubleToStr(safeLots, 5);
   if(StringLen(raw) > 1 && StringSubstr(raw, 0, 1) == "0")
      raw = StringSubstr(raw, 1);
   return "|v=" + raw;
}

string BuildManagedOrderCommentWithEvent(string baseComment, double virtualLots, string eventId)
{
   string comment = UseVirtualResearchAccount ? BuildManagedOrderComment(baseComment, virtualLots) : baseComment;
   if(eventId == "")
      return comment;

   string lotTag = UseVirtualResearchAccount ? BuildVirtualLotsTag(virtualLots) : "";
   string eventKey = BuildCompactEventKey(eventId, 3);
   string eventTag = (eventKey == "" ? "" : "|e=" + eventKey);

   if(eventTag != "" && StringLen(baseComment) + StringLen(eventTag) + StringLen(lotTag) > 31)
   {
      eventKey = BuildCompactEventKey(eventId, 2);
      eventTag = (eventKey == "" ? "" : "|e=" + eventKey);
   }

   if(eventTag == "")
      return comment;

   if(UseVirtualResearchAccount && StringLen(baseComment) + StringLen(eventTag) + StringLen(lotTag) <= 31)
      return baseComment + eventTag + lotTag;

   if(StringLen(comment) + StringLen(eventTag) <= 31)
      return comment + eventTag;

   return comment;
}

double PriceToPips(double priceDistance, string symbol_name)
{
   double point = MarketInfo(symbol_name, MODE_POINT);
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   if(point <= 0)
      return 0.0;

   double pipFactor = ((digits == 3 || digits == 5) ? 10.0 : 1.0);
   return priceDistance / point / pipFactor;
}

int GetStrategyTimeframeByMagic(int magic)
{
   if(magic == MA_Magic)   return MA_Timeframe;
   if(magic == RSI_Magic)  return RSI_Timeframe;
   if(magic == BB_Magic)   return BB_Timeframe;
   if(magic == MACD_Magic) return MACD_Timeframe;
   if(magic == SR_Magic)   return SR_Timeframe;
   return PERIOD_H1;
}

int GetStrategyIndexByMagic(int magic)
{
   if(magic == MA_Magic)   return 0;
   if(magic == RSI_Magic)  return 1;
   if(magic == BB_Magic)   return 2;
   if(magic == MACD_Magic) return 3;
   if(magic == SR_Magic)   return 4;
   return -1;
}

int GetStrategyMagicByIndex(int index)
{
   if(index == 0) return MA_Magic;
   if(index == 1) return RSI_Magic;
   if(index == 2) return BB_Magic;
   if(index == 3) return MACD_Magic;
   if(index == 4) return SR_Magic;
   return 0;
}

string GetStrategyNameByIndex(int index)
{
   if(index == 0) return "MA_Cross";
   if(index == 1) return "RSI_Reversal";
   if(index == 2) return "BB_Triple";
   if(index == 3) return "MACD_Divergence";
   if(index == 4) return "SR_Breakout";
   return "Unknown";
}

bool IsStrategyConfiguredEnabled(int index)
{
   if(index == 0) return Enable_MA;
   if(index == 1) return Enable_RSI;
   if(index == 2) return Enable_BB;
   if(index == 3) return Enable_MACD;
   if(index == 4) return Enable_SR;
   return false;
}

double ClampAdaptiveRiskScale(double scale)
{
   if(scale < 0.10) return 0.10;
   if(scale > 2.50) return 2.50;
   return scale;
}

int GetAdaptiveWindowTradeCount()
{
   int windowTrades = AdaptiveWindowTrades;
   if(windowTrades < 1)
      windowTrades = 1;
   if(windowTrades > 50)
      windowTrades = 50;
   return windowTrades;
}

int GetAdaptiveMinTradeCount()
{
   int minTrades = AdaptiveMinClosedTrades;
   int windowTrades = GetAdaptiveWindowTradeCount();
   if(minTrades < 1)
      minTrades = 1;
   if(minTrades > windowTrades)
      minTrades = windowTrades;
   return minTrades;
}

int GetAdaptivePauseMinTradeCount()
{
   int pauseTrades = AdaptivePauseMinClosedTrades;
   int minTrades = GetAdaptiveMinTradeCount();
   if(pauseTrades < minTrades)
      pauseTrades = minTrades;
   return pauseTrades;
}

int GetAdaptiveBoostMinTradeCount()
{
   int boostTrades = AdaptiveBoostMinClosedTrades;
   int pauseTrades = GetAdaptivePauseMinTradeCount();
   if(boostTrades < pauseTrades)
      boostTrades = pauseTrades;
   return boostTrades;
}

string BuildAdaptiveSummary(int index)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return "n/a";

   return "window " + IntegerToString(gAdaptiveTradeCount[index]) +
          " total " + IntegerToString(gAdaptiveSampleCount[index]) +
          " WR " + DoubleToStr(gAdaptiveWinRate[index], 1) +
          "% PF " + DoubleToStr(gAdaptiveProfitFactor[index], 2) +
          " avg " + DoubleToStr(gAdaptiveAvgNet[index], 2) +
          " net " + DoubleToStr(gAdaptiveNetProfit[index], 2);
}

void AppendAdaptiveStateHistory(int strategyIndex, string prevState, bool prevActive,
                                double prevRiskMultiplier, datetime prevDisabledUntil)
{
   if(!EnableAdaptiveStateHistory)
      return;
   if(strategyIndex < 0 || strategyIndex >= STRATEGY_DIAG_COUNT)
      return;

   string newState = gAdaptiveState[strategyIndex];
   bool newActive = gAdaptiveStrategyActive[strategyIndex];
   double newRiskMultiplier = ClampAdaptiveRiskScale(gAdaptiveRiskMultiplier[strategyIndex]);
   datetime newDisabledUntil = gAdaptiveDisabledUntil[strategyIndex];

   bool changed = (prevState != newState) ||
                  (prevActive != newActive) ||
                  (MathAbs(prevRiskMultiplier - newRiskMultiplier) > 0.0001) ||
                  (prevDisabledUntil != newDisabledUntil);
   if(!changed)
      return;

   int handle = FileOpen("QuantGod_AdaptiveStateHistory.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen("QuantGod_AdaptiveStateHistory.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_AdaptiveStateHistory.csv, error=", GetLastError());
      return;
   }

   if(FileSize(handle) == 0)
   {
      FileWrite(handle,
                "TimeLocal", "TimeServer", "Strategy", "PrevState", "NewState",
                "PrevActive", "NewActive", "PrevRiskMultiplier", "NewRiskMultiplier",
                "PrevDisabledUntil", "NewDisabledUntil", "WindowTrades", "SampleTrades",
                "WinRate", "ProfitFactor", "AvgNet", "NetProfit", "Reason");
   }
   else
      FileSeek(handle, 0, SEEK_END);

   FileWrite(handle,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             GetStrategyNameByIndex(strategyIndex),
             (prevState == "" ? "INIT" : prevState),
             newState,
             BoolLabel(prevActive),
             BoolLabel(newActive),
             DoubleToStr(ClampAdaptiveRiskScale(prevRiskMultiplier), 2),
             DoubleToStr(newRiskMultiplier, 2),
             (prevDisabledUntil > 0 ? TimeToStr(prevDisabledUntil, TIME_DATE|TIME_MINUTES) : ""),
             (newDisabledUntil > 0 ? TimeToStr(newDisabledUntil, TIME_DATE|TIME_MINUTES) : ""),
             gAdaptiveTradeCount[strategyIndex],
             gAdaptiveSampleCount[strategyIndex],
             DoubleToStr(gAdaptiveWinRate[strategyIndex], 1),
             DoubleToStr(gAdaptiveProfitFactor[strategyIndex], 2),
             DoubleToStr(gAdaptiveAvgNet[strategyIndex], 2),
             DoubleToStr(gAdaptiveNetProfit[strategyIndex], 2),
             SanitizeCsvText(gAdaptiveReason[strategyIndex]));

   FileClose(handle);
}

void RefreshAdaptiveControl(bool force)
{
   int historyTotal = OrdersHistoryTotal();
   if(!force && historyTotal == gLastAdaptiveHistoryTotal &&
      TimeCurrent() - gLastAdaptiveRefresh < ADAPTIVE_REFRESH_SECONDS)
      return;

   gLastAdaptiveRefresh = TimeCurrent();
   gLastAdaptiveHistoryTotal = historyTotal;

   string prevState[STRATEGY_DIAG_COUNT];
   bool prevActive[STRATEGY_DIAG_COUNT];
   double prevRiskMultiplier[STRATEGY_DIAG_COUNT];
   datetime prevDisabledUntil[STRATEGY_DIAG_COUNT];

   ArrayInitialize(prevActive, false);
   ArrayInitialize(prevRiskMultiplier, 1.0);
   ArrayInitialize(prevDisabledUntil, 0);

   for(int snapIndex = 0; snapIndex < STRATEGY_DIAG_COUNT; snapIndex++)
   {
      prevState[snapIndex] = "";
      prevState[snapIndex] = gAdaptiveState[snapIndex];
      prevActive[snapIndex] = gAdaptiveStrategyActive[snapIndex];
      prevRiskMultiplier[snapIndex] = gAdaptiveRiskMultiplier[snapIndex];
      prevDisabledUntil[snapIndex] = gAdaptiveDisabledUntil[snapIndex];
   }

   for(int idx = 0; idx < STRATEGY_DIAG_COUNT; idx++)
   {
      bool configured = IsStrategyConfiguredEnabled(idx);
      gAdaptiveStrategyActive[idx] = configured;
      gAdaptiveRiskMultiplier[idx] = 1.0;
      gAdaptiveTradeCount[idx] = 0;
      gAdaptiveSampleCount[idx] = 0;
      gAdaptiveWinCount[idx] = 0;
      gAdaptiveGrossProfit[idx] = 0.0;
      gAdaptiveGrossLoss[idx] = 0.0;
      gAdaptiveNetProfit[idx] = 0.0;
      gAdaptiveAvgNet[idx] = 0.0;
      gAdaptiveWinRate[idx] = 0.0;
      gAdaptiveProfitFactor[idx] = 0.0;
      gAdaptiveLastCloseTime[idx] = 0;
      gAdaptiveDisabledUntil[idx] = 0;
      gAdaptiveState[idx] = configured ? "WARMUP" : "DISABLED";
      gAdaptiveReason[idx] = configured ? "Adaptive warm-up: waiting for first closed sample"
                                        : "Strategy disabled by input";
   }

   if(!EnableAdaptiveControl)
   {
      for(int offIndex = 0; offIndex < STRATEGY_DIAG_COUNT; offIndex++)
      {
         if(!IsStrategyConfiguredEnabled(offIndex))
            continue;
         gAdaptiveState[offIndex] = "ADAPTIVE_OFF";
         gAdaptiveReason[offIndex] = "Adaptive control disabled";
         AppendAdaptiveStateHistory(offIndex, prevState[offIndex], prevActive[offIndex],
                                    prevRiskMultiplier[offIndex], prevDisabledUntil[offIndex]);
      }
      return;
   }

   int windowTrades = GetAdaptiveWindowTradeCount();
   int minTrades = GetAdaptiveMinTradeCount();
   int pauseMinTrades = GetAdaptivePauseMinTradeCount();
   int boostMinTrades = GetAdaptiveBoostMinTradeCount();
   int sampleCounts[STRATEGY_DIAG_COUNT];
   int totalSampleCounts[STRATEGY_DIAG_COUNT];
   ArrayInitialize(sampleCounts, 0);
   ArrayInitialize(totalSampleCounts, 0);

   for(int histIndex = historyTotal - 1; histIndex >= 0; histIndex--)
   {
      if(!OrderSelect(histIndex, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      int strategyIndex = GetStrategyIndexByMagic(OrderMagicNumber());
      if(strategyIndex < 0 || !IsStrategyConfiguredEnabled(strategyIndex)) continue;
      totalSampleCounts[strategyIndex]++;
      gAdaptiveSampleCount[strategyIndex] = totalSampleCounts[strategyIndex];
      if(totalSampleCounts[strategyIndex] == 1)
         gAdaptiveLastCloseTime[strategyIndex] = OrderCloseTime();
      if(sampleCounts[strategyIndex] >= windowTrades) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double closedNet = UseVirtualResearchAccount ? ScaleResearchNet(actualNet, OrderLots(), OrderComment())
                                                   : actualNet;

      sampleCounts[strategyIndex]++;
      gAdaptiveTradeCount[strategyIndex] = sampleCounts[strategyIndex];
      if(closedNet > 0)
      {
         gAdaptiveWinCount[strategyIndex]++;
         gAdaptiveGrossProfit[strategyIndex] += closedNet;
      }
      else if(closedNet < 0)
      {
         gAdaptiveGrossLoss[strategyIndex] += MathAbs(closedNet);
      }
      gAdaptiveNetProfit[strategyIndex] += closedNet;
   }

   for(int evalIndex = 0; evalIndex < STRATEGY_DIAG_COUNT; evalIndex++)
   {
      if(!IsStrategyConfiguredEnabled(evalIndex))
         continue;

      int windowSampleTrades = gAdaptiveTradeCount[evalIndex];
      int totalTrades = gAdaptiveSampleCount[evalIndex];
      if(windowSampleTrades <= 0)
         continue;

      gAdaptiveAvgNet[evalIndex] = gAdaptiveNetProfit[evalIndex] / windowSampleTrades;
      gAdaptiveWinRate[evalIndex] = (double)gAdaptiveWinCount[evalIndex] * 100.0 / windowSampleTrades;
      if(gAdaptiveGrossLoss[evalIndex] > 0.0)
         gAdaptiveProfitFactor[evalIndex] = gAdaptiveGrossProfit[evalIndex] / gAdaptiveGrossLoss[evalIndex];
      else if(gAdaptiveGrossProfit[evalIndex] > 0.0)
         gAdaptiveProfitFactor[evalIndex] = 999.0;

      if(totalTrades < minTrades)
      {
         gAdaptiveState[evalIndex] = "WARMUP";
         gAdaptiveReason[evalIndex] = "Adaptive warm-up | " + BuildAdaptiveSummary(evalIndex) +
                                      " | need " + IntegerToString(minTrades) + " total trades";
         continue;
      }

      bool pauseCandidate = (gAdaptiveNetProfit[evalIndex] < 0.0) &&
                            (gAdaptiveAvgNet[evalIndex] <= AdaptiveDisableAvgNet ||
                             gAdaptiveProfitFactor[evalIndex] <= AdaptiveDisableProfitFactor);
      bool pauseEligible = (totalTrades >= pauseMinTrades);
      bool boostEligible = (totalTrades >= boostMinTrades);

      gAdaptiveDisabledUntil[evalIndex] = 0;
      if(pauseCandidate && pauseEligible &&
         gAdaptiveLastCloseTime[evalIndex] > 0 && AdaptiveCooldownMinutes > 0)
      {
         gAdaptiveDisabledUntil[evalIndex] = gAdaptiveLastCloseTime[evalIndex] + AdaptiveCooldownMinutes * 60;
      }

      if(pauseCandidate && gAdaptiveDisabledUntil[evalIndex] > 0 && TimeCurrent() < gAdaptiveDisabledUntil[evalIndex])
      {
         gAdaptiveStrategyActive[evalIndex] = false;
         gAdaptiveRiskMultiplier[evalIndex] = ClampAdaptiveRiskScale(AdaptiveLowRiskScale);
         gAdaptiveState[evalIndex] = "COOLDOWN";
         gAdaptiveReason[evalIndex] = "Adaptive pause | " + BuildAdaptiveSummary(evalIndex) +
                                      " | until " + TimeToStr(gAdaptiveDisabledUntil[evalIndex], TIME_DATE|TIME_MINUTES);
         continue;
      }

      if(pauseCandidate)
      {
         gAdaptiveRiskMultiplier[evalIndex] = ClampAdaptiveRiskScale(AdaptiveLowRiskScale);
         if(pauseEligible)
         {
            gAdaptiveState[evalIndex] = "RETEST";
            gAdaptiveReason[evalIndex] = "Adaptive retest | " + BuildAdaptiveSummary(evalIndex) +
                                         " | cooldown window passed";
         }
         else
         {
            gAdaptiveState[evalIndex] = "CAUTION";
            gAdaptiveReason[evalIndex] = "Adaptive caution | " + BuildAdaptiveSummary(evalIndex) +
                                         " | cooldown locked until " + IntegerToString(pauseMinTrades) + " total trades";
         }
         continue;
      }

      bool strong = (gAdaptiveNetProfit[evalIndex] > 0.0) &&
                    (gAdaptiveAvgNet[evalIndex] >= AdaptiveHighAvgNet) &&
                    (gAdaptiveProfitFactor[evalIndex] >= AdaptiveHighProfitFactor) &&
                    (gAdaptiveWinRate[evalIndex] >= AdaptiveHighWinRate);
      if(strong && boostEligible)
      {
         gAdaptiveRiskMultiplier[evalIndex] = ClampAdaptiveRiskScale(AdaptiveHighRiskScale);
         gAdaptiveState[evalIndex] = "BOOST";
         gAdaptiveReason[evalIndex] = "Adaptive boost | " + BuildAdaptiveSummary(evalIndex);
         continue;
      }

      bool cautious = (gAdaptiveNetProfit[evalIndex] <= 0.0) ||
                      (gAdaptiveProfitFactor[evalIndex] < 1.05) ||
                      (gAdaptiveWinRate[evalIndex] < 50.0);
      if(cautious)
      {
         gAdaptiveRiskMultiplier[evalIndex] = ClampAdaptiveRiskScale(AdaptiveLowRiskScale);
         gAdaptiveState[evalIndex] = "CAUTION";
         gAdaptiveReason[evalIndex] = "Adaptive caution | " + BuildAdaptiveSummary(evalIndex);
         continue;
      }

      gAdaptiveState[evalIndex] = "NORMAL";
      gAdaptiveReason[evalIndex] = "Adaptive normal | " + BuildAdaptiveSummary(evalIndex) +
                                   (strong && !boostEligible
                                    ? " | boost locked until " + IntegerToString(boostMinTrades) + " total trades"
                                    : "");
   }

   for(int logIndex = 0; logIndex < STRATEGY_DIAG_COUNT; logIndex++)
   {
      AppendAdaptiveStateHistory(logIndex, prevState[logIndex], prevActive[logIndex],
                                 prevRiskMultiplier[logIndex], prevDisabledUntil[logIndex]);
   }
}

bool IsStrategyRuntimeActive(int index)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return true;
   if(!IsStrategyConfiguredEnabled(index))
      return false;
   return gAdaptiveStrategyActive[index];
}

double GetStrategyRiskMultiplier(int index)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return 1.0;
   if(!IsStrategyConfiguredEnabled(index))
      return 1.0;
   return ClampAdaptiveRiskScale(gAdaptiveRiskMultiplier[index]);
}

string GetStrategyAdaptiveReason(int index)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return "";
   return gAdaptiveReason[index];
}

string GetStrategyRuntimeLabel(int index)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return "N/A";
   if(!IsStrategyConfiguredEnabled(index))
      return "OFF";
   if(!IsStrategyRuntimeActive(index))
      return "PAUSED";
   if(gAdaptiveState[index] == "BOOST")
      return "BOOST";
   if(gAdaptiveState[index] == "CAUTION" || gAdaptiveState[index] == "RETEST")
      return "LOW";
   return "ON";
}

int GetResearchMaxHoldMinutes(int timeframe)
{
   if(timeframe <= PERIOD_M15)
      return ResearchMaxHoldMinutes_M15;
   if(timeframe <= PERIOD_H1)
      return ResearchMaxHoldMinutes_H1;
   return ResearchMaxHoldMinutes_H4;
}

double AdjustTakeProfitPipsForResearch(double desiredTpPips, double slPips, string symbol_name)
{
   if(!UseVirtualResearchAccount || !EnableResearchFastExit)
      return desiredTpPips;

   double minTargetPips = MathMax(2.0, GetSpreadPips(symbol_name) * 3.0);
   double fastTargetPips = MathMax(minTargetPips, slPips * ResearchTargetRR);
   return MathMin(desiredTpPips, fastTargetPips);
}

bool SafeOrderCloseCurrent(string reason)
{
   string symbolName = OrderSymbol();
   int ticket = OrderTicket();
   double lots = OrderLots();
   int orderType = OrderType();
   int digits = DigitsForSymbolName(symbolName);
   double price = (orderType == OP_BUY) ? MarketInfo(symbolName, MODE_BID) : MarketInfo(symbolName, MODE_ASK);

   if(price <= 0)
      return false;

   RefreshRates();
   if(orderType == OP_BUY)
      price = MarketInfo(symbolName, MODE_BID);
   else if(orderType == OP_SELL)
      price = MarketInfo(symbolName, MODE_ASK);

   ResetLastError();
   bool closed = OrderClose(ticket, lots, NormalizeDouble(price, digits), 3, clrSilver);
   if(!closed)
   {
      int err = GetLastError();
      Print("[QG-EXIT] close failed | ticket=", ticket, " | ", symbolName, " | reason=", reason, " | err=", err);
      if(err == 136 || err == 137 || err == 138 || err == 146 || err == 4110)
      {
         Sleep(300);
         RefreshRates();
         if(orderType == OP_BUY)
            price = MarketInfo(symbolName, MODE_BID);
         else if(orderType == OP_SELL)
            price = MarketInfo(symbolName, MODE_ASK);

         ResetLastError();
         closed = OrderClose(ticket, lots, NormalizeDouble(price, digits), 3, clrSilver);
         if(!closed)
            Print("[QG-EXIT] retry failed | ticket=", ticket, " | ", symbolName, " | reason=", reason, " | err=", GetLastError());
      }
   }
   else
      Print("[QG-EXIT] closed | ticket=", ticket, " | ", symbolName, " | reason=", reason);

   return closed;
}

void ManageResearchFastExitForSelectedOrder()
{
   if(!UseVirtualResearchAccount || !EnableResearchFastExit)
      return;

   if(IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment()))
      return;

   int orderType = OrderType();
   if(orderType != OP_BUY && orderType != OP_SELL)
      return;

   string symbolName = OrderSymbol();
   double openPrice = OrderOpenPrice();
   double stopLoss = OrderStopLoss();
   if(stopLoss <= 0)
      return;

   double riskPips = PriceToPips(MathAbs(openPrice - stopLoss), symbolName);
   if(riskPips <= 0)
      return;

   double marketPrice = (orderType == OP_BUY) ? MarketInfo(symbolName, MODE_BID) : MarketInfo(symbolName, MODE_ASK);
   if(marketPrice <= 0)
      return;

   double profitPips = 0.0;
   if(orderType == OP_BUY)
      profitPips = PriceToPips(marketPrice - openPrice, symbolName);
   else
      profitPips = PriceToPips(openPrice - marketPrice, symbolName);

   double rr = profitPips / riskPips;
   int holdMinutes = (int)((TimeCurrent() - OrderOpenTime()) / 60);
   int maxHoldMinutes = GetResearchMaxHoldMinutes(GetStrategyTimeframeByMagic(OrderMagicNumber()));
   int digits = DigitsForSymbolName(symbolName);

   if(rr >= ResearchBreakEvenRR)
   {
      double protectOffset = PipsToPrice(ResearchBreakEvenLockPips, symbolName);
      double newSL = OrderStopLoss();
      bool shouldModify = false;

      if(orderType == OP_BUY)
      {
         newSL = NormalizeDouble(openPrice + protectOffset, digits);
         if(newSL > OrderStopLoss() + MarketInfo(symbolName, MODE_POINT))
            shouldModify = true;
      }
      else
      {
         newSL = NormalizeDouble(openPrice - protectOffset, digits);
         if(OrderStopLoss() == 0 || newSL < OrderStopLoss() - MarketInfo(symbolName, MODE_POINT))
            shouldModify = true;
      }

      if(shouldModify)
      {
         ResetLastError();
         if(!OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrYellow))
            Print("[QG-EXIT] breakeven modify failed | ticket=", OrderTicket(), " | err=", GetLastError());
      }
   }

   if(maxHoldMinutes > 0 && holdMinutes >= maxHoldMinutes)
   {
      string reason = "time_exit_flat";
      if(rr >= 0.20)
         reason = "time_exit_profit";
      else if(rr <= -0.20)
         reason = "time_exit_loss";

      SafeOrderCloseCurrent(reason + "|rr=" + DoubleToStr(rr, 2) + "|hold=" + IntegerToString(holdMinutes));
   }
}

void ManageResearchFastExits(string symbol_name)
{
   if(!UseVirtualResearchAccount || !EnableResearchFastExit)
      return;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(!IsManagedMagic(OrderMagicNumber())) continue;

      ManageResearchFastExitForSelectedOrder();
   }
}

double GetDisplayedBalance()
{
   return UseVirtualResearchAccount ? GetResearchBalance() : AccountBalance();
}

double GetDisplayedEquity()
{
   return UseVirtualResearchAccount ? GetResearchEquity() : AccountEquity();
}

double GetDisplayedProfit()
{
   return UseVirtualResearchAccount ? GetResearchProfit() : AccountProfit();
}

double GetDisplayedDrawdownPercent()
{
   if(UseVirtualResearchAccount)
      return GetResearchDrawdownPercent();

   double balance = AccountBalance();
   double equity = AccountEquity();
   if(balance <= 0)
      return 0.0;

   return MathMax(0.0, (balance - equity) / balance * 100.0);
}

double GetResearchSymbolFloatingProfit(string symbol_name)
{
   double symbolProfit = 0.0;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(!IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      symbolProfit += ScaleResearchNet(actualNet, OrderLots(), OrderComment());
   }

   return symbolProfit;
}

double GetResearchSymbolClosedProfit(string symbol_name, int &closedTrades, int &winTrades, datetime &lastCloseTime)
{
   closedTrades = 0;
   winTrades = 0;
   lastCloseTime = 0;

   double symbolProfit = 0.0;
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(!IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      datetime closeTime = OrderCloseTime();

      closedTrades++;
      symbolProfit += researchNet;
      if(researchNet > 0)
         winTrades++;
      if(closeTime > lastCloseTime)
         lastCloseTime = closeTime;
   }

   return symbolProfit;
}

bool LoadManagedSymbols()
{
   gManagedSymbolCount = 0;

   string csv = TradingSymbols;
   StringReplace(csv, ";", ",");
   StringReplace(csv, " ", "");

   string parts[];
   int partCount = StringSplit(csv, ',', parts);

   if(partCount > 0)
   {
      for(int i = 0; i < partCount && gManagedSymbolCount < MAX_MANAGED_SYMBOLS; i++)
      {
         string symbolName = parts[i];
         if(symbolName == "") continue;

         bool exists = false;
         for(int j = 0; j < gManagedSymbolCount; j++)
         {
            if(gManagedSymbols[j] == symbolName)
            {
               exists = true;
               break;
            }
         }
         if(exists) continue;

         if(AutoSelectSymbols)
            SymbolSelect(symbolName, true);

         double point = MarketInfo(symbolName, MODE_POINT);
         int digits = (int)MarketInfo(symbolName, MODE_DIGITS);
         if(point <= 0 || digits <= 0)
         {
            Print("[QuantGod] 霍ｳ霑・ｸ榊庄逕ｨ蜩∫ｧ・ ", symbolName);
            continue;
         }

         gManagedSymbols[gManagedSymbolCount] = symbolName;
         gManagedSymbolCount++;
      }
   }

   if(gManagedSymbolCount == 0)
   {
      gManagedSymbols[0] = gChartSymbol;
      gManagedSymbolCount = 1;
   }

   gDashboardSymbol = gManagedSymbols[0];
   for(int k = 0; k < gManagedSymbolCount; k++)
   {
      if(gManagedSymbols[k] == gChartSymbol)
      {
         gDashboardSymbol = gChartSymbol;
         break;
      }
   }

   return gManagedSymbolCount > 0;
}

bool PrepareSymbolContext(string symbol_name)
{
   if(symbol_name == "")
   {
      gCurrentDiagSymbolIndex = -1;
      return false;
   }

   gCurrentDiagSymbolIndex = GetManagedSymbolIndex(symbol_name);

   double point = MarketInfo(symbol_name, MODE_POINT);
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   if(point <= 0 || digits <= 0)
      return false;

   gSymbol = symbol_name;
   gDigits = digits;
   gPoint = point;
   return true;
}

int GetManagedSymbolIndex(string symbol_name)
{
   for(int i = 0; i < gManagedSymbolCount; i++)
   {
      if(gManagedSymbols[i] == symbol_name)
         return i;
   }
   return -1;
}

bool IsManagedSymbol(string symbol_name)
{
   return GetManagedSymbolIndex(symbol_name) >= 0;
}

bool IsManagedMagic(int magic)
{
   return magic == MA_Magic || magic == RSI_Magic || magic == BB_Magic ||
          magic == MACD_Magic || magic == SR_Magic;
}

string GetManagedSymbolsLabel()
{
   string label = "";
   for(int i = 0; i < gManagedSymbolCount; i++)
   {
      if(i > 0) label += ",";
      label += gManagedSymbols[i];
   }
   return label;
}

int CountPositionsAllSymbols(int magic)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != magic) continue;
      if(!IsManagedSymbol(OrderSymbol())) continue;
      count++;
   }
   return count;
}

int CountStrategyPositionsForSymbol(int magic, string symbol_name)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != magic) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(!IsManagedSymbol(OrderSymbol())) continue;
      count++;
   }
   return count;
}

int CountManagedPositionsForSymbol(string symbol_name)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(!IsManagedMagic(OrderMagicNumber())) continue;
      count++;
   }
   return count;
}

void FlattenManagedPortfolio()
{
   static datetime lastFlattenLog = 0;

   for(int i = 0; i < gManagedSymbolCount; i++)
   {
      string symbolName = gManagedSymbols[i];
      CloseAllByMagic(MA_Magic, symbolName);
      CloseAllByMagic(RSI_Magic, symbolName);
      CloseAllByMagic(BB_Magic, symbolName);
      CloseAllByMagic(MACD_Magic, symbolName);
      CloseAllByMagic(SR_Magic, symbolName);
   }

   if(TimeCurrent() - lastFlattenLog >= 15)
   {
      lastFlattenLog = TimeCurrent();
      Print("[QG-FLAT] FlattenManagedPositions active | remaining positions=", CountAllPositions());
   }
}

int DigitsForSymbolName(string symbol_name)
{
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   if(digits <= 0)
      return gDigits;
   return digits;
}

int GetTickAgeSecondsForSymbol(string symbol_name)
{
   datetime lastTick = (datetime)MarketInfo(symbol_name, MODE_TIME);
   if(lastTick <= 0)
      return -1;

   int age = (int)(TimeCurrent() - lastTick);
   if(age < 0)
      age = 0;
   return age;
}

bool IsNewStrategyBar(int strategyIndex, string symbol_name, int timeframe)
{
   int symbolIndex = GetManagedSymbolIndex(symbol_name);
   if(symbolIndex < 0 || strategyIndex < 0 || strategyIndex >= STRATEGY_DIAG_COUNT)
      return false;

   datetime currentBar = iTime(symbol_name, timeframe, 0);
   if(currentBar <= 0)
      return false;

   if(gStrategyLastBars[strategyIndex][symbolIndex] == currentBar)
      return false;

   gStrategyLastBars[strategyIndex][symbolIndex] = currentBar;
   return true;
}

void ProcessManagedSymbol(string symbol_name)
{
   if(!PrepareSymbolContext(symbol_name))
      return;

   RefreshStrategyDiagnostics();

   int tickAge = GetTickAgeSecondsForSymbol(symbol_name);
   if(tickAge < 0 || tickAge > 180)
      return;

   double ask = MarketInfo(symbol_name, MODE_ASK);
   double bid = MarketInfo(symbol_name, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   // Validate both terminal-level and symbol-level trade permissions.
   if(!IsTradeAllowed() || !MarketInfo(symbol_name, MODE_TRADEALLOWED))
   {
      static datetime lastTradeWarn = 0;
      if(TimeCurrent() - lastTradeWarn >= 60)
      {
         lastTradeWarn = TimeCurrent();
         Print("[QG-WARN] Trading not allowed for ", symbol_name);
      }
      return;
   }

   if(Enable_MA)
   {
      if(IsStrategyRuntimeActive(0))
      {
         gCurrentEntryStrategyIndex = 0;
         Strategy_MA_Cross();
      }
      else
      {
         SetStrategyDiagnostic(0, "AUTO_PAUSED", GetStrategyAdaptiveReason(0), 100);
         LogStrategySignal(0, gSymbol, MA_Timeframe, "AUTO_PAUSED", GetStrategyAdaptiveReason(0),
                           "NONE", 100, 0, 0, "runtime=" + GetStrategyRuntimeLabel(0));
      }
   }

   if(Enable_RSI)
   {
      if(IsStrategyRuntimeActive(1))
      {
         gCurrentEntryStrategyIndex = 1;
         Strategy_RSI_Reversal_V2();
      }
      else
      {
         SetStrategyDiagnostic(1, "AUTO_PAUSED", GetStrategyAdaptiveReason(1), 100);
         LogStrategySignal(1, gSymbol, RSI_Timeframe, "AUTO_PAUSED", GetStrategyAdaptiveReason(1),
                           "NONE", 100, 0, 0, "runtime=" + GetStrategyRuntimeLabel(1));
      }
   }

   if(Enable_BB)
   {
      if(IsStrategyRuntimeActive(2))
      {
         gCurrentEntryStrategyIndex = 2;
         Strategy_BB_Triple();
      }
      else
      {
         SetStrategyDiagnostic(2, "AUTO_PAUSED", GetStrategyAdaptiveReason(2), 100);
         LogStrategySignal(2, gSymbol, BB_Timeframe, "AUTO_PAUSED", GetStrategyAdaptiveReason(2),
                           "NONE", 100, 0, 0, "runtime=" + GetStrategyRuntimeLabel(2));
      }
   }

   if(Enable_MACD)
   {
      if(IsStrategyRuntimeActive(3))
      {
         gCurrentEntryStrategyIndex = 3;
         Strategy_MACD_Divergence_V2();
      }
      else
      {
         SetStrategyDiagnostic(3, "AUTO_PAUSED", GetStrategyAdaptiveReason(3), 100);
         LogStrategySignal(3, gSymbol, MACD_Timeframe, "AUTO_PAUSED", GetStrategyAdaptiveReason(3),
                           "NONE", 100, 0, 0, "runtime=" + GetStrategyRuntimeLabel(3));
      }
   }

   if(Enable_SR)
   {
      if(IsStrategyRuntimeActive(4))
      {
         gCurrentEntryStrategyIndex = 4;
         Strategy_SR_Breakout_V2();
      }
      else
      {
         SetStrategyDiagnostic(4, "AUTO_PAUSED", GetStrategyAdaptiveReason(4), 100);
         LogStrategySignal(4, gSymbol, SR_Timeframe, "AUTO_PAUSED", GetStrategyAdaptiveReason(4),
                           "NONE", 100, 0, 0, "runtime=" + GetStrategyRuntimeLabel(4));
      }
   }

   gCurrentEntryStrategyIndex = -1;

   if(TrailingStopPips > 0)
   {
      if(Enable_MA)   TrailingStop(MA_Magic, TrailingStopPips, symbol_name);
      if(Enable_RSI)  TrailingStop(RSI_Magic, TrailingStopPips, symbol_name);
      if(Enable_BB)   TrailingStop(BB_Magic, TrailingStopPips, symbol_name);
      if(Enable_MACD) TrailingStop(MACD_Magic, TrailingStopPips, symbol_name);
      if(Enable_SR)   TrailingStop(SR_Magic, TrailingStopPips, symbol_name);
   }
}

void ProcessManagedTrading()
{
   static datetime lastGuardLog = 0;
   bool logGuard = (TimeCurrent() - lastGuardLog >= 60);

   RefreshAdaptiveControl();

   if(FlattenManagedPositions)
   {
      if(logGuard)
      {
         lastGuardLog = TimeCurrent();
         Print("[QG-BLOCK] FlattenManagedPositions=true | closing all managed positions");
      }
      FlattenManagedPortfolio();
      PrepareSymbolContext(gDashboardSymbol);
      return;
   }

   for(int manageIndex = 0; manageIndex < gManagedSymbolCount; manageIndex++)
      ManageResearchFastExits(gManagedSymbols[manageIndex]);

   if(PauseNewEntries)
   {
      if(logGuard)
      {
         lastGuardLog = TimeCurrent();
         Print("[QG-BLOCK] PauseNewEntries=true | skipping new entries");
      }
      PrepareSymbolContext(gDashboardSymbol);
      return;
   }

   if(!CheckResearchDrawdownLimit())
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] MaxDrawdown exceeded | researchDD=", DoubleToStr(GetResearchDrawdownPercent(), 2));} return; }
   if(UseTradeSession && !IsTradeSession())
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] Out of trade session");} return; }
   if(!IsConnected())
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] Not connected");} return; }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] ACCOUNT_TRADE_ALLOWED=false");} return; }
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] ACCOUNT_TRADE_EXPERT=false");} return; }
   if(!IsTerminalTradeEnabled())
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] TerminalTradeEnabled=false");} return; }
   if(!IsProgramTradeEnabled())
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] ProgramTradeEnabled=false (EA Allow live trading OFF)");} return; }

   if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-PASS] All guards passed, executing strategies");}

   static datetime lastDebugLog = 0;
   bool doDebug = (TimeCurrent() - lastDebugLog >= 300); // 每5分钟输出一次状态
   if(doDebug) lastDebugLog = TimeCurrent();

   for(int pass = 0; pass < 2; pass++)
   {
      for(int i = 0; i < gManagedSymbolCount; i++)
      {
         string symbolName = gManagedSymbols[i];
         bool isDashboardSymbol = (symbolName == gDashboardSymbol);
         if((pass == 0 && isDashboardSymbol) || (pass == 1 && !isDashboardSymbol))
            continue;

         ProcessManagedSymbol(symbolName);
      }
   }

   if(doDebug)
      Print("[QG] ProcessManagedTrading OK | symbols=", gManagedSymbolCount,
            " | positions=", CountAllPositions(), "/", MaxTotalTrades);

   PrepareSymbolContext(gDashboardSymbol);
}

void Strategy_RSI_Reversal_V2()
{
   if(HasOpenPosition(RSI_Magic, gSymbol))
   {
      string reason = "Existing RSI_Reversal position is still open";
      SetStrategyDiagnostic(1, "IN_POSITION", reason, 100);
      LogStrategySignal(1, gSymbol, RSI_Timeframe, "IN_POSITION", reason, "NONE", 100, 0, 0, "");
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      string reason = "Max concurrent trades reached";
      SetStrategyDiagnostic(1, "PORTFOLIO_LIMIT", reason, 100);
      LogStrategySignal(1, gSymbol, RSI_Timeframe, "PORTFOLIO_LIMIT", reason, "NONE", 100, 0, 0, "");
      return;
   }

   if(!IsNewStrategyBar(1, gSymbol, RSI_Timeframe))
   {
      SetStrategyDiagnostic(1, "WAIT_BAR", BuildWaitBarReason(1), GetLastEvalScore(1));
      return;
   }

   double rsi1 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 1);
   double rsi2 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 2);
   double bbLower = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbUpper = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double close1 = iClose(gSymbol, RSI_Timeframe, 1);
   double atrSL = GetATRStopLoss(gSymbol, RSI_Timeframe, 14, 1.5);
   double ask = MarketInfo(gSymbol, MODE_ASK);
   double bid = MarketInfo(gSymbol, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   bool buyReversal = (rsi1 <= RSI_OS || (rsi2 < RSI_OS && rsi1 > RSI_OS));
   bool buyBand = (close1 <= bbLower * 1.008);
   bool sellReversal = (rsi1 >= RSI_OB || (rsi2 > RSI_OB && rsi1 < RSI_OB));
   bool sellBand = (close1 >= bbUpper * 0.992);
   double buyScore = (double)((buyReversal ? 1 : 0) + (buyBand ? 1 : 0)) / 2.0 * 100.0;
   double sellScore = (double)((sellReversal ? 1 : 0) + (sellBand ? 1 : 0)) / 2.0 * 100.0;

   Print("[RSI] ", gSymbol, " | RSI2=", DoubleToStr(rsi1,1), " prev=", DoubleToStr(rsi2,1),
         " close=", DoubleToStr(close1,5), " bbL=", DoubleToStr(bbLower,5), " bbU=", DoubleToStr(bbUpper,5),
         " | rev=", (buyReversal?"BUY":(sellReversal?"SELL":"NONE")),
         " band=", (buyBand?"LOW":(sellBand?"HIGH":"MID")));

   if(buyReversal && buyBand)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 1.5, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);
      string detail = "reversal=Y band=Y";
      string buyReason = "RSI_Reversal buy order sent on " + TimeframeLabel(RSI_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_RSI_Rev_BUY", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            orderComment, RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 1, gSymbol, RSI_Timeframe, "BUY_ORDER_SENT", "BUY", 100,
                              ask, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(1, "BUY_ORDER_SENT", buyReason, 100);
         LogStrategySignalWithEvent(1, gSymbol, RSI_Timeframe, "BUY_ORDER_SENT", buyReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "RSI buy setup failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(1, gSymbol, RSI_Timeframe, "ORDER_SEND_FAILED", failReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   if(sellReversal && sellBand)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 1.5, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);
      string detail = "reversal=Y band=Y";
      string sellReason = "RSI_Reversal sell order sent on " + TimeframeLabel(RSI_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_RSI_Rev_SELL", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            orderComment, RSI_Magic, 0, clrOrange);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 1, gSymbol, RSI_Timeframe, "SELL_ORDER_SENT", "SELL", 100,
                              bid, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(1, "SELL_ORDER_SENT", sellReason, 100);
         LogStrategySignalWithEvent(1, gSymbol, RSI_Timeframe, "SELL_ORDER_SENT", sellReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "RSI sell setup failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(1, gSymbol, RSI_Timeframe, "ORDER_SEND_FAILED", failReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   if(buyScore >= sellScore)
   {
      string reason = "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | reversal=" + BoolLabel(buyReversal) +
                      " band=" + BoolLabel(buyBand);
      string detail = "reversal=" + BoolLabel(buyReversal) + " band=" + BoolLabel(buyBand);
      SetStrategyDiagnostic(1, "NO_SETUP", reason, buyScore);
      LogStrategySignal(1, gSymbol, RSI_Timeframe, "NO_SETUP", reason, "BUY", buyScore, buyScore, sellScore, detail);
   }
   else
   {
      string reason = "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | reversal=" + BoolLabel(sellReversal) +
                      " band=" + BoolLabel(sellBand);
      string detail = "reversal=" + BoolLabel(sellReversal) + " band=" + BoolLabel(sellBand);
      SetStrategyDiagnostic(1, "NO_SETUP", reason, sellScore);
      LogStrategySignal(1, gSymbol, RSI_Timeframe, "NO_SETUP", reason, "SELL", sellScore, buyScore, sellScore, detail);
   }
}

int DetectBullishDivergenceV2()
{
   double priceLow1 = 0, priceLow2 = 0;
   double macdLow1 = 0, macdLow2 = 0;
   int pos1 = 0, pos2 = 0;

   for(int i = 2; i < MACD_LookBack; i++)
   {
      double lowPrev = iLow(gSymbol, MACD_Timeframe, i + 1);
      double lowCurr = iLow(gSymbol, MACD_Timeframe, i);
      double lowNext = iLow(gSymbol, MACD_Timeframe, i - 1);

      if(lowCurr < lowPrev && lowCurr < lowNext)
      {
         if(pos1 == 0)
         {
            pos1 = i;
            priceLow1 = lowCurr;
            macdLow1 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
         }
         else if(pos2 == 0)
         {
            pos2 = i;
            priceLow2 = lowCurr;
            macdLow2 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
            break;
         }
      }
   }

   if(pos1 == 0 || pos2 == 0)
      return 0;

   if(priceLow1 < priceLow2 && macdLow1 > macdLow2)
      return 1;

   return 0;
}

int DetectBearishDivergenceV2()
{
   double priceHigh1 = 0, priceHigh2 = 0;
   double macdHigh1 = 0, macdHigh2 = 0;
   int pos1 = 0, pos2 = 0;

   for(int i = 2; i < MACD_LookBack; i++)
   {
      double highPrev = iHigh(gSymbol, MACD_Timeframe, i + 1);
      double highCurr = iHigh(gSymbol, MACD_Timeframe, i);
      double highNext = iHigh(gSymbol, MACD_Timeframe, i - 1);

      if(highCurr > highPrev && highCurr > highNext)
      {
         if(pos1 == 0)
         {
            pos1 = i;
            priceHigh1 = highCurr;
            macdHigh1 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
         }
         else if(pos2 == 0)
         {
            pos2 = i;
            priceHigh2 = highCurr;
            macdHigh2 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
            break;
         }
      }
   }

   if(pos1 == 0 || pos2 == 0)
      return 0;

   if(priceHigh1 > priceHigh2 && macdHigh1 < macdHigh2)
      return 1;

   return 0;
}

void Strategy_MACD_Divergence_V2()
{
   if(HasOpenPosition(MACD_Magic, gSymbol))
   {
      string reason = "Existing MACD_Divergence position is still open";
      SetStrategyDiagnostic(3, "IN_POSITION", reason, 100);
      LogStrategySignal(3, gSymbol, MACD_Timeframe, "IN_POSITION", reason, "NONE", 100, 0, 0, "");
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      string reason = "Max concurrent trades reached";
      SetStrategyDiagnostic(3, "PORTFOLIO_LIMIT", reason, 100);
      LogStrategySignal(3, gSymbol, MACD_Timeframe, "PORTFOLIO_LIMIT", reason, "NONE", 100, 0, 0, "");
      return;
   }

   if(!IsNewStrategyBar(3, gSymbol, MACD_Timeframe))
   {
      SetStrategyDiagnostic(3, "WAIT_BAR", BuildWaitBarReason(3), GetLastEvalScore(3));
      return;
   }

   int bullDiv = DetectBullishDivergenceV2();
   int bearDiv = DetectBearishDivergenceV2();
   double atrSL = GetATRStopLoss(gSymbol, MACD_Timeframe, 14, 2.0);
   double ask = MarketInfo(gSymbol, MODE_ASK);
   double bid = MarketInfo(gSymbol, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   if(bullDiv > 0)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);
      string detail = "bullDiv=Y bearDiv=N";
      string buyReason = "Bullish MACD divergence triggered a buy";
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_MACD_Div_BUY", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            orderComment, MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 蠎戊レ遖ｻ荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 3, gSymbol, MACD_Timeframe, "BUY_ORDER_SENT", "BUY", 100,
                              ask, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(3, "BUY_ORDER_SENT", buyReason, 100);
         LogStrategySignalWithEvent(3, gSymbol, MACD_Timeframe, "BUY_ORDER_SENT", buyReason, "BUY", 100,
                                    100, 0, detail, eventId);
      }
      else
      {
         string failReason = "Bullish MACD divergence failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(3, gSymbol, MACD_Timeframe, "ORDER_SEND_FAILED", failReason, "BUY", 100,
                                    100, 0, detail, eventId);
      }
      return;
   }

   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);
      string detail = "bullDiv=N bearDiv=Y";
      string sellReason = "Bearish MACD divergence triggered a sell";
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_MACD_Div_SELL", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            orderComment, MACD_Magic, 0, clrCrimson);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 鬘ｶ閭檎ｦｻ蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 3, gSymbol, MACD_Timeframe, "SELL_ORDER_SENT", "SELL", 100,
                              bid, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(3, "SELL_ORDER_SENT", sellReason, 100);
         LogStrategySignalWithEvent(3, gSymbol, MACD_Timeframe, "SELL_ORDER_SENT", sellReason, "SELL", 100,
                                    0, 100, detail, eventId);
      }
      else
      {
         string failReason = "Bearish MACD divergence failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(3, gSymbol, MACD_Timeframe, "ORDER_SEND_FAILED", failReason, "SELL", 100,
                                    0, 100, detail, eventId);
      }
      return;
   }

   string noSetupReason = "No MACD divergence found in the last " + IntegerToString(MACD_LookBack) + " bars";
   string noSetupDetail = "bullDiv=" + BoolLabel(bullDiv > 0) + " bearDiv=" + BoolLabel(bearDiv > 0);
   SetStrategyDiagnostic(3, "NO_SETUP", noSetupReason, 0);
   LogStrategySignal(3, gSymbol, MACD_Timeframe, "NO_SETUP", noSetupReason, "NONE", 0, 0, 0, noSetupDetail);
}

void Strategy_SR_Breakout_V2()
{
   if(HasOpenPosition(SR_Magic, gSymbol))
   {
      string reason = "Existing SR_Breakout position is still open";
      SetStrategyDiagnostic(4, "IN_POSITION", reason, 100);
      LogStrategySignal(4, gSymbol, SR_Timeframe, "IN_POSITION", reason, "NONE", 100, 0, 0, "");
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      string reason = "Max concurrent trades reached";
      SetStrategyDiagnostic(4, "PORTFOLIO_LIMIT", reason, 100);
      LogStrategySignal(4, gSymbol, SR_Timeframe, "PORTFOLIO_LIMIT", reason, "NONE", 100, 0, 0, "");
      return;
   }

   if(!IsNewStrategyBar(4, gSymbol, SR_Timeframe))
   {
      SetStrategyDiagnostic(4, "WAIT_BAR", BuildWaitBarReason(4), GetLastEvalScore(4));
      return;
   }

   double resistance = 0;
   double support = 999999;
   for(int i = 1; i <= SR_LookBack; i++)
   {
      double high = iHigh(gSymbol, SR_Timeframe, i);
      double low = iLow(gSymbol, SR_Timeframe, i);
      if(high > resistance) resistance = high;
      if(low < support) support = low;
   }

   double close1 = iClose(gSymbol, SR_Timeframe, 1);
   double close2 = iClose(gSymbol, SR_Timeframe, 2);
   double breakPrice = PipsToPrice(SR_BreakPips, gSymbol);
   double avgVol = 0;
   for(int j = 1; j <= 20; j++)
      avgVol += (double)iVolume(gSymbol, SR_Timeframe, j);
   avgVol /= 20.0;

   bool volumeConfirm = iVolume(gSymbol, SR_Timeframe, 1) > avgVol * 1.05;
   bool buyPrevBelow = (close2 < resistance);
   bool buyBreak = (close1 > resistance + breakPrice);
   bool sellPrevAbove = (close2 > support);
   bool sellBreak = (close1 < support - breakPrice);
   double buyScore = (double)((buyPrevBelow ? 1 : 0) + (buyBreak ? 1 : 0) + (volumeConfirm ? 1 : 0)) / 3.0 * 100.0;
   double sellScore = (double)((sellPrevAbove ? 1 : 0) + (sellBreak ? 1 : 0) + (volumeConfirm ? 1 : 0)) / 3.0 * 100.0;
   double atrSL = GetATRStopLoss(gSymbol, SR_Timeframe, 14, 1.5);
   double ask = MarketInfo(gSymbol, MODE_ASK);
   double bid = MarketInfo(gSymbol, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   if(buyPrevBelow && buyBreak)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);
      string detail = "prevBelow=Y break=Y volume=" + BoolLabel(volumeConfirm);
      string buyReason = "SR_Breakout resistance breakout buy";
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_SR_Break_BUY", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            orderComment, SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR遯∫ｴ] 遯∫ｴ髦ｻ蜉帑ｹｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol, " R=", resistance);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 4, gSymbol, SR_Timeframe, "BUY_ORDER_SENT", "BUY", 100,
                              ask, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(4, "BUY_ORDER_SENT", buyReason, 100);
         LogStrategySignalWithEvent(4, gSymbol, SR_Timeframe, "BUY_ORDER_SENT", buyReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "SR breakout buy failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(4, gSymbol, SR_Timeframe, "ORDER_SEND_FAILED", failReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   if(sellPrevAbove && sellBreak)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);
      string detail = "prevAbove=Y break=Y volume=" + BoolLabel(volumeConfirm);
      string sellReason = "SR_Breakout support breakdown sell";
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_SR_Break_SELL", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            orderComment, SR_Magic, 0, clrTomato);
      if(ticket > 0) Print("[SR遯∫ｴ] 霍檎ｴ謾ｯ謦大獄蜃ｺ ", lots, " 謇・@ ", bid, " | ", gSymbol, " S=", support);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 4, gSymbol, SR_Timeframe, "SELL_ORDER_SENT", "SELL", 100,
                              bid, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(4, "SELL_ORDER_SENT", sellReason, 100);
         LogStrategySignalWithEvent(4, gSymbol, SR_Timeframe, "SELL_ORDER_SENT", sellReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "SR breakout sell failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(4, gSymbol, SR_Timeframe, "ORDER_SEND_FAILED", failReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   if(buyScore >= sellScore)
   {
      string noSetupReason = "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | prevBelow=" + BoolLabel(buyPrevBelow) +
                             " break=" + BoolLabel(buyBreak) + " volume=" + BoolLabel(volumeConfirm);
      string noSetupDetail = "prevBelow=" + BoolLabel(buyPrevBelow) + " break=" + BoolLabel(buyBreak) +
                             " volume=" + BoolLabel(volumeConfirm);
      SetStrategyDiagnostic(4, "NO_SETUP", noSetupReason, buyScore);
      LogStrategySignal(4, gSymbol, SR_Timeframe, "NO_SETUP", noSetupReason, "BUY", buyScore, buyScore, sellScore, noSetupDetail);
   }
   else
   {
      string noSetupReason = "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | prevAbove=" + BoolLabel(sellPrevAbove) +
                             " break=" + BoolLabel(sellBreak) + " volume=" + BoolLabel(volumeConfirm);
      string noSetupDetail = "prevAbove=" + BoolLabel(sellPrevAbove) + " break=" + BoolLabel(sellBreak) +
                             " volume=" + BoolLabel(volumeConfirm);
      SetStrategyDiagnostic(4, "NO_SETUP", noSetupReason, sellScore);
      LogStrategySignal(4, gSymbol, SR_Timeframe, "NO_SETUP", noSetupReason, "SELL", sellScore, buyScore, sellScore, noSetupDetail);
   }
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Print("[QuantGod] Engine stopped, reason=", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTimer()
{
   EnsureAutoTradingEnabled();
   PrepareSymbolContext(gDashboardSymbol);
   RefreshAdaptiveControl();
   RefreshAllManagedDiagnostics();
   ProcessManagedTrading();
   PrepareSymbolContext(gDashboardSymbol);
   AuditClosedTrades();
   ProcessOpportunityLabels(false);
   ExportStrategyEvaluationReport(false);
   if(TimeLocal() - gLastSnapshotLog >= 300)
   {
      LogAccountSnapshot("TIMER");
      gLastSnapshotLog = TimeLocal();
   }
   UpdateChartDisplayV2();

   if(EnableDashboard)
   {
      ExportDashboardData();
      gLastExport = TimeLocal();
   }
}

void OnTick()
{
   static int tickCount = 0;
   tickCount++;
   if(tickCount <= 3 || tickCount % 500 == 0)
      Print("[QG-TICK] #", tickCount, " symbol=", Symbol(), " dash=", gDashboardSymbol,
            " managed=", gManagedSymbolCount, " connected=", IsConnected());

   gLastTickTime = (datetime)MarketInfo(gDashboardSymbol, MODE_TIME);
   PrepareSymbolContext(gDashboardSymbol);
   RefreshAdaptiveControl();
   RefreshAllManagedDiagnostics();

   // 执行交易策略
   ProcessManagedTrading();

   // 追踪止损
   if(TrailingStopPips > 0)
   {
      for(int i = 0; i < gManagedSymbolCount; i++)
      {
         string sym = gManagedSymbols[i];
         if(Enable_MA)   TrailingStop(MA_Magic, TrailingStopPips, sym);
         if(Enable_RSI)  TrailingStop(RSI_Magic, TrailingStopPips, sym);
         if(Enable_BB)   TrailingStop(BB_Magic, TrailingStopPips, sym);
         if(Enable_MACD) TrailingStop(MACD_Magic, TrailingStopPips, sym);
         if(Enable_SR)   TrailingStop(SR_Magic, TrailingStopPips, sym);
      }
   }

   // 更新图表显示
   UpdateChartDisplayV2();

   // 导出面板数据 (每30秒)
   if(EnableDashboard && TimeCurrent() - gLastExport >= 30)
   {
      ExportDashboardData();
      gLastExport = TimeCurrent();
   }
}

int SafeOrderSend(string sym, int cmd, double volume, double price, int slippage,
                   double sl, double tp, string comment, int magic, datetime expiration, color arrow)
{
   gLastOrderSendError = 0;
   RefreshRates();
   // Refresh price for the actual symbol
   if(cmd == OP_BUY)
      price = MarketInfo(sym, MODE_ASK);
   else if(cmd == OP_SELL)
      price = MarketInfo(sym, MODE_BID);

   ResetLastError();
   int ticket = OrderSend(sym, cmd, volume, NormalizeDouble(price, (int)MarketInfo(sym, MODE_DIGITS)),
                          slippage, sl, tp, comment, magic, expiration, arrow);
   if(ticket < 0)
   {
      int err = GetLastError();
      gLastOrderSendError = err;
      Print("[QG-ORDER] FAILED ", sym, " ", (cmd==OP_BUY?"BUY":"SELL"), " ", volume,
            " @ ", price, " err=", err);
      // Retry once after short wait for transient errors
      if(err == 136 || err == 137 || err == 138 || err == 146 || err == 4110)
      {
         Sleep(500);
         RefreshRates();
         if(cmd == OP_BUY) price = MarketInfo(sym, MODE_ASK);
         else if(cmd == OP_SELL) price = MarketInfo(sym, MODE_BID);
         ResetLastError();
         ticket = OrderSend(sym, cmd, volume, NormalizeDouble(price, (int)MarketInfo(sym, MODE_DIGITS)),
                           slippage, sl, tp, comment, magic, expiration, arrow);
         if(ticket < 0)
         {
            gLastOrderSendError = GetLastError();
            Print("[QG-ORDER] RETRY FAILED ", sym, " err=", gLastOrderSendError);
         }
         else
         {
            gLastOrderSendError = 0;
            Print("[QG-ORDER] RETRY OK ", sym, " ticket=", ticket);
         }
      }
   }
   else
   {
      gLastOrderSendError = 0;
      Print("[QG-ORDER] OK ", sym, " ", (cmd==OP_BUY?"BUY":"SELL"), " ", volume,
            " @ ", price, " ticket=", ticket);
   }
   return ticket;
}

string BoolLabel(bool value)
{
   return value ? "Y" : "N";
}

string TimeframeLabel(int timeframe)
{
   switch(timeframe)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      case PERIOD_MN1: return "MN1";
      default:         return IntegerToString(timeframe);
   }
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", " ");
   StringReplace(value, "\n", " ");
   return value;
}

string SanitizeCsvText(string value)
{
   StringReplace(value, ",", ";");
   StringReplace(value, "\"", "'");
   StringReplace(value, "\r", " ");
   StringReplace(value, "\n", " ");
   return value;
}

int GetTimeframeSeconds(int timeframe)
{
   switch(timeframe)
   {
      case PERIOD_M1:  return 60;
      case PERIOD_M5:  return 300;
      case PERIOD_M15: return 900;
      case PERIOD_M30: return 1800;
      case PERIOD_H1:  return 3600;
      case PERIOD_H4:  return 14400;
      case PERIOD_D1:  return 86400;
      case PERIOD_W1:  return 604800;
      default:         return 0;
   }
}

int GetOpportunityHorizonBars(int timeframe)
{
   int horizonBars = OpportunityHorizonBars_H4;
   if(timeframe <= PERIOD_M15)
      horizonBars = OpportunityHorizonBars_M15;
   else if(timeframe <= PERIOD_H1)
      horizonBars = OpportunityHorizonBars_H1;

   if(horizonBars < 1)
      horizonBars = 1;
   return horizonBars;
}

string BuildSignalEventId()
{
   string eventId = IntegerToString((int)TimeCurrent()) + "_" + IntegerToString(gSignalEventCounter);
   gSignalEventCounter++;
   return eventId;
}

bool BuildSignalFeatureSnapshot(string symbol_name, int timeframe, SignalFeatureSnapshot &snapshot)
{
   snapshot.eventBarTime = iTime(symbol_name, timeframe, 1);
   if(snapshot.eventBarTime <= 0)
      snapshot.eventBarTime = TimeCurrent();

   snapshot.horizonBars = GetOpportunityHorizonBars(timeframe);
   int timeframeSeconds = GetTimeframeSeconds(timeframe);
   snapshot.labelReadyTime = (timeframeSeconds > 0)
                             ? snapshot.eventBarTime + (snapshot.horizonBars + 1) * timeframeSeconds
                             : 0;

   snapshot.open1 = iOpen(symbol_name, timeframe, 1);
   snapshot.high1 = iHigh(symbol_name, timeframe, 1);
   snapshot.low1 = iLow(symbol_name, timeframe, 1);
   snapshot.close1 = iClose(symbol_name, timeframe, 1);
   snapshot.close2 = iClose(symbol_name, timeframe, 2);
   snapshot.refPrice = snapshot.close1;

   snapshot.spreadPips = GetSpreadPips(symbol_name);
   snapshot.atrPips = PriceToPips(iATR(symbol_name, timeframe, 14, 1), symbol_name);
   snapshot.adxValue = iADX(symbol_name, timeframe, 14, PRICE_CLOSE, MODE_MAIN, 1);

   snapshot.bbUpper = iBands(symbol_name, timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_UPPER, 1);
   snapshot.bbMiddle = iBands(symbol_name, timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_MAIN, 1);
   snapshot.bbLower = iBands(symbol_name, timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_LOWER, 1);
   snapshot.bbWidthPips = PriceToPips(MathAbs(snapshot.bbUpper - snapshot.bbLower), symbol_name);

   double bbWidthPrice = MathAbs(snapshot.bbUpper - snapshot.bbLower);
   snapshot.bbPosPct = 50.0;
   if(bbWidthPrice > 0.0)
      snapshot.bbPosPct = (snapshot.close1 - snapshot.bbLower) / bbWidthPrice * 100.0;

   snapshot.barRangePips = PriceToPips(snapshot.high1 - snapshot.low1, symbol_name);
   snapshot.barBodyPips = PriceToPips(MathAbs(snapshot.close1 - snapshot.open1), symbol_name);
   snapshot.closeDeltaPips = PriceToPips(snapshot.close1 - snapshot.close2, symbol_name);

   snapshot.rsi2 = iRSI(symbol_name, timeframe, 2, PRICE_CLOSE, 1);
   snapshot.rsi14 = iRSI(symbol_name, timeframe, 14, PRICE_CLOSE, 1);

   snapshot.emaFast = iMA(symbol_name, timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   snapshot.emaSlow = iMA(symbol_name, timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   snapshot.trendMA = iMA(symbol_name, timeframe, MA_TrendPeriod, 0, MODE_SMA, PRICE_CLOSE, 1);
   snapshot.maGapPips = PriceToPips(snapshot.emaFast - snapshot.emaSlow, symbol_name);
   snapshot.trendDistancePips = PriceToPips(snapshot.close1 - snapshot.trendMA, symbol_name);

   snapshot.macdMain = iMACD(symbol_name, timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, 1);
   snapshot.macdSignal = iMACD(symbol_name, timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_SIGNAL, 1);
   snapshot.macdHist = snapshot.macdMain - snapshot.macdSignal;

   snapshot.volume1 = (double)iVolume(symbol_name, timeframe, 1);
   snapshot.avgVolume20 = 0.0;
   for(int volShift = 1; volShift <= 20; volShift++)
      snapshot.avgVolume20 += (double)iVolume(symbol_name, timeframe, volShift);
   snapshot.avgVolume20 /= 20.0;
   snapshot.volumeRatio20 = (snapshot.avgVolume20 > 0.0) ? (snapshot.volume1 / snapshot.avgVolume20) : 0.0;

   snapshot.support = 999999.0;
   snapshot.resistance = 0.0;
   int srLookback = MathMax(1, SR_LookBack);
   for(int srShift = 1; srShift <= srLookback; srShift++)
   {
      double barHigh = iHigh(symbol_name, timeframe, srShift);
      double barLow = iLow(symbol_name, timeframe, srShift);
      if(barHigh > snapshot.resistance)
         snapshot.resistance = barHigh;
      if(barLow < snapshot.support)
         snapshot.support = barLow;
   }
   snapshot.supportDistancePips = PriceToPips(snapshot.close1 - snapshot.support, symbol_name);
   snapshot.resistanceDistancePips = PriceToPips(snapshot.resistance - snapshot.close1, symbol_name);

   snapshot.regime = DetectMarketRegime(symbol_name, timeframe, snapshot.atrPips,
                                        snapshot.adxValue, snapshot.bbWidthPips, snapshot.spreadPips);

   if(snapshot.bbPosPct < 0.0) snapshot.bbPosPct = 0.0;
   if(snapshot.bbPosPct > 100.0) snapshot.bbPosPct = 100.0;
   if(snapshot.atrPips < 0.0) snapshot.atrPips = 0.0;
   if(snapshot.adxValue < 0.0) snapshot.adxValue = 0.0;
   if(snapshot.bbWidthPips < 0.0) snapshot.bbWidthPips = 0.0;
   if(snapshot.spreadPips < 0.0) snapshot.spreadPips = 0.0;

   return true;
}

bool ShouldQueueOpportunityLabel(string signalStatus)
{
   if(!EnableOpportunityLabels)
      return false;

   return (signalStatus == "NO_SETUP" ||
           signalStatus == "QUALITY_FILTER" ||
           signalStatus == "BUY_ORDER_SENT" ||
           signalStatus == "SELL_ORDER_SENT" ||
           signalStatus == "ORDER_SEND_FAILED");
}

bool HasProcessedOpportunityEvent(string eventId)
{
   if(eventId == "")
      return true;

   for(int i = 0; i < gOpportunityProcessedCount; i++)
   {
      if(gOpportunityProcessedIds[i] == eventId)
         return true;
   }
   return false;
}

void RememberProcessedOpportunityEvent(string eventId)
{
   if(eventId == "" || HasProcessedOpportunityEvent(eventId))
      return;

   ArrayResize(gOpportunityProcessedIds, gOpportunityProcessedCount + 1);
   gOpportunityProcessedIds[gOpportunityProcessedCount] = eventId;
   gOpportunityProcessedCount++;
}

void LoadOpportunityLabelState()
{
   gOpportunityProcessedCount = 0;
   ArrayResize(gOpportunityProcessedIds, 0);

   if(!EnableOpportunityLabels)
      return;

   int handle = FileOpen("QuantGod_OpportunityLabels.csv", FILE_CSV | FILE_ANSI | FILE_READ, ',');
   if(handle == INVALID_HANDLE)
      return;

   while(!FileIsEnding(handle))
   {
      string eventId = FileReadString(handle);
      if(FileIsEnding(handle) && eventId == "")
         break;

      for(int col = 1; col < OPPORTUNITY_LABEL_COLUMNS && !FileIsEnding(handle); col++)
         FileReadString(handle);

      if(eventId == "" || eventId == "EventId")
         continue;

      RememberProcessedOpportunityEvent(eventId);
   }

   FileClose(handle);
}

void AppendOpportunityQueue(string eventId, int strategyIndex, string symbol_name, int timeframe,
                            string signalStatus, string signalDirection, double signalScore,
                            double buyScore, double sellScore, string detail,
                            SignalFeatureSnapshot &snapshot)
{
   if(!ShouldQueueOpportunityLabel(signalStatus))
      return;

   int handle = FileOpen("QuantGod_SignalOpportunityQueue.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen("QuantGod_SignalOpportunityQueue.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_SignalOpportunityQueue.csv, error=", GetLastError());
      return;
   }

   if(FileSize(handle) == 0)
   {
      FileWrite(handle,
                "EventId", "TimeLocal", "TimeServer", "EventBarTime", "LabelReadyServer",
                "Symbol", "Strategy", "TimeframeCode", "SignalStatus", "SignalDirection",
                "SignalScore", "BuyScore", "SellScore", "Regime", "AdaptiveState",
                "RiskMultiplier", "ReferencePrice", "SpreadPips", "ATRPips", "HorizonBars", "Detail");
   }
   else
      FileSeek(handle, 0, SEEK_END);

   FileWrite(handle,
             eventId,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(snapshot.eventBarTime, TIME_DATE|TIME_MINUTES),
             (snapshot.labelReadyTime > 0 ? TimeToStr(snapshot.labelReadyTime, TIME_DATE|TIME_MINUTES) : ""),
             symbol_name,
             GetStrategyNameByIndex(strategyIndex),
             timeframe,
             signalStatus,
             (signalDirection == "" ? "NONE" : signalDirection),
             DoubleToStr(signalScore, 1),
             DoubleToStr(buyScore, 1),
             DoubleToStr(sellScore, 1),
             snapshot.regime,
             gAdaptiveState[strategyIndex],
             DoubleToStr(GetStrategyRiskMultiplier(strategyIndex), 2),
             DoubleToStr(snapshot.refPrice, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.spreadPips, 1),
             DoubleToStr(snapshot.atrPips, 1),
             snapshot.horizonBars,
             SanitizeCsvText(detail));

   FileClose(handle);
}

void ProcessOpportunityLabels(bool force)
{
   if(!EnableOpportunityLabels)
      return;

   int intervalSeconds = OpportunityLabelIntervalSeconds;
   if(intervalSeconds < 5)
      intervalSeconds = 5;

   datetime nowServer = TimeCurrent();
   if(!force && gLastOpportunityLabelScan > 0 &&
      nowServer - gLastOpportunityLabelScan < intervalSeconds)
      return;

   gLastOpportunityLabelScan = nowServer;

   int queueHandle = FileOpen("QuantGod_SignalOpportunityQueue.csv", FILE_CSV | FILE_ANSI | FILE_READ, ',');
   if(queueHandle == INVALID_HANDLE)
      return;

   int labelHandle = FileOpen("QuantGod_OpportunityLabels.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(labelHandle == INVALID_HANDLE)
      labelHandle = FileOpen("QuantGod_OpportunityLabels.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(labelHandle == INVALID_HANDLE)
   {
      FileClose(queueHandle);
      Print("[QuantGod] Failed to open QuantGod_OpportunityLabels.csv, error=", GetLastError());
      return;
   }

   if(FileSize(labelHandle) == 0)
   {
      FileWrite(labelHandle,
                "EventId", "LabelTimeLocal", "LabelTimeServer", "EventTimeServer", "EventBarTime",
                "Symbol", "Strategy", "Timeframe", "SignalStatus", "SignalDirection",
                "SignalScore", "Regime", "AdaptiveState", "RiskMultiplier", "HorizonBars",
                "ReferencePrice", "FutureClose", "LongClosePips", "ShortClosePips",
                "LongMFEPips", "LongMAEPips", "ShortMFEPips", "ShortMAEPips",
                "NeutralThresholdPips", "DirectionalOutcome", "BestOpportunity", "LabelReason");
   }
   else
      FileSeek(labelHandle, 0, SEEK_END);

   while(!FileIsEnding(queueHandle))
   {
      string eventId = FileReadString(queueHandle);
      if(FileIsEnding(queueHandle) && eventId == "")
         break;

      string eventTimeLocal = FileReadString(queueHandle);
      string eventTimeServer = FileReadString(queueHandle);
      string eventBarTimeText = FileReadString(queueHandle);
      string labelReadyText = FileReadString(queueHandle);
      string symbol_name = FileReadString(queueHandle);
      string strategyName = FileReadString(queueHandle);
      int timeframe = (int)StrToInteger(FileReadString(queueHandle));
      string signalStatus = FileReadString(queueHandle);
      string signalDirection = FileReadString(queueHandle);
      double signalScore = StrToDouble(FileReadString(queueHandle));
      double buyScore = StrToDouble(FileReadString(queueHandle));
      double sellScore = StrToDouble(FileReadString(queueHandle));
      string regime = FileReadString(queueHandle);
      string adaptiveState = FileReadString(queueHandle);
      double riskMultiplier = StrToDouble(FileReadString(queueHandle));
      double referencePrice = StrToDouble(FileReadString(queueHandle));
      double spreadPips = StrToDouble(FileReadString(queueHandle));
      double atrPips = StrToDouble(FileReadString(queueHandle));
      int horizonBars = (int)StrToInteger(FileReadString(queueHandle));
      string detail = FileReadString(queueHandle);

      if(eventId == "EventId" || eventId == "")
         continue;
      if(HasProcessedOpportunityEvent(eventId))
         continue;

      datetime labelReadyTime = StrToTime(labelReadyText);
      if(labelReadyTime > 0 && nowServer < labelReadyTime)
         continue;

      datetime eventBarTime = StrToTime(eventBarTimeText);
      if(eventBarTime <= 0)
         continue;

      int eventShift = iBarShift(symbol_name, timeframe, eventBarTime, true);
      if(eventShift < 0)
         eventShift = iBarShift(symbol_name, timeframe, eventBarTime, false);
      if(eventShift <= horizonBars)
         continue;

      int futureCloseShift = eventShift - horizonBars;
      double futureClose = iClose(symbol_name, timeframe, futureCloseShift);
      double futureHigh = -1.0e10;
      double futureLow = 1.0e10;

      for(int shift = eventShift - 1; shift >= eventShift - horizonBars; shift--)
      {
         double barHigh = iHigh(symbol_name, timeframe, shift);
         double barLow = iLow(symbol_name, timeframe, shift);
         if(barHigh > futureHigh)
            futureHigh = barHigh;
         if(barLow < futureLow)
            futureLow = barLow;
      }

      if(futureClose <= 0.0 || futureHigh <= -1.0e9 || futureLow >= 1.0e9)
         continue;

      double longClosePips = PriceToPips(futureClose - referencePrice, symbol_name);
      double shortClosePips = PriceToPips(referencePrice - futureClose, symbol_name);
      double longMFEPips = PriceToPips(futureHigh - referencePrice, symbol_name);
      double longMAEPips = PriceToPips(referencePrice - futureLow, symbol_name);
      double shortMFEPips = PriceToPips(referencePrice - futureLow, symbol_name);
      double shortMAEPips = PriceToPips(futureHigh - referencePrice, symbol_name);
      double neutralThresholdPips = MathMax(0.5, MathMax(atrPips * OpportunityNeutralThresholdATR, spreadPips * 2.0));

      string directionalOutcome = "UNSPECIFIED";
      double biasClosePips = 0.0;
      if(signalDirection == "BUY")
      {
         biasClosePips = longClosePips;
         if(biasClosePips > neutralThresholdPips) directionalOutcome = "POSITIVE";
         else if(biasClosePips < -neutralThresholdPips) directionalOutcome = "NEGATIVE";
         else directionalOutcome = "NEUTRAL";
      }
      else if(signalDirection == "SELL")
      {
         biasClosePips = shortClosePips;
         if(biasClosePips > neutralThresholdPips) directionalOutcome = "POSITIVE";
         else if(biasClosePips < -neutralThresholdPips) directionalOutcome = "NEGATIVE";
         else directionalOutcome = "NEUTRAL";
      }

      string bestOpportunity = "NEUTRAL";
      if(longClosePips > neutralThresholdPips)
         bestOpportunity = "BUY";
      else if(shortClosePips > neutralThresholdPips)
         bestOpportunity = "SELL";

      string labelReason = "bias=" + directionalOutcome +
                           " longClose=" + DoubleToStr(longClosePips, 1) +
                           " shortClose=" + DoubleToStr(shortClosePips, 1) +
                           " neutral=" + DoubleToStr(neutralThresholdPips, 1) +
                           " buyScore=" + DoubleToStr(buyScore, 0) +
                           " sellScore=" + DoubleToStr(sellScore, 0) +
                           " detail=" + SanitizeCsvText(detail);

      FileWrite(labelHandle,
                eventId,
                TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                TimeToStr(nowServer, TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                eventTimeServer,
                eventBarTimeText,
                symbol_name,
                strategyName,
                TimeframeLabel(timeframe),
                signalStatus,
                signalDirection,
                DoubleToStr(signalScore, 1),
                regime,
                adaptiveState,
                DoubleToStr(riskMultiplier, 2),
                horizonBars,
                DoubleToStr(referencePrice, DigitsForSymbolName(symbol_name)),
                DoubleToStr(futureClose, DigitsForSymbolName(symbol_name)),
                DoubleToStr(longClosePips, 1),
                DoubleToStr(shortClosePips, 1),
                DoubleToStr(longMFEPips, 1),
                DoubleToStr(longMAEPips, 1),
                DoubleToStr(shortMFEPips, 1),
                DoubleToStr(shortMAEPips, 1),
                DoubleToStr(neutralThresholdPips, 1),
                directionalOutcome,
                bestOpportunity,
                SanitizeCsvText(labelReason));

      RememberProcessedOpportunityEvent(eventId);
   }

   FileClose(queueHandle);
   FileClose(labelHandle);
}

void GetStrategyClosedStats(int strategyIndex, string symbol_name, int &closedTrades, int &winTrades,
                            double &netProfit, double &grossProfit, double &grossLoss, datetime &lastCloseTime)
{
   closedTrades = 0;
   winTrades = 0;
   netProfit = 0.0;
   grossProfit = 0.0;
   grossLoss = 0.0;
   lastCloseTime = 0;

   int magic = GetStrategyMagicByIndex(strategyIndex);
   if(magic == 0)
      return;

   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() != magic) continue;
      if(OrderSymbol() != symbol_name) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double closedNet = UseVirtualResearchAccount ? ScaleResearchNet(actualNet, OrderLots(), OrderComment())
                                                   : actualNet;

      closedTrades++;
      netProfit += closedNet;
      if(closedNet > 0.0)
      {
         winTrades++;
         grossProfit += closedNet;
      }
      else if(closedNet < 0.0)
         grossLoss += MathAbs(closedNet);

      if(OrderCloseTime() > lastCloseTime)
         lastCloseTime = OrderCloseTime();
   }
}

string DetectMarketRegime(string symbol_name, int timeframe, double &atrPips, double &adxValue,
                          double &bbWidthPips, double &spreadPips)
{
   spreadPips = GetSpreadPips(symbol_name);
   atrPips = PriceToPips(iATR(symbol_name, timeframe, 14, 1), symbol_name);
   adxValue = iADX(symbol_name, timeframe, 14, PRICE_CLOSE, MODE_MAIN, 1);

   double bbUpper = iBands(symbol_name, timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbLower = iBands(symbol_name, timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 1);
   bbWidthPips = PriceToPips(MathAbs(bbUpper - bbLower), symbol_name);

   double close1 = iClose(symbol_name, timeframe, 1);
   double ema20 = iMA(symbol_name, timeframe, 20, 0, MODE_EMA, PRICE_CLOSE, 1);
   double ema50 = iMA(symbol_name, timeframe, 50, 0, MODE_EMA, PRICE_CLOSE, 1);

   if(atrPips < 0.0) atrPips = 0.0;
   if(adxValue < 0.0) adxValue = 0.0;
   if(bbWidthPips < 0.0) bbWidthPips = 0.0;
   if(spreadPips < 0.0) spreadPips = 0.0;

   bool trendUp = (close1 > ema20 && ema20 > ema50);
   bool trendDown = (close1 < ema20 && ema20 < ema50);
   double atrBase = MathMax(atrPips, 0.5);
   double squeezeThreshold = MathMax(atrBase * 1.15, spreadPips * 3.0);

   if(adxValue >= 30.0 && bbWidthPips >= atrBase * 2.4)
      return trendUp ? "TREND_EXP_UP" : (trendDown ? "TREND_EXP_DOWN" : "TREND_EXP");

   if(adxValue >= 23.0 && (trendUp || trendDown))
      return trendUp ? "TREND_UP" : "TREND_DOWN";

   if(adxValue < 18.0 && bbWidthPips <= squeezeThreshold)
      return "SQUEEZE";

   if(adxValue < 20.0 && bbWidthPips >= atrBase * 2.0)
      return "RANGE_HIGHVOL";

   if(adxValue < 23.0)
      return "RANGE";

   return "TRANSITION";
}

bool ShouldLogSignalEvent(int strategyIndex, string symbol_name, int timeframe, string eventKey,
                          bool transitionOnly=false)
{
   if(!EnableSignalLog)
      return false;

   int symbolIndex = GetManagedSymbolIndex(symbol_name);
   if(symbolIndex < 0 || strategyIndex < 0 || strategyIndex >= STRATEGY_DIAG_COUNT)
      return false;

   datetime barTime = iTime(symbol_name, timeframe, 0);
   datetime now = TimeCurrent();
   if(barTime <= 0)
      barTime = now;

   if(transitionOnly)
   {
      if(gSignalLogLastKey[symbolIndex][strategyIndex] == eventKey)
         return false;
   }
   else
   {
      if(gSignalLogLastKey[symbolIndex][strategyIndex] == eventKey &&
         gSignalLogLastBarTime[symbolIndex][strategyIndex] == barTime &&
         now - gSignalLogLastWriteTime[symbolIndex][strategyIndex] < 10)
         return false;
   }

   gSignalLogLastKey[symbolIndex][strategyIndex] = eventKey;
   gSignalLogLastBarTime[symbolIndex][strategyIndex] = barTime;
   gSignalLogLastWriteTime[symbolIndex][strategyIndex] = now;
   return true;
}

void AppendSignalLog(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                     string signalReason, string signalDirection, double signalScore,
                     double buyScore, double sellScore, string detail)
{
   AppendSignalLogWithEvent(strategyIndex, symbol_name, timeframe, signalStatus, signalReason,
                            signalDirection, signalScore, buyScore, sellScore, detail, "");
}

void AppendSignalLogWithEvent(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                              string signalReason, string signalDirection, double signalScore,
                              double buyScore, double sellScore, string detail, string eventId)
{
   if(!EnableSignalLog)
      return;

   SignalFeatureSnapshot snapshot;
   BuildSignalFeatureSnapshot(symbol_name, timeframe, snapshot);
   string resolvedEventId = eventId;
   if(resolvedEventId == "")
      resolvedEventId = BuildSignalEventId();

   int handle = FileOpen("QuantGod_SignalLog.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen("QuantGod_SignalLog.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_SignalLog.csv, error=", GetLastError());
      return;
   }

   if(FileSize(handle) == 0)
   {
      FileWrite(handle,
                "EventId", "TimeLocal", "TimeServer", "EventBarTime", "OpportunityReadyServer",
                "OpportunityHorizonBars", "Symbol", "Strategy", "Timeframe", "Regime",
                "AdaptiveState", "RiskMultiplier", "TradingStatus", "SignalStatus", "SignalReason",
                "SignalScore", "SignalDirection", "BuyScore", "SellScore", "SpreadPips",
                "ATRPips", "ADX", "BBWidthPips", "Open1", "High1", "Low1", "Close1", "Close2",
                "BarRangePips", "BarBodyPips", "CloseDeltaPips", "RSI2", "RSI14",
                "EMAFast", "EMASlow", "TrendMA", "MAGapPips", "TrendDistancePips",
                "BBUpper", "BBMiddle", "BBLower", "BBPosPct", "MACDMain", "MACDSignal", "MACDHist",
                "Volume1", "AvgVolume20", "VolumeRatio20", "Support", "Resistance",
                "SupportDistancePips", "ResistanceDistancePips", "OpenPositions", "StrategyPositions",
                "DisplayBalance", "DisplayEquity", "DisplayDrawdown", "Detail");
   }
   else
      FileSeek(handle, 0, SEEK_END);

   int magic = GetStrategyMagicByIndex(strategyIndex);
   int symbolOpenPositions = CountManagedPositionsForSymbol(symbol_name);
   int strategyPositions = (magic > 0) ? CountStrategyPositionsForSymbol(magic, symbol_name) : 0;

   FileWrite(handle,
             resolvedEventId,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(snapshot.eventBarTime, TIME_DATE|TIME_MINUTES),
             (snapshot.labelReadyTime > 0 ? TimeToStr(snapshot.labelReadyTime, TIME_DATE|TIME_MINUTES) : ""),
             snapshot.horizonBars,
             symbol_name,
             GetStrategyNameByIndex(strategyIndex),
             TimeframeLabel(timeframe),
             snapshot.regime,
             gAdaptiveState[strategyIndex],
             DoubleToStr(GetStrategyRiskMultiplier(strategyIndex), 2),
             GetTradingStatusForSymbol(symbol_name),
             signalStatus,
             SanitizeCsvText(signalReason),
             DoubleToStr(signalScore, 1),
             (signalDirection == "" ? "NONE" : signalDirection),
             DoubleToStr(buyScore, 1),
             DoubleToStr(sellScore, 1),
             DoubleToStr(snapshot.spreadPips, 1),
             DoubleToStr(snapshot.atrPips, 1),
             DoubleToStr(snapshot.adxValue, 1),
             DoubleToStr(snapshot.bbWidthPips, 1),
             DoubleToStr(snapshot.open1, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.high1, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.low1, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.close1, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.close2, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.barRangePips, 1),
             DoubleToStr(snapshot.barBodyPips, 1),
             DoubleToStr(snapshot.closeDeltaPips, 1),
             DoubleToStr(snapshot.rsi2, 1),
             DoubleToStr(snapshot.rsi14, 1),
             DoubleToStr(snapshot.emaFast, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.emaSlow, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.trendMA, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.maGapPips, 1),
             DoubleToStr(snapshot.trendDistancePips, 1),
             DoubleToStr(snapshot.bbUpper, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.bbMiddle, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.bbLower, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.bbPosPct, 1),
             DoubleToStr(snapshot.macdMain, 5),
             DoubleToStr(snapshot.macdSignal, 5),
             DoubleToStr(snapshot.macdHist, 5),
             DoubleToStr(snapshot.volume1, 0),
             DoubleToStr(snapshot.avgVolume20, 1),
             DoubleToStr(snapshot.volumeRatio20, 2),
             DoubleToStr(snapshot.support, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.resistance, DigitsForSymbolName(symbol_name)),
             DoubleToStr(snapshot.supportDistancePips, 1),
             DoubleToStr(snapshot.resistanceDistancePips, 1),
             symbolOpenPositions,
             strategyPositions,
             DoubleToStr(GetDisplayedBalance(), 2),
             DoubleToStr(GetDisplayedEquity(), 2),
             DoubleToStr(GetDisplayedDrawdownPercent(), 2),
             SanitizeCsvText(detail));

   FileClose(handle);
   AppendOpportunityQueue(resolvedEventId, strategyIndex, symbol_name, timeframe, signalStatus,
                          signalDirection, signalScore, buyScore, sellScore, detail, snapshot);
}

void LogStrategySignal(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                       string signalReason, string signalDirection, double signalScore,
                       double buyScore, double sellScore, string detail)
{
   LogStrategySignalWithEvent(strategyIndex, symbol_name, timeframe, signalStatus, signalReason,
                              signalDirection, signalScore, buyScore, sellScore, detail, "");
}

void LogStrategySignalWithEvent(int strategyIndex, string symbol_name, int timeframe, string signalStatus,
                                string signalReason, string signalDirection, double signalScore,
                                double buyScore, double sellScore, string detail, string eventId)
{
   bool transitionOnly = (signalStatus == "AUTO_PAUSED");
   string eventKey = signalStatus + "|" + signalDirection;
   if(signalStatus == "AUTO_PAUSED")
   {
      eventKey += "|" + gAdaptiveState[strategyIndex] +
                  "|" + DoubleToStr(GetStrategyRiskMultiplier(strategyIndex), 2) +
                  "|" + GetStrategyAdaptiveReason(strategyIndex);
   }
   else if(signalStatus == "NO_SETUP" || signalStatus == "QUALITY_FILTER")
      eventKey += "|" + DoubleToStr(MathMax(buyScore, sellScore), 0);

   if(!ShouldLogSignalEvent(strategyIndex, symbol_name, timeframe, eventKey, transitionOnly))
      return;

   AppendSignalLogWithEvent(strategyIndex, symbol_name, timeframe, signalStatus, signalReason,
                            signalDirection, signalScore, buyScore, sellScore, detail, eventId);
}

bool CanSyncToCloud()
{
   if(!EnableCloudSync)
      return false;
   if(StringLen(CloudSyncEndpoint) < 12)
      return false;
   if(IsTesting())
      return false;
   return true;
}

bool ReadBinaryFile(string filename, char &data[])
{
   ArrayResize(data, 0);
   ResetLastError();
   int handle = FileOpen(filename, FILE_READ | FILE_BIN);
   if(handle == INVALID_HANDLE)
      return false;

   int fileSize = (int)FileSize(handle);
   if(fileSize <= 0)
   {
      FileClose(handle);
      return false;
   }

   ArrayResize(data, fileSize);
   uint bytesRead = FileReadArray(handle, data, 0, fileSize);
   FileClose(handle);
   return bytesRead == (uint)fileSize;
}

void RecordCloudSyncResult(string status, int httpCode, string message, bool success)
{
   gLastCloudSyncStatus = status;
   gLastCloudSyncHttpCode = httpCode;
   gLastCloudSyncMessage = message;
   if(StringLen(gLastCloudSyncMessage) > 180)
      gLastCloudSyncMessage = StringSubstr(gLastCloudSyncMessage, 0, 180);
   if(success)
      gLastCloudSyncSuccess = TimeLocal();
}

bool SyncDashboardToCloud(string filename)
{
   gLastCloudSyncAttempt = TimeLocal();

   if(!EnableCloudSync)
   {
      RecordCloudSyncResult("DISABLED", 0, "Cloud sync is disabled", false);
      return false;
   }

   if(StringLen(CloudSyncEndpoint) < 12)
   {
      RecordCloudSyncResult("MISSING_ENDPOINT", 0, "CloudSyncEndpoint is empty", false);
      return false;
   }

   char payload[];
   if(!ReadBinaryFile(filename, payload))
   {
      int readErr = GetLastError();
      RecordCloudSyncResult("FILE_READ_ERROR", 0, "Failed to read dashboard payload, err=" + IntegerToString(readErr), false);
      Print("[QG-CLOUD] Failed to read dashboard payload | err=", readErr);
      return false;
   }

   char response[];
   string responseHeaders = "";
   string headers = "Content-Type: application/json\r\nX-QuantGod-Source: mt4\r\n";
   if(StringLen(CloudSyncToken) > 0)
      headers += "Authorization: Bearer " + CloudSyncToken + "\r\n";

   ResetLastError();
   int httpCode = WebRequest("POST", CloudSyncEndpoint, headers, CloudSyncTimeoutMs, payload, response, responseHeaders);
   if(httpCode == -1)
   {
      int webErr = GetLastError();
      string errMsg = "WebRequest failed, add endpoint to MT4 allowed URLs, err=" + IntegerToString(webErr);
      RecordCloudSyncResult("REQUEST_ERROR", 0, errMsg, false);
      Print("[QG-CLOUD] WebRequest failed | err=", webErr, " | endpoint=", CloudSyncEndpoint);
      return false;
   }

   string responseText = CharArrayToString(response, 0, ArraySize(response));
   StringReplace(responseText, "\r", " ");
   StringReplace(responseText, "\n", " ");
   if(StringLen(responseText) == 0)
      responseText = "HTTP " + IntegerToString(httpCode);

   if(httpCode >= 200 && httpCode < 300)
   {
      RecordCloudSyncResult("SYNCED", httpCode, responseText, true);
      return true;
   }

   RecordCloudSyncResult("HTTP_ERROR", httpCode, responseText, false);
   Print("[QG-CLOUD] HTTP error | code=", httpCode, " | body=", responseText);
   return false;
}

int StrategyTimeframe(int index)
{
   switch(index)
   {
      case 0: return MA_Timeframe;
      case 1: return RSI_Timeframe;
      case 2: return BB_Timeframe;
      case 3: return MACD_Timeframe;
      case 4: return SR_Timeframe;
   }
   return PERIOD_CURRENT;
}

bool IsStableDiagnosticStatus(string status)
{
   return status != "WAIT_SIGNAL" && status != "WAIT_BAR";
}

double GetLastEvalScore(int index)
{
   if(gCurrentDiagSymbolIndex < 0 || gCurrentDiagSymbolIndex >= MAX_MANAGED_SYMBOLS)
      return 10;

   double score = gStrategyLastEvalScore[gCurrentDiagSymbolIndex][index];
   return (score > 0 ? score : 10);
}

string BuildWaitBarReason(int index)
{
   string tf = TimeframeLabel(StrategyTimeframe(index));
   string baseReason = "Waiting for a new " + tf + " bar";

   if(gCurrentDiagSymbolIndex < 0 || gCurrentDiagSymbolIndex >= MAX_MANAGED_SYMBOLS)
      return baseReason;

   string lastStatus = gStrategyLastEvalStatus[gCurrentDiagSymbolIndex][index];
   string lastReason = gStrategyLastEvalReason[gCurrentDiagSymbolIndex][index];
   datetime lastTime = gStrategyLastEvalTime[gCurrentDiagSymbolIndex][index];

   if(lastStatus == "" || lastTime <= 0)
      return baseReason;

   return "Last " + tf + " check @ " + TimeToStr(lastTime, TIME_DATE|TIME_MINUTES) +
          ": " + lastStatus + " | " + lastReason;
}

void SetStrategyDiagnostic(int index, string status, string reason, double score)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return;

   if(score < 0) score = 0;
   if(score > 100) score = 100;

   if(gCurrentDiagSymbolIndex >= 0 && gCurrentDiagSymbolIndex < MAX_MANAGED_SYMBOLS)
   {
      gManagedDiagStatus[gCurrentDiagSymbolIndex][index] = status;
      gManagedDiagReason[gCurrentDiagSymbolIndex][index] = reason;
      gManagedDiagScore[gCurrentDiagSymbolIndex][index] = score;

      if(IsStableDiagnosticStatus(status))
      {
         gStrategyLastEvalStatus[gCurrentDiagSymbolIndex][index] = status;
         gStrategyLastEvalReason[gCurrentDiagSymbolIndex][index] = reason;
         gStrategyLastEvalScore[gCurrentDiagSymbolIndex][index] = score;
         gStrategyLastEvalTime[gCurrentDiagSymbolIndex][index] = TimeCurrent();
      }
   }

   if(gSymbol == gDashboardSymbol)
   {
      gStrategyDiagStatus[index] = status;
      gStrategyDiagReason[index] = reason;
      gStrategyDiagScore[index] = score;
   }
}

void RefreshAllManagedDiagnostics()
{
   for(int i = 0; i < gManagedSymbolCount; i++)
   {
      if(!PrepareSymbolContext(gManagedSymbols[i]))
         continue;

      RefreshStrategyDiagnostics();
   }

   PrepareSymbolContext(gDashboardSymbol);
}

string TradingStatusReason(string status)
{
   if(status == "DISCONNECTED") return "Terminal is disconnected from broker";
   if(status == "ACCOUNT_TRADE_DISABLED") return "Broker account trading is disabled";
   if(status == "SERVER_EXPERTS_DISABLED") return "Broker server disabled expert trading";
   if(status == "TERMINAL_AUTOTRADING_OFF") return "MT4 terminal AutoTrading is off";
   if(status == "EA_LIVE_TRADING_OFF") return "EA live trading permission is off";
   if(status == "FLATTENING") return "Closing all managed demo positions";
   if(status == "PAUSED") return "New entries are paused for research mode";
   if(status == "OUT_OF_SESSION") return "Session filter is blocking entries";
   if(status == "WAITING_MARKET") return "Waiting for fresh market ticks";
   if(status == "READY") return "Ready for signal evaluation";
   return "Runtime status: " + status;
}

void RefreshStrategyDiagnostics()
{
   SetStrategyDiagnostic(0, Enable_MA ? "WAIT_SIGNAL" : "DISABLED",
                         Enable_MA ? "Waiting for MA_Cross evaluation" : "MA_Cross is disabled", 0);
   SetStrategyDiagnostic(1, Enable_RSI ? "WAIT_SIGNAL" : "DISABLED",
                         Enable_RSI ? "Waiting for RSI_Reversal evaluation" : "RSI_Reversal is disabled", 0);
   SetStrategyDiagnostic(2, Enable_BB ? "WAIT_SIGNAL" : "DISABLED",
                         Enable_BB ? "Waiting for BB_Triple evaluation" : "BB_Triple is disabled", 0);
   SetStrategyDiagnostic(3, Enable_MACD ? "WAIT_SIGNAL" : "DISABLED",
                         Enable_MACD ? "Waiting for MACD_Divergence evaluation" : "MACD_Divergence is disabled", 0);
   SetStrategyDiagnostic(4, Enable_SR ? "WAIT_SIGNAL" : "DISABLED",
                         Enable_SR ? "Waiting for SR_Breakout evaluation" : "SR_Breakout is disabled", 0);

   if(!CheckMaxDrawdown(MaxDrawdownPercent))
   {
      if(Enable_MA)   SetStrategyDiagnostic(0, "DRAWDOWN_GUARD", "Max drawdown guard paused entries", 100);
      if(Enable_RSI)  SetStrategyDiagnostic(1, "DRAWDOWN_GUARD", "Max drawdown guard paused entries", 100);
      if(Enable_BB)   SetStrategyDiagnostic(2, "DRAWDOWN_GUARD", "Max drawdown guard paused entries", 100);
      if(Enable_MACD) SetStrategyDiagnostic(3, "DRAWDOWN_GUARD", "Max drawdown guard paused entries", 100);
      if(Enable_SR)   SetStrategyDiagnostic(4, "DRAWDOWN_GUARD", "Max drawdown guard paused entries", 100);
      return;
   }

   string runtimeStatus = GetTradingStatus();
   if(runtimeStatus != "READY")
   {
      string reason = TradingStatusReason(runtimeStatus);
      if(Enable_MA)   SetStrategyDiagnostic(0, runtimeStatus, reason, 0);
      if(Enable_RSI)  SetStrategyDiagnostic(1, runtimeStatus, reason, 0);
      if(Enable_BB)   SetStrategyDiagnostic(2, runtimeStatus, reason, 0);
      if(Enable_MACD) SetStrategyDiagnostic(3, runtimeStatus, reason, 0);
      if(Enable_SR)   SetStrategyDiagnostic(4, runtimeStatus, reason, 0);
      return;
   }

   for(int adaptiveIndex = 0; adaptiveIndex < STRATEGY_DIAG_COUNT; adaptiveIndex++)
   {
      if(IsStrategyConfiguredEnabled(adaptiveIndex) && !IsStrategyRuntimeActive(adaptiveIndex))
         SetStrategyDiagnostic(adaptiveIndex, "AUTO_PAUSED", GetStrategyAdaptiveReason(adaptiveIndex), 100);
   }

   if(CountAllPositions() >= MaxTotalTrades)
   {
      string capReason = "Max concurrent trades reached";
      if(Enable_MA && IsStrategyRuntimeActive(0))   SetStrategyDiagnostic(0, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_RSI && IsStrategyRuntimeActive(1))  SetStrategyDiagnostic(1, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_BB && IsStrategyRuntimeActive(2))   SetStrategyDiagnostic(2, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_MACD && IsStrategyRuntimeActive(3)) SetStrategyDiagnostic(3, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_SR && IsStrategyRuntimeActive(4))   SetStrategyDiagnostic(4, "PORTFOLIO_LIMIT", capReason, 100);
   }
}

//+------------------------------------------------------------------+
//| 遲也払1: MA驥大初豁ｻ蜿・                                                 |
//+------------------------------------------------------------------+
void Strategy_MA_Cross()
{
   if(HasOpenPosition(MA_Magic, gSymbol))
   {
      string reason = "Existing MA_Cross position is still open";
      SetStrategyDiagnostic(0, "IN_POSITION", reason, 100);
      LogStrategySignal(0, gSymbol, MA_Timeframe, "IN_POSITION", reason, "NONE", 100, 0, 0, "");
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      string reason = "Max concurrent trades reached";
      SetStrategyDiagnostic(0, "PORTFOLIO_LIMIT", reason, 100);
      LogStrategySignal(0, gSymbol, MA_Timeframe, "PORTFOLIO_LIMIT", reason, "NONE", 100, 0, 0, "");
      return;
   }

   // 莉・惠譁ｰK郤ｿ蠑蟋区慮譽譟･
   if(!IsNewStrategyBar(0, gSymbol, MA_Timeframe))
   {
      SetStrategyDiagnostic(0, "WAIT_BAR", BuildWaitBarReason(0), GetLastEvalScore(0));
      return;
   }

   double fastMA_1 = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slowMA_1 = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double trendMA  = iMA(gSymbol, MA_TrendTimeframe, MA_TrendPeriod, 0, MODE_SMA, PRICE_CLOSE, 1);

   double atrSL = GetATRStopLoss(gSymbol, MA_Timeframe, 14, 2.0);
   double close1 = iClose(gSymbol, MA_Timeframe, 1);
   double trendClose = iClose(gSymbol, MA_TrendTimeframe, 1);

   // Research mode: keep entries recent enough to avoid chasing old crosses.
   bool buyCross = false;
   bool sellCross = false;
   for(int c = 1; c <= MA_CrossLookbackBars; c++)
   {
      double fPrev = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, c+1);
      double sPrev = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, c+1);
      double fCurr = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, c);
      double sCurr = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, c);
      if(fPrev <= sPrev && fCurr > sCurr) buyCross = true;
      if(fPrev >= sPrev && fCurr < sCurr) sellCross = true;
   }

   bool buyTrend = (trendClose > trendMA);
   bool sellTrend = (trendClose < trendMA);
   double spreadPips = GetSpreadPips(gSymbol);
   double pipFactor = ((gDigits == 3 || gDigits == 5) ? 10.0 : 1.0);
   double entryDistancePips = MathAbs(close1 - fastMA_1) / gPoint / pipFactor;
   double maxEntryDistancePips = MathMax(2.0, atrSL * MA_MaxEntryDistanceATR);
   bool spreadOk = (spreadPips <= MA_MaxSpreadPips);
   bool entryDistanceOk = (entryDistancePips <= maxEntryDistancePips);
   bool qualityOk = (spreadOk && entryDistanceOk);

   Print("[MA_Cross] ", gSymbol, " | fast=", DoubleToStr(fastMA_1,5), " slow=", DoubleToStr(slowMA_1,5),
         " trend=", DoubleToStr(trendMA,5), " close=", DoubleToStr(close1,5),
         " trendClose=", DoubleToStr(trendClose,5),
         " spread=", DoubleToStr(spreadPips,1),
         " dist=", DoubleToStr(entryDistancePips,1), "/", DoubleToStr(maxEntryDistancePips,1),
         " | cross=", (buyCross?"BUY":(sellCross?"SELL":"NONE")),
         " trend=", (buyTrend?"UP":(sellTrend?"DN":"FLAT")));

   double buyScore = (double)((buyCross ? 1 : 0) + (buyTrend ? 1 : 0)) / 2.0 * 100.0;
   double sellScore = (double)((sellCross ? 1 : 0) + (sellTrend ? 1 : 0)) / 2.0 * 100.0;
   int buyTicket = -1;
   int sellTicket = -1;
   int ticket = -1;
   double ask = MarketInfo(gSymbol, MODE_ASK);
   double bid = MarketInfo(gSymbol, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   if((buyCross && buyTrend) || (sellCross && sellTrend))
   {
      if(!qualityOk)
      {
         string filterReason = "spread=" + DoubleToStr(spreadPips, 1) + "/" + DoubleToStr(MA_MaxSpreadPips, 1) +
                              " dist=" + DoubleToStr(entryDistancePips, 1) + "/" + DoubleToStr(maxEntryDistancePips, 1);
         SetStrategyDiagnostic(0, "QUALITY_FILTER", filterReason, MathMax(buyScore, sellScore));
         LogStrategySignal(0, gSymbol, MA_Timeframe, "QUALITY_FILTER", filterReason,
                           (buyScore >= sellScore ? "BUY" : "SELL"),
                           MathMax(buyScore, sellScore), buyScore, sellScore,
                           "cross=" + BoolLabel(buyCross || sellCross) + " trend=" + BoolLabel(buyTrend || sellTrend) +
                           " spread=" + BoolLabel(spreadOk) + " dist=" + BoolLabel(entryDistanceOk));
         return;
      }
   }

   // Buy: recent cross + H1 trend confirmed + quality filter passed
   if(buyCross && buyTrend && qualityOk)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);
      string detail = "cross=Y trend=Y spread=" + BoolLabel(spreadOk) + " dist=" + BoolLabel(entryDistanceOk);
      string buyReason = "MA_Cross buy order sent on " + TimeframeLabel(MA_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_MA_Cross_BUY", virtualLots, eventId);

      ResetLastError();
      buyTicket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            orderComment, MA_Magic, 0, clrLime);
      ticket = buyTicket;
      if(ticket > 0) Print("[MA莠､蜿云 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 0, gSymbol, MA_Timeframe, "BUY_ORDER_SENT", "BUY", 100,
                              ask, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(0, "BUY_ORDER_SENT", buyReason, 100);
         LogStrategySignalWithEvent(0, gSymbol, MA_Timeframe, "BUY_ORDER_SENT", buyReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "MA buy setup failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(0, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(0, gSymbol, MA_Timeframe, "ORDER_SEND_FAILED", failReason, "BUY", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   // Sell: recent cross + H1 trend confirmed + quality filter passed
   if(sellCross && sellTrend && qualityOk)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);
      string detail = "cross=Y trend=Y spread=" + BoolLabel(spreadOk) + " dist=" + BoolLabel(entryDistanceOk);
      string sellReason = "MA_Cross sell order sent on " + TimeframeLabel(MA_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_MA_Cross_SELL", virtualLots, eventId);

      ResetLastError();
      sellTicket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            orderComment, MA_Magic, 0, clrRed);
      ticket = sellTicket;
      if(ticket > 0) Print("[MA莠､蜿云 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 0, gSymbol, MA_Timeframe, "SELL_ORDER_SENT", "SELL", 100,
                              bid, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(0, "SELL_ORDER_SENT", sellReason, 100);
         LogStrategySignalWithEvent(0, gSymbol, MA_Timeframe, "SELL_ORDER_SENT", sellReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      else
      {
         string failReason = "MA sell setup failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(0, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(0, gSymbol, MA_Timeframe, "ORDER_SEND_FAILED", failReason, "SELL", 100,
                                    buyScore, sellScore, detail, eventId);
      }
      return;
   }

   if(buyScore >= sellScore)
   {
      string noSetupReason = "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | cross=" + BoolLabel(buyCross) +
                             " trend=" + BoolLabel(buyTrend) + " spread=" + BoolLabel(spreadOk) +
                             " dist=" + BoolLabel(entryDistanceOk);
      string noSetupDetail = "cross=" + BoolLabel(buyCross) + " trend=" + BoolLabel(buyTrend) +
                             " spread=" + BoolLabel(spreadOk) + " dist=" + BoolLabel(entryDistanceOk);
      SetStrategyDiagnostic(0, "NO_SETUP", noSetupReason, buyScore);
      LogStrategySignal(0, gSymbol, MA_Timeframe, "NO_SETUP", noSetupReason, "BUY", buyScore, buyScore, sellScore, noSetupDetail);
   }
   else
   {
      string noSetupReason = "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | cross=" + BoolLabel(sellCross) +
                             " trend=" + BoolLabel(sellTrend) + " spread=" + BoolLabel(spreadOk) +
                             " dist=" + BoolLabel(entryDistanceOk);
      string noSetupDetail = "cross=" + BoolLabel(sellCross) + " trend=" + BoolLabel(sellTrend) +
                             " spread=" + BoolLabel(spreadOk) + " dist=" + BoolLabel(entryDistanceOk);
      SetStrategyDiagnostic(0, "NO_SETUP", noSetupReason, sellScore);
      LogStrategySignal(0, gSymbol, MA_Timeframe, "NO_SETUP", noSetupReason, "SELL", sellScore, buyScore, sellScore, noSetupDetail);
   }
}

//+------------------------------------------------------------------+
//| 遲也払2: RSI(2) 蝮・ｼ蝗槫ｽ・                                            |
//+------------------------------------------------------------------+
void Strategy_RSI_Reversal()
{
   if(HasOpenPosition(RSI_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_rsi = 0;
   datetime curBar = iTime(gSymbol, RSI_Timeframe, 0);
   if(curBar == lastBar_rsi) return;
   lastBar_rsi = curBar;

   double rsi_1 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 1);
   double rsi_2 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 2);

   // 蟶・棊蟶ｦ遑ｮ隶､
   double bbLower = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbUpper = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbMiddle = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN, 1);
   double close1 = iClose(gSymbol, RSI_Timeframe, 1);

   double atrSL = GetATRStopLoss(gSymbol, RSI_Timeframe, 14, 1.5);

   // 雜・獄蜿榊ｼｹ荵ｰ蜈･: RSI莉手ｶ・獄蝗槫合 + 莉ｷ譬ｼ蝨ｨ荳玖ｽｨ髯・ｿ・   if(rsi_2 < RSI_OS && rsi_1 > RSI_OS && close1 <= bbLower * 1.001)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 1.5, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_RSI_Rev_BUY", virtualLots), RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 荵ｰ蜈･ ", lots, " 謇・@ ", Ask);
   }

   // 雜・ｹｰ蝗櫁誠蜊門・: RSI莉手ｶ・ｹｰ蝗櫁誠 + 莉ｷ譬ｼ蝨ｨ荳願ｽｨ髯・ｿ・   if(rsi_2 > RSI_OB && rsi_1 < RSI_OB && close1 >= bbUpper * 0.999)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 1.5, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_RSI_Rev_SELL", virtualLots), RSI_Magic, 0, clrOrange);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 蜊門・ ", lots, " 謇・@ ", Bid);
   }
}

//+------------------------------------------------------------------+
//| 遲也払3: 蟶・棊蟶ｦ+RSI+MACD 荳蛾㍾遑ｮ隶､ (78%閭懃紫遲也払)                       |
//+------------------------------------------------------------------+
void Strategy_BB_Triple()
{
   if(HasOpenPosition(BB_Magic, gSymbol))
   {
      string reason = "Existing BB_Triple position is still open";
      SetStrategyDiagnostic(2, "IN_POSITION", reason, 100);
      LogStrategySignal(2, gSymbol, BB_Timeframe, "IN_POSITION", reason, "NONE", 100, 0, 0, "");
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      string reason = "Max concurrent trades reached";
      SetStrategyDiagnostic(2, "PORTFOLIO_LIMIT", reason, 100);
      LogStrategySignal(2, gSymbol, BB_Timeframe, "PORTFOLIO_LIMIT", reason, "NONE", 100, 0, 0, "");
      return;
   }

   if(!IsNewStrategyBar(2, gSymbol, BB_Timeframe))
   {
      SetStrategyDiagnostic(2, "WAIT_BAR", BuildWaitBarReason(2), GetLastEvalScore(2));
      return;
   }

   double close1 = iClose(gSymbol, BB_Timeframe, 1);

   // 蟶・棊蟶ｦ
   double bbUpper = iBands(gSymbol, BB_Timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbLower = iBands(gSymbol, BB_Timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbMiddle = iBands(gSymbol, BB_Timeframe, BB_Period, BB_Deviation, 0, PRICE_CLOSE, MODE_MAIN, 1);

   // RSI
   double rsi = iRSI(gSymbol, BB_Timeframe, BB_RSI_Period, PRICE_CLOSE, 1);
   double rsi_prev = iRSI(gSymbol, BB_Timeframe, BB_RSI_Period, PRICE_CLOSE, 2);

   // MACD
   double macdMain_1 = iMACD(gSymbol, BB_Timeframe, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 1);
   double macdMain_2 = iMACD(gSymbol, BB_Timeframe, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 2);
   double macdSig_1 = iMACD(gSymbol, BB_Timeframe, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 1);
   double macdSig_2 = iMACD(gSymbol, BB_Timeframe, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 2);

   double atrSL = GetATRStopLoss(gSymbol, BB_Timeframe, 14, 2.0);
   double ask = MarketInfo(gSymbol, MODE_ASK);
   double bid = MarketInfo(gSymbol, MODE_BID);
   if(ask <= 0 || bid <= 0)
      return;

   // 荳蛾㍾遑ｮ隶､荵ｰ蜈･:
   // 1) 莉ｷ譬ｼ隗ｦ蜿・霍檎ｴ荳玖ｽｨ
   // 2) RSI < 30 荳泌屓蜊・   // 3) MACD驥大初
   bool bbBuySignal = (close1 <= bbLower * 1.005);
   bool rsiBuySignal = (rsi < BB_RSI_OS || (rsi_prev < BB_RSI_OS && rsi > BB_RSI_OS));
   bool macdBuyConfirm = (macdMain_1 > macdSig_1 || (macdMain_2 < macdSig_2 && macdMain_1 > macdSig_1));

   if(bbBuySignal && rsiBuySignal)
   {
      double sl = atrSL;
      double tp_dist = MathAbs(bbUpper - close1) / gPoint / ((gDigits == 3 || gDigits == 5) ? 10.0 : 1.0);
      double tp = AdjustTakeProfitPipsForResearch(MathMax(tp_dist, sl * 1.5), sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);
      string detail = "band=Y rsi=Y macd=" + BoolLabel(macdBuyConfirm);
      string buyReason = "BB_Triple buy order sent on " + TimeframeLabel(BB_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_BB_Triple_BUY", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                           orderComment, BB_Magic, 0, clrGold);
      if(ticket > 0) Print("[BB荳蛾㍾] 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol, " TP->荳願ｽｨ");
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 2, gSymbol, BB_Timeframe, "BUY_ORDER_SENT", "BUY", 100,
                              ask, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(2, "BUY_ORDER_SENT", buyReason, 100);
         LogStrategySignalWithEvent(2, gSymbol, BB_Timeframe, "BUY_ORDER_SENT", buyReason, "BUY", 100,
                                    100, 0, detail, eventId);
      }
      else
      {
         string failReason = "BB triple buy failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(2, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(2, gSymbol, BB_Timeframe, "ORDER_SEND_FAILED", failReason, "BUY", 100,
                                    100, 0, detail, eventId);
      }
      return;
   }

    // 荳蛾㍾遑ｮ隶､蜊門・
   bool bbSellSignal = (close1 >= bbUpper * 0.995);
   bool rsiSellSignal = (rsi > BB_RSI_OB || (rsi_prev > BB_RSI_OB && rsi < BB_RSI_OB));
   bool macdSellConfirm = (macdMain_1 < macdSig_1 || (macdMain_2 > macdSig_2 && macdMain_1 < macdSig_1));

   if(bbSellSignal && rsiSellSignal)
   {
      double sl = atrSL;
      double tp_dist = MathAbs(close1 - bbLower) / gPoint / ((gDigits == 3 || gDigits == 5) ? 10.0 : 1.0);
      double tp = AdjustTakeProfitPipsForResearch(MathMax(tp_dist, sl * 1.5), sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);
      string detail = "band=Y rsi=Y macd=" + BoolLabel(macdSellConfirm);
      string sellReason = "BB_Triple sell order sent on " + TimeframeLabel(BB_Timeframe);
      string eventId = BuildSignalEventId();
      string orderComment = BuildManagedOrderCommentWithEvent("QG_BB_Triple_SELL", virtualLots, eventId);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                           orderComment, BB_Magic, 0, clrMagenta);
      if(ticket > 0) Print("[BB荳蛾㍾] 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol, " TP->荳玖ｽｨ");
      if(ticket > 0)
      {
         AppendTradeEventLink(eventId, ticket, 2, gSymbol, BB_Timeframe, "SELL_ORDER_SENT", "SELL", 100,
                              bid, slPrice, tpPrice, lots, virtualLots, orderComment);
         SetStrategyDiagnostic(2, "SELL_ORDER_SENT", sellReason, 100);
         LogStrategySignalWithEvent(2, gSymbol, BB_Timeframe, "SELL_ORDER_SENT", sellReason, "SELL", 100,
                                    0, 100, detail, eventId);
      }
      else
      {
         string failReason = "BB triple sell failed, error=" + IntegerToString(gLastOrderSendError);
         SetStrategyDiagnostic(2, "ORDER_SEND_FAILED", failReason, 100);
         LogStrategySignalWithEvent(2, gSymbol, BB_Timeframe, "ORDER_SEND_FAILED", failReason, "SELL", 100,
                                    0, 100, detail, eventId);
      }
      return;
   }

   double buyScore = (double)((bbBuySignal ? 1 : 0) + (rsiBuySignal ? 1 : 0) + (macdBuyConfirm ? 1 : 0)) / 3.0 * 100.0;
   double sellScore = (double)((bbSellSignal ? 1 : 0) + (rsiSellSignal ? 1 : 0) + (macdSellConfirm ? 1 : 0)) / 3.0 * 100.0;
   if(buyScore >= sellScore)
   {
      string noSetupReason = "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | band=" + BoolLabel(bbBuySignal) +
                             " rsi=" + BoolLabel(rsiBuySignal) + " macd=" + BoolLabel(macdBuyConfirm);
      string noSetupDetail = "band=" + BoolLabel(bbBuySignal) + " rsi=" + BoolLabel(rsiBuySignal) +
                             " macd=" + BoolLabel(macdBuyConfirm);
      SetStrategyDiagnostic(2, "NO_SETUP", noSetupReason, buyScore);
      LogStrategySignal(2, gSymbol, BB_Timeframe, "NO_SETUP", noSetupReason, "BUY", buyScore, buyScore, sellScore, noSetupDetail);
   }
   else
   {
      string noSetupReason = "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | band=" + BoolLabel(bbSellSignal) +
                             " rsi=" + BoolLabel(rsiSellSignal) + " macd=" + BoolLabel(macdSellConfirm);
      string noSetupDetail = "band=" + BoolLabel(bbSellSignal) + " rsi=" + BoolLabel(rsiSellSignal) +
                             " macd=" + BoolLabel(macdSellConfirm);
      SetStrategyDiagnostic(2, "NO_SETUP", noSetupReason, sellScore);
      LogStrategySignal(2, gSymbol, BB_Timeframe, "NO_SETUP", noSetupReason, "SELL", sellScore, buyScore, sellScore, noSetupDetail);
   }
}

//+------------------------------------------------------------------+
//| 遲也払4: MACD閭檎ｦｻ                                                    |
//+------------------------------------------------------------------+
void Strategy_MACD_Divergence()
{
   if(HasOpenPosition(MACD_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_macd = 0;
   datetime curBar = iTime(gSymbol, MACD_Timeframe, 0);
   if(curBar == lastBar_macd) return;
   lastBar_macd = curBar;

   // 譽豬玖レ遖ｻ
   int bullDiv = DetectBullishDivergence();
   int bearDiv = DetectBearishDivergence();

   double atrSL = GetATRStopLoss(gSymbol, MACD_Timeframe, 14, 2.0);

   // 蠎戊レ遖ｻ荵ｰ蜈･
   if(bullDiv > 0)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_MACD_Div_BUY", virtualLots), MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 蠎戊レ遖ｻ荵ｰ蜈･ ", lots, " 謇・@ ", Ask);
   }

   // 鬘ｶ閭檎ｦｻ蜊門・
   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_MACD_Div_SELL", virtualLots), MACD_Magic, 0, clrCrimson);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 鬘ｶ閭檎ｦｻ蜊門・ ", lots, " 謇・@ ", Bid);
   }
}

//+------------------------------------------------------------------+
//| 譽豬句ｺ戊レ遖ｻ (莉ｷ譬ｼ譁ｰ菴・ MACD譛ｪ譁ｰ菴・                                    |
//+------------------------------------------------------------------+
int DetectBullishDivergence()
{
   double priceLow1 = 0, priceLow2 = 0;
   double macdLow1 = 0, macdLow2 = 0;
   int pos1 = 0, pos2 = 0;

   // 謇ｾ譛霑台ｸ､荳ｪ莉ｷ譬ｼ菴守せ
   for(int i = 2; i < MACD_LookBack; i++)
   {
      double low_prev = iLow(gSymbol, MACD_Timeframe, i+1);
      double low_curr = iLow(gSymbol, MACD_Timeframe, i);
      double low_next = iLow(gSymbol, MACD_Timeframe, i-1);

      if(low_curr < low_prev && low_curr < low_next)
      {
         if(pos1 == 0)
         {
            pos1 = i;
            priceLow1 = low_curr;
            macdLow1 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
         }
         else if(pos2 == 0)
         {
            pos2 = i;
            priceLow2 = low_curr;
            macdLow2 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
            break;
         }
      }
   }

   if(pos1 == 0 || pos2 == 0) return 0;

   // 蠎戊レ遖ｻ: 莉ｷ譬ｼ蛻帶眠菴惹ｽ・ACD譛ｪ蛻帶眠菴・   if(priceLow1 < priceLow2 && macdLow1 > macdLow2)
      return 1;

   return 0;
}

//+------------------------------------------------------------------+
//| 譽豬矩｡ｶ閭檎ｦｻ (莉ｷ譬ｼ譁ｰ鬮・ MACD譛ｪ譁ｰ鬮・                                    |
//+------------------------------------------------------------------+
int DetectBearishDivergence()
{
   double priceHigh1 = 0, priceHigh2 = 0;
   double macdHigh1 = 0, macdHigh2 = 0;
   int pos1 = 0, pos2 = 0;

   for(int i = 2; i < MACD_LookBack; i++)
   {
      double high_prev = iHigh(gSymbol, MACD_Timeframe, i+1);
      double high_curr = iHigh(gSymbol, MACD_Timeframe, i);
      double high_next = iHigh(gSymbol, MACD_Timeframe, i-1);

      if(high_curr > high_prev && high_curr > high_next)
      {
         if(pos1 == 0)
         {
            pos1 = i;
            priceHigh1 = high_curr;
            macdHigh1 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
         }
         else if(pos2 == 0)
         {
            pos2 = i;
            priceHigh2 = high_curr;
            macdHigh2 = iMACD(gSymbol, MACD_Timeframe, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE, MODE_MAIN, i);
            break;
         }
      }
   }

   if(pos1 == 0 || pos2 == 0) return 0;

   // 鬘ｶ閭檎ｦｻ: 莉ｷ譬ｼ蛻帶眠鬮倅ｽ・ACD譛ｪ蛻帶眠鬮・   if(priceHigh1 > priceHigh2 && macdHigh1 < macdHigh2)
      return 1;

   return 0;
}

//+------------------------------------------------------------------+
//| 遲也払5: 謾ｯ謦鷹仆蜉帷ｪ∫ｴ                                                 |
//+------------------------------------------------------------------+
void Strategy_SR_Breakout()
{
   if(HasOpenPosition(SR_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_sr = 0;
   datetime curBar = iTime(gSymbol, SR_Timeframe, 0);
   if(curBar == lastBar_sr) return;
   lastBar_sr = curBar;

   double resistance = 0, support = 999999;
   for(int i = 1; i <= SR_LookBack; i++)
   {
      double high = iHigh(gSymbol, SR_Timeframe, i);
      double low  = iLow(gSymbol, SR_Timeframe, i);
      if(high > resistance) resistance = high;
      if(low < support)     support = low;
   }

   double close1 = iClose(gSymbol, SR_Timeframe, 1);
   double close2 = iClose(gSymbol, SR_Timeframe, 2);
   double breakPrice = PipsToPrice(SR_BreakPips, gSymbol);

   // 謌蝉ｺ､驥冗｡ｮ隶､ (蠖灘燕K郤ｿ謌蝉ｺ､驥・> 20蜻ｨ譛溷ｹｳ蝮・
   double avgVol = 0;
   for(int i = 1; i <= 20; i++)
      avgVol += (double)iVolume(gSymbol, SR_Timeframe, i);
   avgVol /= 20.0;
   bool volumeConfirm = iVolume(gSymbol, SR_Timeframe, 1) > avgVol * 1.2;

   double atrSL = GetATRStopLoss(gSymbol, SR_Timeframe, 14, 1.5);

   // 遯∫ｴ髦ｻ蜉帑ｹｰ蜈･
   if(close2 < resistance && close1 > resistance + breakPrice && volumeConfirm)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_SR_Break_BUY", virtualLots), SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR遯∫ｴ] 遯∫ｴ髦ｻ蜉帑ｹｰ蜈･ ", lots, " 謇・@ ", Ask, " R=", resistance);
   }

   // 霍檎ｴ謾ｯ謦大獄蜃ｺ
   if(close2 > support && close1 < support - breakPrice && volumeConfirm)
   {
      double sl = atrSL;
      double tp = AdjustTakeProfitPipsForResearch(sl * 2.0, sl, gSymbol);
      double virtualLots = 0.0;
      double lots = CalculateManagedLots(sl, gSymbol, virtualLots);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            BuildManagedOrderComment("QG_SR_Break_SELL", virtualLots), SR_Magic, 0, clrTomato);
      if(ticket > 0) Print("[SR遯∫ｴ] 霍檎ｴ謾ｯ謦大獄蜃ｺ ", lots, " 謇・@ ", Bid, " S=", support);
   }
}

//+------------------------------------------------------------------+
//| 扈溯ｮ｡謇譛画戟莉捺焚                                                     |
//+------------------------------------------------------------------+
int CountAllPositions()
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(IsManagedSymbol(OrderSymbol()) && IsManagedMagic(OrderMagicNumber()))
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| 譖ｴ譁ｰ蝗ｾ陦ｨ菫｡諱ｯ譏ｾ遉ｺ                                                    |
//+------------------------------------------------------------------+
int GetTickAgeSeconds()
{
   return GetTickAgeSecondsForSymbol(gDashboardSymbol);
}

bool IsTerminalTradeEnabled()
{
   return (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
}

bool IsProgramTradeEnabled()
{
   return (bool)MQLInfoInteger(MQL_TRADE_ALLOWED);
}

bool IsDllImportEnabled()
{
   return (bool)MQLInfoInteger(MQL_DLLS_ALLOWED);
}

bool ToggleTerminalAutoTrading()
{
   int chartWindow = WindowHandle(gSymbol, Period());
   if(chartWindow == 0)
      return false;

   int mainWindow = GetAncestor(chartWindow, GA_ROOT);
   if(mainWindow == 0)
      return false;

   return PostMessageA(mainWindow, WM_COMMAND, MT4_WMCMD_EXPERTS, 0) != 0;
}

void EnsureAutoTradingEnabled()
{
   static datetime lastAttempt = 0;

   if(!AutoEnableTrading)
      return;

   if(IsTerminalTradeEnabled())
      return;

   if(IsTesting() || !IsDllImportEnabled())
      return;

   if(TimeLocal() - lastAttempt < 15)
      return;

   lastAttempt = TimeLocal();

   bool toggleSent = ToggleTerminalAutoTrading();
   Print("[QuantGod] Auto-enable trading attempt sent=", toggleSent,
         " | terminalAllowed=", IsTerminalTradeEnabled(),
         " | programAllowed=", IsProgramTradeEnabled(),
         " | dllAllowed=", IsDllImportEnabled());
}

string GetTradingStatus()
{
   return GetTradingStatusForSymbol(gSymbol);
}

string GetTradingStatusForSymbol(string symbol_name)
{
   if(!IsConnected())
      return "DISCONNECTED";

   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return "ACCOUNT_TRADE_DISABLED";

   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return "SERVER_EXPERTS_DISABLED";

   if(!IsTerminalTradeEnabled())
      return "TERMINAL_AUTOTRADING_OFF";

   if(!IsProgramTradeEnabled())
      return "EA_LIVE_TRADING_OFF";

   if(FlattenManagedPositions)
      return "FLATTENING";

   if(PauseNewEntries)
      return "PAUSED";

   if(!CheckResearchDrawdownLimit())
      return "DRAWDOWN_GUARD";

   if(UseTradeSession && !IsTradeSession())
      return "OUT_OF_SESSION";

   int tickAge = GetTickAgeSecondsForSymbol(symbol_name);
   if(tickAge < 0 || tickAge > 180)
      return "WAITING_MARKET";

   return "READY";
}

void UpdateChartDisplayV2()
{
   PrepareSymbolContext(gDashboardSymbol);
   double balance = GetDisplayedBalance();
   double equity = GetDisplayedEquity();
   double profit = GetDisplayedProfit();
   double dd = GetDisplayedDrawdownPercent();
   int tickAge = GetTickAgeSeconds();
   string tradingStatus = GetTradingStatus();
   string terminalTrading = IsTerminalTradeEnabled() ? "ON" : "OFF";
   string programTrading = IsProgramTradeEnabled() ? "ON" : "OFF";
   string dllTrading = IsDllImportEnabled() ? "ON" : "OFF";

   string info = "";
   info += "QuantGod Multi-Strategy v2.6\n";
   info += "Focus: " + gDashboardSymbol + "  Chart: " + gChartSymbol + "\n";
   info += "Watchlist: " + GetManagedSymbolsLabel() + "\n";
   info += "Mode: " + (UseVirtualResearchAccount ? "Virtual Research" : "Broker Balance") + "\n";
   info += "Balance: $" + DoubleToStr(balance, 2) + "\n";
   info += "Equity:  $" + DoubleToStr(equity, 2) + "\n";
   info += "Profit:  $" + DoubleToStr(profit, 2) + "\n";
   info += "Drawdown: " + DoubleToStr(dd, 2) + "%\n";
   if(UseVirtualResearchAccount)
   {
      info += "Start: $" + DoubleToStr(VirtualStartingBalance, 2) +
              "  Risk: " + DoubleToStr(VirtualRiskPercent, 2) + "%\n";
      info += "Exec Lot: " + DoubleToStr(NormalizeLotForSymbol(MathMax(ResearchExecutionLot, MarketInfo(gSymbol, MODE_MINLOT)), gSymbol), 2) + "\n";
      info += "Broker Equity: $" + DoubleToStr(AccountEquity(), 2) + "\n";
   }
   info += "Terminal AutoTrading: " + terminalTrading + "\n";
   info += "EA Live Trading: " + programTrading + "  DLL: " + dllTrading + "\n";
   info += "Status: " + tradingStatus + "\n";
   if(tickAge >= 0)
      info += "Last Tick Age: " + IntegerToString(tickAge) + " sec\n";
   else
      info += "Last Tick Age: N/A\n";
   info += "Open Positions: " + IntegerToString(CountAllPositions()) + "/" + IntegerToString(MaxTotalTrades) + "\n";
   info += "Spread: " + DoubleToStr(GetSpreadPips(gSymbol), 1) + " pips\n";
   info += "MA: " + GetStrategyRuntimeLabel(0) + " x" + DoubleToStr(GetStrategyRiskMultiplier(0), 2) +
           " (" + IntegerToString(CountPositionsAllSymbols(MA_Magic)) + ")\n";
   info += "RSI: " + GetStrategyRuntimeLabel(1) + " x" + DoubleToStr(GetStrategyRiskMultiplier(1), 2) +
           " (" + IntegerToString(CountPositionsAllSymbols(RSI_Magic)) + ")\n";
   info += "BB: " + GetStrategyRuntimeLabel(2) + " x" + DoubleToStr(GetStrategyRiskMultiplier(2), 2) +
           " (" + IntegerToString(CountPositionsAllSymbols(BB_Magic)) + ")\n";
   info += "MACD: " + GetStrategyRuntimeLabel(3) + " x" + DoubleToStr(GetStrategyRiskMultiplier(3), 2) +
           " (" + IntegerToString(CountPositionsAllSymbols(MACD_Magic)) + ")\n";
   info += "SR: " + GetStrategyRuntimeLabel(4) + " x" + DoubleToStr(GetStrategyRiskMultiplier(4), 2) +
           " (" + IntegerToString(CountPositionsAllSymbols(SR_Magic)) + ")";

   Comment(info);
}

void UpdateChartDisplay()
{
   double balance = AccountBalance();
   double equity = AccountEquity();
   double profit = AccountProfit();
   double dd = 0;
   if(balance > 0) dd = (balance - equity) / balance * 100.0;

   string info = "";
   info += "笊披武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶風\n";
   info += "笊・    QuantGod Multi-Strategy v2.0     笊曾n";
   info += "笊笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊｣\n";
   info += "笊・菴咎｢・ $" + DoubleToStr(balance, 2) + "\n";
   info += "笊・蜃蛟ｼ: $" + DoubleToStr(equity, 2) + "\n";
   info += "笊・豬ｮ逶・ $" + DoubleToStr(profit, 2) + "\n";
   info += "笊・蝗樊彫: " + DoubleToStr(dd, 2) + "%\n";
   info += "笊笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊｣\n";
   info += "笊・MA莠､蜿・  " + (Enable_MA ? "ON" : "OFF") + "  | 謖∽ｻ・ " + IntegerToString(CountPositions(MA_Magic, gSymbol)) + "\n";
   info += "笊・RSI蝗槫ｽ・ " + (Enable_RSI ? "ON" : "OFF") + " | 謖∽ｻ・ " + IntegerToString(CountPositions(RSI_Magic, gSymbol)) + "\n";
   info += "笊・BB荳蛾㍾:  " + (Enable_BB ? "ON" : "OFF") + "  | 謖∽ｻ・ " + IntegerToString(CountPositions(BB_Magic, gSymbol)) + "\n";
   info += "笊・MACD閭檎ｦｻ:" + (Enable_MACD ? "ON" : "OFF") + " | 謖∽ｻ・ " + IntegerToString(CountPositions(MACD_Magic, gSymbol)) + "\n";
   info += "笊・SR遯∫ｴ:  " + (Enable_SR ? "ON" : "OFF") + "  | 謖∽ｻ・ " + IntegerToString(CountPositions(SR_Magic, gSymbol)) + "\n";
   info += "笊笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊｣\n";
   info += "笊・諤ｻ謖∽ｻ・ " + IntegerToString(CountAllPositions()) + "/" + IntegerToString(MaxTotalTrades) + "\n";
   info += "笊・轤ｹ蟾ｮ: " + DoubleToStr(GetSpreadPips(gSymbol), 1) + " pips\n";
   info += "笊壺武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶幅\n";

   Comment(info);
}

void ExportStrategyEvaluationReport(bool force)
{
   if(!EnableStrategyReport)
      return;

   int intervalSeconds = StrategyReportIntervalSeconds;
   if(intervalSeconds < 30)
      intervalSeconds = 30;

   datetime nowLocal = TimeLocal();
   if(!force && gLastStrategyReportExport > 0 &&
      nowLocal - gLastStrategyReportExport < intervalSeconds)
      return;

   int handle = FileOpen("QuantGod_StrategyEvaluationReport.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_StrategyEvaluationReport.csv, error=", GetLastError());
      return;
   }

   FileWrite(handle,
             "ReportTimeLocal", "ReportTimeServer", "Symbol", "Strategy", "Timeframe", "Regime",
             "Enabled", "Active", "RuntimeLabel", "AdaptiveState", "AdaptiveReason", "RiskMultiplier",
             "TradingStatus", "SignalStatus", "SignalReason", "SignalScore", "ClosedTrades", "WinRate",
             "ProfitFactor", "AvgNet", "NetProfit", "GrossProfit", "GrossLoss", "OpenPositions",
             "StrategyPositions", "TickAgeSeconds", "SpreadPips", "ATRPips", "ADX", "BBWidthPips",
             "LastEvalTime", "LastClosedTime");

   for(int symIndex = 0; symIndex < gManagedSymbolCount; symIndex++)
   {
      string symbolName = gManagedSymbols[symIndex];
      string tradingStatus = GetTradingStatusForSymbol(symbolName);
      int tickAge = GetTickAgeSecondsForSymbol(symbolName);
      int symbolOpenPositions = CountManagedPositionsForSymbol(symbolName);

      for(int strategyIndex = 0; strategyIndex < STRATEGY_DIAG_COUNT; strategyIndex++)
      {
         int timeframe = StrategyTimeframe(strategyIndex);
         int magic = GetStrategyMagicByIndex(strategyIndex);
         double atrPips = 0.0;
         double adxValue = 0.0;
         double bbWidthPips = 0.0;
         double spreadPips = 0.0;
         string regime = DetectMarketRegime(symbolName, timeframe, atrPips, adxValue, bbWidthPips, spreadPips);

         int closedTrades = 0;
         int winTrades = 0;
         double netProfit = 0.0;
         double grossProfit = 0.0;
         double grossLoss = 0.0;
         datetime lastCloseTime = 0;
         GetStrategyClosedStats(strategyIndex, symbolName, closedTrades, winTrades,
                                netProfit, grossProfit, grossLoss, lastCloseTime);

         double winRate = (closedTrades > 0) ? ((double)winTrades * 100.0 / closedTrades) : 0.0;
         double avgNet = (closedTrades > 0) ? (netProfit / closedTrades) : 0.0;
         double profitFactor = 0.0;
         if(grossLoss > 0.0)
            profitFactor = grossProfit / grossLoss;
         else if(grossProfit > 0.0)
            profitFactor = 999.0;

         FileWrite(handle,
                   TimeToStr(nowLocal, TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                   TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                   symbolName,
                   GetStrategyNameByIndex(strategyIndex),
                   TimeframeLabel(timeframe),
                   regime,
                   BoolLabel(IsStrategyConfiguredEnabled(strategyIndex)),
                   BoolLabel(IsStrategyRuntimeActive(strategyIndex)),
                   GetStrategyRuntimeLabel(strategyIndex),
                   gAdaptiveState[strategyIndex],
                   SanitizeCsvText(gAdaptiveReason[strategyIndex]),
                   DoubleToStr(GetStrategyRiskMultiplier(strategyIndex), 2),
                   tradingStatus,
                   gManagedDiagStatus[symIndex][strategyIndex],
                   SanitizeCsvText(gManagedDiagReason[symIndex][strategyIndex]),
                   DoubleToStr(gManagedDiagScore[symIndex][strategyIndex], 1),
                   closedTrades,
                   DoubleToStr(winRate, 1),
                   DoubleToStr(profitFactor, 2),
                   DoubleToStr(avgNet, 2),
                   DoubleToStr(netProfit, 2),
                   DoubleToStr(grossProfit, 2),
                   DoubleToStr(grossLoss, 2),
                   symbolOpenPositions,
                   (magic > 0 ? CountStrategyPositionsForSymbol(magic, symbolName) : 0),
                   tickAge,
                   DoubleToStr(spreadPips, 1),
                   DoubleToStr(atrPips, 1),
                   DoubleToStr(adxValue, 1),
                   DoubleToStr(bbWidthPips, 1),
                   (gStrategyLastEvalTime[symIndex][strategyIndex] > 0 ? TimeToStr(gStrategyLastEvalTime[symIndex][strategyIndex], TIME_DATE|TIME_MINUTES|TIME_SECONDS) : ""),
                   (lastCloseTime > 0 ? TimeToStr(lastCloseTime, TIME_DATE|TIME_MINUTES|TIME_SECONDS) : ""));
      }
   }

   FileClose(handle);
   gLastStrategyReportExport = nowLocal;
}

//+------------------------------------------------------------------+
//| 蟇ｼ蜃ｺ謨ｰ謐ｮ蛻ｰWeb髱｢譚ｿ                                                   |
//+------------------------------------------------------------------+
void ExportDashboardData()
{
   PrepareSymbolContext(gDashboardSymbol);
   string filename = "QuantGod_Dashboard.json";
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   double brokerBalance = AccountBalance();
   double brokerEquity = AccountEquity();
   double brokerProfit = AccountProfit();
   double brokerMargin = AccountMargin();
   double brokerFreeMargin = AccountFreeMargin();
   double brokerDD = 0.0;
   if(brokerBalance > 0)
      brokerDD = (brokerBalance - brokerEquity) / brokerBalance * 100.0;

   double displayBalance = GetDisplayedBalance();
   double displayEquity = GetDisplayedEquity();
   double displayProfit = GetDisplayedProfit();
   double displayDD = GetDisplayedDrawdownPercent();

   FileWriteString(handle, "{\n");
   FileWriteString(handle, "  \"timestamp\": \"" + TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "  \"build\": \"QuantGod-v2.7-fast-exit\",\n");
   FileWriteString(handle, "  \"runtime\": {\n");
   FileWriteString(handle, "    \"tradeStatus\": \"" + GetTradingStatus() + "\",\n");
   FileWriteString(handle, "    \"connected\": " + (IsConnected() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"terminalTradeAllowed\": " + (IsTerminalTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"programTradeAllowed\": " + (IsProgramTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"dllAllowed\": " + (IsDllImportEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tradeAllowed\": " + (IsTradeAllowed() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tickAgeSeconds\": " + IntegerToString(GetTickAgeSeconds()) + ",\n");
   FileWriteString(handle, "    \"researchMode\": " + (UseVirtualResearchAccount ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"serverTime\": \"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "    \"gmtTime\": \"" + TimeToStr(TimeGMT(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "    \"localTime\": \"" + TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\"\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"cloudSync\": {\n");
   FileWriteString(handle, "    \"enabled\": " + (EnableCloudSync ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"configured\": " + ((StringLen(CloudSyncEndpoint) >= 12) ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"endpoint\": \"" + JsonEscape(CloudSyncEndpoint) + "\",\n");
   FileWriteString(handle, "    \"intervalSeconds\": " + IntegerToString(CloudSyncIntervalSeconds) + ",\n");
   FileWriteString(handle, "    \"lastAttemptLocal\": \"" + (gLastCloudSyncAttempt > 0 ? TimeToStr(gLastCloudSyncAttempt, TIME_DATE|TIME_MINUTES|TIME_SECONDS) : "") + "\",\n");
   FileWriteString(handle, "    \"lastSuccessLocal\": \"" + (gLastCloudSyncSuccess > 0 ? TimeToStr(gLastCloudSyncSuccess, TIME_DATE|TIME_MINUTES|TIME_SECONDS) : "") + "\",\n");
   FileWriteString(handle, "    \"status\": \"" + JsonEscape(gLastCloudSyncStatus) + "\",\n");
   FileWriteString(handle, "    \"httpCode\": " + IntegerToString(gLastCloudSyncHttpCode) + ",\n");
   FileWriteString(handle, "    \"message\": \"" + JsonEscape(gLastCloudSyncMessage) + "\"\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"account\": {\n");
   FileWriteString(handle, "    \"number\": " + IntegerToString(AccountNumber()) + ",\n");
   FileWriteString(handle, "    \"name\": \"" + JsonEscape(AccountName()) + "\",\n");
   FileWriteString(handle, "    \"server\": \"" + JsonEscape(AccountServer()) + "\",\n");
   FileWriteString(handle, "    \"currency\": \"" + JsonEscape(AccountCurrency()) + "\",\n");
   FileWriteString(handle, "    \"mode\": \"" + (UseVirtualResearchAccount ? "virtual_research" : "broker_account") + "\",\n");
   FileWriteString(handle, "    \"startingBalance\": " + DoubleToStr(UseVirtualResearchAccount ? VirtualStartingBalance : brokerBalance, 2) + ",\n");
   FileWriteString(handle, "    \"riskPercent\": " + DoubleToStr(UseVirtualResearchAccount ? VirtualRiskPercent : RiskPercent, 2) + ",\n");
   FileWriteString(handle, "    \"executionLot\": " + DoubleToStr(NormalizeLotForSymbol(MathMax(ResearchExecutionLot, MarketInfo(gSymbol, MODE_MINLOT)), gSymbol), 2) + ",\n");
   FileWriteString(handle, "    \"balance\": " + DoubleToStr(displayBalance, 2) + ",\n");
   FileWriteString(handle, "    \"equity\": " + DoubleToStr(displayEquity, 2) + ",\n");
   FileWriteString(handle, "    \"profit\": " + DoubleToStr(displayProfit, 2) + ",\n");
   FileWriteString(handle, "    \"margin\": " + DoubleToStr(brokerMargin, 2) + ",\n");
   FileWriteString(handle, "    \"freeMargin\": " + DoubleToStr(brokerFreeMargin, 2) + ",\n");
   FileWriteString(handle, "    \"drawdown\": " + DoubleToStr(displayDD, 2) + ",\n");
   FileWriteString(handle, "    \"maxDrawdownPercent\": " + DoubleToStr(MaxDrawdownPercent, 2) + ",\n");
   FileWriteString(handle, "    \"maxTotalTrades\": " + IntegerToString(MaxTotalTrades) + ",\n");
   FileWriteString(handle, "    \"leverage\": " + IntegerToString(AccountLeverage()) + "\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"brokerAccount\": {\n");
   FileWriteString(handle, "    \"balance\": " + DoubleToStr(brokerBalance, 2) + ",\n");
   FileWriteString(handle, "    \"equity\": " + DoubleToStr(brokerEquity, 2) + ",\n");
   FileWriteString(handle, "    \"profit\": " + DoubleToStr(brokerProfit, 2) + ",\n");
   FileWriteString(handle, "    \"margin\": " + DoubleToStr(brokerMargin, 2) + ",\n");
   FileWriteString(handle, "    \"freeMargin\": " + DoubleToStr(brokerFreeMargin, 2) + ",\n");
   FileWriteString(handle, "    \"drawdown\": " + DoubleToStr(brokerDD, 2) + ",\n");
   FileWriteString(handle, "    \"server\": \"" + JsonEscape(AccountServer()) + "\",\n");
   FileWriteString(handle, "    \"leverage\": " + IntegerToString(AccountLeverage()) + "\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"watchlist\": \"" + JsonEscape(GetManagedSymbolsLabel()) + "\",\n");
   FileWriteString(handle, "  \"symbols\": [\n");

   bool firstSymbolEntry = true;
   for(int symIndex = 0; symIndex < gManagedSymbolCount; symIndex++)
   {
      string symbolName = gManagedSymbols[symIndex];
      int symbolDigits = DigitsForSymbolName(symbolName);
      double symbolBid = MarketInfo(symbolName, MODE_BID);
      double symbolAsk = MarketInfo(symbolName, MODE_ASK);
      double symbolSpread = GetSpreadPips(symbolName);
      int symbolTickAge = GetTickAgeSecondsForSymbol(symbolName);
      int symbolOpenPositions = 0;
      double symbolActualFloatingProfit = 0.0;

      for(int openIndex = 0; openIndex < OrdersTotal(); openIndex++)
      {
         if(!OrderSelect(openIndex, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderSymbol() != symbolName) continue;
         if(!IsManagedMagic(OrderMagicNumber())) continue;

         symbolOpenPositions++;
         symbolActualFloatingProfit += (OrderProfit() + OrderSwap() + OrderCommission());
      }

      int symbolClosedTrades = 0;
      int symbolWinTrades = 0;
      datetime symbolLastCloseTime = 0;
      double symbolClosedProfit = GetResearchSymbolClosedProfit(symbolName, symbolClosedTrades, symbolWinTrades, symbolLastCloseTime);
      double symbolFloatingProfit = UseVirtualResearchAccount ? GetResearchSymbolFloatingProfit(symbolName) : symbolActualFloatingProfit;
      double symbolWinRate = (symbolClosedTrades > 0)
                           ? ((double)symbolWinTrades * 100.0 / symbolClosedTrades)
                           : 0.0;

      double symbolActualClosedProfit = 0.0;
      for(int historyIndex = OrdersHistoryTotal() - 1; historyIndex >= 0; historyIndex--)
      {
         if(!OrderSelect(historyIndex, SELECT_BY_POS, MODE_HISTORY)) continue;
         if(OrderSymbol() != symbolName) continue;
         if(!IsManagedMagic(OrderMagicNumber())) continue;
         symbolActualClosedProfit += (OrderProfit() + OrderSwap() + OrderCommission());
      }

      if(!UseVirtualResearchAccount)
         symbolClosedProfit = symbolActualClosedProfit;

      string symbolStatus = GetTradingStatusForSymbol(symbolName);
      if(symbolStatus == "READY" && symbolOpenPositions > 0)
         symbolStatus = "IN_POSITION";

      if(!firstSymbolEntry) FileWriteString(handle, ",\n");
      firstSymbolEntry = false;

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"symbol\": \"" + symbolName + "\",\n");
      FileWriteString(handle, "      \"role\": \"" + ((symbolName == gDashboardSymbol) ? "focus" : "managed") + "\",\n");
      FileWriteString(handle, "      \"status\": \"" + symbolStatus + "\",\n");
      FileWriteString(handle, "      \"tickAgeSeconds\": " + IntegerToString(symbolTickAge) + ",\n");
      FileWriteString(handle, "      \"bid\": " + DoubleToStr(symbolBid, symbolDigits) + ",\n");
      FileWriteString(handle, "      \"ask\": " + DoubleToStr(symbolAsk, symbolDigits) + ",\n");
      FileWriteString(handle, "      \"spread\": " + DoubleToStr(symbolSpread, 1) + ",\n");
      FileWriteString(handle, "      \"openPositions\": " + IntegerToString(symbolOpenPositions) + ",\n");
      FileWriteString(handle, "      \"floatingProfit\": " + DoubleToStr(symbolFloatingProfit, 2) + ",\n");
      FileWriteString(handle, "      \"actualFloatingProfit\": " + DoubleToStr(symbolActualFloatingProfit, 2) + ",\n");
      FileWriteString(handle, "      \"closedTrades\": " + IntegerToString(symbolClosedTrades) + ",\n");
      FileWriteString(handle, "      \"winRate\": " + DoubleToStr(symbolWinRate, 1) + ",\n");
      FileWriteString(handle, "      \"closedProfit\": " + DoubleToStr(symbolClosedProfit, 2) + ",\n");
      FileWriteString(handle, "      \"actualClosedProfit\": " + DoubleToStr(symbolActualClosedProfit, 2) + ",\n");
      FileWriteString(handle, "      \"lastCloseTime\": \"" + (symbolLastCloseTime > 0 ? TimeToStr(symbolLastCloseTime, TIME_DATE|TIME_MINUTES) : "") + "\",\n");
      FileWriteString(handle, "      \"strategies\": {\n");
      FileWriteString(handle, "        \"MA_Cross\": {\"status\": \"" + JsonEscape(gManagedDiagStatus[symIndex][0]) + "\", \"score\": " + DoubleToStr(gManagedDiagScore[symIndex][0], 1) + ", \"reason\": \"" + JsonEscape(gManagedDiagReason[symIndex][0]) + "\"},\n");
      FileWriteString(handle, "        \"RSI_Reversal\": {\"status\": \"" + JsonEscape(gManagedDiagStatus[symIndex][1]) + "\", \"score\": " + DoubleToStr(gManagedDiagScore[symIndex][1], 1) + ", \"reason\": \"" + JsonEscape(gManagedDiagReason[symIndex][1]) + "\"},\n");
      FileWriteString(handle, "        \"BB_Triple\": {\"status\": \"" + JsonEscape(gManagedDiagStatus[symIndex][2]) + "\", \"score\": " + DoubleToStr(gManagedDiagScore[symIndex][2], 1) + ", \"reason\": \"" + JsonEscape(gManagedDiagReason[symIndex][2]) + "\"},\n");
      FileWriteString(handle, "        \"MACD_Divergence\": {\"status\": \"" + JsonEscape(gManagedDiagStatus[symIndex][3]) + "\", \"score\": " + DoubleToStr(gManagedDiagScore[symIndex][3], 1) + ", \"reason\": \"" + JsonEscape(gManagedDiagReason[symIndex][3]) + "\"},\n");
      FileWriteString(handle, "        \"SR_Breakout\": {\"status\": \"" + JsonEscape(gManagedDiagStatus[symIndex][4]) + "\", \"score\": " + DoubleToStr(gManagedDiagScore[symIndex][4], 1) + ", \"reason\": \"" + JsonEscape(gManagedDiagReason[symIndex][4]) + "\"}\n");
      FileWriteString(handle, "      }\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   FileWriteString(handle, "  \"openTrades\": [\n");
   bool firstTrade = true;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchLots = GetResearchLotsFromComment(OrderComment(), OrderLots());
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      if(!firstTrade) FileWriteString(handle, ",\n");
      firstTrade = false;

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"symbol\": \"" + OrderSymbol() + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(UseVirtualResearchAccount ? researchLots : OrderLots(), 5) + ",\n");
      FileWriteString(handle, "      \"actualLots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"virtualLots\": " + DoubleToStr(researchLots, 5) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"sl\": " + DoubleToStr(OrderStopLoss(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"tp\": " + DoubleToStr(OrderTakeProfit(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(UseVirtualResearchAccount ? researchNet : actualNet, 2) + ",\n");
      FileWriteString(handle, "      \"actualProfit\": " + DoubleToStr(actualNet, 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + JsonEscape(OrderComment()) + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   FileWriteString(handle, "  \"closedTrades\": [\n");
   bool firstClosed = true;
   int historyTotal = OrdersHistoryTotal();
   for(int j = historyTotal - 1; j >= 0; j--)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchLots = GetResearchLotsFromComment(OrderComment(), OrderLots());
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      if(!firstClosed) FileWriteString(handle, ",\n");
      firstClosed = false;

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"symbol\": \"" + OrderSymbol() + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(UseVirtualResearchAccount ? researchLots : OrderLots(), 5) + ",\n");
      FileWriteString(handle, "      \"actualLots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"virtualLots\": " + DoubleToStr(researchLots, 5) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"closePrice\": " + DoubleToStr(OrderClosePrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(UseVirtualResearchAccount ? researchNet : actualNet, 2) + ",\n");
      FileWriteString(handle, "      \"actualProfit\": " + DoubleToStr(actualNet, 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"closeTime\": \"" + TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + JsonEscape(OrderComment()) + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   FileWriteString(handle, "  \"strategies\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"enabled\": " + (Enable_MA ? "true" : "false") +
                               ", \"active\": " + (IsStrategyRuntimeActive(0) ? "true" : "false") +
                               ", \"state\": \"" + JsonEscape(gAdaptiveState[0]) + "\"" +
                               ", \"riskMultiplier\": " + DoubleToStr(GetStrategyRiskMultiplier(0), 2) +
                               ", \"sampleTrades\": " + IntegerToString(gAdaptiveSampleCount[0]) +
                               ", \"sampleWindowTrades\": " + IntegerToString(gAdaptiveTradeCount[0]) +
                               ", \"winRate\": " + DoubleToStr(gAdaptiveWinRate[0], 1) +
                               ", \"profitFactor\": " + DoubleToStr(gAdaptiveProfitFactor[0], 2) +
                               ", \"avgNet\": " + DoubleToStr(gAdaptiveAvgNet[0], 2) +
                               ", \"netProfit\": " + DoubleToStr(gAdaptiveNetProfit[0], 2) +
                               ", \"disabledUntil\": \"" + (gAdaptiveDisabledUntil[0] > 0 ? TimeToStr(gAdaptiveDisabledUntil[0], TIME_DATE|TIME_MINUTES) : "") + "\"" +
                               ", \"reason\": \"" + JsonEscape(gAdaptiveReason[0]) + "\"" +
                               ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(MA_Magic)) + "},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"enabled\": " + (Enable_RSI ? "true" : "false") +
                               ", \"active\": " + (IsStrategyRuntimeActive(1) ? "true" : "false") +
                               ", \"state\": \"" + JsonEscape(gAdaptiveState[1]) + "\"" +
                               ", \"riskMultiplier\": " + DoubleToStr(GetStrategyRiskMultiplier(1), 2) +
                               ", \"sampleTrades\": " + IntegerToString(gAdaptiveSampleCount[1]) +
                               ", \"sampleWindowTrades\": " + IntegerToString(gAdaptiveTradeCount[1]) +
                               ", \"winRate\": " + DoubleToStr(gAdaptiveWinRate[1], 1) +
                               ", \"profitFactor\": " + DoubleToStr(gAdaptiveProfitFactor[1], 2) +
                               ", \"avgNet\": " + DoubleToStr(gAdaptiveAvgNet[1], 2) +
                               ", \"netProfit\": " + DoubleToStr(gAdaptiveNetProfit[1], 2) +
                               ", \"disabledUntil\": \"" + (gAdaptiveDisabledUntil[1] > 0 ? TimeToStr(gAdaptiveDisabledUntil[1], TIME_DATE|TIME_MINUTES) : "") + "\"" +
                               ", \"reason\": \"" + JsonEscape(gAdaptiveReason[1]) + "\"" +
                               ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(RSI_Magic)) + "},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"enabled\": " + (Enable_BB ? "true" : "false") +
                               ", \"active\": " + (IsStrategyRuntimeActive(2) ? "true" : "false") +
                               ", \"state\": \"" + JsonEscape(gAdaptiveState[2]) + "\"" +
                               ", \"riskMultiplier\": " + DoubleToStr(GetStrategyRiskMultiplier(2), 2) +
                               ", \"sampleTrades\": " + IntegerToString(gAdaptiveSampleCount[2]) +
                               ", \"sampleWindowTrades\": " + IntegerToString(gAdaptiveTradeCount[2]) +
                               ", \"winRate\": " + DoubleToStr(gAdaptiveWinRate[2], 1) +
                               ", \"profitFactor\": " + DoubleToStr(gAdaptiveProfitFactor[2], 2) +
                               ", \"avgNet\": " + DoubleToStr(gAdaptiveAvgNet[2], 2) +
                               ", \"netProfit\": " + DoubleToStr(gAdaptiveNetProfit[2], 2) +
                               ", \"disabledUntil\": \"" + (gAdaptiveDisabledUntil[2] > 0 ? TimeToStr(gAdaptiveDisabledUntil[2], TIME_DATE|TIME_MINUTES) : "") + "\"" +
                               ", \"reason\": \"" + JsonEscape(gAdaptiveReason[2]) + "\"" +
                               ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(BB_Magic)) + "},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"enabled\": " + (Enable_MACD ? "true" : "false") +
                               ", \"active\": " + (IsStrategyRuntimeActive(3) ? "true" : "false") +
                               ", \"state\": \"" + JsonEscape(gAdaptiveState[3]) + "\"" +
                               ", \"riskMultiplier\": " + DoubleToStr(GetStrategyRiskMultiplier(3), 2) +
                               ", \"sampleTrades\": " + IntegerToString(gAdaptiveSampleCount[3]) +
                               ", \"sampleWindowTrades\": " + IntegerToString(gAdaptiveTradeCount[3]) +
                               ", \"winRate\": " + DoubleToStr(gAdaptiveWinRate[3], 1) +
                               ", \"profitFactor\": " + DoubleToStr(gAdaptiveProfitFactor[3], 2) +
                               ", \"avgNet\": " + DoubleToStr(gAdaptiveAvgNet[3], 2) +
                               ", \"netProfit\": " + DoubleToStr(gAdaptiveNetProfit[3], 2) +
                               ", \"disabledUntil\": \"" + (gAdaptiveDisabledUntil[3] > 0 ? TimeToStr(gAdaptiveDisabledUntil[3], TIME_DATE|TIME_MINUTES) : "") + "\"" +
                               ", \"reason\": \"" + JsonEscape(gAdaptiveReason[3]) + "\"" +
                               ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(MACD_Magic)) + "},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"enabled\": " + (Enable_SR ? "true" : "false") +
                               ", \"active\": " + (IsStrategyRuntimeActive(4) ? "true" : "false") +
                               ", \"state\": \"" + JsonEscape(gAdaptiveState[4]) + "\"" +
                               ", \"riskMultiplier\": " + DoubleToStr(GetStrategyRiskMultiplier(4), 2) +
                               ", \"sampleTrades\": " + IntegerToString(gAdaptiveSampleCount[4]) +
                               ", \"sampleWindowTrades\": " + IntegerToString(gAdaptiveTradeCount[4]) +
                               ", \"winRate\": " + DoubleToStr(gAdaptiveWinRate[4], 1) +
                               ", \"profitFactor\": " + DoubleToStr(gAdaptiveProfitFactor[4], 2) +
                               ", \"avgNet\": " + DoubleToStr(gAdaptiveAvgNet[4], 2) +
                               ", \"netProfit\": " + DoubleToStr(gAdaptiveNetProfit[4], 2) +
                               ", \"disabledUntil\": \"" + (gAdaptiveDisabledUntil[4] > 0 ? TimeToStr(gAdaptiveDisabledUntil[4], TIME_DATE|TIME_MINUTES) : "") + "\"" +
                               ", \"reason\": \"" + JsonEscape(gAdaptiveReason[4]) + "\"" +
                               ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(SR_Magic)) + "}\n");
   FileWriteString(handle, "  },\n");

   FileWriteString(handle, "  \"diagnostics\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[0]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[0], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[0]) + "\"},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[1]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[1], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[1]) + "\"},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[2]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[2], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[2]) + "\"},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[3]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[3], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[3]) + "\"},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[4]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[4], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[4]) + "\"}\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"market\": {\n");
   FileWriteString(handle, "    \"symbol\": \"" + gSymbol + "\",\n");
   FileWriteString(handle, "    \"bid\": " + DoubleToStr(MarketInfo(gSymbol, MODE_BID), gDigits) + ",\n");
   FileWriteString(handle, "    \"ask\": " + DoubleToStr(MarketInfo(gSymbol, MODE_ASK), gDigits) + ",\n");
   FileWriteString(handle, "    \"spread\": " + DoubleToStr(GetSpreadPips(gSymbol), 1) + "\n");
   FileWriteString(handle, "  }\n");
   FileWriteString(handle, "}\n");
   FileClose(handle);

   if(CanSyncToCloud())
   {
      if(gLastCloudSyncAttempt <= 0 || TimeLocal() - gLastCloudSyncAttempt >= CloudSyncIntervalSeconds)
         SyncDashboardToCloud(filename);
   }

   ExportBalanceHistoryV2();
}

//+------------------------------------------------------------------+
//| 蟇ｼ蜃ｺ菴咎｢晏紙蜿ｲ                                                       |
//+------------------------------------------------------------------+
void LoadTradeLogState()
{
   int handle = FileOpen("QuantGod_LogState.csv", FILE_CSV | FILE_ANSI | FILE_READ, ',');
   if(handle == INVALID_HANDLE)
      return;

   if(!FileIsEnding(handle))
   {
      gLastLoggedCloseTime = (datetime)FileReadNumber(handle);
      gLastLoggedCloseTicket = (int)FileReadNumber(handle);
   }

   FileClose(handle);
}

void AppendTradeEventLink(string eventId, int ticket, int strategyIndex, string symbol_name, int timeframe,
                          string signalStatus, string signalDirection, double signalScore,
                          double requestedPrice, double stopLoss, double takeProfit,
                          double actualLots, double researchLots, string orderComment)
{
   if(eventId == "" || ticket <= 0)
      return;

   int handle = FileOpen("QuantGod_TradeEventLinks.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen("QuantGod_TradeEventLinks.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_TradeEventLinks.csv, error=", GetLastError());
      return;
   }

   if(FileSize(handle) == 0)
   {
      FileWrite(handle,
                "EventId", "EventKey", "Ticket", "TimeLocal", "TimeServer", "Strategy", "Symbol", "Timeframe",
                "SignalStatus", "SignalDirection", "SignalScore", "EventBarTime",
                "RequestedPrice", "StopLoss", "TakeProfit", "ActualLots", "ResearchLots", "OrderComment");
   }
   else
      FileSeek(handle, 0, SEEK_END);

   datetime eventBarTime = iTime(symbol_name, timeframe, 1);
   if(eventBarTime <= 0)
      eventBarTime = TimeCurrent();

   FileWrite(handle,
             eventId,
             ParseTaggedText(orderComment, "|e="),
             ticket,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
             GetStrategyNameByIndex(strategyIndex),
             symbol_name,
             TimeframeLabel(timeframe),
             signalStatus,
             signalDirection,
             DoubleToStr(signalScore, 1),
             TimeToStr(eventBarTime, TIME_DATE|TIME_MINUTES),
             DoubleToStr(requestedPrice, DigitsForSymbolName(symbol_name)),
             DoubleToStr(stopLoss, DigitsForSymbolName(symbol_name)),
             DoubleToStr(takeProfit, DigitsForSymbolName(symbol_name)),
             DoubleToStr(actualLots, 2),
             DoubleToStr(researchLots, 5),
             orderComment);

   FileClose(handle);
}

bool LoadTradeEventLinks(TradeEventLink &links[], int &linkCount)
{
   linkCount = 0;
   ArrayResize(links, 0);

   int handle = FileOpen("QuantGod_TradeEventLinks.csv", FILE_CSV | FILE_ANSI | FILE_READ, ',');
   if(handle == INVALID_HANDLE)
      return false;

   while(!FileIsEnding(handle))
   {
      string eventId = FileReadString(handle);
      if(FileIsEnding(handle) && eventId == "")
         break;

      string eventKey = FileReadString(handle);
      int ticket = (int)StrToInteger(FileReadString(handle));
      string timeLocal = FileReadString(handle);
      string timeServer = FileReadString(handle);
      string strategy = FileReadString(handle);
      string symbolName = FileReadString(handle);
      string timeframe = FileReadString(handle);
      string signalStatus = FileReadString(handle);
      string signalDirection = FileReadString(handle);
      double signalScore = StrToDouble(FileReadString(handle));
      string eventBarTime = FileReadString(handle);
      double requestedPrice = StrToDouble(FileReadString(handle));
      double stopLoss = StrToDouble(FileReadString(handle));
      double takeProfit = StrToDouble(FileReadString(handle));
      double actualLots = StrToDouble(FileReadString(handle));
      double researchLots = StrToDouble(FileReadString(handle));
      string orderComment = FileReadString(handle);

      if(eventId == "" || eventId == "EventId")
         continue;

      int nextIndex = linkCount;
      ArrayResize(links, nextIndex + 1);
      links[nextIndex].eventId = eventId;
      links[nextIndex].eventKey = eventKey;
      links[nextIndex].ticket = ticket;
      links[nextIndex].strategy = strategy;
      links[nextIndex].symbol = symbolName;
      links[nextIndex].timeframe = timeframe;
      links[nextIndex].signalStatus = signalStatus;
      links[nextIndex].signalDirection = signalDirection;
      links[nextIndex].signalScore = signalScore;
      links[nextIndex].eventTimeServer = StrToTime(timeServer);
      links[nextIndex].eventBarTime = StrToTime(eventBarTime);
      links[nextIndex].requestedPrice = requestedPrice;
      links[nextIndex].stopLoss = stopLoss;
      links[nextIndex].takeProfit = takeProfit;
      links[nextIndex].actualLots = actualLots;
      links[nextIndex].researchLots = researchLots;
      links[nextIndex].orderComment = orderComment;
      linkCount++;
   }

   FileClose(handle);
   return linkCount > 0;
}

int FindTradeEventLinkIndexByTicket(TradeEventLink &links[], int linkCount, int ticket)
{
   for(int i = 0; i < linkCount; i++)
   {
      if(links[i].ticket == ticket)
         return i;
   }
   return -1;
}

int FindTradeEventLinkIndexByEventKey(TradeEventLink &links[], int linkCount, string eventKey)
{
   if(eventKey == "")
      return -1;

   for(int i = 0; i < linkCount; i++)
   {
      if(links[i].eventKey == eventKey)
         return i;
   }
   return -1;
}

double GetInitialRiskPipsFromLink(TradeEventLink &link, int orderType, double openPrice, string symbol_name)
{
   if(orderType == OP_BUY && link.stopLoss > 0.0)
      return MathAbs(PriceToPips(openPrice - link.stopLoss, symbol_name));
   if(orderType == OP_SELL && link.stopLoss > 0.0)
      return MathAbs(PriceToPips(link.stopLoss - openPrice, symbol_name));
   return 0.0;
}

string GetTradeOutcomeFromPips(double realizedPips)
{
   if(realizedPips > 0.1)
      return "POSITIVE";
   if(realizedPips < -0.1)
      return "NEGATIVE";
   return "FLAT";
}

string DetectTradeCloseReason(int orderType, double closePrice, double stopLoss, double takeProfit,
                              int durationMinutes, int timeframe, string comment, string symbol_name)
{
   string upperComment = comment;
   StringToUpper(upperComment);
   if(StringFind(upperComment, "[TP]") >= 0)
      return "TAKE_PROFIT";
   if(StringFind(upperComment, "[SL]") >= 0)
      return "STOP_LOSS";

   double tolerancePrice = PipsToPrice(MathMax(0.3, GetSpreadPips(symbol_name) * 0.5), symbol_name);
   if(takeProfit > 0.0 && MathAbs(closePrice - takeProfit) <= tolerancePrice)
      return "TAKE_PROFIT";
   if(stopLoss > 0.0 && MathAbs(closePrice - stopLoss) <= tolerancePrice)
      return "STOP_LOSS";

   int maxHoldMinutes = GetResearchMaxHoldMinutes(timeframe);
   if(EnableResearchFastExit && maxHoldMinutes > 0 && durationMinutes >= maxHoldMinutes)
      return "TIME_EXIT_OR_FAST_EXIT";

   return "MANUAL_OR_OTHER";
}

void ExportTradeOutcomeLabels()
{
   TradeEventLink links[];
   int linkCount = 0;
   LoadTradeEventLinks(links, linkCount);

   int handle = FileOpen("QuantGod_TradeOutcomeLabels.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_TradeOutcomeLabels.csv, error=", GetLastError());
      return;
   }

   FileWrite(handle,
             "EventId", "LinkStatus", "Ticket", "Strategy", "Symbol", "Timeframe", "SignalDirection", "SignalScore",
             "EventTimeServer", "EventBarTime", "OpenTime", "CloseTime", "OrderType", "ActualLots", "ResearchLots",
             "EntryPrice", "ClosePrice", "EntrySL", "EntryTP", "InitialRiskPips", "RealizedPips",
             "ActualNet", "ResearchNet", "DurationMinutes", "Outcome", "CloseReason", "OrderComment");

   int historyTotal = OrdersHistoryTotal();
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      int linkIndex = FindTradeEventLinkIndexByTicket(links, linkCount, OrderTicket());
      if(linkIndex < 0)
      {
         string historyEventKey = ParseTaggedText(OrderComment(), "|e=");
         linkIndex = FindTradeEventLinkIndexByEventKey(links, linkCount, historyEventKey);
      }

      TradeEventLink link;
      bool linked = (linkIndex >= 0);
      if(linked)
         link = links[linkIndex];

      string strategyName = linked ? link.strategy : GetStrategyName(OrderMagicNumber());
      string timeframeLabel = linked ? link.timeframe : TimeframeLabel(GetStrategyTimeframeByMagic(OrderMagicNumber()));
      string signalDirection = linked
                               ? link.signalDirection
                               : ((OrderType() == OP_BUY) ? "BUY" : "SELL");
      double signalScore = linked ? link.signalScore : 0.0;
      double entryStopLoss = linked ? link.stopLoss : OrderStopLoss();
      double entryTakeProfit = linked ? link.takeProfit : OrderTakeProfit();
      double initialRiskPips = linked
                               ? GetInitialRiskPipsFromLink(link, OrderType(), OrderOpenPrice(), OrderSymbol())
                               : 0.0;
      double realizedPips = (OrderType() == OP_BUY)
                            ? PriceToPips(OrderClosePrice() - OrderOpenPrice(), OrderSymbol())
                            : PriceToPips(OrderOpenPrice() - OrderClosePrice(), OrderSymbol());
      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchLots = linked ? link.researchLots : GetResearchLotsFromComment(OrderComment(), OrderLots());
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      string closeReason = DetectTradeCloseReason(OrderType(), OrderClosePrice(), entryStopLoss, entryTakeProfit,
                                                  durationMinutes, GetStrategyTimeframeByMagic(OrderMagicNumber()),
                                                  OrderComment(), OrderSymbol());
      string outcome = GetTradeOutcomeFromPips(realizedPips);

      FileWrite(handle,
                linked ? link.eventId : "",
                linked ? "LINKED" : "UNLINKED",
                OrderTicket(),
                strategyName,
                OrderSymbol(),
                timeframeLabel,
                signalDirection,
                DoubleToStr(signalScore, 1),
                linked && link.eventTimeServer > 0 ? TimeToStr(link.eventTimeServer, TIME_DATE|TIME_MINUTES|TIME_SECONDS) : "",
                linked && link.eventBarTime > 0 ? TimeToStr(link.eventBarTime, TIME_DATE|TIME_MINUTES) : "",
                TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                (OrderType() == OP_BUY ? "BUY" : "SELL"),
                DoubleToStr(OrderLots(), 2),
                DoubleToStr(researchLots, 5),
                DoubleToStr(OrderOpenPrice(), DigitsForSymbolName(OrderSymbol())),
                DoubleToStr(OrderClosePrice(), DigitsForSymbolName(OrderSymbol())),
                DoubleToStr(entryStopLoss, DigitsForSymbolName(OrderSymbol())),
                DoubleToStr(entryTakeProfit, DigitsForSymbolName(OrderSymbol())),
                DoubleToStr(initialRiskPips, 1),
                DoubleToStr(realizedPips, 1),
                DoubleToStr(actualNet, 2),
                DoubleToStr(researchNet, 2),
                durationMinutes,
                outcome,
                closeReason,
                OrderComment());
   }

   FileClose(handle);
}

void SaveTradeLogState()
{
   int handle = FileOpen("QuantGod_LogState.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      return;

   FileWrite(handle, (int)gLastLoggedCloseTime, gLastLoggedCloseTicket);
   FileClose(handle);
}

void LogAccountSnapshot(string sourceTag)
{
   ResetLastError();
   int handle = FileOpen("QuantGod_EquitySnapshots.csv", FILE_CSV | FILE_ANSI | FILE_READ | FILE_WRITE, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen("QuantGod_EquitySnapshots.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_EquitySnapshots.csv, error=", GetLastError());
      return;
   }

   if(FileSize(handle) == 0)
      FileWrite(handle, "Time", "Source", "Status", "Mode", "DisplayBalance", "DisplayEquity", "DisplayProfit", "DisplayDrawdown", "BrokerBalance", "BrokerEquity", "BrokerProfit", "Margin", "FreeMargin", "Spread", "OpenPositions");
   else
      FileSeek(handle, 0, SEEK_END);

   FileWrite(handle,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_SECONDS),
             sourceTag,
             GetTradingStatus(),
             UseVirtualResearchAccount ? "VIRTUAL_RESEARCH" : "BROKER_ACCOUNT",
             DoubleToStr(GetDisplayedBalance(), 2),
             DoubleToStr(GetDisplayedEquity(), 2),
             DoubleToStr(GetDisplayedProfit(), 2),
             DoubleToStr(GetDisplayedDrawdownPercent(), 2),
             DoubleToStr(AccountBalance(), 2),
             DoubleToStr(AccountEquity(), 2),
             DoubleToStr(AccountProfit(), 2),
             DoubleToStr(AccountMargin(), 2),
             DoubleToStr(AccountFreeMargin(), 2),
             DoubleToStr(GetSpreadPips(gSymbol), 1),
             CountAllPositions());

   FileClose(handle);
}

void AuditClosedTrades()
{
   ResetLastError();
   int handle = FileOpen("QuantGod_TradeJournal.csv", FILE_CSV | FILE_ANSI | FILE_WRITE, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("[QuantGod] Failed to open QuantGod_TradeJournal.csv, error=", GetLastError());
      return;
   }

   FileWrite(handle, "CloseTime", "Ticket", "Strategy", "Type", "Symbol", "ActualLots", "ResearchLots", "OpenPrice", "ClosePrice", "SL", "TP", "ActualProfit", "Swap", "Commission", "ActualNet", "ResearchNet", "DurationMinutes", "Mode", "Comment");

   int historyTotal = OrdersHistoryTotal();
   if(historyTotal <= 0)
   {
      FileClose(handle);
      ExportTradeOutcomeLabels();
      return;
   }

   double runningDisplayBalance = UseVirtualResearchAccount ? VirtualStartingBalance : AccountBalance();
   if(!UseVirtualResearchAccount)
   {
      double totalClosedActual = 0.0;
      for(int seed = 0; seed < historyTotal; seed++)
      {
         if(!OrderSelect(seed, SELECT_BY_POS, MODE_HISTORY)) continue;
         if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
         totalClosedActual += (OrderProfit() + OrderSwap() + OrderCommission());
      }
      runningDisplayBalance = AccountBalance() - totalClosedActual;
   }

   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchLots = GetResearchLotsFromComment(OrderComment(), OrderLots());
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      double displayNet = UseVirtualResearchAccount ? researchNet : actualNet;
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      int orderDigits = DigitsForSymbolName(OrderSymbol());
      runningDisplayBalance += displayNet;

      FileWrite(handle,
                TimeToStr(OrderCloseTime(), TIME_DATE|TIME_SECONDS),
                OrderTicket(),
                GetStrategyName(OrderMagicNumber()),
                typeStr,
                OrderSymbol(),
                DoubleToStr(OrderLots(), 2),
                DoubleToStr(researchLots, 5),
                DoubleToStr(OrderOpenPrice(), orderDigits),
                DoubleToStr(OrderClosePrice(), orderDigits),
                DoubleToStr(OrderStopLoss(), orderDigits),
                DoubleToStr(OrderTakeProfit(), orderDigits),
                DoubleToStr(OrderProfit(), 2),
                DoubleToStr(OrderSwap(), 2),
                DoubleToStr(OrderCommission(), 2),
                DoubleToStr(actualNet, 2),
                DoubleToStr(researchNet, 2),
                durationMinutes,
                UseVirtualResearchAccount ? "VIRTUAL_RESEARCH" : "BROKER_ACCOUNT",
                OrderComment());
   }

   FileClose(handle);
   ExportTradeOutcomeLabels();
}

void ExportBalanceHistoryV2()
{
   string filename = "QuantGod_BalanceHistory.csv";
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   FileWriteString(handle, "RowType,Time,Status,Strategy,Ticket,Type,Symbol,ActualLots,ResearchLots,OpenPrice,ClosePrice,ActualNetProfit,ResearchNetProfit,Balance,Equity,BrokerBalance,BrokerEquity,DurationMinutes,Comment\n");

   int historyTotal = OrdersHistoryTotal();
   double totalClosedDisplayNet = 0;
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedMagic(OrderMagicNumber()) || !IsManagedSymbol(OrderSymbol())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      totalClosedDisplayNet += (UseVirtualResearchAccount ? researchNet : actualNet);
   }

   double runningBalance = UseVirtualResearchAccount ? VirtualStartingBalance : (AccountBalance() - totalClosedDisplayNet);

   for(int j = 0; j < historyTotal; j++)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedMagic(OrderMagicNumber()) || !IsManagedSymbol(OrderSymbol())) continue;
      if(UseVirtualResearchAccount && IgnoreLegacyTradesInVirtualStats && !HasResearchTag(OrderComment())) continue;

      double actualNet = OrderProfit() + OrderSwap() + OrderCommission();
      double researchNet = ScaleResearchNet(actualNet, OrderLots(), OrderComment());
      double displayNet = UseVirtualResearchAccount ? researchNet : actualNet;
      double researchLots = GetResearchLotsFromComment(OrderComment(), OrderLots());
      runningBalance += displayNet;
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      int orderDigits = DigitsForSymbolName(OrderSymbol());
      string commentText = OrderComment();
      StringReplace(commentText, ",", " ");
      StringReplace(commentText, "\r", " ");
      StringReplace(commentText, "\n", " ");

      FileWriteString(handle,
                      "CLOSED_TRADE," +
                      TimeToStr(OrderCloseTime(), TIME_DATE|TIME_SECONDS) + "," +
                      "CLOSED," +
                      GetStrategyName(OrderMagicNumber()) + "," +
                      IntegerToString(OrderTicket()) + "," +
                      typeStr + "," +
                      OrderSymbol() + "," +
                      DoubleToStr(OrderLots(), 2) + "," +
                      DoubleToStr(researchLots, 5) + "," +
                      DoubleToStr(OrderOpenPrice(), orderDigits) + "," +
                      DoubleToStr(OrderClosePrice(), orderDigits) + "," +
                      DoubleToStr(actualNet, 2) + "," +
                      DoubleToStr(researchNet, 2) + "," +
                      DoubleToStr(runningBalance, 2) + "," +
                      DoubleToStr(runningBalance, 2) + "," +
                      DoubleToStr(AccountBalance(), 2) + "," +
                      DoubleToStr(AccountEquity(), 2) + "," +
                      IntegerToString(durationMinutes) + "," +
                      commentText + "\n");
   }

   FileWriteString(handle,
                   "ACCOUNT_SNAPSHOT," +
                   TimeToStr(TimeLocal(), TIME_DATE|TIME_SECONDS) + "," +
                   GetTradingStatus() + "," +
                   "Current,0,N/A," + gDashboardSymbol + ",0,0,0,0," +
                   DoubleToStr(AccountProfit(), 2) + "," +
                   DoubleToStr(GetDisplayedProfit(), 2) + "," +
                   DoubleToStr(GetDisplayedBalance(), 2) + "," +
                   DoubleToStr(GetDisplayedEquity(), 2) + "," +
                   DoubleToStr(AccountBalance(), 2) + "," +
                   DoubleToStr(AccountEquity(), 2) + ",0,Runtime\n");

   FileClose(handle);
}

void ExportTradeJournal()
{
   int handle = FileOpen("QuantGod_TradeJournal.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   FileWriteString(handle, "CloseTime,Ticket,Strategy,Type,Symbol,Lots,OpenPrice,ClosePrice,SL,TP,Profit,Swap,Commission,Net,DurationMinutes,Comment\n");

   int historyTotal = OrdersHistoryTotal();
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;

      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      string commentText = OrderComment();
      StringReplace(commentText, ",", " ");
      StringReplace(commentText, "\r", " ");
      StringReplace(commentText, "\n", " ");

      FileWriteString(handle,
                      TimeToStr(OrderCloseTime(), TIME_DATE|TIME_SECONDS) + "," +
                      IntegerToString(OrderTicket()) + "," +
                      GetStrategyName(OrderMagicNumber()) + "," +
                      typeStr + "," +
                      OrderSymbol() + "," +
                      DoubleToStr(OrderLots(), 2) + "," +
                      DoubleToStr(OrderOpenPrice(), orderDigits) + "," +
                      DoubleToStr(OrderClosePrice(), orderDigits) + "," +
                      DoubleToStr(OrderStopLoss(), orderDigits) + "," +
                      DoubleToStr(OrderTakeProfit(), orderDigits) + "," +
                      DoubleToStr(OrderProfit(), 2) + "," +
                      DoubleToStr(OrderSwap(), 2) + "," +
                      DoubleToStr(OrderCommission(), 2) + "," +
                      DoubleToStr(netProfit, 2) + "," +
                      IntegerToString(durationMinutes) + "," +
                      commentText + "\n");
   }

   FileClose(handle);
}

//+------------------------------------------------------------------+
//| 闔ｷ蜿也ｭ也払蜷咲ｧｰ                                                       |
//+------------------------------------------------------------------+
string GetStrategyName(int magic)
{
   return GetStrategyNameByIndex(GetStrategyIndexByMagic(magic));
}
//+------------------------------------------------------------------+
