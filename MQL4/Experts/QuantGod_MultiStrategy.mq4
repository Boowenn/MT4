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
input string   _g0 = "══════ 全局设置 ══════";
input double   RiskPercent        = 1.5;     // 每笔风险 (%)
input double   MaxDrawdownPercent = 15.0;    // 最大回撤限制 (%)
input int      MaxTotalTrades     = 6;       // 最大同时持仓数
input bool     UseTradeSession    = true;    // 仅在活跃时段交易
input double   TrailingStopPips   = 25.0;    // 追踪止损 (pips, 0=关闭)
input bool     EnableDashboard    = true;    // 启用数据导出到面板

//=== 策略1: MA交叉 ===
input string   _s1 = "══════ 策略1: MA交叉 ══════";
input bool     Enable_MA         = true;     // 启用MA交叉策略
input int      MA_FastPeriod     = 9;        // 快线周期
input int      MA_SlowPeriod     = 21;       // 慢线周期
input int      MA_TrendPeriod    = 200;      // 趋势过滤MA
input ENUM_TIMEFRAMES MA_Timeframe = PERIOD_H1;  // 时间框架
input int      MA_Magic          = 10001;    // Magic Number

//=== 策略2: RSI均值回归 ===
input string   _s2 = "══════ 策略2: RSI均值回归 ══════";
input bool     Enable_RSI        = true;     // 启用RSI策略
input int      RSI_Period        = 2;        // RSI周期
input int      RSI_OB            = 85;       // 超买水平
input int      RSI_OS            = 15;       // 超卖水平
input ENUM_TIMEFRAMES RSI_Timeframe = PERIOD_H4;  // 时间框架
input int      RSI_Magic         = 10002;    // Magic Number

//=== 策略3: 布林带三重确认 ===
input string   _s3 = "══════ 策略3: BB+RSI+MACD三重确认 ══════";
input bool     Enable_BB         = true;     // 启用布林带策略
input int      BB_Period         = 20;       // 布林带周期
input double   BB_Deviation      = 2.0;      // 标准差倍数
input int      BB_RSI_Period     = 14;       // RSI周期
input int      BB_RSI_OB         = 70;       // RSI超买
input int      BB_RSI_OS         = 30;       // RSI超卖
input ENUM_TIMEFRAMES BB_Timeframe = PERIOD_H4;  // 时间框架
input int      BB_Magic          = 10003;    // Magic Number

//=== 策略4: MACD背离 ===
input string   _s4 = "══════ 策略4: MACD背离 ══════";
input bool     Enable_MACD       = true;     // 启用MACD背离策略
input int      MACD_Fast         = 12;       // MACD快线
input int      MACD_Slow         = 26;       // MACD慢线
input int      MACD_Signal       = 9;        // MACD信号线
input int      MACD_LookBack     = 20;       // 背离回溯周期
input ENUM_TIMEFRAMES MACD_Timeframe = PERIOD_H4; // 时间框架
input int      MACD_Magic        = 10004;    // Magic Number

//=== 策略5: 支撑阻力突破 ===
input string   _s5 = "══════ 策略5: 支撑阻力突破 ══════";
input bool     Enable_SR         = true;     // 启用支撑阻力突破
input int      SR_LookBack       = 50;       // 回溯周期
input double   SR_BreakPips      = 5.0;      // 突破确认点数
input ENUM_TIMEFRAMES SR_Timeframe = PERIOD_H1;   // 时间框架
input int      SR_Magic          = 10005;    // Magic Number

//=== 全局变量 ===
input bool     AutoEnableTrading  = true;    // Try to turn terminal AutoTrading on

string gSymbol;
int    gDigits;
double gPoint;
int    gTotalSignals;
datetime gLastExport;
datetime gLastTickTime;
datetime gLastSnapshotLog;
datetime gLastLoggedCloseTime;
int      gLastLoggedCloseTicket;

#define STRATEGY_DIAG_COUNT 5
string gStrategyDiagStatus[STRATEGY_DIAG_COUNT];
string gStrategyDiagReason[STRATEGY_DIAG_COUNT];
double gStrategyDiagScore[STRATEGY_DIAG_COUNT];

