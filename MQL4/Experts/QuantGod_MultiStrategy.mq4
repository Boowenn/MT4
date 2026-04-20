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

//=== 全局设置 ===
input string   _g0 = "====== 全局设置 ======";
input double   RiskPercent        = 0.10;    // 单笔风险 (%)
input double   MaxDrawdownPercent = 8.0;     // 最大回撤保护 (%)
input int      MaxTotalTrades     = 2;       // 最大并发持仓数
input bool     UseTradeSession    = false;   // 关闭时段过滤，避免时区干扰
input double   TrailingStopPips   = 0.0;     // 研究模式先关闭追踪止损
input bool     EnableDashboard    = true;    // 导出 dashboard 数据
input string   TradingSymbols     = "EURUSD,USDJPY"; // 研究模式先聚焦双品种
input bool     AutoSelectSymbols  = true;    // 自动加入 Market Watch
input bool     PauseNewEntries    = false;   // 暂停开新仓，只管理已有仓位
input bool     FlattenManagedPositions = false; // 紧急清空当前策略组合仓位

//=== 策略1: MA交叉 ===
input string   _s1 = "====== 策略1: MA交叉 ======";
input bool     Enable_MA          = true;    // 启用 MA 交叉策略
input int      MA_FastPeriod      = 9;       // 快线周期
input int      MA_SlowPeriod      = 21;      // 慢线周期
input int      MA_TrendPeriod     = 100;     // 趋势过滤 SMA
input ENUM_TIMEFRAMES MA_Timeframe = PERIOD_H1; // 研究模式：H1
input int      MA_Magic           = 10001;   // Magic Number

//=== 策略2: RSI 均值回归 ===
input string   _s2 = "====== 策略2: RSI 均值回归 ======";
input bool     Enable_RSI         = false;   // 研究模式先关闭
input int      RSI_Period         = 2;       // RSI 周期
input int      RSI_OB             = 80;      // 超买阈值
input int      RSI_OS             = 20;      // 超卖阈值
input ENUM_TIMEFRAMES RSI_Timeframe = PERIOD_H1; // 更活跃：H1
input int      RSI_Magic          = 10002;   // Magic Number

//=== 策略3: BB + RSI + MACD 三重确认 ===
input string   _s3 = "====== 策略3: BB+RSI+MACD 三重确认 ======";
input bool     Enable_BB          = false;   // 研究模式先关闭
input int      BB_Period          = 20;      // 布林周期
input double   BB_Deviation       = 2.0;     // 布林标准差
input int      BB_RSI_Period      = 14;      // RSI 周期
input int      BB_RSI_OB          = 65;      // RSI 超买
input int      BB_RSI_OS          = 35;      // RSI 超卖
input ENUM_TIMEFRAMES BB_Timeframe = PERIOD_H1; // 更活跃：H1
input int      BB_Magic           = 10003;   // Magic Number

//=== 策略4: MACD 背离 ===
input string   _s4 = "====== 策略4: MACD 背离 ======";
input bool     Enable_MACD        = false;   // 研究模式先关闭
input int      MACD_Fast          = 12;      // 快线
input int      MACD_Slow          = 26;      // 慢线
input int      MACD_Signal        = 9;       // 信号线
input int      MACD_LookBack      = 24;      // 背离回溯周期
input ENUM_TIMEFRAMES MACD_Timeframe = PERIOD_H1; // 更活跃：H1
input int      MACD_Magic         = 10004;   // Magic Number

