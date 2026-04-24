//+------------------------------------------------------------------+
//|                                         QuantGod_MultiStrategy.mq5 |
//|                              QuantGod MT5 Migration Skeleton      |
//+------------------------------------------------------------------+
#property copyright "QuantGod"
#property link      "https://github.com/Boowenn/MT4"
#property version   "3.12"
#property strict

#include <Trade/Trade.mqh>

input string DashboardBuild      = "QuantGod-v3.12-mt5-live-pilot-trailing";
input string Watchlist           = "EURUSD,USDJPY";
input string PreferredSymbolSuffix = "AUTO";
input bool   ShadowMode          = true;
input bool   ReadOnlyMode        = true;
input int    RefreshIntervalSec  = 5;
input int    ClosedTradeLimit    = 50;
input int    HistoryLookbackDays = 30;
input bool   EnablePilotAutoTrading   = false;
input bool   EnablePilotMA            = true;
input ENUM_TIMEFRAMES PilotSignalTimeframe = PERIOD_M15;
input ENUM_TIMEFRAMES PilotTrendTimeframe  = PERIOD_H1;
input int    PilotCrossLookbackBars   = 3;
input int    PilotContinuationLookbackBars = 16;
input bool   PilotBlockRangeEntries   = true;
input int    PilotLossCooldownMinutes = 60;
input bool   EnablePilotBreakevenProtect = true;
input int    PilotBreakevenMinAgeMinutes = 60;
input double PilotBreakevenTriggerPips = 6.0;
input double PilotBreakevenLockPips    = 1.0;
input bool   EnablePilotTrailingStop   = true;
input double PilotTrailingStartPips    = 10.0;
input double PilotTrailingDistancePips = 5.0;
input double PilotTrailingStepPips     = 1.0;
input bool   EnableManualSafetyGuard    = true;
input bool   ManualSafetyWatchlistOnly  = true;
input double ManualSafetyInitialSLPips  = 25.0;
input double ManualSafetyBreakevenTriggerPips = 8.0;
input double ManualSafetyBreakevenLockPips    = 1.0;
input bool   EnableManualTrailingStop   = true;
input double ManualSafetyTrailingStartPips    = 10.0;
input double ManualSafetyTrailingDistancePips = 6.0;
input double ManualSafetyTrailingStepPips     = 1.0;
input double ManualSafetyMaxLossUSC     = 20.0;
input bool   ManualSafetyCloseOnMaxLoss = true;
input int    PilotFastMAPeriod        = 9;
input int    PilotSlowMAPeriod        = 21;
input int    PilotTrendMAPeriod       = 200;
input int    PilotATRPeriod           = 14;
input double PilotATRMulitplierSL     = 2.0;
input double PilotRewardRatio         = 1.5;
input double PilotLotSize             = 0.01;
input double PilotMaxSpreadPips       = 3.0;
input int    PilotMaxTotalPositions   = 1;
input int    PilotMaxPositionsPerSymbol = 1;
input bool   PilotBlockManualPerSymbol  = true;
input bool   PilotRestrictSession       = true;
input int    PilotSessionStartHour      = 7;
input int    PilotSessionEndHour        = 21;
input bool   EnablePilotNewsFilter      = true;
input int    PilotNewsPreBlockMinutes   = 10;
input int    PilotNewsPostBlockMinutes  = 5;
input int    PilotNewsBiasMinutes       = 45;
input int    PilotNewsRefreshSeconds    = 15;
input double PilotUsdJpyNoChaseLevel    = 160.0;
input double PilotUsdJpyNoChaseBufferPips = 10.0;
input double PilotMaxFloatingLossUSC    = 30.0;
input double PilotMaxRealizedLossDayUSC = 60.0;
input int    PilotMaxConsecutiveLosses  = 2;
input bool   PilotCloseOnKillSwitch     = true;
input long   PilotMagic                 = 520001;
input int    PilotDeviationPoints       = 30;

string g_symbols[];
string g_focusSymbol = "";
string g_requestedSymbols[];
string g_resolvedWatchlist = "";
string g_detectedSuffix = "";
string g_strategyKeys[5] =
{
   "MA_Cross",
   "RSI_Reversal",
   "BB_Triple",
   "MACD_Divergence",
   "SR_Breakout"
};

CTrade g_trade;

struct SymbolSnapshot
{
   string   symbol;
   string   role;
   string   status;
   int      tickAgeSeconds;
   double   bid;
   double   ask;
   double   spread;
   int      openPositions;
   double   floatingProfit;
   double   actualFloatingProfit;
   int      closedTrades;
   int      wins;
   double   closedProfit;
   double   actualClosedProfit;
   datetime lastCloseTime;
};

struct StrategyStatusSnapshot
{
   bool     enabled;
   bool     active;
   string   runtimeLabel;
   string   status;
   string   adaptiveState;
   string   adaptiveReason;
   double   riskMultiplier;
   double   score;
   string   reason;
};

struct PilotTelemetrySnapshot
{
   int      dayKey;
   int      evaluationPasses;
   int      signalHits;
   int      waitBarSkips;
   int      noCrossMisses;
   int      spreadBlocks;
   int      sessionBlocks;
   int      newsBlocks;
   int      newsFiltered;
   int      manualBlocks;
   int      portfolioBlocks;
   int      inPositionBlocks;
   int      regimeBlocks;
   int      cooldownBlocks;
   int      orderSent;
   int      orderFailed;
   datetime lastEvalTime;
   datetime lastSignalTime;
   datetime lastOrderTime;
   string   lastStatus;
   string   lastReason;
   int      lastDirection;
};

struct ClosedTradeRecord
{
   ulong    ticket;
   ulong    positionId;
   string   type;
   string   symbol;
   double   lots;
   double   actualLots;
   double   virtualLots;
   double   openPrice;
   double   closePrice;
   double   profit;
   double   actualProfit;
   double   swap;
   datetime openTime;
   datetime closeTime;
   string   strategy;
   string   source;
   string   comment;
   string   entryRegime;
   string   exitRegime;
   string   regimeTimeframe;
   int      durationMinutes;
   double   commission;
   double   grossProfit;
};

struct RegimeSnapshot
{
   string   label;
   string   timeframe;
   double   directionalMovePips;
   double   averageRangePips;
   double   recentRangePips;
};

struct TradeJournalRecord
{
   ulong    dealTicket;
   ulong    positionId;
   string   eventType;
   string   side;
   string   symbol;
   double   lots;
   double   price;
   double   grossProfit;
   double   commission;
   double   swap;
   double   netProfit;
   datetime eventTime;
   string   strategy;
   string   source;
   string   comment;
   string   regime;
   string   regimeTimeframe;
};

struct StrategyAggregateRecord
{
   string   symbol;
   string   strategy;
   string   timeframe;
   int      closedTrades;
   int      wins;
   double   grossProfit;
   double   grossLoss;
   double   netProfit;
   datetime lastCloseTime;
   int      openPositions;
   int      strategyPositions;
};

struct RegimeAggregateRecord
{
   string   symbol;
   string   strategy;
   string   timeframe;
   string   entryRegime;
   int      closedTrades;
   int      linkedTrades;
   int      positiveTrades;
   int      negativeTrades;
   int      flatTrades;
   double   grossProfit;
   double   grossLoss;
   double   netProfit;
   double   totalDurationMinutes;
   datetime lastEventTime;
   datetime lastCloseTime;
};

struct NewsFilterState
{
   bool     enabled;
   bool     calendarAvailable;
   bool     blocked;
   bool     biasActive;
   int      usdBiasDirection;
   string   status;
   string   phase;
   string   eventName;
   datetime eventTime;
   double   actual;
   double   forecast;
   double   previous;
   int      minutesToEvent;
   int      minutesSinceEvent;
   string   reason;
};

datetime g_lastPilotBarTime[];
StrategyStatusSnapshot g_maRuntimeStates[];
PilotTelemetrySnapshot g_pilotTelemetry[];
bool g_pilotKillSwitch = false;
string g_pilotKillReason = "";
double g_pilotRealizedLossToday = 0.0;
int g_pilotConsecutiveLosses = 0;
ulong g_usdTrackedEventIds[];
string g_usdTrackedEventNames[];
int g_usdTrackedEventKinds[];
NewsFilterState g_newsState;
datetime g_lastNewsRefresh = 0;

enum ENUM_USD_NEWS_KIND
{
   USD_NEWS_UNKNOWN = 0,
   USD_NEWS_JOBLESS = 1,
   USD_NEWS_PMI     = 2
};

enum ENUM_PILOT_EVAL_CODE
{
   PILOT_EVAL_NONE = 0,
   PILOT_EVAL_NOT_ENOUGH_BARS = 1,
   PILOT_EVAL_TICK_UNAVAILABLE = 2,
   PILOT_EVAL_SPREAD_BLOCK = 3,
   PILOT_EVAL_SESSION_BLOCK = 4,
   PILOT_EVAL_INDICATOR_NOT_READY = 5,
   PILOT_EVAL_TREND_NOT_READY = 6,
   PILOT_EVAL_ATR_UNAVAILABLE = 7,
   PILOT_EVAL_RANGE_BLOCK = 8,
   PILOT_EVAL_SIGNAL_BUY = 9,
   PILOT_EVAL_SIGNAL_SELL = 10,
   PILOT_EVAL_NO_CROSS = 11
};

string TrimString(string value)
{
   int start = 0;
   int end = StringLen(value) - 1;

   while(start <= end)
   {
      ushort c = StringGetCharacter(value, start);
      if(c != ' ' && c != '\t' && c != '\r' && c != '\n')
         break;
      start++;
   }

   while(end >= start)
   {
      ushort c = StringGetCharacter(value, end);
      if(c != ' ' && c != '\t' && c != '\r' && c != '\n')
         break;
      end--;
   }

   if(end < start)
      return "";

   return StringSubstr(value, start, end - start + 1);
}

void PushString(string &values[], string value)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = value;
}

void PushULong(ulong &values[], ulong value)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = value;
}

void PushInt(int &values[], int value)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = value;
}

void PushClosedTrade(ClosedTradeRecord &values[], ClosedTradeRecord &record)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = record;
}

void PushTradeJournal(TradeJournalRecord &values[], TradeJournalRecord &record)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = record;
}

string ToUpperString(string value)
{
   string result = value;
   StringToUpper(result);
   return result;
}

bool ContainsInsensitive(string value, string token)
{
   string haystack = ToUpperString(value);
   string needle = ToUpperString(token);
   return (StringFind(haystack, needle) >= 0);
}

bool EndsWith(string value, string suffix)
{
   int valueLength = StringLen(value);
   int suffixLength = StringLen(suffix);
   if(suffixLength <= 0 || suffixLength > valueLength)
      return false;

   return (StringSubstr(value, valueLength - suffixLength) == suffix);
}

string RemoveTrailingSuffix(string value, string suffix)
{
   if(!EndsWith(value, suffix))
      return value;
   return StringSubstr(value, 0, StringLen(value) - StringLen(suffix));
}

int FindSymbolIndex(string symbol)
{
   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      if(g_symbols[i] == symbol)
         return i;
   }
   return -1;
}

bool SymbolExistsInTerminal(string symbol)
{
   bool isCustom = false;
   return (StringLen(symbol) > 0 && SymbolExist(symbol, isCustom));
}

string DetectAccountSymbolSuffix()
{
   string requested = TrimString(PreferredSymbolSuffix);
   if(StringLen(requested) > 0 && ToUpperString(requested) != "AUTO")
      return requested;

   string chartSymbol = _Symbol;
   if(StringLen(chartSymbol) > 6)
   {
      string chartPrefix = StringSubstr(chartSymbol, 0, 6);
      if(chartPrefix == "EURUSD" || chartPrefix == "USDJPY" || chartPrefix == "GBPUSD")
         return StringSubstr(chartSymbol, 6);
   }

   string accountCurrency = ToUpperString(AccountInfoString(ACCOUNT_CURRENCY));
   if(accountCurrency == "USC")
      return "c";

   string server = ToUpperString(AccountInfoString(ACCOUNT_SERVER));
   if(StringFind(server, "HFMARKETS") >= 0)
   {
      if(SymbolExistsInTerminal("EURUSDc") || SymbolExistsInTerminal("USDJPYc"))
         return "c";
   }

   return "";
}

string ResolveWatchSymbol(string token, string suffix)
{
   string requested = TrimString(token);
   if(StringLen(requested) == 0)
      return "";

   if(SymbolExistsInTerminal(requested))
      return requested;

   string cleanSuffix = TrimString(suffix);
   string normalized = requested;

   if(StringLen(cleanSuffix) > 0)
   {
      normalized = RemoveTrailingSuffix(requested, cleanSuffix);
      string candidate = normalized + cleanSuffix;
      if(SymbolExistsInTerminal(candidate))
         return candidate;
   }

   if(SymbolExistsInTerminal(normalized))
      return normalized;

   if(StringLen(cleanSuffix) == 0 && SymbolExistsInTerminal(normalized + "c"))
      return normalized + "c";

   int symbolsTotal = SymbolsTotal(false);
   string prefixUpper = ToUpperString(normalized);
   string fallback = "";

   for(int i = 0; i < symbolsTotal; i++)
   {
      string symbolName = SymbolName(i, false);
      if(StringLen(symbolName) < StringLen(normalized))
         continue;
      string head = ToUpperString(StringSubstr(symbolName, 0, StringLen(normalized)));
      if(head != prefixUpper)
         continue;

      if(StringLen(cleanSuffix) > 0 && EndsWith(symbolName, cleanSuffix))
         return symbolName;

      if(fallback == "")
         fallback = symbolName;
   }

   return fallback;
}

string JoinResolvedWatchlist()
{
   string value = "";
   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      if(i > 0)
         value += ",";
      value += g_symbols[i];
   }
   return value;
}

string AccountMarginModeToString(long marginMode)
{
   if(marginMode == ACCOUNT_MARGIN_MODE_RETAIL_NETTING)
      return "NETTING";
   if(marginMode == ACCOUNT_MARGIN_MODE_EXCHANGE)
      return "EXCHANGE";
   if(marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      return "HEDGING";
   return "UNKNOWN";
}

bool InitializeWatchlist()
{
   ArrayResize(g_symbols, 0);
   ArrayResize(g_requestedSymbols, 0);
   string remaining = Watchlist;
   g_detectedSuffix = DetectAccountSymbolSuffix();

   while(StringLen(remaining) > 0)
   {
      int commaPos = StringFind(remaining, ",");
      string token = (commaPos >= 0) ? StringSubstr(remaining, 0, commaPos) : remaining;
      token = TrimString(token);
      if(StringLen(token) > 0)
      {
         PushString(g_requestedSymbols, token);
         string resolved = ResolveWatchSymbol(token, g_detectedSuffix);
         if(StringLen(resolved) > 0 && FindSymbolIndex(resolved) < 0)
            PushString(g_symbols, resolved);
      }
      if(commaPos < 0)
         break;
      remaining = StringSubstr(remaining, commaPos + 1);
   }

   if(ArraySize(g_symbols) == 0)
   {
      string fallback = _Symbol;
      if(StringLen(fallback) == 0)
         fallback = "EURUSD";
      PushString(g_symbols, fallback);
   }

   g_focusSymbol = g_symbols[0];
   g_resolvedWatchlist = JoinResolvedWatchlist();

   for(int i = 0; i < ArraySize(g_symbols); i++)
      SymbolSelect(g_symbols[i], true);

   ArrayResize(g_lastPilotBarTime, ArraySize(g_symbols));
   ArrayResize(g_maRuntimeStates, ArraySize(g_symbols));
   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      g_lastPilotBarTime[i] = 0;
      g_maRuntimeStates[i].enabled = false;
      g_maRuntimeStates[i].active = false;
      g_maRuntimeStates[i].runtimeLabel = "PORT";
      g_maRuntimeStates[i].status = "NO_DATA";
      g_maRuntimeStates[i].adaptiveState = "WARMUP";
      g_maRuntimeStates[i].adaptiveReason = "MT5 pilot runtime has not evaluated yet";
      g_maRuntimeStates[i].riskMultiplier = 0.0;
      g_maRuntimeStates[i].score = 0.0;
      g_maRuntimeStates[i].reason = "MT5 pilot runtime has not evaluated yet";
   }

   return true;
}

datetime CurrentServerTime()
{
   datetime value = TimeTradeServer();
   if(value <= 0)
      value = TimeCurrent();
   if(value <= 0)
      value = TimeLocal();
   return value;
}

void ResetNewsFilterState()
{
   g_newsState.enabled = EnablePilotNewsFilter;
   g_newsState.calendarAvailable = false;
   g_newsState.blocked = false;
   g_newsState.biasActive = false;
   g_newsState.usdBiasDirection = 0;
   g_newsState.status = EnablePilotNewsFilter ? "IDLE" : "DISABLED";
   g_newsState.phase = "none";
   g_newsState.eventName = "";
   g_newsState.eventTime = 0;
   g_newsState.actual = 0.0;
   g_newsState.forecast = 0.0;
   g_newsState.previous = 0.0;
   g_newsState.minutesToEvent = 0;
   g_newsState.minutesSinceEvent = 0;
   g_newsState.reason = EnablePilotNewsFilter
      ? "USD high-impact news filter is armed"
      : "USD high-impact news filter is disabled";
}