void Strategy_RSI_Reversal_V2();
void Strategy_MACD_Divergence_V2();
void Strategy_SR_Breakout_V2();
int DetectBullishDivergenceV2();
int DetectBearishDivergenceV2();
void ExportBalanceHistoryV2();

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   gSymbol = Symbol();
   gDigits = Digits;
   gPoint  = Point;
   gTotalSignals = 0;
   gLastExport = 0;
   gLastTickTime = (datetime)MarketInfo(gSymbol, MODE_TIME);
   gLastSnapshotLog = 0;
   gLastLoggedCloseTime = 0;
   gLastLoggedCloseTicket = 0;

   // 图表显示设置
   ChartSetInteger(0, CHART_SHOW_GRID, false);
   Comment("");
   EventSetTimer(5);
   EnsureAutoTradingEnabled();
   RefreshStrategyDiagnostics();

   Print("★ QuantGod Multi-Strategy Engine v2.0 启动 ★");
   Print("货币对: ", gSymbol, " | 风险: ", RiskPercent, "% | 最大回撤: ", MaxDrawdownPercent, "%");

   LoadTradeLogState();
   LogAccountSnapshot("INIT");
   gLastSnapshotLog = TimeLocal();
   AuditClosedTrades();
   UpdateChartDisplayV2();
   if(EnableDashboard) ExportDashboardData();

   return INIT_SUCCEEDED;
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

   static datetime lastBar = 0;
   datetime curBar = iTime(gSymbol, RSI_Timeframe, 0);
   if(curBar == lastBar)
   {
      SetStrategyDiagnostic(1, "WAIT_BAR", "Waiting for a new " + TimeframeLabel(RSI_Timeframe) + " bar", 10);
      return;
   }
   lastBar = curBar;

   double rsi1 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 1);
   double rsi2 = iRSI(gSymbol, RSI_Timeframe, RSI_Period, PRICE_CLOSE, 2);
   double bbLower = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbUpper = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double close1 = iClose(gSymbol, RSI_Timeframe, 1);
   double atrSL = GetATRStopLoss(gSymbol, RSI_Timeframe, 14, 1.5);

   bool buyReversal = (rsi2 < RSI_OS && rsi1 > RSI_OS);
   bool buyBand = (close1 <= bbLower * 1.001);
   bool sellReversal = (rsi2 > RSI_OB && rsi1 < RSI_OB);
   bool sellBand = (close1 >= bbUpper * 0.999);
   double buyScore = (double)((buyReversal ? 1 : 0) + (buyBand ? 1 : 0)) / 2.0 * 100.0;
   double sellScore = (double)((sellReversal ? 1 : 0) + (sellBand ? 1 : 0)) / 2.0 * 100.0;

   if(buyReversal && buyBand)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_BUY", RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI回归] 买入 ", lots, " 手 @ ", Ask);
      if(ticket > 0)
         SetStrategyDiagnostic(1, "BUY_ORDER_SENT", "RSI_Reversal buy order sent on " + TimeframeLabel(RSI_Timeframe), 100);
      else
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", "RSI buy setup failed, error=" + IntegerToString(GetLastError()), 100);
      return;
   }

   if(sellReversal && sellBand)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_SELL", RSI_Magic, 0, clrOrange);
      if(ticket > 0) Print("[RSI回归] 卖出 ", lots, " 手 @ ", Bid);
      if(ticket > 0)
         SetStrategyDiagnostic(1, "SELL_ORDER_SENT", "RSI_Reversal sell order sent on " + TimeframeLabel(RSI_Timeframe), 100);
      else
         SetStrategyDiagnostic(1, "ORDER_SEND_FAILED", "RSI sell setup failed, error=" + IntegerToString(GetLastError()), 100);
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

   static datetime lastBar = 0;
   datetime curBar = iTime(gSymbol, MACD_Timeframe, 0);
   if(curBar == lastBar)
   {
      SetStrategyDiagnostic(3, "WAIT_BAR", "Waiting for a new " + TimeframeLabel(MACD_Timeframe) + " bar", 10);
      return;
   }
   lastBar = curBar;

   int bullDiv = DetectBullishDivergenceV2();
   int bearDiv = DetectBearishDivergenceV2();
   double atrSL = GetATRStopLoss(gSymbol, MACD_Timeframe, 14, 2.0);

   if(bullDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_MACD_Div_BUY", MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD背离] 底背离买入 ", lots, " 手 @ ", Ask);
      if(ticket > 0)
         SetStrategyDiagnostic(3, "BUY_ORDER_SENT", "Bullish MACD divergence triggered a buy", 100);
      else
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", "Bullish MACD divergence failed, error=" + IntegerToString(GetLastError()), 100);
      return;
   }

   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_MACD_Div_SELL", MACD_Magic, 0, clrCrimson);
      if(ticket > 0) Print("[MACD背离] 顶背离卖出 ", lots, " 手 @ ", Bid);
      if(ticket > 0)
         SetStrategyDiagnostic(3, "SELL_ORDER_SENT", "Bearish MACD divergence triggered a sell", 100);
      else
         SetStrategyDiagnostic(3, "ORDER_SEND_FAILED", "Bearish MACD divergence failed, error=" + IntegerToString(GetLastError()), 100);
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

   static datetime lastBar = 0;
   datetime curBar = iTime(gSymbol, SR_Timeframe, 0);
   if(curBar == lastBar)
   {
      SetStrategyDiagnostic(4, "WAIT_BAR", "Waiting for a new " + TimeframeLabel(SR_Timeframe) + " bar", 10);
      return;
   }
   lastBar = curBar;

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

   bool volumeConfirm = iVolume(gSymbol, SR_Timeframe, 1) > avgVol * 1.2;
   bool buyPrevBelow = (close2 < resistance);
   bool buyBreak = (close1 > resistance + breakPrice);
   bool sellPrevAbove = (close2 > support);
   bool sellBreak = (close1 < support - breakPrice);
   double buyScore = (double)((buyPrevBelow ? 1 : 0) + (buyBreak ? 1 : 0) + (volumeConfirm ? 1 : 0)) / 3.0 * 100.0;
   double sellScore = (double)((sellPrevAbove ? 1 : 0) + (sellBreak ? 1 : 0) + (volumeConfirm ? 1 : 0)) / 3.0 * 100.0;
   double atrSL = GetATRStopLoss(gSymbol, SR_Timeframe, 14, 1.5);

   if(buyPrevBelow && buyBreak && volumeConfirm)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_SR_Break_BUY", SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR突破] 突破阻力买入 ", lots, " 手 @ ", Ask, " R=", resistance);
      if(ticket > 0)
         SetStrategyDiagnostic(4, "BUY_ORDER_SENT", "SR_Breakout resistance breakout buy", 100);
      else
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", "SR breakout buy failed, error=" + IntegerToString(GetLastError()), 100);
      return;
   }

   if(sellPrevAbove && sellBreak && volumeConfirm)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_SR_Break_SELL", SR_Magic, 0, clrTomato);
      if(ticket > 0) Print("[SR突破] 跌破支撑卖出 ", lots, " 手 @ ", Bid, " S=", support);
      if(ticket > 0)
         SetStrategyDiagnostic(4, "SELL_ORDER_SENT", "SR_Breakout support breakdown sell", 100);
      else
         SetStrategyDiagnostic(4, "ORDER_SEND_FAILED", "SR breakout sell failed, error=" + IntegerToString(GetLastError()), 100);
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
   Print("★ QuantGod Engine 停止, 原因: ", reason, " ★");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTimer()
{
   EnsureAutoTradingEnabled();
   RefreshStrategyDiagnostics();
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
   gLastTickTime = (datetime)MarketInfo(gSymbol, MODE_TIME);
   RefreshStrategyDiagnostics();

   // 回撤保护
   if(!CheckMaxDrawdown(MaxDrawdownPercent))
   {
      Comment("⚠ 回撤超限! 暂停交易. DD > " + DoubleToStr(MaxDrawdownPercent, 1) + "%");
      return;
   }

   // 时段过滤
   if(UseTradeSession && !IsTradeSession()) return;

   // 总持仓数检查
   int totalOpen = OrdersTotal();

   // 执行各策略
   if(Enable_MA)   Strategy_MA_Cross();
   if(Enable_RSI)  Strategy_RSI_Reversal_V2();
   if(Enable_BB)   Strategy_BB_Triple();
   if(Enable_MACD) Strategy_MACD_Divergence_V2();
   if(Enable_SR)   Strategy_SR_Breakout_V2();

   // 追踪止损
   if(TrailingStopPips > 0)
   {
      if(Enable_MA)   TrailingStop(MA_Magic, TrailingStopPips, gSymbol);
      if(Enable_RSI)  TrailingStop(RSI_Magic, TrailingStopPips, gSymbol);
      if(Enable_BB)   TrailingStop(BB_Magic, TrailingStopPips, gSymbol);
      if(Enable_MACD) TrailingStop(MACD_Magic, TrailingStopPips, gSymbol);
      if(Enable_SR)   TrailingStop(SR_Magic, TrailingStopPips, gSymbol);
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

void SetStrategyDiagnostic(int index, string status, string reason, double score)
{
   if(index < 0 || index >= STRATEGY_DIAG_COUNT)
      return;

   if(score < 0) score = 0;
   if(score > 100) score = 100;

   gStrategyDiagStatus[index] = status;
   gStrategyDiagReason[index] = reason;
   gStrategyDiagScore[index] = score;
}

string TradingStatusReason(string status)
{
   if(status == "DISCONNECTED") return "Terminal is disconnected from broker";
   if(status == "ACCOUNT_TRADE_DISABLED") return "Broker account trading is disabled";
   if(status == "SERVER_EXPERTS_DISABLED") return "Broker server disabled expert trading";
   if(status == "TERMINAL_AUTOTRADING_OFF") return "MT4 terminal AutoTrading is off";
   if(status == "EA_LIVE_TRADING_OFF") return "EA live trading permission is off";
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
//| 策略1: MA金叉死叉                                                  |
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

   // 仅在新K线开始时检查
   static datetime lastBar = 0;
   datetime curBar = iTime(gSymbol, MA_Timeframe, 0);
   if(curBar == lastBar)
   {
      SetStrategyDiagnostic(0, "WAIT_BAR", "Waiting for a new " + TimeframeLabel(MA_Timeframe) + " bar", 10);
      return;
   }
   lastBar = curBar;

   double fastMA_1 = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double fastMA_2 = iMA(gSymbol, MA_Timeframe, MA_FastPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double slowMA_1 = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slowMA_2 = iMA(gSymbol, MA_Timeframe, MA_SlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double trendMA  = iMA(gSymbol, MA_Timeframe, MA_TrendPeriod, 0, MODE_SMA, PRICE_CLOSE, 1);

   double rsi14 = iRSI(gSymbol, MA_Timeframe, 14, PRICE_CLOSE, 1);
   double atrSL = GetATRStopLoss(gSymbol, MA_Timeframe, 14, 2.0);
   double close1 = iClose(gSymbol, MA_Timeframe, 1);

   bool buyCross = (fastMA_2 < slowMA_2 && fastMA_1 > slowMA_1);
   bool buyTrend = (close1 > trendMA);
   bool buyRsi = (rsi14 > 50);
   bool sellCross = (fastMA_2 > slowMA_2 && fastMA_1 < slowMA_1);
   bool sellTrend = (close1 < trendMA);
   bool sellRsi = (rsi14 < 50);

   double buyScore = (double)((buyCross ? 1 : 0) + (buyTrend ? 1 : 0) + (buyRsi ? 1 : 0)) / 3.0 * 100.0;
   double sellScore = (double)((sellCross ? 1 : 0) + (sellTrend ? 1 : 0) + (sellRsi ? 1 : 0)) / 3.0 * 100.0;
   int buyTicket = -1;
   int sellTicket = -1;
   int ticket = -1;

   // 金叉买入: 快线上穿慢线 + 价格在200MA上方 + RSI>50
   if(buyCross && buyTrend && buyRsi)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      buyTicket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_MA_Cross_BUY", MA_Magic, 0, clrLime);
      ticket = buyTicket;
      if(ticket > 0) Print("[MA交叉] 买入 ", lots, " 手 @ ", Ask);
   }

   // 死叉卖出: 快线下穿慢线 + 价格在200MA下方 + RSI<50
   if(sellCross && sellTrend && sellRsi)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      ResetLastError();
      sellTicket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_MA_Cross_SELL", MA_Magic, 0, clrRed);
      ticket = sellTicket;
      if(ticket > 0) Print("[MA交叉] 卖出 ", lots, " 手 @ ", Bid);
   }
}

//+------------------------------------------------------------------+
//| 策略2: RSI(2) 均值回归                                             |
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

   // 布林带确认
   double bbLower = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double bbUpper = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double bbMiddle = iBands(gSymbol, RSI_Timeframe, 20, 2.0, 0, PRICE_CLOSE, MODE_MAIN, 1);
   double close1 = iClose(gSymbol, RSI_Timeframe, 1);

   double atrSL = GetATRStopLoss(gSymbol, RSI_Timeframe, 14, 1.5);

   // 超卖反弹买入: RSI从超卖回升 + 价格在下轨附近
   if(rsi_2 < RSI_OS && rsi_1 > RSI_OS && close1 <= bbLower * 1.001)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_BUY", RSI_Magic, 0, clrDodgerBlue);
      if(ticket > 0) Print("[RSI回归] 买入 ", lots, " 手 @ ", Ask);
   }

   // 超买回落卖出: RSI从超买回落 + 价格在上轨附近
   if(rsi_2 > RSI_OB && rsi_1 < RSI_OB && close1 >= bbUpper * 0.999)
   {
      double sl = atrSL;
      double tp = sl * 1.5;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_RSI_Rev_SELL", RSI_Magic, 0, clrOrange);
      if(ticket > 0) Print("[RSI回归] 卖出 ", lots, " 手 @ ", Bid);
   }
}