//=== 策略5: 支撑阻力突破 ===
input string   _s5 = "====== 策略5: 支撑阻力突破 ======";
input bool     Enable_SR          = false;   // 研究模式先关闭
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
datetime gLastTickTime;
datetime gLastSnapshotLog;
datetime gLastLoggedCloseTime;
int      gLastLoggedCloseTicket;
int      gCurrentDiagSymbolIndex;
int      gLastOrderSendError;

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
   gCurrentDiagSymbolIndex = -1;
   LoadManagedSymbols();
   PrepareSymbolContext(gDashboardSymbol);
   gLastTickTime = (datetime)MarketInfo(gDashboardSymbol, MODE_TIME);
   gLastSnapshotLog = 0;
   gLastLoggedCloseTime = 0;
   gLastLoggedCloseTicket = 0;

   // 蝗ｾ陦ｨ譏ｾ遉ｺ隶ｾ鄂ｮ
   ChartSetInteger(0, CHART_SHOW_GRID, false);
   Comment("");
   EventSetTimer(5);
   EnsureAutoTradingEnabled();
   RefreshAllManagedDiagnostics();

   Print("[QuantGod] Multi-Strategy Engine v2.0 initialized");
   Print("辟ｦ轤ｹ蜩∫ｧ・ ", gDashboardSymbol, " | 逶第而蛻苓｡ｨ: ", GetManagedSymbolsLabel(),
         " | 鬟朱勦: ", RiskPercent, "% | 譛螟ｧ蝗樊彫: ", MaxDrawdownPercent, "%");

   LoadTradeLogState();
   LogAccountSnapshot("INIT");
   gLastSnapshotLog = TimeLocal();
   AuditClosedTrades();
   UpdateChartDisplayV2();
   if(EnableDashboard) ExportDashboardData();

   return INIT_SUCCEEDED;
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

   if(Enable_MA)   Strategy_MA_Cross();
   if(Enable_RSI)  Strategy_RSI_Reversal_V2();
   if(Enable_BB)   Strategy_BB_Triple();
   if(Enable_MACD) Strategy_MACD_Divergence_V2();
   if(Enable_SR)   Strategy_SR_Breakout_V2();

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

   if(!CheckMaxDrawdown(MaxDrawdownPercent))
   { if(logGuard){lastGuardLog=TimeCurrent(); Print("[QG-BLOCK] MaxDrawdown exceeded");} return; }
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
      SetStrategyDiagnostic(1, "IN_POSITION", "Existing RSI_Reversal position is still open", 100);
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      SetStrategyDiagnostic(1, "PORTFOLIO_LIMIT", "Max concurrent trades reached", 100);
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
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_BUY", RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
      if(ticket > 0)
         SetStrategyDiagnostic(1, "BUY_ORDER_SENT", "RSI_Reversal buy order sent on " + TimeframeLabel(RSI_Timeframe), 100);
      else
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", "RSI buy setup failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   if(sellReversal && sellBand)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_SELL", RSI_Magic, 0, clrOrange);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
      if(ticket > 0)
         SetStrategyDiagnostic(1, "SELL_ORDER_SENT", "RSI_Reversal sell order sent on " + TimeframeLabel(RSI_Timeframe), 100);
      else
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", "RSI sell setup failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   if(buyScore >= sellScore)
      SetStrategyDiagnostic(1, "NO_SETUP",
                            "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | reversal=" + BoolLabel(buyReversal) +
                            " band=" + BoolLabel(buyBand), buyScore);
   else
      SetStrategyDiagnostic(1, "NO_SETUP",
                            "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | reversal=" + BoolLabel(sellReversal) +
                            " band=" + BoolLabel(sellBand), sellScore);
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
      SetStrategyDiagnostic(3, "IN_POSITION", "Existing MACD_Divergence position is still open", 100);
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      SetStrategyDiagnostic(3, "PORTFOLIO_LIMIT", "Max concurrent trades reached", 100);
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
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            "QG_MACD_Div_BUY", MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 蠎戊レ遖ｻ荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
      if(ticket > 0)
         SetStrategyDiagnostic(3, "BUY_ORDER_SENT", "Bullish MACD divergence triggered a buy", 100);
      else
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", "Bullish MACD divergence failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            "QG_MACD_Div_SELL", MACD_Magic, 0, clrCrimson);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 鬘ｶ閭檎ｦｻ蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
      if(ticket > 0)
         SetStrategyDiagnostic(3, "SELL_ORDER_SENT", "Bearish MACD divergence triggered a sell", 100);
      else
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", "Bearish MACD divergence failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   SetStrategyDiagnostic(3, "NO_SETUP",
                         "No MACD divergence found in the last " + IntegerToString(MACD_LookBack) + " bars", 0);
}