int DetermineUsdNewsKind(string sourceText)
{
   string upper = ToUpperString(sourceText);
   bool looksLikeInitialClaims =
      ((StringFind(upper, "JOBLESS") >= 0 || StringFind(upper, "UNEMPLOYMENT CLAIM") >= 0) &&
       StringFind(upper, "CONTINUING") < 0);
   if(looksLikeInitialClaims)
      return USD_NEWS_JOBLESS;

   if(StringFind(upper, "PMI") >= 0 || StringFind(upper, "PURCHASING MANAGERS") >= 0)
      return USD_NEWS_PMI;

   return USD_NEWS_UNKNOWN;
}

string UsdNewsKindLabel(int kind)
{
   if(kind == USD_NEWS_JOBLESS)
      return "JOBLESS";
   if(kind == USD_NEWS_PMI)
      return "PMI";
   return "UNKNOWN";
}

bool CalendarFieldToDouble(long rawValue, double &value)
{
   value = 0.0;
   if(rawValue == LONG_MIN)
      return false;
   value = (double)rawValue / 1000000.0;
   return true;
}

void LoadTrackedUsdCalendarEvents()
{
   ArrayResize(g_usdTrackedEventIds, 0);
   ArrayResize(g_usdTrackedEventNames, 0);
   ArrayResize(g_usdTrackedEventKinds, 0);

   if(!EnablePilotNewsFilter)
      return;

   MqlCalendarEvent events[];
   ResetLastError();
   int count = CalendarEventByCurrency("USD", events);
   if(count <= 0)
   {
      Print("QuantGod MT5 news filter failed to load USD calendar events. err=", GetLastError());
      return;
   }

   for(int i = 0; i < count; i++)
   {
      if(events[i].type != CALENDAR_TYPE_INDICATOR)
         continue;
      if(events[i].importance < CALENDAR_IMPORTANCE_MODERATE)
         continue;

      string descriptor = events[i].event_code + " " + events[i].name;
      int kind = DetermineUsdNewsKind(descriptor);

      PushULong(g_usdTrackedEventIds, events[i].id);
      PushString(g_usdTrackedEventNames, events[i].name);
      PushInt(g_usdTrackedEventKinds, kind);
   }

   if(ArraySize(g_usdTrackedEventIds) > 0)
   {
      Print("QuantGod MT5 news filter armed with ", ArraySize(g_usdTrackedEventIds),
            " USD calendar events");
   }
   else
   {
      Print("QuantGod MT5 news filter found no matching USD events in terminal calendar");
   }
}

int UsdBiasFromEventKind(int kind, double actual, double forecast)
{
   double diff = actual - forecast;
   if(MathAbs(diff) < 0.000001)
      return 0;

   if(kind == USD_NEWS_JOBLESS)
      return (diff < 0.0) ? 1 : -1;

   if(kind == USD_NEWS_PMI)
      return (diff > 0.0) ? 1 : -1;

   return 0;
}

string UsdBiasLabel(int direction)
{
   if(direction > 0)
      return "USD_BULLISH";
   if(direction < 0)
      return "USD_BEARISH";
   return "NEUTRAL";
}

int PilotDirectionBiasForSymbol(string symbol, int usdBiasDirection)
{
   if(usdBiasDirection == 0)
      return 0;

   string upper = ToUpperString(symbol);
   if(StringFind(upper, "EURUSD") >= 0)
      return -usdBiasDirection;
   if(StringFind(upper, "USDJPY") >= 0)
      return usdBiasDirection;
   return 0;
}

string PilotActionLabelForSymbol(string symbol)
{
   if(g_newsState.blocked)
      return "BLOCKED";

   int direction = PilotDirectionBiasForSymbol(symbol, g_newsState.usdBiasDirection);
   if(direction > 0)
      return "BUY_ONLY";
   if(direction < 0)
      return "SELL_ONLY";
   return "BOTH";
}

void RefreshNewsFilterState(bool force=false)
{
   if(!EnablePilotNewsFilter)
   {
      ResetNewsFilterState();
      return;
   }

   datetime now = CurrentServerTime();
   if(!force && g_lastNewsRefresh > 0 && (now - g_lastNewsRefresh) < MathMax(5, PilotNewsRefreshSeconds))
      return;
   g_lastNewsRefresh = now;

   ResetNewsFilterState();

   if(ArraySize(g_usdTrackedEventIds) == 0)
      LoadTrackedUsdCalendarEvents();

   if(ArraySize(g_usdTrackedEventIds) == 0)
   {
      g_newsState.status = "NO_CALENDAR";
      g_newsState.reason = "USD calendar events unavailable in this terminal";
      return;
   }

   g_newsState.calendarAvailable = true;

   datetime fromTime = now - (MathMax(PilotNewsBiasMinutes, PilotNewsPostBlockMinutes) + 60) * 60;
   datetime toTime = now + 360 * 60;

   bool hasPreBlock = false;
   datetime preBlockTime = 0;
   string preBlockName = "";
   int preBlockMinutes = 0;

   bool hasPostBlock = false;
   datetime postBlockTime = 0;
   string postBlockName = "";
   int postBlockMinutes = 0;

   bool hasUpcoming = false;
   datetime upcomingTime = 0;
   string upcomingName = "";
   int upcomingMinutes = 0;

   int biasScore = 0;
   int biasSamples = 0;
   datetime biasEventTime = 0;
   string biasEventName = "";
   double biasActual = 0.0;
   double biasForecast = 0.0;
   double biasPrevious = 0.0;
   int biasMinutesSince = 0;

   for(int i = 0; i < ArraySize(g_usdTrackedEventIds); i++)
   {
      MqlCalendarValue values[];
      ResetLastError();
      int count = CalendarValueHistoryByEvent(g_usdTrackedEventIds[i], values, fromTime, toTime);
      if(count < 0)
         continue;

      for(int j = 0; j < count; j++)
      {
         datetime eventTime = values[j].time;
         if(eventTime <= 0)
            continue;

         string eventName = g_usdTrackedEventNames[i];
         if(eventTime > now)
         {
            int minutesToEvent = (int)MathMax(0, (long)(eventTime - now) / 60);
            if(!hasUpcoming || eventTime < upcomingTime)
            {
               hasUpcoming = true;
               upcomingTime = eventTime;
               upcomingName = eventName;
               upcomingMinutes = minutesToEvent;
            }
            if(minutesToEvent <= PilotNewsPreBlockMinutes && (!hasPreBlock || eventTime < preBlockTime))
            {
               hasPreBlock = true;
               preBlockTime = eventTime;
               preBlockName = eventName;
               preBlockMinutes = minutesToEvent;
            }
            continue;
         }

         int minutesSinceEvent = (int)MathMax(0, (long)(now - eventTime) / 60);
         if(minutesSinceEvent <= PilotNewsPostBlockMinutes)
         {
            if(!hasPostBlock || eventTime > postBlockTime)
            {
               hasPostBlock = true;
               postBlockTime = eventTime;
               postBlockName = eventName;
               postBlockMinutes = minutesSinceEvent;
            }
         }

         double actual = 0.0;
         double forecast = 0.0;
         double previous = 0.0;
         bool hasActual = CalendarFieldToDouble(values[j].actual_value, actual);
         bool hasForecast = CalendarFieldToDouble(values[j].forecast_value, forecast);
         bool hasPrevious = CalendarFieldToDouble(values[j].prev_value, previous);
         if(!hasPrevious)
            CalendarFieldToDouble(values[j].revised_prev_value, previous);

         if(!hasActual || !hasForecast || minutesSinceEvent > PilotNewsBiasMinutes)
            continue;

         int eventBias = UsdBiasFromEventKind(g_usdTrackedEventKinds[i], actual, forecast);
         if(eventBias == 0)
            continue;

         biasScore += eventBias;
         biasSamples++;
         if(eventTime >= biasEventTime)
         {
            biasEventTime = eventTime;
            biasEventName = eventName;
            biasActual = actual;
            biasForecast = forecast;
            biasPrevious = previous;
            biasMinutesSince = minutesSinceEvent;
         }
      }
   }

   if(hasPreBlock)
   {
      g_newsState.blocked = true;
      g_newsState.status = "PRE_BLOCK";
      g_newsState.phase = "pre";
      g_newsState.eventName = preBlockName;
      g_newsState.eventTime = preBlockTime;
      g_newsState.minutesToEvent = preBlockMinutes;
      g_newsState.reason = "USD news pre-block: " + preBlockName +
         " in " + IntegerToString(preBlockMinutes) + "m";
      return;
   }

   if(hasPostBlock)
   {
      g_newsState.blocked = true;
      g_newsState.status = "POST_BLOCK";
      g_newsState.phase = "post";
      g_newsState.eventName = postBlockName;
      g_newsState.eventTime = postBlockTime;
      g_newsState.minutesSinceEvent = postBlockMinutes;
      g_newsState.reason = "USD news post-release cooldown: " + postBlockName +
         " +" + IntegerToString(postBlockMinutes) + "m";
      return;
   }

   if(biasSamples > 0 && biasScore != 0)
   {
      g_newsState.biasActive = true;
      g_newsState.usdBiasDirection = (biasScore > 0) ? 1 : -1;
      g_newsState.status = "BIAS_ACTIVE";
      g_newsState.phase = "bias";
      g_newsState.eventName = biasEventName;
      g_newsState.eventTime = biasEventTime;
      g_newsState.actual = biasActual;
      g_newsState.forecast = biasForecast;
      g_newsState.previous = biasPrevious;
      g_newsState.minutesSinceEvent = biasMinutesSince;
      g_newsState.reason = "USD news bias " + UsdBiasLabel(g_newsState.usdBiasDirection) +
         " from " + biasEventName +
         " | actual=" + DoubleToString(biasActual, 2) +
         " forecast=" + DoubleToString(biasForecast, 2);
      return;
   }

   if(hasUpcoming)
   {
      g_newsState.status = "TRACKING";
      g_newsState.phase = "tracking";
      g_newsState.eventName = upcomingName;
      g_newsState.eventTime = upcomingTime;
      g_newsState.minutesToEvent = upcomingMinutes;
      g_newsState.reason = "Tracking next USD event: " + upcomingName +
         " in " + IntegerToString(upcomingMinutes) + "m";
      return;
   }

   g_newsState.status = "IDLE";
   g_newsState.reason = "No tracked USD event near the current pilot window";
}

bool PilotNewsBlocksSymbol(string symbol, string &reason)
{
   reason = "";
   if(!EnablePilotNewsFilter || !g_newsState.blocked)
      return false;

   int directionBias = PilotDirectionBiasForSymbol(symbol, 1);
   if(directionBias == 0)
      return false;

   reason = g_newsState.reason;
   return true;
}

bool PilotDirectionAllowedByNews(string symbol, int direction, MqlTick &tick, string &reason)
{
   reason = "";
   if(!EnablePilotNewsFilter)
      return true;

   if(g_newsState.blocked)
   {
      reason = g_newsState.reason;
      return false;
   }

   int preferredDirection = PilotDirectionBiasForSymbol(symbol, g_newsState.usdBiasDirection);
   if(g_newsState.biasActive && preferredDirection != 0 && direction != preferredDirection)
   {
      reason = "News bias allows only " + PilotActionLabelForSymbol(symbol) +
         " after " + g_newsState.eventName;
      return false;
   }

   string upper = ToUpperString(symbol);
   if(g_newsState.biasActive &&
      g_newsState.usdBiasDirection > 0 &&
      direction > 0 &&
      StringFind(upper, "USDJPY") >= 0)
   {
      double noChasePrice = PilotUsdJpyNoChaseLevel - (PilotUsdJpyNoChaseBufferPips * PipSize(symbol));
      if(tick.ask >= noChasePrice)
      {
         reason = "USDJPY anti-chase guard near 160 blocks breakout BUY after USD-positive news";
         return false;
      }
   }

   return true;
}

string BuildNewsJson()
{
   bool calendarAvailable = g_newsState.calendarAvailable || ArraySize(g_usdTrackedEventIds) > 0;
   string newsReason = g_newsState.reason;
   if(EnablePilotNewsFilter &&
      calendarAvailable &&
      g_newsState.status == "IDLE" &&
      g_newsState.reason == "USD high-impact news filter is armed")
   {
      newsReason = "No tracked USD event near the current pilot window";
   }

   string json = "{";
   json += "\"enabled\": " + JsonBool(EnablePilotNewsFilter) + ", ";
   json += "\"calendarAvailable\": " + JsonBool(calendarAvailable) + ", ";
   json += "\"trackedEvents\": " + IntegerToString(ArraySize(g_usdTrackedEventIds)) + ", ";
   json += "\"status\": \"" + JsonEscape(g_newsState.status) + "\", ";
   json += "\"phase\": \"" + JsonEscape(g_newsState.phase) + "\", ";
   json += "\"blocked\": " + JsonBool(g_newsState.blocked) + ", ";
   json += "\"biasActive\": " + JsonBool(g_newsState.biasActive) + ", ";
   json += "\"usdBias\": \"" + JsonEscape(UsdBiasLabel(g_newsState.usdBiasDirection)) + "\", ";
   json += "\"eventName\": \"" + JsonEscape(g_newsState.eventName) + "\", ";
   json += "\"eventTimeServer\": \"" + JsonEscape(FormatDateTime(g_newsState.eventTime, true)) + "\", ";
   json += "\"minutesToEvent\": " + IntegerToString(g_newsState.minutesToEvent) + ", ";
   json += "\"minutesSinceEvent\": " + IntegerToString(g_newsState.minutesSinceEvent) + ", ";
   json += "\"actual\": " + FormatNumber(g_newsState.actual, 2) + ", ";
   json += "\"forecast\": " + FormatNumber(g_newsState.forecast, 2) + ", ";
   json += "\"previous\": " + FormatNumber(g_newsState.previous, 2) + ", ";
   json += "\"focusAction\": \"" + JsonEscape(PilotActionLabelForSymbol(g_focusSymbol)) + "\", ";
   json += "\"reason\": \"" + JsonEscape(newsReason) + "\"";
   json += "}";
   return json;
}

bool IsPilotLiveMode()
{
   return (EnablePilotAutoTrading && !ReadOnlyMode);
}

bool IsPilotStrategyComment(string comment)
{
   string upper = ToUpperString(comment);
   return (StringFind(upper, "QG_MA_CROSS_MT5") >= 0 || StringFind(upper, "QG_MA_CROSS") >= 0);
}

string PilotTradeComment(int direction)
{
   return (direction > 0) ? "QG_MA_Cross_MT5_BUY" : "QG_MA_Cross_MT5_SELL";
}

double NormalizeVolumeForSymbol(string symbol, double requested)
{
   double minVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(minVolume <= 0.0)
      minVolume = 0.01;
   if(maxVolume <= 0.0)
      maxVolume = requested;
   if(step <= 0.0)
      step = minVolume;

   double volume = requested;
   volume = MathMax(minVolume, MathMin(maxVolume, volume));
   volume = MathFloor(volume / step + 1e-8) * step;
   if(volume < minVolume)
      volume = minVolume;
   return volume;
}

void ResetPilotRuntimeStates()
{
   g_pilotKillSwitch = false;
   g_pilotKillReason = "";
   g_pilotRealizedLossToday = 0.0;
   g_pilotConsecutiveLosses = 0;

   for(int i = 0; i < ArraySize(g_maRuntimeStates); i++)
   {
      g_maRuntimeStates[i].enabled = IsPilotLiveMode() && EnablePilotMA;
      g_maRuntimeStates[i].active = false;
      g_maRuntimeStates[i].runtimeLabel = g_maRuntimeStates[i].enabled ? "OFF" : "PORT";
      g_maRuntimeStates[i].status = g_maRuntimeStates[i].enabled ? "WAIT_SIGNAL" : "NO_DATA";
      g_maRuntimeStates[i].adaptiveState = g_maRuntimeStates[i].enabled ? "CAUTION" : "WARMUP";
      g_maRuntimeStates[i].adaptiveReason = g_maRuntimeStates[i].enabled
         ? "MT5 0.01 live pilot armed: M15 signal, H1 trend filter, 3-bar cross plus pullback continuation, range guard, and post-loss cooldown"
         : "MT5 phase 1 skeleton: execution engine not ported yet";
      g_maRuntimeStates[i].riskMultiplier = g_maRuntimeStates[i].enabled ? 1.0 : 0.0;
      g_maRuntimeStates[i].score = 0.0;
      g_maRuntimeStates[i].reason = g_maRuntimeStates[i].enabled
         ? "Waiting for first pilot evaluation"
         : "MT5 phase 1 skeleton: execution engine not ported yet";
   }
}