//+------------------------------------------------------------------+
//| 策略3: 布林带+RSI+MACD 三重确认 (78%胜率策略)                       |
//+------------------------------------------------------------------+
void Strategy_BB_Triple()
{
   if(HasOpenPosition(BB_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_bb = 0;
   datetime curBar = iTime(gSymbol, BB_Timeframe, 0);
   if(curBar == lastBar_bb) return;
   lastBar_bb = curBar;

   double close1 = iClose(gSymbol, BB_Timeframe, 1);

   // 布林带
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

   // 三重确认买入:
   // 1) 价格触及/跌破下轨
   // 2) RSI < 30 且回升
   // 3) MACD金叉
   bool bbBuySignal = (close1 <= bbLower * 1.002);
   bool rsiBuySignal = (rsi < BB_RSI_OS || (rsi_prev < BB_RSI_OS && rsi > BB_RSI_OS));
   bool macdBuySignal = (macdMain_2 < macdSig_2 && macdMain_1 > macdSig_1);

   if(bbBuySignal && rsiBuySignal && macdBuySignal)
   {
      double sl = atrSL;
      double tp_dist = MathAbs(bbUpper - close1) / gPoint / ((gDigits == 3 || gDigits == 5) ? 10.0 : 1.0);
      double tp = MathMax(tp_dist, sl * 1.5);
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_BB_Triple_BUY", BB_Magic, 0, clrGold);
      if(ticket > 0) Print("[BB三重] 买入 ", lots, " 手 @ ", Ask, " TP->上轨");
   }

   // 三重确认卖出
   bool bbSellSignal = (close1 >= bbUpper * 0.998);
   bool rsiSellSignal = (rsi > BB_RSI_OB || (rsi_prev > BB_RSI_OB && rsi < BB_RSI_OB));
   bool macdSellSignal = (macdMain_2 > macdSig_2 && macdMain_1 < macdSig_1);

   if(bbSellSignal && rsiSellSignal && macdSellSignal)
   {
      double sl = atrSL;
      double tp_dist = MathAbs(close1 - bbLower) / gPoint / ((gDigits == 3 || gDigits == 5) ? 10.0 : 1.0);
      double tp = MathMax(tp_dist, sl * 1.5);
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_BB_Triple_SELL", BB_Magic, 0, clrMagenta);
      if(ticket > 0) Print("[BB三重] 卖出 ", lots, " 手 @ ", Bid, " TP->下轨");
   }
}

//+------------------------------------------------------------------+
//| 策略4: MACD背离                                                    |
//+------------------------------------------------------------------+
void Strategy_MACD_Divergence()
{
   if(HasOpenPosition(MACD_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_macd = 0;
   datetime curBar = iTime(gSymbol, MACD_Timeframe, 0);
   if(curBar == lastBar_macd) return;
   lastBar_macd = curBar;

   // 检测背离
   int bullDiv = DetectBullishDivergence();
   int bearDiv = DetectBearishDivergence();

   double atrSL = GetATRStopLoss(gSymbol, MACD_Timeframe, 14, 2.0);

   // 底背离买入
   if(bullDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_MACD_Div_BUY", MACD_Magic, 0, clrAqua);
      if(ticket > 0) Print("[MACD背离] 底背离买入 ", lots, " 手 @ ", Ask);
   }

   // 顶背离卖出
   if(bearDiv > 0)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_MACD_Div_SELL", MACD_Magic, 0, clrCrimson);
      if(ticket > 0) Print("[MACD背离] 顶背离卖出 ", lots, " 手 @ ", Bid);
   }
}

//+------------------------------------------------------------------+
//| 检测底背离 (价格新低, MACD未新低)                                    |
//+------------------------------------------------------------------+
int DetectBullishDivergence()
{
   double priceLow1 = 0, priceLow2 = 0;
   double macdLow1 = 0, macdLow2 = 0;
   int pos1 = 0, pos2 = 0;

   // 找最近两个价格低点
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

   // 底背离: 价格创新低但MACD未创新低
   if(priceLow1 < priceLow2 && macdLow1 > macdLow2)
      return 1;

   return 0;
}

//+------------------------------------------------------------------+
//| 检测顶背离 (价格新高, MACD未新高)                                    |
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

   // 顶背离: 价格创新高但MACD未创新高
   if(priceHigh1 > priceHigh2 && macdHigh1 < macdHigh2)
      return 1;

   return 0;
}

//+------------------------------------------------------------------+
//| 策略5: 支撑阻力突破                                                 |
//+------------------------------------------------------------------+
void Strategy_SR_Breakout()
{
   if(HasOpenPosition(SR_Magic, gSymbol)) return;
   if(CountAllPositions() >= MaxTotalTrades) return;

   static datetime lastBar_sr = 0;
   datetime curBar = iTime(gSymbol, SR_Timeframe, 0);
   if(curBar == lastBar_sr) return;
   lastBar_sr = curBar;

   // 计算支撑和阻力
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

   // 成交量确认 (当前K线成交量 > 20周期平均)
   double avgVol = 0;
   for(int i = 1; i <= 20; i++)
      avgVol += (double)iVolume(gSymbol, SR_Timeframe, i);
   avgVol /= 20.0;
   bool volumeConfirm = iVolume(gSymbol, SR_Timeframe, 1) > avgVol * 1.2;

   double atrSL = GetATRStopLoss(gSymbol, SR_Timeframe, 14, 1.5);

   // 突破阻力买入
   if(close2 < resistance && close1 > resistance + breakPrice && volumeConfirm)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Ask - PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Ask + PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_BUY, lots, Ask, 3, slPrice, tpPrice,
                            "QG_SR_Break_BUY", SR_Magic, 0, clrSpringGreen);
      if(ticket > 0) Print("[SR突破] 突破阻力买入 ", lots, " 手 @ ", Ask, " R=", resistance);
   }

   // 跌破支撑卖出
   if(close2 > support && close1 < support - breakPrice && volumeConfirm)
   {
      double sl = atrSL;
      double tp = sl * 2.0;
      double lots = CalcLotSize(RiskPercent, sl, gSymbol);
      double slPrice = NormalizeDouble(Bid + PipsToPrice(sl, gSymbol), gDigits);
      double tpPrice = NormalizeDouble(Bid - PipsToPrice(tp, gSymbol), gDigits);

      int ticket = OrderSend(gSymbol, OP_SELL, lots, Bid, 3, slPrice, tpPrice,
                            "QG_SR_Break_SELL", SR_Magic, 0, clrTomato);
      if(ticket > 0) Print("[SR突破] 跌破支撑卖出 ", lots, " 手 @ ", Bid, " S=", support);
   }
}

