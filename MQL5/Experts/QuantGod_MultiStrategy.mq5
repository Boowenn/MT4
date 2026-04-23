//+------------------------------------------------------------------+
//|                                         QuantGod_MultiStrategy.mq5 |
//|                              QuantGod MT5 Migration Skeleton      |
//+------------------------------------------------------------------+
#property copyright "QuantGod"
#property link      "https://github.com/Boowenn/MT4"
#property version   "3.00"
#property strict

input string DashboardBuild      = "QuantGod-v3.0-mt5-skeleton";
input string Watchlist           = "EURUSD,USDJPY";
input int    RefreshIntervalSec  = 5;
input int    ClosedTradeLimit    = 50;
input int    HistoryLookbackDays = 30;

string g_symbols[];
string g_focusSymbol = "";
string g_strategyKeys[5] =
{
   "MA_Cross",
   "RSI_Reversal",
   "BB_Triple",
   "MACD_Divergence",
   "SR_Breakout"
};

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

struct ClosedTradeRecord
{
   ulong    ticket;
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
   string   comment;
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

void PushClosedTrade(ClosedTradeRecord &values[], ClosedTradeRecord &record)
{
   int size = ArraySize(values);
   ArrayResize(values, size + 1);
   values[size] = record;
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

bool InitializeWatchlist()
{
   ArrayResize(g_symbols, 0);
   string remaining = Watchlist;

   while(StringLen(remaining) > 0)
   {
      int commaPos = StringFind(remaining, ",");
      string token = (commaPos >= 0) ? StringSubstr(remaining, 0, commaPos) : remaining;
      token = TrimString(token);
      if(StringLen(token) > 0 && FindSymbolIndex(token) < 0)
         PushString(g_symbols, token);
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

   for(int i = 0; i < ArraySize(g_symbols); i++)
      SymbolSelect(g_symbols[i], true);

   return true;
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
   if(StringLen(TrimString(comment)) == 0)
      return "MT5_Skeleton";
   return "Manual/Other";
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

void WriteTextFile(string fileName, string content)
{
   int handle = FileOpen(fileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      Print("QuantGod MT5 skeleton failed to open file for write: ", fileName, " err=", GetLastError());
      return;
   }
   FileWriteString(handle, content);
   FileClose(handle);
}

void ExportPlaceholderCsvs()
{
   string strategyHeader = "ReportTimeLocal,ReportTimeServer,Symbol,Strategy,Timeframe,Regime,Enabled,Active,RuntimeLabel,AdaptiveState,AdaptiveReason,RiskMultiplier,TradingStatus,SignalStatus,SignalReason,SignalScore,ClosedTrades,WinRate,ProfitFactor,AvgNet,NetProfit,GrossProfit,GrossLoss,OpenPositions,StrategyPositions,TickAgeSeconds,SpreadPips,ATRPips,ADX,BBWidthPips,LastEvalTime,LastClosedTime\r\n";
   string regimeHeader = "ReportTimeLocal,ReportTimeServer,Symbol,Strategy,Timeframe,EntryRegime,ClosedTrades,LinkedTrades,LinkCoverage,WinRate,ProfitFactor,AvgNet,NetProfit,GrossProfit,GrossLoss,AvgDurationMinutes,AvgSignalScore,PositiveTrades,NegativeTrades,FlatTrades,LastEventTime,LastCloseTime\r\n";
   string opportunityHeader = "EventId,LabelTimeLocal,LabelTimeServer,EventTimeServer,EventBarTime,Symbol,Strategy,Timeframe,SignalStatus,SignalDirection,SignalScore,Regime,AdaptiveState,RiskMultiplier,HorizonBars,ReferencePrice,FutureClose,LongClosePips,ShortClosePips,LongMFEPips,LongMAEPips,ShortMFEPips,ShortMAEPips,NeutralThresholdPips,DirectionalOutcome,BestOpportunity,LabelReason\r\n";

   WriteTextFile("QuantGod_StrategyEvaluationReport.csv", strategyHeader);
   WriteTextFile("QuantGod_RegimeEvaluationReport.csv", regimeHeader);
   WriteTextFile("QuantGod_OpportunityLabels.csv", opportunityHeader);
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
      if(symbolIndex < 0)
         continue;

      double volume = PositionGetDouble(POSITION_VOLUME);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);
      double swap = PositionGetDouble(POSITION_SWAP);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      string comment = PositionGetString(POSITION_COMMENT);
      string strategy = InferStrategyFromComment(comment);
      string typeText = PositionTypeToString(PositionGetInteger(POSITION_TYPE));

      snapshots[symbolIndex].openPositions++;
      snapshots[symbolIndex].floatingProfit += profit;
      snapshots[symbolIndex].actualFloatingProfit += profit;
      snapshots[symbolIndex].status = "IN_POSITION";

      string json = "    {";
      json += "\"ticket\": " + IntegerToString((int)ticket) + ", ";
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
      json += "\"strategy\": \"" + JsonEscape(strategy) + "\", ";
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

void CollectClosedTrades(SymbolSnapshot &snapshots[], ClosedTradeRecord &closedTrades[])
{
   ArrayResize(closedTrades, 0);

   datetime fromTime = TimeCurrent() - (HistoryLookbackDays * 86400);
   if(!HistorySelect(fromTime, TimeCurrent()))
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
      if(symbolIndex < 0)
         continue;

      ulong positionId = (ulong)HistoryDealGetInteger(exitTicket, DEAL_POSITION_ID);
      ulong entryTicket = 0;
      FindPositionEntryDeal(positionId, entryTicket);

      datetime closeTime = (datetime)HistoryDealGetInteger(exitTicket, DEAL_TIME);
      double closePrice = HistoryDealGetDouble(exitTicket, DEAL_PRICE);
      double exitProfit = HistoryDealGetDouble(exitTicket, DEAL_PROFIT)
                        + HistoryDealGetDouble(exitTicket, DEAL_SWAP)
                        + HistoryDealGetDouble(exitTicket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(exitTicket, DEAL_SWAP);
      double volume = HistoryDealGetDouble(exitTicket, DEAL_VOLUME);
      string exitComment = HistoryDealGetString(exitTicket, DEAL_COMMENT);

      datetime openTime = closeTime;
      double openPrice = closePrice;
      string comment = exitComment;
      string typeText = DealEntryToPositionTypeString(HistoryDealGetInteger(exitTicket, DEAL_TYPE));

      if(entryTicket != 0)
      {
         openTime = (datetime)HistoryDealGetInteger(entryTicket, DEAL_TIME);
         openPrice = HistoryDealGetDouble(entryTicket, DEAL_PRICE);
         string entryComment = HistoryDealGetString(entryTicket, DEAL_COMMENT);
         if(StringLen(TrimString(entryComment)) > 0)
            comment = entryComment;
         typeText = DealEntryToPositionTypeString(HistoryDealGetInteger(entryTicket, DEAL_TYPE));
      }

      ClosedTradeRecord record;
      record.ticket = exitTicket;
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
      record.comment = comment;

      PushClosedTrade(closedTrades, record);

      snapshots[symbolIndex].closedTrades++;
      if(exitProfit > 0.0)
         snapshots[symbolIndex].wins++;
      snapshots[symbolIndex].closedProfit += exitProfit;
      snapshots[symbolIndex].actualClosedProfit += exitProfit;
      if(closeTime > snapshots[symbolIndex].lastCloseTime)
         snapshots[symbolIndex].lastCloseTime = closeTime;
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
      json += "\"strategy\": \"" + JsonEscape(record.strategy) + "\", ";
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
   string placeholderReason = "MT5 phase 1 skeleton: JSON export is live, strategy execution port is not implemented yet";
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
      json += "\"strategies\": {";

      for(int s = 0; s < ArraySize(g_strategyKeys); s++)
      {
         if(s > 0)
            json += ", ";
         json += "\"" + g_strategyKeys[s] + "\": ";
         json += SymbolStrategyPlaceholderJson(placeholderReason);
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
   string reason = "MT5 phase 1 skeleton: adaptive control and strategy execution have not been ported yet";

   for(int i = 0; i < ArraySize(g_strategyKeys); i++)
   {
      if(i > 0)
         json += ", ";
      json += "\"" + g_strategyKeys[i] + "\": ";
      json += StrategyPlaceholderJson(g_focusSymbol, reason);
   }

   json += "}";
   return json;
}

string BuildDiagnosticsJson()
{
   string json = "{";
   string reason = "MT5 phase 1 skeleton: diagnostics become live after the MT5 strategy engine is ported";

   for(int i = 0; i < ArraySize(g_strategyKeys); i++)
   {
      if(i > 0)
         json += ", ";
      json += "\"" + g_strategyKeys[i] + "\": ";
      json += DiagnosticPlaceholderJson(reason);
   }

   json += "}";
   return json;
}

void ExportDashboard()
{
   if(ArraySize(g_symbols) == 0)
      InitializeWatchlist();

   SymbolSnapshot snapshots[];
   InitializeSnapshots(snapshots);

   string openTradesJson = BuildOpenTradesJson(snapshots);

   ClosedTradeRecord closedTrades[];
   CollectClosedTrades(snapshots, closedTrades);
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

   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   bool terminalTradeAllowed = (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   bool programTradeAllowed = (bool)MQLInfoInteger(MQL_TRADE_ALLOWED);
   bool dllAllowed = (bool)MQLInfoInteger(MQL_DLLS_ALLOWED);
   bool tradeAllowed = (connected && terminalTradeAllowed && programTradeAllowed);

   datetime serverClock = TimeTradeServer();
   if(serverClock <= 0 || !connected)
      serverClock = TimeLocal();

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
   json += "    \"tradeStatus\": \"" + (tradeAllowed ? "READY" : "NO_DATA") + "\",\r\n";
   json += "    \"connected\": " + JsonBool(connected) + ",\r\n";
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
   json += "    \"number\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + ",\r\n";
   json += "    \"name\": \"" + JsonEscape(AccountInfoString(ACCOUNT_NAME)) + "\",\r\n";
   json += "    \"server\": \"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",\r\n";
   json += "    \"currency\": \"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",\r\n";
   json += "    \"mode\": \"mt5_skeleton\",\r\n";
   json += "    \"startingBalance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"riskPercent\": 0.00,\r\n";
   json += "    \"executionLot\": 0.01,\r\n";
   json += "    \"balance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"equity\": " + FormatNumber(equity, 2) + ",\r\n";
   json += "    \"profit\": " + FormatNumber(profit, 2) + ",\r\n";
   json += "    \"margin\": " + FormatNumber(margin, 2) + ",\r\n";
   json += "    \"freeMargin\": " + FormatNumber(freeMargin, 2) + ",\r\n";
   json += "    \"drawdown\": " + FormatNumber(drawdown, 2) + ",\r\n";
   json += "    \"maxDrawdownPercent\": 0.00,\r\n";
   json += "    \"maxTotalTrades\": 0,\r\n";
   json += "    \"leverage\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\r\n";
   json += "  },\r\n";

   json += "  \"brokerAccount\": {\r\n";
   json += "    \"balance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"equity\": " + FormatNumber(equity, 2) + ",\r\n";
   json += "    \"profit\": " + FormatNumber(profit, 2) + ",\r\n";
   json += "    \"margin\": " + FormatNumber(margin, 2) + ",\r\n";
   json += "    \"freeMargin\": " + FormatNumber(freeMargin, 2) + ",\r\n";
   json += "    \"drawdown\": " + FormatNumber(drawdown, 2) + ",\r\n";
   json += "    \"server\": \"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",\r\n";
   json += "    \"leverage\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\r\n";
   json += "  },\r\n";

   json += "  \"watchlist\": \"" + JsonEscape(Watchlist) + "\",\r\n";
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

   WriteTextFile("QuantGod_Dashboard.json", json);
   ExportPlaceholderCsvs();
}

int OnInit()
{
   InitializeWatchlist();
   EventSetTimer(MathMax(1, RefreshIntervalSec));
   ExportDashboard();
   Print("QuantGod MT5 skeleton initialized. Focus symbol=", g_focusSymbol);
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