int CurrentServerDayKey()
{
   datetime serverNow = TimeTradeServer();
   if(serverNow <= 0)
      serverNow = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(serverNow, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
}

void ResetPilotTelemetryForIndex(int index, int dayKey)
{
   if(index < 0 || index >= ArraySize(g_pilotTelemetry))
      return;

   g_pilotTelemetry[index].dayKey = dayKey;
   g_pilotTelemetry[index].evaluationPasses = 0;
   g_pilotTelemetry[index].signalHits = 0;
   g_pilotTelemetry[index].waitBarSkips = 0;
   g_pilotTelemetry[index].noCrossMisses = 0;
   g_pilotTelemetry[index].spreadBlocks = 0;
   g_pilotTelemetry[index].sessionBlocks = 0;
   g_pilotTelemetry[index].newsBlocks = 0;
   g_pilotTelemetry[index].newsFiltered = 0;
   g_pilotTelemetry[index].manualBlocks = 0;
   g_pilotTelemetry[index].portfolioBlocks = 0;
   g_pilotTelemetry[index].inPositionBlocks = 0;
   g_pilotTelemetry[index].regimeBlocks = 0;
   g_pilotTelemetry[index].cooldownBlocks = 0;
   g_pilotTelemetry[index].orderSent = 0;
   g_pilotTelemetry[index].orderFailed = 0;
   g_pilotTelemetry[index].lastEvalTime = 0;
   g_pilotTelemetry[index].lastSignalTime = 0;
   g_pilotTelemetry[index].lastOrderTime = 0;
   g_pilotTelemetry[index].lastStatus = "NO_DATA";
   g_pilotTelemetry[index].lastReason = "Waiting for first pilot evaluation";
   g_pilotTelemetry[index].lastDirection = 0;
}

void EnsurePilotTelemetryState()
{
   int symbolCount = ArraySize(g_symbols);
   if(ArraySize(g_pilotTelemetry) != symbolCount)
      ArrayResize(g_pilotTelemetry, symbolCount);

   int dayKey = CurrentServerDayKey();
   for(int i = 0; i < symbolCount; i++)
   {
      if(g_pilotTelemetry[i].dayKey != dayKey)
         ResetPilotTelemetryForIndex(i, dayKey);
   }
}

void UpdatePilotTelemetrySnapshot(int index, string status, string reason, int direction = 0)
{
   if(index < 0 || index >= ArraySize(g_pilotTelemetry))
      return;

   g_pilotTelemetry[index].lastStatus = status;
   g_pilotTelemetry[index].lastReason = reason;
   g_pilotTelemetry[index].lastDirection = direction;
}

string BuildPilotTelemetryJson(int index)
{
   if(index < 0 || index >= ArraySize(g_pilotTelemetry))
      return "{}";

   PilotTelemetrySnapshot telemetry = g_pilotTelemetry[index];
   string json = "{";
   json += "\"dayKey\": " + IntegerToString(telemetry.dayKey) + ", ";
   json += "\"evaluationPasses\": " + IntegerToString(telemetry.evaluationPasses) + ", ";
   json += "\"signalHits\": " + IntegerToString(telemetry.signalHits) + ", ";
   json += "\"waitBarSkips\": " + IntegerToString(telemetry.waitBarSkips) + ", ";
   json += "\"noCrossMisses\": " + IntegerToString(telemetry.noCrossMisses) + ", ";
   json += "\"spreadBlocks\": " + IntegerToString(telemetry.spreadBlocks) + ", ";
   json += "\"sessionBlocks\": " + IntegerToString(telemetry.sessionBlocks) + ", ";
   json += "\"newsBlocks\": " + IntegerToString(telemetry.newsBlocks) + ", ";
   json += "\"newsFiltered\": " + IntegerToString(telemetry.newsFiltered) + ", ";
   json += "\"manualBlocks\": " + IntegerToString(telemetry.manualBlocks) + ", ";
   json += "\"portfolioBlocks\": " + IntegerToString(telemetry.portfolioBlocks) + ", ";
   json += "\"inPositionBlocks\": " + IntegerToString(telemetry.inPositionBlocks) + ", ";
   json += "\"regimeBlocks\": " + IntegerToString(telemetry.regimeBlocks) + ", ";
   json += "\"cooldownBlocks\": " + IntegerToString(telemetry.cooldownBlocks) + ", ";
   json += "\"orderSent\": " + IntegerToString(telemetry.orderSent) + ", ";
   json += "\"orderFailed\": " + IntegerToString(telemetry.orderFailed) + ", ";
   json += "\"lastEvalTime\": \"" + JsonEscape(FormatDateTime(telemetry.lastEvalTime, true)) + "\", ";
   json += "\"lastSignalTime\": \"" + JsonEscape(FormatDateTime(telemetry.lastSignalTime, true)) + "\", ";
   json += "\"lastOrderTime\": \"" + JsonEscape(FormatDateTime(telemetry.lastOrderTime, true)) + "\", ";
   json += "\"lastStatus\": \"" + JsonEscape(telemetry.lastStatus) + "\", ";
   json += "\"lastReason\": \"" + JsonEscape(telemetry.lastReason) + "\", ";
   json += "\"lastDirection\": " + IntegerToString(telemetry.lastDirection);
   json += "}";
   return json;
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   StringReplace(value, "\t", "\\t");
   return value;
}

string JsonBool(bool value)
{
   return value ? "true" : "false";
}

string FormatDateTime(datetime value, bool withSeconds = false)
{
   if(value <= 0)
      return "";
   int flags = TIME_DATE | TIME_MINUTES;
   if(withSeconds)
      flags |= TIME_SECONDS;
   return TimeToString(value, flags);
}

string FormatNumber(double value, int digits)
{
   if(!MathIsValidNumber(value))
      value = 0.0;
   return DoubleToString(value, digits);
}

double CalcSpreadPips(string symbol, double bid, double ask)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(point <= 0.0)
      return 0.0;
   double spreadPoints = (ask - bid) / point;
   if(digits == 3 || digits == 5)
      spreadPoints /= 10.0;
   return spreadPoints;
}

bool IsPilotManagedPosition(string comment, long magic)
{
   return (magic == PilotMagic || IsPilotStrategyComment(comment));
}

int CountPilotPositions(string symbol = "")
{
   int count = 0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      string posSymbol = PositionGetString(POSITION_SYMBOL);
      if(StringLen(symbol) > 0 && posSymbol != symbol)
         continue;
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(IsPilotManagedPosition(comment, magic))
         count++;
   }
   return count;
}

bool HasManualPositionOnSymbol(string symbol)
{
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      string posSymbol = PositionGetString(POSITION_SYMBOL);
      if(posSymbol != symbol)
         continue;
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         return true;
   }
   return false;
}

double SumPilotFloatingProfit()
{
   double totalProfit = 0.0;
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;
      totalProfit += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return totalProfit;
}

void UpdatePilotClosedStats()
{
   g_pilotRealizedLossToday = 0.0;
   g_pilotConsecutiveLosses = 0;

   datetime nowServer = CurrentServerTime();
   MqlDateTime parts;
   TimeToStruct(nowServer, parts);
   parts.hour = 0;
   parts.min = 0;
   parts.sec = 0;
   datetime dayStart = StructToTime(parts);

   if(!HistorySelect(dayStart - 86400 * 7, nowServer))
      return;

   int total = HistoryDealsTotal();
   bool streakLocked = false;
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      long dealType = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL)
         continue;
      long entryType = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(!IsExitDeal(entryType))
         continue;
      string comment = HistoryDealGetString(ticket, DEAL_COMMENT);
      long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;

      double net = HistoryDealGetDouble(ticket, DEAL_PROFIT) +
                   HistoryDealGetDouble(ticket, DEAL_SWAP) +
                   HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      datetime dealTime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(dealTime >= dayStart && net < 0.0)
         g_pilotRealizedLossToday += MathAbs(net);

      if(!streakLocked)
      {
         if(net < 0.0)
            g_pilotConsecutiveLosses++;
         else
            streakLocked = true;
      }
   }
}

bool GetLatestPilotClosedTradeForSymbol(string symbol, datetime &closeTime, double &netProfit)
{
   closeTime = 0;
   netProfit = 0.0;

   datetime nowServer = CurrentServerTime();
   if(!HistorySelect(nowServer - 86400 * 7, nowServer))
      return false;

   int total = HistoryDealsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      long dealType = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL)
         continue;
      long entryType = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(!IsExitDeal(entryType))
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != symbol)
         continue;

      string comment = HistoryDealGetString(ticket, DEAL_COMMENT);
      long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;

      closeTime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      netProfit = HistoryDealGetDouble(ticket, DEAL_PROFIT) +
                  HistoryDealGetDouble(ticket, DEAL_SWAP) +
                  HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      return true;
   }

   return false;
}

bool PilotLossCooldownActive(string symbol, string &reason)
{
   reason = "";
   if(PilotLossCooldownMinutes <= 0)
      return false;

   datetime closeTime = 0;
   double netProfit = 0.0;
   if(!GetLatestPilotClosedTradeForSymbol(symbol, closeTime, netProfit))
      return false;
   if(netProfit >= 0.0 || closeTime <= 0)
      return false;

   int elapsedMinutes = (int)((CurrentServerTime() - closeTime) / 60);
   if(elapsedMinutes >= PilotLossCooldownMinutes)
      return false;

   int minutesLeft = PilotLossCooldownMinutes - elapsedMinutes;
   reason = "Loss cooldown active for " + IntegerToString(minutesLeft) +
            "m after " + FormatNumber(MathAbs(netProfit), 2) + " USC stopout";
   return true;
}

bool IsPilotSessionOpen()
{
   if(!PilotRestrictSession)
      return true;
   MqlDateTime parts;
   TimeToStruct(CurrentServerTime(), parts);
   int hour = parts.hour;
   if(PilotSessionStartHour <= PilotSessionEndHour)
      return (hour >= PilotSessionStartHour && hour <= PilotSessionEndHour);
   return (hour >= PilotSessionStartHour || hour <= PilotSessionEndHour);
}

bool IsNewPilotBar(string symbol, ENUM_TIMEFRAMES timeframe, int symbolIndex)
{
   datetime barTime = iTime(symbol, timeframe, 0);
   if(barTime <= 0)
      return false;
   if(g_lastPilotBarTime[symbolIndex] == 0)
   {
      g_lastPilotBarTime[symbolIndex] = barTime;
      return false;
   }
   if(barTime != g_lastPilotBarTime[symbolIndex])
   {
      g_lastPilotBarTime[symbolIndex] = barTime;
      return true;
   }
   return false;
}

string PilotStatusJson(const StrategyStatusSnapshot &state)
{
   string json = "{";
   json += "\"enabled\": " + JsonBool(state.enabled) + ", ";
   json += "\"active\": " + JsonBool(state.active) + ", ";
   json += "\"runtimeLabel\": \"" + JsonEscape(state.runtimeLabel) + "\", ";
   json += "\"status\": \"" + JsonEscape(state.status) + "\", ";
   json += "\"score\": " + FormatNumber(state.score, 1) + ", ";
   json += "\"reason\": \"" + JsonEscape(state.reason) + "\", ";
   json += "\"adaptiveState\": \"" + JsonEscape(state.adaptiveState) + "\", ";
   json += "\"adaptiveReason\": \"" + JsonEscape(state.adaptiveReason) + "\", ";
   json += "\"riskMultiplier\": " + FormatNumber(state.riskMultiplier, 2);
   json += "}";
   return json;
}