//+------------------------------------------------------------------+
//| 统计所有持仓数                                                     |
//+------------------------------------------------------------------+
int CountAllPositions()
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderSymbol() == gSymbol &&
            (OrderMagicNumber() == MA_Magic || OrderMagicNumber() == RSI_Magic ||
             OrderMagicNumber() == BB_Magic || OrderMagicNumber() == MACD_Magic ||
             OrderMagicNumber() == SR_Magic))
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| 更新图表信息显示                                                    |
//+------------------------------------------------------------------+
int GetTickAgeSeconds()
{
   datetime lastTick = (datetime)MarketInfo(gSymbol, MODE_TIME);
   if(lastTick <= 0)
      return -1;

   int age = (int)(TimeLocal() - lastTick);
   if(age < 0)
      age = 0;

   return age;
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

   if(UseTradeSession && !IsTradeSession())
      return "OUT_OF_SESSION";

   if(GetTickAgeSeconds() > 180)
      return "WAITING_MARKET";

   return "READY";
}

void UpdateChartDisplayV2()
{
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
   info += "Symbol: " + gSymbol + "  TF: " + IntegerToString(Period()) + "\n";
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
   info += "MA: " + (Enable_MA ? "ON" : "OFF") + " (" + IntegerToString(CountPositions(MA_Magic, gSymbol)) + ")\n";
   info += "RSI: " + (Enable_RSI ? "ON" : "OFF") + " (" + IntegerToString(CountPositions(RSI_Magic, gSymbol)) + ")\n";
   info += "BB: " + (Enable_BB ? "ON" : "OFF") + " (" + IntegerToString(CountPositions(BB_Magic, gSymbol)) + ")\n";
   info += "MACD: " + (Enable_MACD ? "ON" : "OFF") + " (" + IntegerToString(CountPositions(MACD_Magic, gSymbol)) + ")\n";
   info += "SR: " + (Enable_SR ? "ON" : "OFF") + " (" + IntegerToString(CountPositions(SR_Magic, gSymbol)) + ")";

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
   info += "╔══════════════════════════════════════╗\n";
   info += "║     QuantGod Multi-Strategy v2.0     ║\n";
   info += "╠══════════════════════════════════════╣\n";
   info += "║ 余额: $" + DoubleToStr(balance, 2) + "\n";
   info += "║ 净值: $" + DoubleToStr(equity, 2) + "\n";
   info += "║ 浮盈: $" + DoubleToStr(profit, 2) + "\n";
   info += "║ 回撤: " + DoubleToStr(dd, 2) + "%\n";
   info += "╠══════════════════════════════════════╣\n";
   info += "║ MA交叉:  " + (Enable_MA ? "ON" : "OFF") + "  | 持仓: " + IntegerToString(CountPositions(MA_Magic, gSymbol)) + "\n";
   info += "║ RSI回归: " + (Enable_RSI ? "ON" : "OFF") + " | 持仓: " + IntegerToString(CountPositions(RSI_Magic, gSymbol)) + "\n";
   info += "║ BB三重:  " + (Enable_BB ? "ON" : "OFF") + "  | 持仓: " + IntegerToString(CountPositions(BB_Magic, gSymbol)) + "\n";
   info += "║ MACD背离:" + (Enable_MACD ? "ON" : "OFF") + " | 持仓: " + IntegerToString(CountPositions(MACD_Magic, gSymbol)) + "\n";
   info += "║ SR突破:  " + (Enable_SR ? "ON" : "OFF") + "  | 持仓: " + IntegerToString(CountPositions(SR_Magic, gSymbol)) + "\n";
   info += "╠══════════════════════════════════════╣\n";
   info += "║ 总持仓: " + IntegerToString(CountAllPositions()) + "/" + IntegerToString(MaxTotalTrades) + "\n";
   info += "║ 点差: " + DoubleToStr(GetSpreadPips(gSymbol), 1) + " pips\n";
   info += "╚══════════════════════════════════════╝\n";

   Comment(info);
}

