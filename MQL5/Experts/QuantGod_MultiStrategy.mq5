//+------------------------------------------------------------------+
//|                                         QuantGod_MultiStrategy.mq5 |
//|                              QuantGod MT5 Migration Skeleton      |
//+------------------------------------------------------------------+
#property copyright "QuantGod"
#property link      "https://github.com/Boowenn/MT4"
#property version   "3.20"
#property strict

input string DashboardBuild      = "QuantGod-v3.2-mt5-live-journal";
input string Watchlist           = "EURUSD,USDJPY";
input string PreferredSymbolSuffix = "AUTO";
input bool   ShadowMode          = true;
input bool   ReadOnlyMode        = true;
input int    RefreshIntervalSec  = 5;
input int    ClosedTradeLimit    = 50;
input int    HistoryLookbackDays = 30;

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
   int handle = FileOpen(fileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      Print("QuantGod MT5 skeleton failed to open file for write: ", fileName, " err=", GetLastError());
      return;
   }
   FileWriteString(handle, content);
   FileClose(handle);
}

void UpdateShadowChartComment(string tradeStatus, bool connected, long accountLogin)
{
   string message = "QuantGod MT5 Shadow\r\n";
   message += "Status: " + tradeStatus + "\r\n";
   message += "ReadOnly: " + (ReadOnlyMode ? "true" : "false") + "\r\n";
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

      csv += CsvEscape(FormatDateTime(TimeLocal(), true)) + ",";
      csv += CsvEscape(FormatDateTime(serverClock, true)) + ",";
      csv += CsvEscape(record.symbol) + ",";
      csv += CsvEscape(record.strategy) + ",";
      csv += CsvEscape(record.timeframe) + ",";
      csv += CsvEscape("ALL") + ",";
      csv += "false,false,";
      csv += CsvEscape("SHADOW") + ",";
      csv += CsvEscape("WARMUP") + ",";
      csv += CsvEscape("MT5 shadow journaling only") + ",";
      csv += "0.00,";
      csv += CsvEscape("SHADOW") + ",";
      csv += CsvEscape("NO_DATA") + ",";
      csv += CsvEscape("HFM MT5 shadow journaling active") + ",";
      csv += "0.0,";
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

      if(symbolIndex >= 0)
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
   string tradeStatus = connected ? (ReadOnlyMode ? "SHADOW" : "READY") : "NO_DATA";

   datetime serverClock = TimeTradeServer();
   if(serverClock <= 0)
      serverClock = TimeCurrent();
   if(serverClock <= 0)
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
   json += "    \"tradeStatus\": \"" + tradeStatus + "\",\r\n";
    json += "    \"shadowMode\": " + JsonBool(ShadowMode) + ",\r\n";
    json += "    \"readOnlyMode\": " + JsonBool(ReadOnlyMode) + ",\r\n";
   json += "    \"executionEnabled\": " + JsonBool(!ReadOnlyMode) + ",\r\n";
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
   json += "    \"mode\": \"" + JsonEscape(ShadowMode ? "mt5_shadow" : "mt5_runtime") + "\",\r\n";
   json += "    \"accountMode\": \"" + AccountMarginModeToString(AccountInfoInteger(ACCOUNT_MARGIN_MODE)) + "\",\r\n";
   json += "    \"symbolSuffix\": \"" + JsonEscape(g_detectedSuffix) + "\",\r\n";
   json += "    \"startingBalance\": " + FormatNumber(balance, 2) + ",\r\n";
   json += "    \"riskPercent\": 0.00,\r\n";
   json += "    \"executionLot\": " + FormatNumber(SymbolInfoDouble(g_focusSymbol, SYMBOL_VOLUME_MIN), 2) + ",\r\n";
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
   statusFile += "connected=" + (connected ? "true" : "false") + "\r\n";
   statusFile += "focusSymbol=" + g_focusSymbol + "\r\n";
   statusFile += "watchlist=" + g_resolvedWatchlist + "\r\n";
   statusFile += "account=" + IntegerToString((int)accountLogin) + "\r\n";
   statusFile += "server=" + accountServer + "\r\n";
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
   EventSetTimer(MathMax(1, RefreshIntervalSec));
   ExportDashboard();
   Print("QuantGod MT5 shadow runtime initialized. Focus symbol=", g_focusSymbol,
         " watchlist=", g_resolvedWatchlist, " suffix=", g_detectedSuffix,
         " readOnly=", (ReadOnlyMode ? "true" : "false"));
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