void Strategy_SR_Breakout_V2()
{
   if(HasOpenPosition(SR_Magic, gSymbol))
   {
      SetStrategyDiagnostic(4, "IN_POSITION", "Existing SR_Breakout position is still open", 100);
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      SetStrategyDiagnostic(4, "PORTFOLIO_LIMIT", "Max concurrent trades reached", 100);
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
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            "QG_SR_Break_BUY", SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR遯∫ｴ] 遯∫ｴ髦ｻ蜉帑ｹｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol, " R=", resistance);
      if(ticket > 0)
         SetStrategyDiagnostic(4, "BUY_ORDER_SENT", "SR_Breakout resistance breakout buy", 100);
      else
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", "SR breakout buy failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   if(sellPrevAbove && sellBreak)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            "QG_SR_Break_SELL", SR_Magic, 0, clrTomato);
      if(ticket > 0) Print("[SR遯∫ｴ] 霍檎ｴ謾ｯ謦大獄蜃ｺ ", lots, " 謇・@ ", bid, " | ", gSymbol, " S=", support);
      if(ticket > 0)
         SetStrategyDiagnostic(4, "SELL_ORDER_SENT", "SR_Breakout support breakdown sell", 100);
      else
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", "SR breakout sell failed, error=" + IntegerToString(gLastOrderSendError), 100);
      return;
   }

   if(buyScore >= sellScore)
      SetStrategyDiagnostic(4, "NO_SETUP",
                            "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | prevBelow=" + BoolLabel(buyPrevBelow) +
                            " break=" + BoolLabel(buyBreak) + " volume=" + BoolLabel(volumeConfirm), buyScore);
   else
      SetStrategyDiagnostic(4, "NO_SETUP",
                            "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | prevAbove=" + BoolLabel(sellPrevAbove) +
                            " break=" + BoolLabel(sellBreak) + " volume=" + BoolLabel(volumeConfirm), sellScore);
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
   RefreshAllManagedDiagnostics();
   ProcessManagedTrading();
   PrepareSymbolContext(gDashboardSymbol);
   AuditClosedTrades();
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

   if(CountAllPositions() >= MaxTotalTrades)
   {
      string capReason = "Max concurrent trades reached";
      if(Enable_MA)   SetStrategyDiagnostic(0, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_RSI)  SetStrategyDiagnostic(1, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_BB)   SetStrategyDiagnostic(2, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_MACD) SetStrategyDiagnostic(3, "PORTFOLIO_LIMIT", capReason, 100);
      if(Enable_SR)   SetStrategyDiagnostic(4, "PORTFOLIO_LIMIT", capReason, 100);
   }
}