//+------------------------------------------------------------------+
//| 导出数据到Web面板                                                   |
//+------------------------------------------------------------------+
void ExportDashboardData()
{
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

   // JSON头
   FileWriteString(handle, "{\n");
   FileWriteString(handle, "  \"timestamp\": \"" + TimeToStr(TimeLocal(), TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "  \"build\": \"QuantGod-v2.3-diagnostics\",\n");
   FileWriteString(handle, "  \"runtime\": {\n");
   FileWriteString(handle, "    \"tradeStatus\": \"" + GetTradingStatus() + "\",\n");
    FileWriteString(handle, "    \"connected\": " + (IsConnected() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"terminalTradeAllowed\": " + (IsTerminalTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"programTradeAllowed\": " + (IsProgramTradeEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"dllAllowed\": " + (IsDllImportEnabled() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tradeAllowed\": " + (IsTradeAllowed() ? "true" : "false") + ",\n");
   FileWriteString(handle, "    \"tickAgeSeconds\": " + IntegerToString(GetTickAgeSeconds()) + "\n");
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

   // 当前持仓
   FileWriteString(handle, "  \"openTrades\": [\n");
   bool firstTrade = true;
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != gSymbol) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      if(!firstTrade) FileWriteString(handle, ",\n");
      firstTrade = false;

      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"symbol\": \"" + OrderSymbol() + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), gDigits) + ",\n");
      FileWriteString(handle, "      \"sl\": " + DoubleToStr(OrderStopLoss(), gDigits) + ",\n");
      FileWriteString(handle, "      \"tp\": " + DoubleToStr(OrderTakeProfit(), gDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(OrderProfit(), 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + OrderComment() + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   // 历史交易
   FileWriteString(handle, "  \"closedTrades\": [\n");
   bool firstClosed = true;
   int historyTotal = OrdersHistoryTotal();
   int maxHistory = historyTotal;

   for(int i = historyTotal - 1; i >= historyTotal - maxHistory && i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != gSymbol) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      if(!firstClosed) FileWriteString(handle, ",\n");
      firstClosed = false;

      string stratName = GetStrategyName(OrderMagicNumber());
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";

      FileWriteString(handle, "    {\n");
      FileWriteString(handle, "      \"ticket\": " + IntegerToString(OrderTicket()) + ",\n");
      FileWriteString(handle, "      \"type\": \"" + typeStr + "\",\n");
      FileWriteString(handle, "      \"lots\": " + DoubleToStr(OrderLots(), 2) + ",\n");
      FileWriteString(handle, "      \"openPrice\": " + DoubleToStr(OrderOpenPrice(), gDigits) + ",\n");
      FileWriteString(handle, "      \"closePrice\": " + DoubleToStr(OrderClosePrice(), gDigits) + ",\n");
      FileWriteString(handle, "      \"profit\": " + DoubleToStr(OrderProfit(), 2) + ",\n");
      FileWriteString(handle, "      \"swap\": " + DoubleToStr(OrderSwap(), 2) + ",\n");
      FileWriteString(handle, "      \"openTime\": \"" + TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"closeTime\": \"" + TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES) + "\",\n");
      FileWriteString(handle, "      \"strategy\": \"" + stratName + "\",\n");
      FileWriteString(handle, "      \"comment\": \"" + OrderComment() + "\"\n");
      FileWriteString(handle, "    }");
   }
   FileWriteString(handle, "\n  ],\n");

   // 策略状态
   FileWriteString(handle, "  \"strategies\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"enabled\": " + (Enable_MA ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositions(MA_Magic, gSymbol)) + "},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"enabled\": " + (Enable_RSI ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositions(RSI_Magic, gSymbol)) + "},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"enabled\": " + (Enable_BB ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositions(BB_Magic, gSymbol)) + "},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"enabled\": " + (Enable_MACD ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositions(MACD_Magic, gSymbol)) + "},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"enabled\": " + (Enable_SR ? "true" : "false") + ", \"positions\": " + IntegerToString(CountPositions(SR_Magic, gSymbol)) + "}\n");
   FileWriteString(handle, "  },\n");

   FileWriteString(handle, "  \"diagnostics\": {\n");
   FileWriteString(handle, "    \"MA_Cross\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[0]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[0], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[0]) + "\"},\n");
   FileWriteString(handle, "    \"RSI_Reversal\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[1]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[1], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[1]) + "\"},\n");
   FileWriteString(handle, "    \"BB_Triple\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[2]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[2], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[2]) + "\"},\n");
   FileWriteString(handle, "    \"MACD_Divergence\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[3]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[3], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[3]) + "\"},\n");
   FileWriteString(handle, "    \"SR_Breakout\": {\"status\": \"" + JsonEscape(gStrategyDiagStatus[4]) + "\", \"score\": " + DoubleToStr(gStrategyDiagScore[4], 1) + ", \"reason\": \"" + JsonEscape(gStrategyDiagReason[4]) + "\"}\n");
   FileWriteString(handle, "  },\n");

   // 市场信息
   FileWriteString(handle, "  \"market\": {\n");
   FileWriteString(handle, "    \"symbol\": \"" + gSymbol + "\",\n");
   FileWriteString(handle, "    \"bid\": " + DoubleToStr(MarketInfo(gSymbol, MODE_BID), gDigits) + ",\n");
   FileWriteString(handle, "    \"ask\": " + DoubleToStr(MarketInfo(gSymbol, MODE_ASK), gDigits) + ",\n");
   FileWriteString(handle, "    \"spread\": " + DoubleToStr(GetSpreadPips(gSymbol), 1) + "\n");
   FileWriteString(handle, "  }\n");

   FileWriteString(handle, "}\n");
   FileClose(handle);

   // 同时导出余额历史CSV
   ExportBalanceHistoryV2();
}

//+------------------------------------------------------------------+
//| 导出余额历史                                                       |
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
      if(OrderSymbol() != gSymbol) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      datetime closeTime = OrderCloseTime();
      int ticket = OrderTicket();
      if(closeTime <= 0) continue;
      if(closeTime < gLastLoggedCloseTime) continue;
      if(closeTime == gLastLoggedCloseTime && ticket <= gLastLoggedCloseTicket) continue;

      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);

      FileWrite(handle,
                TimeToStr(closeTime, TIME_DATE|TIME_SECONDS),
                ticket,
                GetStrategyName(OrderMagicNumber()),
                typeStr,
                OrderSymbol(),
                DoubleToStr(OrderLots(), 2),
                DoubleToStr(OrderOpenPrice(), gDigits),
                DoubleToStr(OrderClosePrice(), gDigits),
                DoubleToStr(OrderStopLoss(), gDigits),
                DoubleToStr(OrderTakeProfit(), gDigits),
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
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      runningBalance += netProfit;
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);
      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
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
                      DoubleToStr(OrderOpenPrice(), gDigits) + "," +
                      DoubleToStr(OrderClosePrice(), gDigits) + "," +
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
                   "Current,0,N/A," + gSymbol + ",0,0,0," +
                   DoubleToStr(AccountProfit(), 2) + "," +
                   DoubleToStr(AccountProfit(), 2) + ",0,0," +
                   DoubleToStr(AccountBalance(), 2) + "," +
                   DoubleToStr(AccountEquity(), 2) + ",0,Runtime\n");

   FileClose(handle);
}