string PilotAggregateJson(string scopeSymbol)
{
   int positions = CountPilotPositions(scopeSymbol);
   string json = "{";
   json += "\"enabled\": " + JsonBool(IsPilotLiveMode() && EnablePilotMA) + ", ";
   json += "\"active\": " + JsonBool((IsPilotLiveMode() && EnablePilotMA) && !g_pilotKillSwitch) + ", ";
   json += "\"scopeSymbol\": \"" + JsonEscape(scopeSymbol) + "\", ";
   json += "\"state\": \"" + JsonEscape(g_pilotKillSwitch ? "COOLDOWN" : "CAUTION") + "\", ";
   json += "\"riskMultiplier\": " + FormatNumber((IsPilotLiveMode() && EnablePilotMA) ? 1.0 : 0.0, 2) + ", ";
   json += "\"sampleTrades\": 0, ";
   json += "\"sampleWindowTrades\": 0, ";
   json += "\"winRate\": 0.0, ";
   json += "\"profitFactor\": 0.00, ";
   json += "\"avgNet\": 0.00, ";
   json += "\"netProfit\": 0.00, ";
   json += "\"disabledUntil\": \"\", ";
   json += "\"reason\": \"" + JsonEscape(g_pilotKillSwitch ? g_pilotKillReason : "MT5 0.01 live pilot: M15 trigger, H1 trend filter, 3-bar cross plus pullback continuation, range guard, post-loss cooldown, USD news filter") + "\", ";
   json += "\"positions\": " + IntegerToString(positions) + ", ";
   json += "\"portfolioPositions\": " + IntegerToString(CountPilotPositions());
   json += "}";
   return json;
}
bool EvaluatePilotMASignal(string symbol, int symbolIndex, int &direction, double &score, string &reason, double &slPrice, double &tpPrice, int &evalCode)
{
   direction = 0;
   score = 0.0;
   reason = "Waiting for next evaluation";
   slPrice = 0.0;
   tpPrice = 0.0;
   evalCode = PILOT_EVAL_NONE;
   int signalBars = Bars(symbol, PilotSignalTimeframe);
   int trendBars = Bars(symbol, PilotTrendTimeframe);
   if(signalBars < MathMax(PilotSlowMAPeriod + PilotCrossLookbackBars + 5, PilotATRPeriod + 5) ||
      trendBars < PilotTrendMAPeriod + 5)
   {
      reason = "Not enough bars for M15/H1 pilot";
      evalCode = PILOT_EVAL_NOT_ENOUGH_BARS;
      return false;
   }
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
   {
      reason = "Tick data unavailable";
      evalCode = PILOT_EVAL_TICK_UNAVAILABLE;
      return false;
   }
   double spread = CalcSpreadPips(symbol, tick.bid, tick.ask);
   if(spread > PilotMaxSpreadPips)
   {
      reason = "Spread above pilot limit";
      evalCode = PILOT_EVAL_SPREAD_BLOCK;
      return false;
   }
   if(!IsPilotSessionOpen())
   {
      reason = "Outside pilot trading session";
      evalCode = PILOT_EVAL_SESSION_BLOCK;
      return false;
   }
   double trend1 = MAValue(symbol, PilotTrendTimeframe, PilotTrendMAPeriod, 1, MODE_SMA);
   double trendClose1 = iClose(symbol, PilotTrendTimeframe, 1);
   double atr1 = ATRValue(symbol, PilotSignalTimeframe, PilotATRPeriod, 1);
   double fast1 = MAValue(symbol, PilotSignalTimeframe, PilotFastMAPeriod, 1, MODE_EMA);
   double fast2 = MAValue(symbol, PilotSignalTimeframe, PilotFastMAPeriod, 2, MODE_EMA);
   double slow1 = MAValue(symbol, PilotSignalTimeframe, PilotSlowMAPeriod, 1, MODE_EMA);
   double slow2 = MAValue(symbol, PilotSignalTimeframe, PilotSlowMAPeriod, 2, MODE_EMA);
   double close1 = iClose(symbol, PilotSignalTimeframe, 1);
   double low1 = iLow(symbol, PilotSignalTimeframe, 1);
   double high1 = iHigh(symbol, PilotSignalTimeframe, 1);
   bool buyCross = false;
   bool sellCross = false;
   bool recentBullCross = false;
   bool recentBearCross = false;
   int buyCrossShift = -1;
   int sellCrossShift = -1;
   int recentBullCrossShift = -1;
   int recentBearCrossShift = -1;
   int maxShift = MathMax(1, PilotCrossLookbackBars);
   int continuationMaxShift = MathMax(maxShift, MathMax(4, PilotContinuationLookbackBars));
   for(int shift = 1; shift <= continuationMaxShift; shift++)
   {
      double fastCurr = MAValue(symbol, PilotSignalTimeframe, PilotFastMAPeriod, shift, MODE_EMA);
      double fastPrev = MAValue(symbol, PilotSignalTimeframe, PilotFastMAPeriod, shift + 1, MODE_EMA);
      double slowCurr = MAValue(symbol, PilotSignalTimeframe, PilotSlowMAPeriod, shift, MODE_EMA);
      double slowPrev = MAValue(symbol, PilotSignalTimeframe, PilotSlowMAPeriod, shift + 1, MODE_EMA);
      if(fastCurr == EMPTY_VALUE || fastPrev == EMPTY_VALUE ||
         slowCurr == EMPTY_VALUE || slowPrev == EMPTY_VALUE)
      {
         reason = "Indicator buffers not ready";
         evalCode = PILOT_EVAL_INDICATOR_NOT_READY;
         return false;
      }
      bool bullishCross = (fastPrev <= slowPrev && fastCurr > slowCurr);
      bool bearishCross = (fastPrev >= slowPrev && fastCurr < slowCurr);
      if(!recentBullCross && bullishCross)
      {
         recentBullCross = true;
         recentBullCrossShift = shift;
      }
      if(!recentBearCross && bearishCross)
      {
         recentBearCross = true;
         recentBearCrossShift = shift;
      }
      if(shift > maxShift)
         continue;
      if(!buyCross && bullishCross)
      {
         buyCross = true;
         buyCrossShift = shift;
      }
      if(!sellCross && bearishCross)
      {
         sellCross = true;
         sellCrossShift = shift;
      }
   }

   if(trend1 == EMPTY_VALUE || trendClose1 == 0.0 ||
      fast1 == EMPTY_VALUE || fast2 == EMPTY_VALUE ||
      slow1 == EMPTY_VALUE || slow2 == EMPTY_VALUE ||
      close1 == 0.0 || low1 == 0.0 || high1 == 0.0)
   {
      reason = "Trend filter not ready";
      evalCode = PILOT_EVAL_TREND_NOT_READY;
      return false;
   }
   if(atr1 <= 0.0)
   {
      reason = "ATR unavailable";
      evalCode = PILOT_EVAL_ATR_UNAVAILABLE;
      return false;
   }

    RegimeSnapshot regime = EvaluateRegimeAt(symbol, PilotTrendTimeframe, 0);
    if(PilotBlockRangeEntries &&
       (regime.label == "RANGE" || regime.label == "RANGE_TIGHT"))
    {
       reason = "MA_Cross blocked in " + regime.label + " regime";
       evalCode = PILOT_EVAL_RANGE_BLOCK;
       return false;
    }

   bool buyTrend = (trendClose1 > trend1);
   bool sellTrend = (trendClose1 < trend1);
   bool bullishStructure = (fast1 > slow1 && fast2 > slow2);
   bool bearishStructure = (fast1 < slow1 && fast2 < slow2);
   double touchTolerance = atr1 * 0.20;
   double slowGuardTolerance = atr1 * 0.10;
   bool buyPullbackTouch = (low1 <= fast1 + touchTolerance);
   bool buyPullbackHeld = (low1 >= slow1 - slowGuardTolerance && close1 >= fast1);
   bool sellPullbackTouch = (high1 >= fast1 - touchTolerance);
   bool sellPullbackHeld = (high1 <= slow1 + slowGuardTolerance && close1 <= fast1);
   if(buyCross && buyTrend)
   {
      direction = 1;
      score = 100.0 - (double)(buyCrossShift - 1) * 10.0;
      double stopDistance = atr1 * PilotATRMulitplierSL;
      slPrice = NormalizeDouble(tick.ask - stopDistance, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      tpPrice = NormalizeDouble(tick.ask + stopDistance * PilotRewardRatio, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      reason = "M15 bullish crossover within lookback, H1 trend confirmed";
      evalCode = PILOT_EVAL_SIGNAL_BUY;
      return true;
   }
   if(sellCross && sellTrend)
   {
      direction = -1;
      score = 100.0 - (double)(sellCrossShift - 1) * 10.0;
      double stopDistance = atr1 * PilotATRMulitplierSL;
      slPrice = NormalizeDouble(tick.bid + stopDistance, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      tpPrice = NormalizeDouble(tick.bid - stopDistance * PilotRewardRatio, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      reason = "M15 bearish crossover within lookback, H1 trend confirmed";
      evalCode = PILOT_EVAL_SIGNAL_SELL;
      return true;
   }
   if(recentBullCross && recentBullCrossShift > maxShift &&
      buyTrend && bullishStructure && buyPullbackTouch && buyPullbackHeld)
   {
      direction = 1;
      score = MathMax(62.0, 84.0 - (double)(recentBullCrossShift - maxShift) * 4.0);
      double stopDistance = atr1 * PilotATRMulitplierSL;
      slPrice = NormalizeDouble(tick.ask - stopDistance, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      tpPrice = NormalizeDouble(tick.ask + stopDistance * PilotRewardRatio, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      reason = "M15 bullish continuation after pullback, H1 trend confirmed";
      evalCode = PILOT_EVAL_SIGNAL_BUY;
      return true;
   }
   if(recentBearCross && recentBearCrossShift > maxShift &&
      sellTrend && bearishStructure && sellPullbackTouch && sellPullbackHeld)
   {
      direction = -1;
      score = MathMax(62.0, 84.0 - (double)(recentBearCrossShift - maxShift) * 4.0);
      double stopDistance = atr1 * PilotATRMulitplierSL;
      slPrice = NormalizeDouble(tick.bid + stopDistance, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      tpPrice = NormalizeDouble(tick.bid - stopDistance * PilotRewardRatio, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      reason = "M15 bearish continuation after pullback, H1 trend confirmed";
      evalCode = PILOT_EVAL_SIGNAL_SELL;
      return true;
   }
   score = ((buyTrend || sellTrend) ? 55.0 : 25.0);
   reason = "H1 trend exists but no fresh crossover or healthy pullback continuation";
   evalCode = PILOT_EVAL_NO_CROSS;
   return false;
}
bool SendPilotMarketOrder(string symbol, int direction, double slPrice, double tpPrice)
{
   double volume = NormalizeVolumeForSymbol(symbol, PilotLotSize);
   g_trade.SetExpertMagicNumber(PilotMagic);
   g_trade.SetDeviationInPoints(PilotDeviationPoints);
   g_trade.SetTypeFillingBySymbol(symbol);

   bool ok = false;
   string comment = PilotTradeComment(direction);
   if(direction > 0)
      ok = g_trade.Buy(volume, symbol, 0.0, slPrice, tpPrice, comment);
   else if(direction < 0)
      ok = g_trade.Sell(volume, symbol, 0.0, slPrice, tpPrice, comment);

   if(!ok || (g_trade.ResultRetcode() != TRADE_RETCODE_DONE && g_trade.ResultRetcode() != TRADE_RETCODE_PLACED))
   {
      Print("QuantGod MT5 pilot order failed: symbol=", symbol,
            " dir=", direction, " retcode=", g_trade.ResultRetcode(),
            " comment=", g_trade.ResultComment());
      return false;
   }

   Print("QuantGod MT5 pilot order sent: symbol=", symbol,
         " dir=", direction > 0 ? "BUY" : "SELL",
         " volume=", DoubleToString(volume, 2),
         " sl=", DoubleToString(slPrice, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
         " tp=", DoubleToString(tpPrice, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
   return true;
}

void ClosePilotPositions(const string reason)
{
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;

      g_trade.SetExpertMagicNumber(PilotMagic);
      g_trade.SetDeviationInPoints(PilotDeviationPoints);
      g_trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
      bool closed = g_trade.PositionClose(ticket);
      Print("QuantGod MT5 pilot emergency close ticket=", ticket,
            " ok=", (closed ? "true" : "false"),
            " retcode=", g_trade.ResultRetcode(),
            " reason=", reason);
   }
}

bool ModifyPilotPositionStops(ulong ticket, string symbol, double slPrice, double tpPrice)
{
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   MqlTradeRequest request;
   MqlTradeResult result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol = symbol;
   request.sl = NormalizeDouble(slPrice, digits);
   request.tp = NormalizeDouble(tpPrice, digits);
   request.magic = PilotMagic;

   ResetLastError();
   bool ok = OrderSend(request, result);
   if(!ok || (result.retcode != TRADE_RETCODE_DONE && result.retcode != TRADE_RETCODE_PLACED))
   {
      static datetime lastWarn = 0;
      datetime now = CurrentServerTime();
      if(now - lastWarn >= 60)
      {
         lastWarn = now;
         Print("QuantGod MT5 breakeven modify failed: ticket=", ticket,
               " symbol=", symbol,
               " retcode=", result.retcode,
               " err=", GetLastError(),
               " comment=", result.comment);
      }
      return false;
   }

   return true;
}

void ManagePilotBreakevenStops()
{
   bool breakevenOn = (EnablePilotBreakevenProtect && PilotBreakevenTriggerPips > 0.0);
   bool trailingOn = (EnablePilotTrailingStop &&
                      PilotTrailingStartPips > 0.0 &&
                      PilotTrailingDistancePips > 0.0);
   if(!breakevenOn && !trailingOn)
      return;

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int ageMinutes = (int)MathMax(0, (long)(CurrentServerTime() - openTime) / 60);
      if(ageMinutes < PilotBreakevenMinAgeMinutes)
         continue;

      double pip = PipSize(symbol);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      if(pip <= 0.0 || point <= 0.0)
         continue;

      MqlTick tick;
      ZeroMemory(tick);
      if(!SymbolInfoTick(symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
         continue;

      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      long positionType = PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double lockPips = MathMax(0.0, PilotBreakevenLockPips);
      double favorablePips = 0.0;
      double targetSL = 0.0;
      bool shouldModify = false;

      int stopsLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      int freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
      double minDistance = (double)MathMax(stopsLevel, freezeLevel) * point + point;
      double stepDistance = MathMax(0.1, PilotTrailingStepPips) * pip;

      if(positionType == POSITION_TYPE_BUY)
      {
         favorablePips = (tick.bid - openPrice) / pip;
         if(breakevenOn && favorablePips >= PilotBreakevenTriggerPips)
            targetSL = NormalizeDouble(openPrice + lockPips * pip, digits);
         if(trailingOn && favorablePips >= PilotTrailingStartPips)
         {
            double trailingSL = NormalizeDouble(tick.bid - PilotTrailingDistancePips * pip, digits);
            if(targetSL <= 0.0 || trailingSL > targetSL)
               targetSL = trailingSL;
         }
         if(targetSL <= 0.0)
            continue;

         if(currentSL > 0.0 && currentSL >= targetSL - stepDistance)
            continue;
         if(targetSL > tick.bid - minDistance)
            continue;
         shouldModify = true;
      }
      else if(positionType == POSITION_TYPE_SELL)
      {
         favorablePips = (openPrice - tick.ask) / pip;
         if(breakevenOn && favorablePips >= PilotBreakevenTriggerPips)
            targetSL = NormalizeDouble(openPrice - lockPips * pip, digits);
         if(trailingOn && favorablePips >= PilotTrailingStartPips)
         {
            double trailingSL = NormalizeDouble(tick.ask + PilotTrailingDistancePips * pip, digits);
            if(targetSL <= 0.0 || trailingSL < targetSL)
               targetSL = trailingSL;
         }
         if(targetSL <= 0.0)
            continue;

         if(currentSL > 0.0 && currentSL <= targetSL + stepDistance)
            continue;
         if(targetSL < tick.ask + minDistance)
            continue;
         shouldModify = true;
      }
      else
         continue;

      if(shouldModify && ModifyPilotPositionStops(ticket, symbol, targetSL, currentTP))
      {
         Print("QuantGod MT5 pilot stop protected ticket=", ticket,
               " symbol=", symbol,
               " age=", ageMinutes, "m",
               " favorablePips=", DoubleToString(favorablePips, 1),
               " newSL=", DoubleToString(targetSL, digits));
      }
   }
}

bool ManualSafetySymbolAllowed(string symbol)
{
   if(!ManualSafetyWatchlistOnly)
      return true;
   return (FindSymbolIndex(symbol) >= 0);
}

void ManageManualSafetyGuard()
{
   if(!EnableManualSafetyGuard)
      return;

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      if(!ManualSafetySymbolAllowed(symbol))
         continue;

      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(IsPilotManagedPosition(comment, magic))
         continue;

      double netProfit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      if(ManualSafetyCloseOnMaxLoss &&
         ManualSafetyMaxLossUSC > 0.0 &&
         netProfit <= -MathAbs(ManualSafetyMaxLossUSC))
      {
         g_trade.SetDeviationInPoints(PilotDeviationPoints);
         g_trade.SetTypeFillingBySymbol(symbol);
         bool closed = g_trade.PositionClose(ticket);
         Print("QuantGod MT5 manual safety close ticket=", ticket,
               " symbol=", symbol,
               " net=", DoubleToString(netProfit, 2),
               " ok=", (closed ? "true" : "false"),
               " retcode=", g_trade.ResultRetcode());
         continue;
      }

      bool initialSlOn = (ManualSafetyInitialSLPips > 0.0);
      bool trailingOn = (EnableManualTrailingStop &&
                         ManualSafetyTrailingStartPips > 0.0 &&
                         ManualSafetyTrailingDistancePips > 0.0);
      if(!initialSlOn && !trailingOn)
         continue;

      double pip = PipSize(symbol);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      if(pip <= 0.0 || point <= 0.0)
         continue;

      MqlTick tick;
      ZeroMemory(tick);
      if(!SymbolInfoTick(symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
         continue;

      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      long positionType = PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double lockPips = MathMax(0.0, ManualSafetyBreakevenLockPips);
      double favorablePips = 0.0;
      double targetSL = 0.0;
      bool shouldModify = false;

      int stopsLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      int freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
      double minDistance = (double)MathMax(stopsLevel, freezeLevel) * point + point;
      double stepDistance = MathMax(0.1, ManualSafetyTrailingStepPips) * pip;

      if(positionType == POSITION_TYPE_BUY)
      {
         favorablePips = (tick.bid - openPrice) / pip;
         double fallbackSL = initialSlOn ? NormalizeDouble(openPrice - ManualSafetyInitialSLPips * pip, digits) : 0.0;
         if(ManualSafetyBreakevenTriggerPips > 0.0 &&
            favorablePips >= ManualSafetyBreakevenTriggerPips)
            targetSL = NormalizeDouble(openPrice + lockPips * pip, digits);
         if(trailingOn && favorablePips >= ManualSafetyTrailingStartPips)
         {
            double trailingSL = NormalizeDouble(tick.bid - ManualSafetyTrailingDistancePips * pip, digits);
            if(targetSL <= 0.0 || trailingSL > targetSL)
               targetSL = trailingSL;
         }
         if(targetSL <= 0.0 && initialSlOn && (currentSL <= 0.0 || currentSL < fallbackSL - point))
            targetSL = fallbackSL;
         if(targetSL <= 0.0)
            continue;

         if(currentSL > 0.0 && currentSL >= targetSL - stepDistance)
            continue;
         if(targetSL > tick.bid - minDistance)
            continue;
         shouldModify = true;
      }
      else if(positionType == POSITION_TYPE_SELL)
      {
         favorablePips = (openPrice - tick.ask) / pip;
         double fallbackSL = initialSlOn ? NormalizeDouble(openPrice + ManualSafetyInitialSLPips * pip, digits) : 0.0;
         if(ManualSafetyBreakevenTriggerPips > 0.0 &&
            favorablePips >= ManualSafetyBreakevenTriggerPips)
            targetSL = NormalizeDouble(openPrice - lockPips * pip, digits);
         if(trailingOn && favorablePips >= ManualSafetyTrailingStartPips)
         {
            double trailingSL = NormalizeDouble(tick.ask + ManualSafetyTrailingDistancePips * pip, digits);
            if(targetSL <= 0.0 || trailingSL < targetSL)
               targetSL = trailingSL;
         }
         if(targetSL <= 0.0 && initialSlOn && (currentSL <= 0.0 || currentSL > fallbackSL + point))
            targetSL = fallbackSL;
         if(targetSL <= 0.0)
            continue;

         if(currentSL > 0.0 && currentSL <= targetSL + stepDistance)
            continue;
         if(targetSL < tick.ask + minDistance)
            continue;
         shouldModify = true;
      }

      if(shouldModify && ModifyPilotPositionStops(ticket, symbol, targetSL, currentTP))
      {
         Print("QuantGod MT5 manual safety protected ticket=", ticket,
               " symbol=", symbol,
               " favorablePips=", DoubleToString(favorablePips, 1),
               " newSL=", DoubleToString(targetSL, digits));
      }
   }
}

void RunPilotExecutionLoop()
{
   ResetPilotRuntimeStates();
   EnsurePilotTelemetryState();
   if(!IsPilotLiveMode() || !EnablePilotMA)
      return;
   UpdatePilotClosedStats();
   RefreshNewsFilterState();
   if(g_pilotRealizedLossToday >= PilotMaxRealizedLossDayUSC)
   {
      g_pilotKillSwitch = true;
      g_pilotKillReason = "Daily realized loss limit reached";
   }
   if(g_pilotConsecutiveLosses >= PilotMaxConsecutiveLosses)
   {
      g_pilotKillSwitch = true;
      g_pilotKillReason = "Consecutive loss limit reached";
   }
   if(SumPilotFloatingProfit() <= -MathAbs(PilotMaxFloatingLossUSC))
   {
      g_pilotKillSwitch = true;
      g_pilotKillReason = "Floating loss limit reached";
   }
   if(g_pilotKillSwitch && PilotCloseOnKillSwitch)
      ClosePilotPositions(g_pilotKillReason);
   ManageManualSafetyGuard();
   if(!g_pilotKillSwitch)
      ManagePilotBreakevenStops();
   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      string symbol = g_symbols[i];
      g_maRuntimeStates[i].enabled = true;
      g_maRuntimeStates[i].riskMultiplier = 1.0;
      g_maRuntimeStates[i].adaptiveState = g_pilotKillSwitch ? "COOLDOWN" : "CAUTION";
      g_maRuntimeStates[i].adaptiveReason = g_pilotKillSwitch
         ? g_pilotKillReason
         : "HFM MT5 0.01 live pilot with M15 trigger, H1 trend filter, range guard, post-loss cooldown, USD news filter, hard SL/TP, and kill switch";
      if(g_pilotKillSwitch)
      {
         g_maRuntimeStates[i].active = false;
         g_maRuntimeStates[i].runtimeLabel = "PAUSED";
         g_maRuntimeStates[i].status = "AUTO_PAUSED";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = g_pilotKillReason;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      if(CountPilotPositions() >= PilotMaxTotalPositions)
      {
         g_maRuntimeStates[i].active = false;
         g_maRuntimeStates[i].runtimeLabel = "LIMIT";
         g_maRuntimeStates[i].status = "PORTFOLIO_LIMIT";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = "Portfolio position limit reached";
         g_pilotTelemetry[i].portfolioBlocks++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      if(CountPilotPositions(symbol) >= PilotMaxPositionsPerSymbol)
      {
         g_maRuntimeStates[i].active = true;
         g_maRuntimeStates[i].runtimeLabel = "ON";
         g_maRuntimeStates[i].status = "IN_POSITION";
         g_maRuntimeStates[i].score = 100.0;
         g_maRuntimeStates[i].reason = "Pilot position already open on this symbol";
         g_pilotTelemetry[i].inPositionBlocks++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      if(PilotBlockManualPerSymbol && HasManualPositionOnSymbol(symbol))
      {
         g_maRuntimeStates[i].active = false;
         g_maRuntimeStates[i].runtimeLabel = "BLOCK";
         g_maRuntimeStates[i].status = "POSITION_LIMIT";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = "Manual position on symbol blocks pilot entries";
         g_pilotTelemetry[i].manualBlocks++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      string cooldownReason = "";
      if(PilotLossCooldownActive(symbol, cooldownReason))
      {
         g_maRuntimeStates[i].active = false;
         g_maRuntimeStates[i].runtimeLabel = "COOL";
         g_maRuntimeStates[i].status = "LOSS_COOLDOWN";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = cooldownReason;
         g_pilotTelemetry[i].cooldownBlocks++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      string newsReason = "";
      if(PilotNewsBlocksSymbol(symbol, newsReason))
      {
         g_maRuntimeStates[i].active = false;
         g_maRuntimeStates[i].runtimeLabel = "NEWS";
         g_maRuntimeStates[i].status = "NEWS_BLOCK";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = newsReason;
         g_pilotTelemetry[i].newsBlocks++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      if(!IsNewPilotBar(symbol, PilotSignalTimeframe, i))
      {
         g_maRuntimeStates[i].active = true;
         g_maRuntimeStates[i].runtimeLabel = "ON";
         g_maRuntimeStates[i].status = "WAIT_BAR";
         g_maRuntimeStates[i].score = 0.0;
         g_maRuntimeStates[i].reason = "Waiting for next M15 bar";
         if(g_newsState.biasActive)
            g_maRuntimeStates[i].reason += " | news " + PilotActionLabelForSymbol(symbol) +
               " after " + g_newsState.eventName;
         g_pilotTelemetry[i].waitBarSkips++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      int direction = 0;
      double score = 0.0;
      string reason = "";
      double slPrice = 0.0;
      double tpPrice = 0.0;
      int evalCode = PILOT_EVAL_NONE;
      g_pilotTelemetry[i].evaluationPasses++;
      g_pilotTelemetry[i].lastEvalTime = TimeCurrent();
      bool hasSignal = EvaluatePilotMASignal(symbol, i, direction, score, reason, slPrice, tpPrice, evalCode);
      g_maRuntimeStates[i].active = true;
      g_maRuntimeStates[i].runtimeLabel = "ON";
      g_maRuntimeStates[i].score = score;
      g_maRuntimeStates[i].reason = reason;
      if(!hasSignal || direction == 0)
      {
         g_maRuntimeStates[i].status = "WAIT_SIGNAL";
         if(evalCode == PILOT_EVAL_SPREAD_BLOCK)
            g_pilotTelemetry[i].spreadBlocks++;
         else if(evalCode == PILOT_EVAL_SESSION_BLOCK)
            g_pilotTelemetry[i].sessionBlocks++;
         else if(evalCode == PILOT_EVAL_RANGE_BLOCK)
            g_pilotTelemetry[i].regimeBlocks++;
         else if(evalCode == PILOT_EVAL_NO_CROSS)
            g_pilotTelemetry[i].noCrossMisses++;
         if(g_newsState.biasActive)
            g_maRuntimeStates[i].reason = reason + " | news " + PilotActionLabelForSymbol(symbol) +
               " after " + g_newsState.eventName;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason);
         continue;
      }
      g_pilotTelemetry[i].signalHits++;
      g_pilotTelemetry[i].lastSignalTime = TimeCurrent();
      MqlTick tick;
      ZeroMemory(tick);
      SymbolInfoTick(symbol, tick);
      if(!PilotDirectionAllowedByNews(symbol, direction, tick, newsReason))
      {
         g_maRuntimeStates[i].status = "NEWS_FILTERED";
         g_maRuntimeStates[i].reason = newsReason;
         g_pilotTelemetry[i].newsFiltered++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason, direction);
         continue;
      }
      if(SendPilotMarketOrder(symbol, direction, slPrice, tpPrice))
      {
         g_maRuntimeStates[i].status = (direction > 0) ? "BUY_ORDER_SENT" : "SELL_ORDER_SENT";
         g_maRuntimeStates[i].reason = reason + " | Pilot order sent with 0.01 lot";
         g_pilotTelemetry[i].orderSent++;
         g_pilotTelemetry[i].lastOrderTime = TimeCurrent();
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason, direction);
      }
      else
      {
         g_maRuntimeStates[i].status = "ORDER_SEND_FAILED";
         g_maRuntimeStates[i].reason = reason + " | Order send failed, check MT5 Journal";
         g_pilotTelemetry[i].orderFailed++;
         UpdatePilotTelemetrySnapshot(i, g_maRuntimeStates[i].status, g_maRuntimeStates[i].reason, direction);
      }
   }
}
string StrategyPlaceholderJson(string scopeSymbol, string statusReason)
{
   string json = "{";
   json += "\"enabled\": false, ";
   json += "\"active\": false, ";
   json += "\"scopeSymbol\": \"" + JsonEscape(scopeSymbol) + "\", ";
   json += "\"state\": \"WARMUP\", ";
   json += "\"riskMultiplier\": 0.00, ";
   json += "\"sampleTrades\": 0, ";
   json += "\"sampleWindowTrades\": 0, ";
   json += "\"winRate\": 0.0, ";
   json += "\"profitFactor\": 0.00, ";
   json += "\"avgNet\": 0.00, ";
   json += "\"netProfit\": 0.00, ";
   json += "\"disabledUntil\": \"\", ";
   json += "\"reason\": \"" + JsonEscape(statusReason) + "\", ";
   json += "\"positions\": 0, ";
   json += "\"portfolioPositions\": 0";
   json += "}";
   return json;
}

string SymbolStrategyPlaceholderJson(string statusReason)
{
   string json = "{";
   json += "\"status\": \"NO_DATA\", ";
   json += "\"score\": 0.0, ";
   json += "\"reason\": \"" + JsonEscape(statusReason) + "\", ";
   json += "\"adaptiveState\": \"WARMUP\", ";
   json += "\"adaptiveReason\": \"" + JsonEscape("MT5 phase 1 skeleton: execution engine not ported yet") + "\", ";
   json += "\"active\": false, ";
   json += "\"runtimeLabel\": \"PORT\", ";
   json += "\"riskMultiplier\": 0.00";
   json += "}";
   return json;
}

string DiagnosticPlaceholderJson(string statusReason)
{
   string json = "{";
   json += "\"status\": \"NO_DATA\", ";
   json += "\"score\": 0.0, ";
   json += "\"reason\": \"" + JsonEscape(statusReason) + "\"";
   json += "}";
   return json;
}

string BuildSymbolStrategyJson(string symbol, int symbolIndex, string strategyKey)
{
   if(strategyKey == "MA_Cross" && symbolIndex >= 0 && symbolIndex < ArraySize(g_maRuntimeStates) && (EnablePilotMA || IsPilotLiveMode()))
      return PilotStatusJson(g_maRuntimeStates[symbolIndex]);

   string placeholderReason = "MT5 phase 1 skeleton: JSON export is live, strategy execution port is not implemented yet";
   return SymbolStrategyPlaceholderJson(placeholderReason);
}

string BuildRootStrategyJson(string strategyKey)
{
   if(strategyKey == "MA_Cross" && (EnablePilotMA || IsPilotLiveMode()))
      return PilotAggregateJson(g_focusSymbol);

   string reason = "MT5 phase 1 skeleton: adaptive control and strategy execution have not been ported yet";
   return StrategyPlaceholderJson(g_focusSymbol, reason);
}

string BuildRootDiagnosticJson(string strategyKey)
{
   if(strategyKey == "MA_Cross" && ArraySize(g_maRuntimeStates) > 0 && (EnablePilotMA || IsPilotLiveMode()))
   {
      StrategyStatusSnapshot state = g_maRuntimeStates[0];
      string json = "{";
      json += "\"status\": \"" + JsonEscape(state.status) + "\", ";
      json += "\"score\": " + FormatNumber(state.score, 1) + ", ";
      json += "\"reason\": \"" + JsonEscape(state.reason) + "\"";
      json += "}";
      return json;
   }

   string reason = "MT5 phase 1 skeleton: diagnostics become live after the MT5 strategy engine is ported";
   return DiagnosticPlaceholderJson(reason);
}

string DealEntryToPositionTypeString(long dealType)
{
   if(dealType == DEAL_TYPE_BUY)
      return "BUY";
   if(dealType == DEAL_TYPE_SELL)
      return "SELL";
   return "UNKNOWN";
}

string PositionTypeToString(long positionType)
{
   if(positionType == POSITION_TYPE_BUY)
      return "BUY";
   if(positionType == POSITION_TYPE_SELL)
      return "SELL";
   return "UNKNOWN";
}

string InferTradeSource(string comment)
{
   string upper = ToUpperString(comment);
   if(StringFind(upper, "QG_") >= 0 || StringFind(upper, "QUANTGOD") >= 0)
      return "EA";
   return "MANUAL";
}

string InferStrategyFromComment(string comment)
{
   if(StringFind(comment, "QG_MA_Cross") >= 0)
      return "MA_Cross";
   if(StringFind(comment, "QG_RSI_Rev") >= 0)
      return "RSI_Reversal";
   if(StringFind(comment, "QG_BB_Triple") >= 0)
      return "BB_Triple";
   if(StringFind(comment, "QG_MACD_Div") >= 0)
      return "MACD_Divergence";
   if(StringFind(comment, "QG_SR_Break") >= 0)
      return "SR_Breakout";
   if(InferTradeSource(comment) == "EA")
      return "QuantGod/Other";
   return "Manual/Other";
}

double PipSize(string symbol)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(point <= 0.0)
      return 0.0;
   if(digits == 3 || digits == 5)
      return point * 10.0;
   return point;
}

string TimeframeLabel(ENUM_TIMEFRAMES timeframe)
{
   if(timeframe == PERIOD_M1) return "M1";
   if(timeframe == PERIOD_M5) return "M5";
   if(timeframe == PERIOD_M15) return "M15";
   if(timeframe == PERIOD_M30) return "M30";
   if(timeframe == PERIOD_H1) return "H1";
   if(timeframe == PERIOD_H4) return "H4";
   if(timeframe == PERIOD_D1) return "D1";
   return "UNKNOWN";
}

double ReadSingleBufferValue(int handle, int bufferIndex, int shift)
{
   if(handle == INVALID_HANDLE)
      return 0.0;

   double values[];
   ArraySetAsSeries(values, true);
   int copied = CopyBuffer(handle, bufferIndex, shift, 1, values);
   IndicatorRelease(handle);
   if(copied <= 0)
      return 0.0;
   return values[0];
}

double MAValue(string symbol, ENUM_TIMEFRAMES timeframe, int period, int shift, ENUM_MA_METHOD method)
{
   int handle = iMA(symbol, timeframe, period, 0, method, PRICE_CLOSE);
   return ReadSingleBufferValue(handle, 0, shift);
}

double ATRValue(string symbol, ENUM_TIMEFRAMES timeframe, int period, int shift)
{
   int handle = iATR(symbol, timeframe, period);
   return ReadSingleBufferValue(handle, 0, shift);
}

RegimeSnapshot EvaluateRegimeAt(string symbol, ENUM_TIMEFRAMES timeframe, datetime eventTime)
{
   RegimeSnapshot snapshot;
   snapshot.label = "UNKNOWN";
   snapshot.timeframe = TimeframeLabel(timeframe);
   snapshot.directionalMovePips = 0.0;
   snapshot.averageRangePips = 0.0;
   snapshot.recentRangePips = 0.0;

   if(StringLen(symbol) == 0)
      return snapshot;

   datetime referenceTime = eventTime;
   if(referenceTime <= 0)
      referenceTime = TimeTradeServer();
   if(referenceTime <= 0)
      referenceTime = TimeCurrent();

   int shift = iBarShift(symbol, timeframe, referenceTime, false);
   if(shift < 0)
      return snapshot;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, timeframe, shift, 20, rates);
   if(copied < 8)
      return snapshot;

   double pipSize = PipSize(symbol);
   if(pipSize <= 0.0)
      return snapshot;

   int moveIndex = MathMin(5, copied - 1);
   double movePips = (rates[0].close - rates[moveIndex].close) / pipSize;

   int avgCount = MathMin(14, copied);
   double avgRangePips = 0.0;
   for(int i = 0; i < avgCount; i++)
      avgRangePips += (rates[i].high - rates[i].low) / pipSize;
   avgRangePips /= avgCount;

   int recentCount = MathMin(3, copied);
   double recentRangePips = 0.0;
   for(int i = 0; i < recentCount; i++)
      recentRangePips += (rates[i].high - rates[i].low) / pipSize;
   recentRangePips /= recentCount;

   snapshot.directionalMovePips = movePips;
   snapshot.averageRangePips = avgRangePips;
   snapshot.recentRangePips = recentRangePips;

   if(avgRangePips <= 0.0)
      return snapshot;

   double absMovePips = MathAbs(movePips);
   bool expanding = (recentRangePips >= avgRangePips * 1.20);
   bool tightening = (recentRangePips <= avgRangePips * 0.70);

   if(absMovePips >= avgRangePips * 1.10)
   {
      if(movePips > 0.0)
         snapshot.label = expanding ? "TREND_EXP_UP" : "TREND_UP";
      else
         snapshot.label = expanding ? "TREND_EXP_DOWN" : "TREND_DOWN";
   }
   else if(tightening)
   {
      snapshot.label = "RANGE_TIGHT";
   }
   else
   {
      snapshot.label = "RANGE";
   }

   return snapshot;
}

string CsvEscape(string value)
{
   string escaped = value;
   StringReplace(escaped, "\"", "\"\"");
   return "\"" + escaped + "\"";
}

bool IsExitDeal(long entryType)
{
   return (entryType == DEAL_ENTRY_OUT || entryType == DEAL_ENTRY_OUT_BY || entryType == DEAL_ENTRY_INOUT);
}

bool IsEntryDeal(long entryType)
{
   return (entryType == DEAL_ENTRY_IN || entryType == DEAL_ENTRY_INOUT);
}

bool FindPositionEntryDeal(ulong positionId, ulong &entryTicket)
{
   int total = HistoryDealsTotal();
   entryTicket = 0;

   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((ulong)HistoryDealGetInteger(ticket, DEAL_POSITION_ID) != positionId)
         continue;
      long entryType = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(!IsEntryDeal(entryType))
         continue;
      entryTicket = ticket;
      return true;
   }

   return false;
}

int FindStrategyAggregateIndex(StrategyAggregateRecord &values[], string symbol, string strategy, string timeframe)
{
   for(int i = 0; i < ArraySize(values); i++)
   {
      if(values[i].symbol == symbol && values[i].strategy == strategy && values[i].timeframe == timeframe)
         return i;
   }
   return -1;
}

int FindRegimeAggregateIndex(RegimeAggregateRecord &values[], string symbol, string strategy, string timeframe, string entryRegime)
{
   for(int i = 0; i < ArraySize(values); i++)
   {
      if(values[i].symbol == symbol &&
         values[i].strategy == strategy &&
         values[i].timeframe == timeframe &&
         values[i].entryRegime == entryRegime)
         return i;
   }
   return -1;
}

void WriteTextFile(string fileName, string content)
{
   ResetLastError();
   int handle = FileOpen(fileName,
                         FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE,
                         0, CP_UTF8);
   if(handle == INVALID_HANDLE)
   {
      Print("QuantGod MT5 skeleton failed to open file for write: ", fileName, " err=", GetLastError());
      return;
   }
   FileWriteString(handle, content);
   FileFlush(handle);
   FileClose(handle);
}

void UpdateShadowChartComment(string tradeStatus, bool connected, long accountLogin)
{
   string message = IsPilotLiveMode() ? "QuantGod MT5 Live Pilot\r\n" : "QuantGod MT5 Shadow\r\n";
   message += "Status: " + tradeStatus + "\r\n";
   message += "ReadOnly: " + (ReadOnlyMode ? "true" : "false") + "\r\n";
   message += "PilotAuto: " + (IsPilotLiveMode() ? "true" : "false") + "\r\n";
   message += "Focus: " + g_focusSymbol + "\r\n";
   message += "Watchlist: " + g_resolvedWatchlist + "\r\n";
   message += "Account: " + IntegerToString((int)accountLogin) + "\r\n";
   message += "Connected: " + (connected ? "true" : "false");
   Comment(message);
}

string BuildTradeJournalCsv(TradeJournalRecord &journal[])
{
   string csv = "DealTicket,PositionId,EventType,Side,Symbol,Lots,Price,GrossProfit,Commission,Swap,NetProfit,EventTime,Strategy,Source,Regime,RegimeTimeframe,Comment\r\n";

   for(int i = 0; i < ArraySize(journal); i++)
   {
      TradeJournalRecord record = journal[i];
      csv += IntegerToString((int)record.dealTicket) + ",";
      csv += IntegerToString((int)record.positionId) + ",";
      csv += CsvEscape(record.eventType) + ",";
      csv += CsvEscape(record.side) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += FormatNumber(record.lots, 2) + ",";
      csv += FormatNumber(record.price, (int)SymbolInfoInteger(record.symbol, SYMBOL_DIGITS)) + ",";
      csv += FormatNumber(record.grossProfit, 2) + ",";
      csv += FormatNumber(record.commission, 2) + ",";
      csv += FormatNumber(record.swap, 2) + ",";
      csv += FormatNumber(record.netProfit, 2) + ",";
      csv += CsvEscape(FormatDateTime(record.eventTime)) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.source) + ",";
      csv += CsvEscape(record.regime) + ",";
      csv += CsvEscape(record.regimeTimeframe) + ",";
      csv += CsvEscape(record.comment) + "\r\n";
   }

   return csv;
}

string BuildCloseHistoryCsv(ClosedTradeRecord &closedTrades[])
{
   string csv = "ExitTicket,PositionId,Type,Symbol,Lots,OpenTime,CloseTime,DurationMinutes,OpenPrice,ClosePrice,GrossProfit,Commission,Swap,NetProfit,Strategy,Source,EntryRegime,ExitRegime,RegimeTimeframe,Comment\r\n";

   for(int i = 0; i < ArraySize(closedTrades); i++)
   {
      ClosedTradeRecord record = closedTrades[i];
      csv += IntegerToString((int)record.ticket) + ",";
      csv += IntegerToString((int)record.positionId) + ",";
      csv += CsvEscape(record.type) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += FormatNumber(record.lots, 2) + ",";
      csv += CsvEscape(FormatDateTime(record.openTime)) + ",";
      csv += CsvEscape(FormatDateTime(record.closeTime)) + ",";
      csv += IntegerToString(record.durationMinutes) + ",";
      csv += FormatNumber(record.openPrice, (int)SymbolInfoInteger(record.symbol, SYMBOL_DIGITS)) + ",";
      csv += FormatNumber(record.closePrice, (int)SymbolInfoInteger(record.symbol, SYMBOL_DIGITS)) + ",";
      csv += FormatNumber(record.grossProfit, 2) + ",";
      csv += FormatNumber(record.commission, 2) + ",";
      csv += FormatNumber(record.swap, 2) + ",";
      csv += FormatNumber(record.actualProfit, 2) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.source) + ",";
      csv += CsvEscape(record.entryRegime) + ",";
      csv += CsvEscape(record.exitRegime) + ",";
      csv += CsvEscape(record.regimeTimeframe) + ",";
      csv += CsvEscape(record.comment) + "\r\n";
   }

   return csv;
}

string BuildTradeOutcomeLabelsCsv(ClosedTradeRecord &closedTrades[])
{
   string csv = "LabelTimeLocal,LabelTimeServer,PositionId,ExitTicket,Symbol,Type,Strategy,Source,OpenTime,CloseTime,DurationMinutes,NetProfit,EntryRegime,ExitRegime,RegimeTimeframe,OutcomeLabel,Comment\r\n";
   datetime serverClock = TimeTradeServer();
   if(serverClock <= 0)
      serverClock = TimeCurrent();

   for(int i = 0; i < ArraySize(closedTrades); i++)
   {
      ClosedTradeRecord record = closedTrades[i];
      string outcome = "FLAT";
      if(record.actualProfit > 0.0)
         outcome = "WIN";
      else if(record.actualProfit < 0.0)
         outcome = "LOSS";

      csv += CsvEscape(FormatDateTime(TimeLocal(), true)) + ",";
      csv += CsvEscape(FormatDateTime(serverClock, true)) + ",";
      csv += IntegerToString((int)record.positionId) + ",";
      csv += IntegerToString((int)record.ticket) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += CsvEscape(record.type) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.source) + ",";
      csv += CsvEscape(FormatDateTime(record.openTime)) + ",";
      csv += CsvEscape(FormatDateTime(record.closeTime)) + ",";
      csv += IntegerToString(record.durationMinutes) + ",";
      csv += FormatNumber(record.actualProfit, 2) + ",";
      csv += CsvEscape(record.entryRegime) + ",";
      csv += CsvEscape(record.exitRegime) + ",";
      csv += CsvEscape(record.regimeTimeframe) + ",";
      csv += CsvEscape(outcome) + ",";
      csv += CsvEscape(record.comment) + "\r\n";
   }

   return csv;
}

string BuildTradeEventLinksCsv(ClosedTradeRecord &closedTrades[], TradeJournalRecord &journal[])
{
   string csv = "PositionId,Symbol,Strategy,Source,EntryDeal,ExitDeal,OpenTime,CloseTime,DurationMinutes,EntryRegime,ExitRegime,RegimeTimeframe,Status,Comment\r\n";
   string emittedKeys[];
   ArrayResize(emittedKeys, 0);

   for(int i = 0; i < ArraySize(closedTrades); i++)
   {
      ClosedTradeRecord record = closedTrades[i];
      ulong entryTicket = 0;
      FindPositionEntryDeal(record.positionId, entryTicket);
      csv += IntegerToString((int)record.positionId) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.source) + ",";
      csv += IntegerToString((int)entryTicket) + ",";
      csv += IntegerToString((int)record.ticket) + ",";
      csv += CsvEscape(FormatDateTime(record.openTime)) + ",";
      csv += CsvEscape(FormatDateTime(record.closeTime)) + ",";
      csv += IntegerToString(record.durationMinutes) + ",";
      csv += CsvEscape(record.entryRegime) + ",";
      csv += CsvEscape(record.exitRegime) + ",";
      csv += CsvEscape(record.regimeTimeframe) + ",";
      csv += CsvEscape("CLOSED") + ",";
      csv += CsvEscape(record.comment) + "\r\n";
      PushString(emittedKeys, IntegerToString((int)record.positionId));
   }

   int totalPositions = PositionsTotal();
   for(int i = 0; i < totalPositions; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      ulong positionId = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      string key = IntegerToString((int)positionId);
      bool alreadyEmitted = false;
      for(int e = 0; e < ArraySize(emittedKeys); e++)
      {
         if(emittedKeys[e] == key)
         {
            alreadyEmitted = true;
            break;
         }
      }
      if(alreadyEmitted)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      string comment = PositionGetString(POSITION_COMMENT);
      string strategy = InferStrategyFromComment(comment);
      string source = InferTradeSource(comment);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int durationMinutes = (int)MathMax(0, (long)((TimeTradeServer() > 0 ? TimeTradeServer() : TimeCurrent()) - openTime) / 60);
      RegimeSnapshot entryRegime = EvaluateRegimeAt(symbol, PERIOD_H1, openTime);
      RegimeSnapshot currentRegime = EvaluateRegimeAt(symbol, PERIOD_H1, 0);
      ulong entryTicket = 0;
      FindPositionEntryDeal(positionId, entryTicket);

      csv += IntegerToString((int)positionId) + ",";
      csv += CsvEscape(symbol) + ",";
      csv += CsvEscape(strategy) + ",";
      csv += CsvEscape(source) + ",";
      csv += IntegerToString((int)entryTicket) + ",";
      csv += "0,";
      csv += CsvEscape(FormatDateTime(openTime)) + ",";
      csv += CsvEscape("") + ",";
      csv += IntegerToString(durationMinutes) + ",";
      csv += CsvEscape(entryRegime.label) + ",";
      csv += CsvEscape(currentRegime.label) + ",";
      csv += CsvEscape(currentRegime.timeframe) + ",";
      csv += CsvEscape("OPEN") + ",";
      csv += CsvEscape(comment) + "\r\n";
   }

   return csv;
}

void BuildAggregates(SymbolSnapshot &snapshots[], ClosedTradeRecord &closedTrades[], StrategyAggregateRecord &strategyAggregates[], RegimeAggregateRecord &regimeAggregates[])
{
   ArrayResize(strategyAggregates, 0);
   ArrayResize(regimeAggregates, 0);

   for(int i = 0; i < ArraySize(closedTrades); i++)
   {
      ClosedTradeRecord record = closedTrades[i];
      if(record.source != "EA")
         continue;
      string timeframe = (StringLen(record.regimeTimeframe) > 0) ? record.regimeTimeframe : "H1";

      int strategyIndex = FindStrategyAggregateIndex(strategyAggregates, record.symbol, record.strategy, timeframe);
      if(strategyIndex < 0)
      {
         StrategyAggregateRecord newStrategy;
         newStrategy.symbol = record.symbol;
         newStrategy.strategy = record.strategy;
         newStrategy.timeframe = timeframe;
         newStrategy.closedTrades = 0;
         newStrategy.wins = 0;
         newStrategy.grossProfit = 0.0;
         newStrategy.grossLoss = 0.0;
         newStrategy.netProfit = 0.0;
         newStrategy.lastCloseTime = 0;
         newStrategy.openPositions = 0;
         newStrategy.strategyPositions = 0;
         int newSize = ArraySize(strategyAggregates);
         ArrayResize(strategyAggregates, newSize + 1);
         strategyAggregates[newSize] = newStrategy;
         strategyIndex = newSize;
      }

      strategyAggregates[strategyIndex].closedTrades++;
      if(record.actualProfit > 0.0)
         strategyAggregates[strategyIndex].wins++;
      if(record.actualProfit >= 0.0)
         strategyAggregates[strategyIndex].grossProfit += record.actualProfit;
      else
         strategyAggregates[strategyIndex].grossLoss += MathAbs(record.actualProfit);
      strategyAggregates[strategyIndex].netProfit += record.actualProfit;
      if(record.closeTime > strategyAggregates[strategyIndex].lastCloseTime)
         strategyAggregates[strategyIndex].lastCloseTime = record.closeTime;

      int regimeIndex = FindRegimeAggregateIndex(regimeAggregates, record.symbol, record.strategy, timeframe, record.entryRegime);
      if(regimeIndex < 0)
      {
         RegimeAggregateRecord newRegime;
         newRegime.symbol = record.symbol;
         newRegime.strategy = record.strategy;
         newRegime.timeframe = timeframe;
         newRegime.entryRegime = record.entryRegime;
         newRegime.closedTrades = 0;
         newRegime.linkedTrades = 0;
         newRegime.positiveTrades = 0;
         newRegime.negativeTrades = 0;
         newRegime.flatTrades = 0;
         newRegime.grossProfit = 0.0;
         newRegime.grossLoss = 0.0;
         newRegime.netProfit = 0.0;
         newRegime.totalDurationMinutes = 0.0;
         newRegime.lastEventTime = 0;
         newRegime.lastCloseTime = 0;
         int newSize = ArraySize(regimeAggregates);
         ArrayResize(regimeAggregates, newSize + 1);
         regimeAggregates[newSize] = newRegime;
         regimeIndex = newSize;
      }

      regimeAggregates[regimeIndex].closedTrades++;
      regimeAggregates[regimeIndex].linkedTrades++;
      if(record.actualProfit > 0.0)
         regimeAggregates[regimeIndex].positiveTrades++;
      else if(record.actualProfit < 0.0)
         regimeAggregates[regimeIndex].negativeTrades++;
      else
         regimeAggregates[regimeIndex].flatTrades++;
      if(record.actualProfit >= 0.0)
         regimeAggregates[regimeIndex].grossProfit += record.actualProfit;
      else
         regimeAggregates[regimeIndex].grossLoss += MathAbs(record.actualProfit);
      regimeAggregates[regimeIndex].netProfit += record.actualProfit;
      regimeAggregates[regimeIndex].totalDurationMinutes += record.durationMinutes;
      if(record.openTime > regimeAggregates[regimeIndex].lastEventTime)
         regimeAggregates[regimeIndex].lastEventTime = record.openTime;
      if(record.closeTime > regimeAggregates[regimeIndex].lastCloseTime)
         regimeAggregates[regimeIndex].lastCloseTime = record.closeTime;
   }

   int totalPositions = PositionsTotal();
   for(int i = 0; i < totalPositions; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      string comment = PositionGetString(POSITION_COMMENT);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!IsPilotManagedPosition(comment, magic))
         continue;
      string strategy = InferStrategyFromComment(comment);
      string timeframe = "H1";
      int strategyIndex = FindStrategyAggregateIndex(strategyAggregates, symbol, strategy, timeframe);
      if(strategyIndex < 0)
      {
         StrategyAggregateRecord newStrategy;
         newStrategy.symbol = symbol;
         newStrategy.strategy = strategy;
         newStrategy.timeframe = timeframe;
         newStrategy.closedTrades = 0;
         newStrategy.wins = 0;
         newStrategy.grossProfit = 0.0;
         newStrategy.grossLoss = 0.0;
         newStrategy.netProfit = 0.0;
         newStrategy.lastCloseTime = 0;
         newStrategy.openPositions = 0;
         newStrategy.strategyPositions = 0;
         int newSize = ArraySize(strategyAggregates);
         ArrayResize(strategyAggregates, newSize + 1);
         strategyAggregates[newSize] = newStrategy;
         strategyIndex = newSize;
      }

      strategyAggregates[strategyIndex].openPositions++;
      strategyAggregates[strategyIndex].strategyPositions++;
   }
}

string BuildStrategyEvaluationCsv(SymbolSnapshot &snapshots[], StrategyAggregateRecord &strategyAggregates[])
{
   string csv = "ReportTimeLocal,ReportTimeServer,Symbol,Strategy,Timeframe,Regime,Enabled,Active,RuntimeLabel,AdaptiveState,AdaptiveReason,RiskMultiplier,TradingStatus,SignalStatus,SignalReason,SignalScore,ClosedTrades,WinRate,ProfitFactor,AvgNet,NetProfit,GrossProfit,GrossLoss,OpenPositions,StrategyPositions,TickAgeSeconds,SpreadPips,ATRPips,ADX,BBWidthPips,LastEvalTime,LastClosedTime\r\n";
   datetime serverClock = TimeTradeServer();
   if(serverClock <= 0)
      serverClock = TimeCurrent();

   for(int i = 0; i < ArraySize(strategyAggregates); i++)
   {
      StrategyAggregateRecord record = strategyAggregates[i];
      double winRate = 0.0;
      double profitFactor = 0.0;
      double avgNet = 0.0;
      if(record.closedTrades > 0)
      {
         winRate = (double)record.wins * 100.0 / (double)record.closedTrades;
         avgNet = record.netProfit / (double)record.closedTrades;
         profitFactor = (record.grossLoss > 0.0) ? (record.grossProfit / record.grossLoss) : (record.grossProfit > 0.0 ? 999.0 : 0.0);
      }

      int symbolIndex = FindSymbolIndex(record.symbol);
      int tickAge = (symbolIndex >= 0) ? snapshots[symbolIndex].tickAgeSeconds : 0;
      double spread = (symbolIndex >= 0) ? snapshots[symbolIndex].spread : 0.0;
      bool isPilotMaRow = (record.strategy == "MA_Cross" && symbolIndex >= 0 && symbolIndex < ArraySize(g_maRuntimeStates));
      StrategyStatusSnapshot pilotState;
      if(isPilotMaRow)
         pilotState = g_maRuntimeStates[symbolIndex];

      csv += CsvEscape(FormatDateTime(TimeLocal(), true)) + ",";
      csv += CsvEscape(FormatDateTime(serverClock, true)) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.timeframe) + ",";
      csv += CsvEscape("ALL") + ",";
      csv += (isPilotMaRow && IsPilotLiveMode() ? "true," : "false,");
      csv += (isPilotMaRow ? (pilotState.active ? "true," : "false,") : "false,");
      csv += CsvEscape(isPilotMaRow ? pilotState.runtimeLabel : "SHADOW") + ",";
      csv += CsvEscape(isPilotMaRow ? pilotState.adaptiveState : "WARMUP") + ",";
      csv += CsvEscape(isPilotMaRow ? pilotState.adaptiveReason : "MT5 shadow journaling only") + ",";
      csv += FormatNumber(isPilotMaRow ? pilotState.riskMultiplier : 0.00, 2) + ",";
      csv += CsvEscape(isPilotMaRow ? (g_pilotKillSwitch ? "AUTO_PAUSED" : "READY") : "SHADOW") + ",";
      csv += CsvEscape(isPilotMaRow ? pilotState.status : "NO_DATA") + ",";
      csv += CsvEscape(isPilotMaRow ? pilotState.reason : "HFM MT5 shadow journaling active") + ",";
      csv += FormatNumber(isPilotMaRow ? pilotState.score : 0.0, 1) + ",";
      csv += IntegerToString(record.closedTrades) + ",";
      csv += FormatNumber(winRate, 1) + ",";
      csv += FormatNumber(profitFactor, 2) + ",";
      csv += FormatNumber(avgNet, 2) + ",";
      csv += FormatNumber(record.netProfit, 2) + ",";
      csv += FormatNumber(record.grossProfit, 2) + ",";
      csv += FormatNumber(record.grossLoss, 2) + ",";
      csv += IntegerToString(record.openPositions) + ",";
      csv += IntegerToString(record.strategyPositions) + ",";
      csv += IntegerToString(tickAge) + ",";
      csv += FormatNumber(spread, 1) + ",";
      csv += "0.0,0.0,0.0,";
      csv += CsvEscape(FormatDateTime(serverClock, true)) + ",";
      csv += CsvEscape(FormatDateTime(record.lastCloseTime)) + "\r\n";
   }

   return csv;
}

string BuildRegimeEvaluationCsv(ClosedTradeRecord &closedTrades[], RegimeAggregateRecord &regimeAggregates[])
{
   string csv = "ReportTimeLocal,ReportTimeServer,Symbol,Strategy,Timeframe,EntryRegime,ClosedTrades,LinkedTrades,LinkCoverage,WinRate,ProfitFactor,AvgNet,NetProfit,GrossProfit,GrossLoss,AvgDurationMinutes,AvgSignalScore,PositiveTrades,NegativeTrades,FlatTrades,LastEventTime,LastCloseTime\r\n";
   datetime serverClock = TimeTradeServer();
   if(serverClock <= 0)
      serverClock = TimeCurrent();

   for(int i = 0; i < ArraySize(regimeAggregates); i++)
   {
      RegimeAggregateRecord record = regimeAggregates[i];
      double winRate = 0.0;
      double profitFactor = 0.0;
      double avgNet = 0.0;
      double avgDuration = 0.0;
      double linkCoverage = 0.0;
      if(record.closedTrades > 0)
      {
         winRate = (double)record.positiveTrades * 100.0 / (double)record.closedTrades;
         avgNet = record.netProfit / (double)record.closedTrades;
         avgDuration = record.totalDurationMinutes / (double)record.closedTrades;
         linkCoverage = (double)record.linkedTrades / (double)record.closedTrades;
         profitFactor = (record.grossLoss > 0.0) ? (record.grossProfit / record.grossLoss) : (record.grossProfit > 0.0 ? 999.0 : 0.0);
      }

      csv += CsvEscape(FormatDateTime(TimeLocal(), true)) + ",";
      csv += CsvEscape(FormatDateTime(serverClock, true)) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.timeframe) + ",";
      csv += CsvEscape(record.entryRegime) + ",";
      csv += IntegerToString(record.closedTrades) + ",";
      csv += IntegerToString(record.linkedTrades) + ",";
      csv += FormatNumber(linkCoverage, 2) + ",";
      csv += FormatNumber(winRate, 1) + ",";
      csv += FormatNumber(profitFactor, 2) + ",";
      csv += FormatNumber(avgNet, 2) + ",";
      csv += FormatNumber(record.netProfit, 2) + ",";
      csv += FormatNumber(record.grossProfit, 2) + ",";
      csv += FormatNumber(record.grossLoss, 2) + ",";
      csv += FormatNumber(avgDuration, 1) + ",";
      csv += "0.0,";
      csv += IntegerToString(record.positiveTrades) + ",";
      csv += IntegerToString(record.negativeTrades) + ",";
      csv += IntegerToString(record.flatTrades) + ",";
      csv += CsvEscape(FormatDateTime(record.lastEventTime)) + ",";
      csv += CsvEscape(FormatDateTime(record.lastCloseTime)) + "\r\n";
   }

   return csv;
}

void ExportShadowCsvs(SymbolSnapshot &snapshots[], TradeJournalRecord &journal[], ClosedTradeRecord &closedTrades[])
{
   StrategyAggregateRecord strategyAggregates[];
   RegimeAggregateRecord regimeAggregates[];
   BuildAggregates(snapshots, closedTrades, strategyAggregates, regimeAggregates);

   WriteTextFile("QuantGod_TradeJournal.csv", BuildTradeJournalCsv(journal));
   WriteTextFile("QuantGod_CloseHistory.csv", BuildCloseHistoryCsv(closedTrades));
   WriteTextFile("QuantGod_TradeOutcomeLabels.csv", BuildTradeOutcomeLabelsCsv(closedTrades));
   WriteTextFile("QuantGod_TradeEventLinks.csv", BuildTradeEventLinksCsv(closedTrades, journal));
   WriteTextFile("QuantGod_StrategyEvaluationReport.csv", BuildStrategyEvaluationCsv(snapshots, strategyAggregates));
   WriteTextFile("QuantGod_RegimeEvaluationReport.csv", BuildRegimeEvaluationCsv(closedTrades, regimeAggregates));
   WriteTextFile("QuantGod_OpportunityLabels.csv", "EventId,LabelTimeLocal,LabelTimeServer,EventTimeServer,EventBarTime,Symbol,Strategy,Timeframe,SignalStatus,SignalDirection,SignalScore,Regime,AdaptiveState,RiskMultiplier,HorizonBars,ReferencePrice,FutureClose,LongClosePips,ShortClosePips,LongMFEPips,LongMAEPips,ShortMFEPips,ShortMAEPips,NeutralThresholdPips,DirectionalOutcome,BestOpportunity,LabelReason\r\n");
}

void InitializeSnapshots(SymbolSnapshot &snapshots[])
{
   ArrayResize(snapshots, ArraySize(g_symbols));

   for(int i = 0; i < ArraySize(g_symbols); i++)
   {
      snapshots[i].symbol = g_symbols[i];
      snapshots[i].role = (i == 0) ? "focus" : "managed";
      snapshots[i].status = "READY";
      snapshots[i].tickAgeSeconds = 0;
      snapshots[i].bid = 0.0;
      snapshots[i].ask = 0.0;
      snapshots[i].spread = 0.0;
      snapshots[i].openPositions = 0;
      snapshots[i].floatingProfit = 0.0;
      snapshots[i].actualFloatingProfit = 0.0;
      snapshots[i].closedTrades = 0;
      snapshots[i].wins = 0;
      snapshots[i].closedProfit = 0.0;
      snapshots[i].actualClosedProfit = 0.0;
      snapshots[i].lastCloseTime = 0;

      MqlTick tick;
      if(SymbolInfoTick(g_symbols[i], tick))
      {
         snapshots[i].bid = tick.bid;
         snapshots[i].ask = tick.ask;
         snapshots[i].spread = CalcSpreadPips(g_symbols[i], tick.bid, tick.ask);
         snapshots[i].tickAgeSeconds = (int)MathMax(0, (long)(TimeCurrent() - (datetime)tick.time));
      }
   }
}

string BuildOpenTradesJson(SymbolSnapshot &snapshots[])
{
   string items[];
   ArrayResize(items, 0);

   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      int symbolIndex = FindSymbolIndex(symbol);

      ulong positionId = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);
      double swap = PositionGetDouble(POSITION_SWAP);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      string comment = PositionGetString(POSITION_COMMENT);
      string strategy = InferStrategyFromComment(comment);
      string source = InferTradeSource(comment);
      string typeText = PositionTypeToString(PositionGetInteger(POSITION_TYPE));
      int durationMinutes = (int)MathMax(0, (long)((TimeTradeServer() > 0 ? TimeTradeServer() : TimeCurrent()) - openTime) / 60);
      RegimeSnapshot entryRegime = EvaluateRegimeAt(symbol, PERIOD_H1, openTime);
      RegimeSnapshot currentRegime = EvaluateRegimeAt(symbol, PERIOD_H1, 0);

      if(symbolIndex >= 0)
      {
         snapshots[symbolIndex].openPositions++;
         snapshots[symbolIndex].floatingProfit += profit;
         snapshots[symbolIndex].actualFloatingProfit += profit;
         snapshots[symbolIndex].status = "IN_POSITION";
      }

      string json = "    {";
      json += "\"ticket\": " + IntegerToString((int)ticket) + ", ";
      json += "\"positionId\": " + IntegerToString((int)positionId) + ", ";
      json += "\"type\": \"" + typeText + "\", ";
      json += "\"symbol\": \"" + JsonEscape(symbol) + "\", ";
      json += "\"lots\": " + FormatNumber(volume, 2) + ", ";
      json += "\"actualLots\": " + FormatNumber(volume, 2) + ", ";
      json += "\"virtualLots\": " + FormatNumber(volume, 2) + ", ";
      json += "\"openPrice\": " + FormatNumber(openPrice, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"sl\": " + FormatNumber(sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"tp\": " + FormatNumber(tp, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"profit\": " + FormatNumber(profit, 2) + ", ";
      json += "\"actualProfit\": " + FormatNumber(profit, 2) + ", ";
      json += "\"swap\": " + FormatNumber(swap, 2) + ", ";
      json += "\"openTime\": \"" + FormatDateTime(openTime) + "\", ";
      json += "\"durationMinutes\": " + IntegerToString(durationMinutes) + ", ";
      json += "\"strategy\": \"" + JsonEscape(strategy) + "\", ";
      json += "\"source\": \"" + source + "\", ";
      json += "\"entryRegime\": \"" + entryRegime.label + "\", ";
      json += "\"regime\": \"" + currentRegime.label + "\", ";
      json += "\"regimeTimeframe\": \"" + currentRegime.timeframe + "\", ";
      json += "\"comment\": \"" + JsonEscape(comment) + "\"";
      json += "}";

      PushString(items, json);
   }

   string json = "[";
   for(int i = 0; i < ArraySize(items); i++)
   {
      if(i > 0)
         json += ",";
      json += "\r\n" + items[i];
   }
   if(ArraySize(items) > 0)
      json += "\r\n";
   json += "  ]";
   return json;
}

void CollectTradeJournal(TradeJournalRecord &journal[])
{
   ArrayResize(journal, 0);

   datetime historyNow = TimeTradeServer();
   if(historyNow <= 0)
      historyNow = TimeCurrent();
   if(historyNow <= 0)
      historyNow = TimeLocal();

   datetime fromTime = historyNow - (HistoryLookbackDays * 86400);
   if(!HistorySelect(fromTime, historyNow))
      return;

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0)
         continue;

      string symbol = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
      if(StringLen(symbol) == 0)
         continue;

      long dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL)
         continue;

      long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
      string comment = HistoryDealGetString(dealTicket, DEAL_COMMENT);
      RegimeSnapshot regime = EvaluateRegimeAt(symbol, PERIOD_H1, (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME));

      TradeJournalRecord record;
      record.dealTicket = dealTicket;
      record.positionId = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
      record.eventType = IsExitDeal(entryType) ? "EXIT" : "ENTRY";
      record.side = DealEntryToPositionTypeString(dealType);
      record.symbol = symbol;
      record.lots = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
      record.price = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
      record.grossProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      record.commission = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
      record.swap = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
      record.netProfit = record.grossProfit + record.commission + record.swap;
      record.eventTime = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
      record.strategy = InferStrategyFromComment(comment);
      record.source = InferTradeSource(comment);
      record.comment = comment;
      record.regime = regime.label;
      record.regimeTimeframe = regime.timeframe;

      PushTradeJournal(journal, record);
   }
}

void CollectClosedTrades(SymbolSnapshot &snapshots[], ClosedTradeRecord &closedTrades[])
{
   ArrayResize(closedTrades, 0);

   datetime historyNow = TimeTradeServer();
   if(historyNow <= 0)
      historyNow = TimeCurrent();
   if(historyNow <= 0)
      historyNow = TimeLocal();

   datetime fromTime = historyNow - (HistoryLookbackDays * 86400);
   if(!HistorySelect(fromTime, historyNow))
   {
      Print("QuantGod MT5 skeleton failed HistorySelect err=", GetLastError());
      return;
   }

   int total = HistoryDealsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      if(ArraySize(closedTrades) >= ClosedTradeLimit)
         break;

      ulong exitTicket = HistoryDealGetTicket(i);
      if(exitTicket == 0)
         continue;

      long entryType = HistoryDealGetInteger(exitTicket, DEAL_ENTRY);
      if(!IsExitDeal(entryType))
         continue;

      string symbol = HistoryDealGetString(exitTicket, DEAL_SYMBOL);
      int symbolIndex = FindSymbolIndex(symbol);

      ulong positionId = (ulong)HistoryDealGetInteger(exitTicket, DEAL_POSITION_ID);
      ulong entryTicket = 0;
      FindPositionEntryDeal(positionId, entryTicket);

      datetime closeTime = (datetime)HistoryDealGetInteger(exitTicket, DEAL_TIME);
      double closePrice = HistoryDealGetDouble(exitTicket, DEAL_PRICE);
      double grossProfit = HistoryDealGetDouble(exitTicket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(exitTicket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(exitTicket, DEAL_SWAP);
      double exitProfit = grossProfit + swap + commission;
      double volume = HistoryDealGetDouble(exitTicket, DEAL_VOLUME);
      string exitComment = HistoryDealGetString(exitTicket, DEAL_COMMENT);

      datetime openTime = closeTime;
      double openPrice = closePrice;
      string comment = exitComment;
      string typeText = DealEntryToPositionTypeString(HistoryDealGetInteger(exitTicket, DEAL_TYPE));
      string source = InferTradeSource(comment);

      if(entryTicket != 0)
      {
         openTime = (datetime)HistoryDealGetInteger(entryTicket, DEAL_TIME);
         openPrice = HistoryDealGetDouble(entryTicket, DEAL_PRICE);
         string entryComment = HistoryDealGetString(entryTicket, DEAL_COMMENT);
         if(StringLen(TrimString(entryComment)) > 0)
            comment = entryComment;
         typeText = DealEntryToPositionTypeString(HistoryDealGetInteger(entryTicket, DEAL_TYPE));
         source = InferTradeSource(comment);
      }

      RegimeSnapshot entryRegime = EvaluateRegimeAt(symbol, PERIOD_H1, openTime);
      RegimeSnapshot exitRegime = EvaluateRegimeAt(symbol, PERIOD_H1, closeTime);

      ClosedTradeRecord record;
      record.ticket = exitTicket;
      record.positionId = positionId;
      record.type = typeText;
      record.symbol = symbol;
      record.lots = volume;
      record.actualLots = volume;
      record.virtualLots = volume;
      record.openPrice = openPrice;
      record.closePrice = closePrice;
      record.profit = exitProfit;
      record.actualProfit = exitProfit;
      record.swap = swap;
      record.openTime = openTime;
      record.closeTime = closeTime;
      record.strategy = InferStrategyFromComment(comment);
      record.source = source;
      record.comment = comment;
      record.entryRegime = entryRegime.label;
      record.exitRegime = exitRegime.label;
      record.regimeTimeframe = entryRegime.timeframe;
      record.durationMinutes = (int)MathMax(0, (long)(closeTime - openTime) / 60);
      record.commission = commission;
      record.grossProfit = grossProfit;

      PushClosedTrade(closedTrades, record);

      if(symbolIndex >= 0 && source == "EA")
      {
         snapshots[symbolIndex].closedTrades++;
         if(exitProfit > 0.0)
            snapshots[symbolIndex].wins++;
         snapshots[symbolIndex].closedProfit += exitProfit;
         snapshots[symbolIndex].actualClosedProfit += exitProfit;
         if(closeTime > snapshots[symbolIndex].lastCloseTime)
            snapshots[symbolIndex].lastCloseTime = closeTime;
      }
   }
}

string BuildClosedTradesJson(ClosedTradeRecord &closedTrades[])
{
   string json = "[";

   for(int i = 0; i < ArraySize(closedTrades); i++)
   {
      ClosedTradeRecord record = closedTrades[i];
      if(i > 0)
         json += ",";
      json += "\r\n    {";
      json += "\"ticket\": " + IntegerToString((int)record.ticket) + ", ";
      json += "\"positionId\": " + IntegerToString((int)record.positionId) + ", ";
      json += "\"type\": \"" + record.type + "\", ";
      json += "\"symbol\": \"" + JsonEscape(record.symbol) + "\", ";
      json += "\"lots\": " + FormatNumber(record.lots, 2) + ", ";
      json += "\"actualLots\": " + FormatNumber(record.actualLots, 2) + ", ";
      json += "\"virtualLots\": " + FormatNumber(record.virtualLots, 2) + ", ";
      json += "\"openPrice\": " + FormatNumber(record.openPrice, (int)SymbolInfoInteger(record.symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"closePrice\": " + FormatNumber(record.closePrice, (int)SymbolInfoInteger(record.symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"profit\": " + FormatNumber(record.profit, 2) + ", ";
      json += "\"actualProfit\": " + FormatNumber(record.actualProfit, 2) + ", ";
      json += "\"swap\": " + FormatNumber(record.swap, 2) + ", ";
      json += "\"openTime\": \"" + FormatDateTime(record.openTime) + "\", ";
      json += "\"closeTime\": \"" + FormatDateTime(record.closeTime) + "\", ";
      json += "\"durationMinutes\": " + IntegerToString(record.durationMinutes) + ", ";
      json += "\"strategy\": \"" + JsonEscape(record.strategy) + "\", ";
      json += "\"source\": \"" + record.source + "\", ";
      json += "\"entryRegime\": \"" + record.entryRegime + "\", ";
      json += "\"exitRegime\": \"" + record.exitRegime + "\", ";
      json += "\"regimeTimeframe\": \"" + record.regimeTimeframe + "\", ";
      json += "\"comment\": \"" + JsonEscape(record.comment) + "\"";
      json += "}";
   }

   if(ArraySize(closedTrades) > 0)
      json += "\r\n";
   json += "  ]";
   return json;
}

string BuildSymbolsJson(SymbolSnapshot &snapshots[])
{
   string json = "[";

   for(int i = 0; i < ArraySize(snapshots); i++)
   {
      SymbolSnapshot snapshot = snapshots[i];
      double winRate = 0.0;
      if(snapshot.closedTrades > 0)
         winRate = (double)snapshot.wins * 100.0 / (double)snapshot.closedTrades;

      if(i > 0)
         json += ",";

      json += "\r\n    {";
      json += "\"symbol\": \"" + JsonEscape(snapshot.symbol) + "\", ";
      json += "\"role\": \"" + snapshot.role + "\", ";
      json += "\"status\": \"" + snapshot.status + "\", ";
      json += "\"tickAgeSeconds\": " + IntegerToString(snapshot.tickAgeSeconds) + ", ";
      json += "\"bid\": " + FormatNumber(snapshot.bid, (int)SymbolInfoInteger(snapshot.symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"ask\": " + FormatNumber(snapshot.ask, (int)SymbolInfoInteger(snapshot.symbol, SYMBOL_DIGITS)) + ", ";
      json += "\"spread\": " + FormatNumber(snapshot.spread, 1) + ", ";
      json += "\"openPositions\": " + IntegerToString(snapshot.openPositions) + ", ";
      json += "\"floatingProfit\": " + FormatNumber(snapshot.floatingProfit, 2) + ", ";
      json += "\"actualFloatingProfit\": " + FormatNumber(snapshot.actualFloatingProfit, 2) + ", ";
      json += "\"closedTrades\": " + IntegerToString(snapshot.closedTrades) + ", ";
      json += "\"winRate\": " + FormatNumber(winRate, 1) + ", ";
      json += "\"closedProfit\": " + FormatNumber(snapshot.closedProfit, 2) + ", ";
      json += "\"actualClosedProfit\": " + FormatNumber(snapshot.actualClosedProfit, 2) + ", ";
      json += "\"lastCloseTime\": \"" + FormatDateTime(snapshot.lastCloseTime) + "\", ";
      json += "\"pilotTelemetry\": " + BuildPilotTelemetryJson(i) + ", ";
      json += "\"strategies\": {";

      for(int s = 0; s < ArraySize(g_strategyKeys); s++)
      {
         if(s > 0)
            json += ", ";
         json += "\"" + g_strategyKeys[s] + "\": ";
         json += BuildSymbolStrategyJson(snapshot.symbol, i, g_strategyKeys[s]);
      }

      json += "}";
      json += "}";
   }

   if(ArraySize(snapshots) > 0)
      json += "\r\n";
   json += "  ]";
   return json;
}

string BuildRootStrategiesJson()
{
   string json = "{";

   for(int i = 0; i < ArraySize(g_strategyKeys); i++)
   {
      if(i > 0)
         json += ", ";
      json += "\"" + g_strategyKeys[i] + "\": ";
      json += BuildRootStrategyJson(g_strategyKeys[i]);
   }

   json += "}";
   return json;
}

string BuildDiagnosticsJson()
{
   string json = "{";

   for(int i = 0; i < ArraySize(g_strategyKeys); i++)
   {
      if(i > 0)
         json += ", ";
      json += "\"" + g_strategyKeys[i] + "\": ";
      json += BuildRootDiagnosticJson(g_strategyKeys[i]);
   }

   json += "}";
   return json;
}

void ExportDashboard()
{
   if(ArraySize(g_symbols) == 0)
      InitializeWatchlist();

   RunPilotExecutionLoop();

   SymbolSnapshot snapshots[];
   InitializeSnapshots(snapshots);

   TradeJournalRecord journal[];
   CollectTradeJournal(journal);
   ClosedTradeRecord closedTrades[];
   CollectClosedTrades(snapshots, closedTrades);
   string openTradesJson = BuildOpenTradesJson(snapshots);
   string closedTradesJson = BuildClosedTradesJson(closedTrades);
   string symbolsJson = BuildSymbolsJson(snapshots);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double profit = AccountInfoDouble(ACCOUNT_PROFIT);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double drawdown = balance - equity;
   if(drawdown < 0.0)
      drawdown = 0.0;

   bool terminalConnected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   bool terminalTradeAllowed = (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   bool programTradeAllowed = (bool)MQLInfoInteger(MQL_TRADE_ALLOWED);
   bool dllAllowed = (bool)MQLInfoInteger(MQL_DLLS_ALLOWED);
   long accountLogin = AccountInfoInteger(ACCOUNT_LOGIN);
   string accountServer = AccountInfoString(ACCOUNT_SERVER);
   bool accountAuthorized = (accountLogin > 0 && StringLen(accountServer) > 0);
   bool connected = (terminalConnected || accountAuthorized);
   bool tradeAllowed = (!ReadOnlyMode && connected && terminalTradeAllowed && programTradeAllowed);
   string tradeStatus = "NO_DATA";
   if(connected)
   {
      if(ReadOnlyMode)
         tradeStatus = "SHADOW";
      else if(g_pilotKillSwitch)
         tradeStatus = "AUTO_PAUSED";
      else if(g_newsState.blocked)
         tradeStatus = "NEWS_BLOCK";
      else if(tradeAllowed)
         tradeStatus = "READY";
      else
         tradeStatus = "AUTOTRADING_OFF";
   }

   datetime serverClock = CurrentServerTime();

   MqlTick focusTick;
   ZeroMemory(focusTick);
   SymbolInfoTick(g_focusSymbol, focusTick);
   double focusBid = focusTick.bid;
   double focusAsk = focusTick.ask;
   double focusSpread = CalcSpreadPips(g_focusSymbol, focusBid, focusAsk);
   int focusTickAge = 0;
   if(connected && focusTick.time > 0)
      focusTickAge = (int)MathMax(0, (long)(serverClock - (datetime)focusTick.time));

   string json = "{\r\n";
   json += "  \"timestamp\": \"" + FormatDateTime(TimeLocal(), true) + "\",\r\n";
   json += "  \"build\": \"" + JsonEscape(DashboardBuild) + "\",\r\n";

   json += "  \"runtime\": {\r\n";
   json += "    \"tradeStatus\": \"" + tradeStatus + "\",\r\n";
   json += "    \"shadowMode\": " + JsonBool(ShadowMode) + ",\r\n";
   json += "    \"readOnlyMode\": " + JsonBool(ReadOnlyMode) + ",\r\n";
   json += "    \"executionEnabled\": " + JsonBool(!ReadOnlyMode) + ",\r\n";
   json += "    \"livePilotMode\": " + JsonBool(IsPilotLiveMode()) + ",\r\n";
   json += "    \"pilotKillSwitch\": " + JsonBool(g_pilotKillSwitch) + ",\r\n";
   json += "    \"pilotKillReason\": \"" + JsonEscape(g_pilotKillReason) + "\",\r\n";
   json += "    \"pilotRealizedLossToday\": " + FormatNumber(g_pilotRealizedLossToday, 2) + ",\r\n";
   json += "    \"pilotConsecutiveLosses\": " + IntegerToString(g_pilotConsecutiveLosses) + ",\r\n";
   json += "    \"pilotFloatingProfit\": " + FormatNumber(SumPilotFloatingProfit(), 2) + ",\r\n";
   json += "    \"connected\": " + JsonBool(connected) + ",\r\n";
   json += "    \"terminalConnected\": " + JsonBool(terminalConnected) + ",\r\n";
   json += "    \"accountAuthorized\": " + JsonBool(accountAuthorized) + ",\r\n";
   json += "    \"terminalTradeAllowed\": " + JsonBool(terminalTradeAllowed) + ",\r\n";
   json += "    \"programTradeAllowed\": " + JsonBool(programTradeAllowed) + ",\r\n";
   json += "    \"dllAllowed\": " + JsonBool(dllAllowed) + ",\r\n";
   json += "    \"tradeAllowed\": " + JsonBool(tradeAllowed) + ",\r\n";
   json += "    \"tickAgeSeconds\": " + IntegerToString(focusTickAge) + ",\r\n";
   json += "    \"researchMode\": false,\r\n";
   json += "    \"serverTime\": \"" + FormatDateTime(serverClock, true) + "\",\r\n";
   json += "    \"gmtTime\": \"" + FormatDateTime(TimeGMT(), true) + "\",\r\n";
    json += "    \"localTime\": \"" + FormatDateTime(TimeLocal(), true) + "\"\r\n";
   json += "  },\r\n";

   json += "  \"news\": " + BuildNewsJson() + ",\r\n";

   json += "  \"cloudSync\": {\r\n";
   json += "    \"enabled\": false,\r\n";
   json += "    \"configured\": false,\r\n";
   json += "    \"endpoint\": \"\",\r\n";
   json += "    \"intervalSeconds\": 30,\r\n";
   json += "    \"lastAttemptLocal\": \"\",\r\n";
   json += "    \"lastSuccessLocal\": \"\",\r\n";
   json += "    \"status\": \"DISABLED\",\r\n";
   json += "    \"httpCode\": 0,\r\n";
   json += "    \"message\": \"Cloud sync is disabled in the MT5 phase 1 skeleton\"\r\n";
   json += "  },\r\n";

   json += "  \"account\": {\r\n";
   json += "    \"number\": " + IntegerToString((int)accountLogin) + ",\r\n";
   json += "    \"name\": \"" + JsonEscape(AccountInfoString(ACCOUNT_NAME)) + "\",\r\n";
   json += "    \"server\": \"" + JsonEscape(accountServer) + "\",\r\n";
   json += "    \"currency\": \"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",\r\n";
   string accountModeLabel = ShadowMode ? "mt5_shadow" : (IsPilotLiveMode() ? "mt5_live_pilot" : "mt5_runtime");
   json += "    \"mode\": \"" + JsonEscape(accountModeLabel) + "\",\r\n";
   json += "    \"accountMode\": \"" + AccountMarginModeToString(AccountInfoInteger(ACCOUNT_MARGIN_MODE)) + "\",\r\n";
   json += "    \"symbolSuffix\": \"" + JsonEscape(g_detectedSuffix) + "\",\r\n";
   json += "    \"startingBalance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"riskPercent\": 0.00,\r\n";
   json += "    \"executionLot\": " + FormatNumber(IsPilotLiveMode() ? PilotLotSize : SymbolInfoDouble(g_focusSymbol, SYMBOL_VOLUME_MIN), 2) + ",\r\n";
   json += "    \"balance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"equity\": " + FormatNumber(equity, 2) + ",\r\n";
   json += "    \"profit\": " + FormatNumber(profit, 2) + ",\r\n";
   json += "    \"margin\": " + FormatNumber(margin, 2) + ",\r\n";
   json += "    \"freeMargin\": " + FormatNumber(freeMargin, 2) + ",\r\n";
   json += "    \"drawdown\": " + FormatNumber(drawdown, 2) + ",\r\n";
   json += "    \"maxDrawdownPercent\": " + FormatNumber(IsPilotLiveMode() ? 0.60 : 0.00, 2) + ",\r\n";
   json += "    \"maxTotalTrades\": " + IntegerToString(IsPilotLiveMode() ? PilotMaxTotalPositions : 0) + ",\r\n";
   json += "    \"leverage\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\r\n";
   json += "  },\r\n";

   json += "  \"brokerAccount\": {\r\n";
   json += "    \"balance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"equity\": " + FormatNumber(equity, 2) + ",\r\n";
   json += "    \"profit\": " + FormatNumber(profit, 2) + ",\r\n";
   json += "    \"margin\": " + FormatNumber(margin, 2) + ",\r\n";
   json += "    \"freeMargin\": " + FormatNumber(freeMargin, 2) + ",\r\n";
   json += "    \"drawdown\": " + FormatNumber(drawdown, 2) + ",\r\n";
   json += "    \"server\": \"" + JsonEscape(accountServer) + "\",\r\n";
   json += "    \"leverage\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\r\n";
   json += "  },\r\n";

   json += "  \"watchlist\": \"" + JsonEscape(g_resolvedWatchlist) + "\",\r\n";
   json += "  \"symbols\": " + symbolsJson + ",\r\n";
   json += "  \"openTrades\": " + openTradesJson + ",\r\n";
   json += "  \"closedTrades\": " + closedTradesJson + ",\r\n";
   json += "  \"strategies\": " + BuildRootStrategiesJson() + ",\r\n";
   json += "  \"diagnostics\": " + BuildDiagnosticsJson() + ",\r\n";
   json += "  \"market\": {\r\n";
   json += "    \"symbol\": \"" + JsonEscape(g_focusSymbol) + "\",\r\n";
   json += "    \"bid\": " + FormatNumber(focusBid, (int)SymbolInfoInteger(g_focusSymbol, SYMBOL_DIGITS)) + ",\r\n";
   json += "    \"ask\": " + FormatNumber(focusAsk, (int)SymbolInfoInteger(g_focusSymbol, SYMBOL_DIGITS)) + ",\r\n";
   json += "    \"spread\": " + FormatNumber(focusSpread, 1) + "\r\n";
   json += "  }\r\n";
   json += "}\r\n";

   string statusFile = "build=" + DashboardBuild + "\r\n";
   statusFile += "tradeStatus=" + tradeStatus + "\r\n";
   statusFile += "livePilotMode=" + (IsPilotLiveMode() ? "true" : "false") + "\r\n";
   statusFile += "pilotKillSwitch=" + (g_pilotKillSwitch ? "true" : "false") + "\r\n";
   statusFile += "pilotKillReason=" + g_pilotKillReason + "\r\n";
   statusFile += "pilotRealizedLossToday=" + FormatNumber(g_pilotRealizedLossToday, 2) + "\r\n";
   statusFile += "pilotConsecutiveLosses=" + IntegerToString(g_pilotConsecutiveLosses) + "\r\n";
   statusFile += "pilotFloatingProfit=" + FormatNumber(SumPilotFloatingProfit(), 2) + "\r\n";
   string exportNewsReason = g_newsState.reason;
   if(EnablePilotNewsFilter &&
      (g_newsState.calendarAvailable || ArraySize(g_usdTrackedEventIds) > 0) &&
      g_newsState.status == "IDLE" &&
      g_newsState.reason == "USD high-impact news filter is armed")
   {
      exportNewsReason = "No tracked USD event near the current pilot window";
   }
   statusFile += "newsStatus=" + g_newsState.status + "\r\n";
   statusFile += "newsBias=" + UsdBiasLabel(g_newsState.usdBiasDirection) + "\r\n";
   statusFile += "newsEvent=" + g_newsState.eventName + "\r\n";
   statusFile += "newsReason=" + exportNewsReason + "\r\n";
   statusFile += "connected=" + (connected ? "true" : "false") + "\r\n";
   statusFile += "focusSymbol=" + g_focusSymbol + "\r\n";
   statusFile += "watchlist=" + g_resolvedWatchlist + "\r\n";
   statusFile += "account=" + IntegerToString((int)accountLogin) + "\r\n";
   statusFile += "server=" + accountServer + "\r\n";
   int focusIndex = FindSymbolIndex(g_focusSymbol);
   if(focusIndex >= 0 && focusIndex < ArraySize(g_pilotTelemetry))
   {
      PilotTelemetrySnapshot telemetry = g_pilotTelemetry[focusIndex];
      statusFile += "focusEvalPasses=" + IntegerToString(telemetry.evaluationPasses) + "\r\n";
      statusFile += "focusSignalHits=" + IntegerToString(telemetry.signalHits) + "\r\n";
      statusFile += "focusWaitBarSkips=" + IntegerToString(telemetry.waitBarSkips) + "\r\n";
      statusFile += "focusNoCrossMisses=" + IntegerToString(telemetry.noCrossMisses) + "\r\n";
      statusFile += "focusNewsBlocks=" + IntegerToString(telemetry.newsBlocks + telemetry.newsFiltered) + "\r\n";
      statusFile += "focusLastStatus=" + telemetry.lastStatus + "\r\n";
   }
   statusFile += "journalDeals=" + IntegerToString(ArraySize(journal)) + "\r\n";
   statusFile += "closedTrades=" + IntegerToString(ArraySize(closedTrades)) + "\r\n";
   statusFile += "localTime=" + FormatDateTime(TimeLocal(), true) + "\r\n";
   WriteTextFile("QuantGod_MT5_ShadowStatus.txt", statusFile);
   WriteTextFile("QuantGod_Dashboard.json", json);
   ExportShadowCsvs(snapshots, journal, closedTrades);
   UpdateShadowChartComment(tradeStatus, connected, accountLogin);
}

int OnInit()
{
   InitializeWatchlist();
   LoadTrackedUsdCalendarEvents();
   RefreshNewsFilterState(true);
   EventSetTimer(MathMax(1, RefreshIntervalSec));
   ExportDashboard();
   Print("QuantGod MT5 runtime initialized. Focus symbol=", g_focusSymbol,
         " watchlist=", g_resolvedWatchlist, " suffix=", g_detectedSuffix,
         " readOnly=", (ReadOnlyMode ? "true" : "false"),
         " livePilot=", (IsPilotLiveMode() ? "true" : "false"));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTick()
{
   ExportDashboard();
}

void OnTimer()
{
   ExportDashboard();
}