//+------------------------------------------------------------------+
//| 遲也払1: MA驥大初豁ｻ蜿・                                                 |
//+------------------------------------------------------------------+
void Strategy_MA_Cross()
{
   if(HasOpenPosition(MA_Magic, gSymbol))
   {
      SetStrategyDiagnostic(0, "IN_POSITION", "Existing MA_Cross position is still open", 100);
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      SetStrategyDiagnostic(0, "PORTFOLIO_LIMIT", "Max concurrent trades reached", 100);
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
   double trendMA  = iMA(gSymbol, MA_Timeframe, MA_TrendPeriod, 0, MODE_SMA, PRICE_CLOSE, 1);

   double rsi14 = iRSI(gSymbol, MA_Timeframe, 14, PRICE_CLOSE, 1);
   double atrSL = GetATRStopLoss(gSymbol, MA_Timeframe, 14, 2.0);
   double close1 = iClose(gSymbol, MA_Timeframe, 1);

   // Widen crossover detection: check last 3 bars for a cross
   bool buyCross = false;
   bool sellCross = false;
   for(int c = 1; c <= 3; c++)
   {
      double fPrev = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, c+1);
      double sPrev = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, c+1);
      double fCurr = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, c);
      double sCurr = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, c);
      if(fPrev <= sPrev && fCurr > sCurr) buyCross = true;
      if(fPrev >= sPrev && fCurr < sCurr) sellCross = true;
   }

   bool buyTrend = (close1 > trendMA);
   bool sellTrend = (close1 < trendMA);

   Print("[MA_Cross] ", gSymbol, " | fast=", DoubleToStr(fastMA_1,5), " slow=", DoubleToStr(slowMA_1,5),
         " trend=", DoubleToStr(trendMA,5), " close=", DoubleToStr(close1,5),
         " RSI=", DoubleToStr(rsi14,1),
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

   // Buy: cross detected in last 3 bars + trend confirmed
   if(buyCross && buyTrend)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      buyTicket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            "QG_MA_Cross_BUY", MA_Magic, 0, clrLime);
      ticket = buyTicket;
      if(ticket > 0) Print("[MA莠､蜿云 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol);
   }

   // Sell: cross detected in last 3 bars + trend confirmed
   if(sellCross && sellTrend)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      sellTicket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            "QG_MA_Cross_SELL", MA_Magic, 0, clrRed);
      ticket = sellTicket;
      if(ticket > 0) Print("[MA莠､蜿云 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol);
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
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_BUY", RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI蝗槫ｽ綻 荵ｰ蜈･ ", lots, " 謇・@ ", Ask);
   }

   // 雜・ｹｰ蝗櫁誠蜊門・: RSI莉手ｶ・ｹｰ蝗櫁誠 + 莉ｷ譬ｼ蝨ｨ荳願ｽｨ髯・ｿ・   if(rsi_2 > RSI_OB && rsi_1 < RSI_OB && close1 >= bbUpper * 0.999)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_SELL", RSI_Magic, 0, clrOrange);
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
      SetStrategyDiagnostic(2, "IN_POSITION", "Existing BB_Triple position is still open", 100);
      return;
   }
   if(CountAllPositions() >= MaxTotalTrades)
   {
      SetStrategyDiagnostic(2, "PORTFOLIO_LIMIT", "Max concurrent trades reached", 100);
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
      double tp = MathMax(tp_dist, sl * 1.5);
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(ask + PipsToPrice(tp, gSymbol), gDigits);

       ResetLastError();
       int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, ask, 3, slPrice, tpPrice,
                            "QG_BB_Triple_BUY", BB_Magic, 0, clrGold);
       if(ticket > 0) Print("[BB荳蛾㍾] 荵ｰ蜈･ ", lots, " 謇・@ ", ask, " | ", gSymbol, " TP->荳願ｽｨ");
       if(ticket > 0)
          SetStrategyDiagnostic(2, "BUY_ORDER_SENT", "BB_Triple buy order sent on " + TimeframeLabel(BB_Timeframe), 100);
       else
         SetStrategyDiagnostic(2, "ORDER_SEND_FAILED", "BB triple buy failed, error=" + IntegerToString(gLastOrderSendError), 100);
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
      double tp = MathMax(tp_dist, sl * 1.5);
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(bid - PipsToPrice(tp, gSymbol), gDigits);

       ResetLastError();
       int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, bid, 3, slPrice, tpPrice,
                            "QG_BB_Triple_SELL", BB_Magic, 0, clrMagenta);
       if(ticket > 0) Print("[BB荳蛾㍾] 蜊門・ ", lots, " 謇・@ ", bid, " | ", gSymbol, " TP->荳玖ｽｨ");
       if(ticket > 0)
          SetStrategyDiagnostic(2, "SELL_ORDER_SENT", "BB_Triple sell order sent on " + TimeframeLabel(BB_Timeframe), 100);
       else
         SetStrategyDiagnostic(2, "ORDER_SEND_FAILED", "BB triple sell failed, error=" + IntegerToString(gLastOrderSendError), 100);
       return;
    }

   double buyScore = (double)((bbBuySignal ? 1 : 0) + (rsiBuySignal ? 1 : 0) + (macdBuyConfirm ? 1 : 0)) / 3.0 * 100.0;
   double sellScore = (double)((bbSellSignal ? 1 : 0) + (rsiSellSignal ? 1 : 0) + (macdSellConfirm ? 1 : 0)) / 3.0 * 100.0;
   if(buyScore >= sellScore)
      SetStrategyDiagnostic(2, "NO_SETUP",
                            "BUY bias " + DoubleToStr(buyScore, 0) + "/100 | band=" + BoolLabel(bbBuySignal) +
                            " rsi=" + BoolLabel(rsiBuySignal) + " macd=" + BoolLabel(macdBuyConfirm), buyScore);
   else
      SetStrategyDiagnostic(2, "NO_SETUP",
                            "SELL bias " + DoubleToStr(sellScore, 0) + "/100 | band=" + BoolLabel(bbSellSignal) +
                            " rsi=" + BoolLabel(rsiSellSignal) + " macd=" + BoolLabel(macdSellConfirm), sellScore);
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
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_MACD_Div_BUY", MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD閭檎ｦｻ] 蠎戊レ遖ｻ荵ｰ蜈･ ", lots, " 謇・@ ", Ask);
   }

   // 鬘ｶ閭檎ｦｻ蜊門・
   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_MACD_Div_SELL", MACD_Magic, 0, clrCrimson);
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
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_SR_Break_BUY", SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR遯∫ｴ] 遯∫ｴ髦ｻ蜉帑ｹｰ蜈･ ", lots, " 謇・@ ", Ask, " R=", resistance);
   }

   // 霍檎ｴ謾ｯ謦大獄蜃ｺ
   if(close2 > support && close1 < support - breakPrice && volumeConfirm)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = SafeOrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_SR_Break_SELL", SR_Magic, 0, clrTomato);
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
   double balance = AccountBalance();
   double equity = AccountEquity();
   double profit = AccountProfit();
   double dd = 0;
   int tickAge = GetTickAgeSeconds();
   string tradingStatus = GetTradingStatus();
   string terminalTrading = IsTerminalTradeEnabled() ? "ON" : "OFF";
   string programTrading = IsProgramTradeEnabled() ? "ON" : "OFF";
   string dllTrading = IsDllImportEnabled() ? "ON" : "OFF";

   if(balance > 0)
      dd = (balance - equity) / balance * 100.0;

   string info = "";
   info += "QuantGod Multi-Strategy v2.3\n";
   info += "Focus: " + gDashboardSymbol + "  Chart: " + gChartSymbol + "\n";
   info += "Watchlist: " + GetManagedSymbolsLabel() + "\n";
   info += "Balance: $" + DoubleToStr(balance, 2) + "\n";
   info += "Equity:  $" + DoubleToStr(equity, 2) + "\n";
   info += "Profit:  $" + DoubleToStr(profit, 2) + "\n";
   info += "Drawdown: " + DoubleToStr(dd, 2) + "%\n";
   info += "Terminal AutoTrading: " + terminalTrading + "\n";
   info += "EA Live Trading: " + programTrading + "  DLL: " + dllTrading + "\n";
   info += "Status: " + tradingStatus + "\n";
   if(tickAge >= 0)
      info += "Last Tick Age: " + IntegerToString(tickAge) + " sec\n";
   else
      info += "Last Tick Age: N/A\n";
   info += "Open Positions: " + IntegerToString(CountAllPositions()) + "/" + IntegerToString(MaxTotalTrades) + "\n";
   info += "Spread: " + DoubleToStr(GetSpreadPips(gSymbol), 1) + " pips\n";
   info += "MA: " + (Enable_MA ? "ON" : "OFF") + " (" + IntegerToString(CountPositionsAllSymbols(MA_Magic)) + ")\n";
   info += "RSI: " + (Enable_RSI ? "ON" : "OFF") + " (" + IntegerToString(CountPositionsAllSymbols(RSI_Magic)) + ")\n";
   info += "BB: " + (Enable_BB ? "ON" : "OFF") + " (" + IntegerToString(CountPositionsAllSymbols(BB_Magic)) + ")\n";
   info += "MACD: " + (Enable_MACD ? "ON" : "OFF") + " (" + IntegerToString(CountPositionsAllSymbols(MACD_Magic)) + ")\n";
   info += "SR: " + (Enable_SR ? "ON" : "OFF") + " (" + IntegerToString(CountPositionsAllSymbols(SR_Magic)) + ")";

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