void ExportBalanceHistory()
{
   string filename = "QuantGod_BalanceHistory.csv";
   int handle = FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE) return;

   FileWriteString(handle, "Time,Balance,Equity,Profit,Strategy\n");

   // 写入历史订单的累计收益
   double runningBalance = AccountBalance() - AccountProfit();
   int historyTotal = OrdersHistoryTotal();

   // 先收集所有历史交易并排序
   for(int i = 0; i < historyTotal; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      runningBalance += OrderProfit() + OrderSwap() + OrderCommission();
      string stratName = GetStrategyName(OrderMagicNumber());

      FileWriteString(handle,
         TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES) + "," +
         DoubleToStr(runningBalance, 2) + "," +
         DoubleToStr(runningBalance, 2) + "," +
         DoubleToStr(OrderProfit(), 2) + "," +
         stratName + "\n");
   }

   // 写入当前状态
   FileWriteString(handle,
      TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES) + "," +
      DoubleToStr(AccountBalance(), 2) + "," +
      DoubleToStr(AccountEquity(), 2) + "," +
      DoubleToStr(AccountProfit(), 2) + ",Current\n");

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
      if(OrderSymbol() != gSymbol) continue;
      if(OrderMagicNumber() != MA_Magic && OrderMagicNumber() != RSI_Magic &&
         OrderMagicNumber() != BB_Magic && OrderMagicNumber() != MACD_Magic &&
         OrderMagicNumber() != SR_Magic) continue;

      string typeStr = (OrderType() == OP_BUY) ? "BUY" : "SELL";
      double netProfit = OrderProfit() + OrderSwap() + OrderCommission();
      int durationMinutes = (int)((OrderCloseTime() - OrderOpenTime()) / 60);

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
                      DoubleToStr(OrderOpenPrice(), gDigits) + "," +
                      DoubleToStr(OrderClosePrice(), gDigits) + "," +
                      DoubleToStr(OrderStopLoss(), gDigits) + "," +
                      DoubleToStr(OrderTakeProfit(), gDigits) + "," +
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
//| 获取策略名称                                                       |
//+------------------------------------------------------------------+
string GetStrategyName(int magic)
{
   switch(magic)
   {
      case 10001: return "MA_Cross";
      case 10002: return "RSI_Reversal";
      case 10003: return "BB_Triple";
      case 10004: return "MACD_Divergence";
      case 10005: return "SR_Breakout";
      default:    return "Unknown";
   }
}
//+------------------------------------------------------------------+