//+------------------------------------------------------------------+
//| 蟇ｼ蜃ｺ謨ｰ謐ｮ蛻ｰWeb髱｢譚ｿ                                                   |
//+------------------------------------------------------------------+
void ExportDashboardData()
{
   PrepareSymbolContext(gDashboardSymbol);
   string filename = "QuantGod_Dashboard.json";
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   double balance = AccountBalance();
   double equity = AccountEquity();
   double profit = AccountProfit();
   double margin = AccountMargin();
   double freeMargin = AccountFreeMargin();
   double dd = 0;
   if(balance > 0) dd = (balance - equity) / balance * 100.0;

   // JSON螟ｴ
   FileWriteString(handle, "{\n");
   FileWriteString(handle, "  \"timestamp\": \"" + TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "  \"build\": \"QuantGod-v2.5-symbol-diag\",\n");
   FileWriteString(handle, "  \"runtime\": {\n");
   FileWriteString(handle, "    \"tradeStatus\": \"" + GetTradingStatus() + "\",\n");
    FileWriteString(handle, "    \"connected\": " + (IsConnected() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"terminalTradeAllowed\": " + (IsTerminalTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"programTradeAllowed\": " + (IsProgramTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"dllAllowed\": " + (IsDllImportEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tradeAllowed\": " + (IsTradeAllowed() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tickAgeSeconds\": " + IntegerToString(GetTickAgeSeconds()) + ",\n");
   FileWriteString(handle, "    \"serverTime\": \"" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "    \"gmtTime\": \"" + TimeToStr(TimeGMT(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "    \"localTime\": \"" + TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\"\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"account\": {\n");
   FileWriteString(handle, "    \"number\": " + IntegerToString(AccountNumber()) + ",\n");
   FileWriteString(handle, "    \"name\": \"" + AccountName() + "\",\n");
   FileWriteString(handle, "    \"server\": \"" + AccountServer() + "\",\n");
   FileWriteString(handle, "    \"currency\": \"" + AccountCurrency() + "\",\n");
   FileWriteString(handle, "    \"balance\": " + DoubleToStr(balance, 2) + ",\n");
   FileWriteString(handle, "    \"equity\": " + DoubleToStr(equity, 2) + ",\n");
   FileWriteString(handle, "    \"profit\": " + DoubleToStr(profit, 2) + ",\n");
   FileWriteString(handle, "    \"margin\": " + DoubleToStr(margin, 2) + ",\n");
   FileWriteString(handle, "    \"freeMargin\": " + DoubleToStr(freeMargin, 2) + ",\n");
   FileWriteString(handle, "    \"drawdown\": " + DoubleToStr(dd, 2) + ",\n");
   FileWriteString(handle, "    \"leverage\": " + IntegerToString(AccountLeverage()) + "\n");
   FileWriteString(handle, "  },\n");
   FileWriteString(handle, "  \"watchlist\": \"" + GetManagedSymbolsLabel() + "\",\n");
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
      double symbolFloatingProfit = 0.0;
      int symbolClosedTrades = 0;
      int symbolWinTrades = 0;
      double symbolClosedProfit = 0.0;
      datetime symbolLastCloseTime = 0;

      for(int openIndex = 0; openIndex < OrdersTotal(); openIndex++)
      {
         if(!OrderSelect(openIndex, SELECT_BY_POS, MODE_TRADES)) continue;
         if(OrderSymbol() != symbolName) continue;
         if(!IsManagedMagic(OrderMagicNumber())) continue;

         symbolOpenPositions++;
         symbolFloatingProfit += (OrderProfit() + OrderSwap() + OrderCommission());
      }

      for(int historyIndex = OrdersHistoryTotal() - 1; historyIndex >= 0; historyIndex--)
      {
         if(!OrderSelect(historyIndex, SELECT_BY_POS, MODE_HISTORY)) continue;
         if(OrderSymbol() != symbolName) continue;
         if(!IsManagedMagic(OrderMagicNumber())) continue;

         double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
         datetime closeTime = OrderCloseTime();

         symbolClosedTrades++;
         symbolClosedProfit += netProfit;
         if(netProfit > 0)
            symbolWinTrades++;
         if(closeTime > symbolLastCloseTime)
            symbolLastCloseTime = closeTime;
      }

      double symbolWinRate = (symbolClosedTrades > 0)
                           ? ((double)symbolWinTrades * 100.0 / symbolClosedTrades)
                           : 0.0;

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
      FileWriteString(handle, "      \"closedTrades\": " + IntegerToString(symbolClosedTrades) + ",\n");
      FileWriteString(handle, "      \"winRate\": " + DoubleToStr(symbolWinRate, 1) + ",\n");
      FileWriteString(handle, "      \"closedProfit\": " + DoubleToStr(symbolClosedProfit, 2) + ",\n");
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

      if(!firstTrade) FileWriteString(handle, ",\n");
      firstTrade = false;

      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"symbol\": \"" + OrderSymbol() + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"sl\": " + DoubleToStr(OrderStopLoss(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"tp\": " + DoubleToStr(OrderTakeProfit(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(OrderProfit(), 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + OrderComment() + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   FileWriteString(handle, "  \"closedTrades\": [\n");
   bool firstClosed = true;
   int historyTotal = OrdersHistoryTotal();
   int maxHistory = historyTotal;

   for(int i = historyTotal - 1; i >= historyTotal - maxHistory && i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;

      if(!firstClosed) FileWriteString(handle, ",\n");
      firstClosed = false;

      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"symbol\": \"" + OrderSymbol() + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"closePrice\": " + DoubleToStr(OrderClosePrice(), orderDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(OrderProfit(), 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"closeTime\": \"" + TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + OrderComment() + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   FileWriteString(handle, "  \"strategies\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"enabled\": " + (Enable_MA ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(MA_Magic)) + "},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"enabled\": " + (Enable_RSI ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(RSI_Magic)) + "},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"enabled\": " + (Enable_BB ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(BB_Magic)) + "},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"enabled\": " + (Enable_MACD ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(MACD_Magic)) + "},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"enabled\": " + (Enable_SR ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositionsAllSymbols(SR_Magic)) + "}\n");
   FileWriteString(handle, "  },\n");

   FileWriteString(handle, "  \"diagnostics\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[0]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[0], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[0]) + "\"},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[1]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[1], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[1]) + "\"},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[2]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[2], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[2]) + "\"},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[3]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[3], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[3]) + "\"},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[4]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[4], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[4]) + "\"}\n");
   FileWriteString(handle, "  },\n");

   // 蟶ょ惻菫｡諱ｯ
   FileWriteString(handle, "  \"market\": {\n");
   FileWriteString(handle, "    \"symbol\": \"" + gSymbol + "\",\n");
   FileWriteString(handle, "    \"bid\": " + DoubleToStr(MarketInfo(gSymbol, MODE_BID), gDigits) + ",\n");
   FileWriteString(handle, "    \"ask\": " + DoubleToStr(MarketInfo(gSymbol, MODE_ASK), gDigits) + ",\n");
   FileWriteString(handle, "    \"spread\": " + DoubleToStr(GetSpreadPips(gSymbol), 1) + "\n");
   FileWriteString(handle, "  }\n");

   FileWriteString(handle, "}\n");
   FileClose(handle);

   // 蜷梧慮蟇ｼ蜃ｺ菴咎｢晏紙蜿ｲCSV
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
      FileWrite(handle, "Time", "Source", "Status", "Balance", "Equity", "Profit", "Margin", "FreeMargin", "Spread", "OpenPositions");
   else
      FileSeek(handle, 0, SEEK_END);

   FileWrite(handle,
             TimeToStr(TimeLocal(), TIME_DATE|TIME_SECONDS),
             sourceTag,
             GetTradingStatus(),
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

   FileWrite(handle, "CloseTime", "Ticket", "Strategy", "Type", "Symbol", "Lots", "OpenPrice", "ClosePrice", "SL", "TP", "Profit", "Swap", "Commission", "Net", "DurationMinutes", "Balance", "Equity", "Comment");

   int historyTotal = OrdersHistoryTotal();
   if(historyTotal <= 0)
   {
      FileClose(handle);
      return;
   }

   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedSymbol(OrderSymbol()) || !IsManagedMagic(OrderMagicNumber())) continue;

      datetime closeTime = OrderCloseTime();
      int ticket = OrderTicket();
      if(closeTime <= 0) continue;
      if(closeTime < gLastLoggedCloseTime) continue;
      if(closeTime == gLastLoggedCloseTime && ticket <= gLastLoggedCloseTicket) continue;

      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      int orderDigits = DigitsForSymbolName(OrderSymbol());

      FileWrite(handle,
                TimeToStr(closeTime, TIME_DATE|TIME_SECONDS),
                ticket,
                GetStrategyName(OrderMagicNumber()),
                typeStr,
                OrderSymbol(),
                DoubleToStr(OrderLots(), 2),
                DoubleToStr(OrderOpenPrice(), orderDigits),
                DoubleToStr(OrderClosePrice(), orderDigits),
                DoubleToStr(OrderStopLoss(), orderDigits),
                DoubleToStr(OrderTakeProfit(), orderDigits),
                DoubleToStr(OrderProfit(), 2),
                DoubleToStr(OrderSwap(), 2),
                DoubleToStr(OrderCommission(), 2),
                DoubleToStr(netProfit, 2),
                durationMinutes,
                DoubleToStr(AccountBalance(), 2),
                DoubleToStr(AccountEquity(), 2),
                OrderComment());
   }

   FileClose(handle);
}

void ExportBalanceHistoryV2()
{
   string filename = "QuantGod_BalanceHistory.csv";
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;

   FileWriteString(handle, "RowType,Time,Status,Strategy,Ticket,Type,Symbol,Lots,OpenPrice,ClosePrice,GrossProfit,NetProfit,Swap,Commission,Balance,Equity,DurationMinutes,Comment\n");

   int historyTotal = OrdersHistoryTotal();
   double totalClosedNet = 0;
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      totalClosedNet += OrderProfit() + OrderSwap() + OrderCommission();
   }

   double runningBalance = AccountBalance() - totalClosedNet;

   for(int j = 0; j < historyTotal; j++)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(!IsManagedMagic(OrderMagicNumber()) || !IsManagedSymbol(OrderSymbol())) continue;

      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      runningBalance += netProfit;
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
                      DoubleToStr(OrderOpenPrice(), orderDigits) + "," +
                      DoubleToStr(OrderClosePrice(), orderDigits) + "," +
                      DoubleToStr(OrderProfit(), 2) + "," +
                      DoubleToStr(netProfit, 2) + "," +
                      DoubleToStr(OrderSwap(), 2) + "," +
                      DoubleToStr(OrderCommission(), 2) + "," +
                      DoubleToStr(runningBalance, 2) + "," +
                      DoubleToStr(runningBalance, 2) + "," +
                      IntegerToString(durationMinutes) + "," +
                      commentText + "\n");
   }

   FileWriteString(handle,
                   "ACCOUNT_SNAPSHOT," +
                   TimeToStr(TimeLocal(), TIME_DATE|TIME_SECONDS) + "," +
                   GetTradingStatus() + "," +
                   "Current,0,N/A," + gDashboardSymbol + ",0,0,0," +
                   DoubleToStr(AccountProfit(), 2) + "," +
                   DoubleToStr(AccountProfit(), 2) + ",0,0," +
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
   if(magic == MA_Magic)   return "MA_Cross";
   if(magic == RSI_Magic)  return "RSI_Reversal";
   if(magic == BB_Magic)   return "BB_Triple";
   if(magic == MACD_Magic) return "MACD_Divergence";
   if(magic == SR_Magic)   return "SR_Breakout";
   return "Unknown";
}
//+------------------------------------------------------------------+
