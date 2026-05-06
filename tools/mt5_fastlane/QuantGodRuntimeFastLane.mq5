#property strict
#property description "QuantGod runtime fast lane exporter. Read-only evidence writer."

input string QG_Symbols = "USDJPYc";
input int QG_TimerSeconds = 1;
input int QG_TickFlushEvery = 1;
input int QG_IndicatorPeriod = 14;

string symbols[];
ulong tick_sequence = 0;
ulong timer_sequence = 0;
ulong on_tick_sequence = 0;

string IsoNow()
{
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", " ");
   StringReplace(value, "\n", " ");
   return value;
}

void SplitSymbols()
{
   string raw = QG_Symbols;
   StringReplace(raw, " ", "");
   int count = StringSplit(raw, ',', symbols);
   if(count <= 0)
   {
      ArrayResize(symbols, 1);
      symbols[0] = _Symbol;
   }
}

void WriteTextFile(string filename, string text)
{
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;
   FileWriteString(handle, text);
   FileClose(handle);
}

void AppendTextFile(string filename, string text)
{
   int handle = FileOpen(filename, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return;
   FileSeek(handle, 0, SEEK_END);
   FileWriteString(handle, text + "\n");
   FileClose(handle);
}

string SafetyJson()
{
   return "\"safety\":{\"localOnly\":true,\"readOnlyDataPlane\":true,\"advisoryOnly\":true,\"runtimeEvidenceOnly\":true,\"orderSendAllowed\":false,\"closeAllowed\":false,\"cancelAllowed\":false,\"modifyAllowed\":false,\"brokerExecutionAllowed\":false,\"livePresetMutationAllowed\":false,\"credentialStorageAllowed\":false,\"telegramCommandExecutionAllowed\":false,\"telegramWebhookReceiverAllowed\":false,\"webhookReceiverAllowed\":false,\"canOverrideKillSwitch\":false}";
}

void WriteHeartbeat()
{
   timer_sequence++;
   string body = "{";
   body += "\"schema\":\"quantgod.mt5.fast_lane.heartbeat.v1\",";
   body += "\"generatedAt\":\"" + IsoNow() + "\",";
   body += "\"source\":\"mt5_runtime_fast_lane_ea\",";
   body += "\"timerSequence\":" + (string)timer_sequence + ",";
   body += "\"terminalConnected\":" + (TerminalInfoInteger(TERMINAL_CONNECTED) ? "true" : "false") + ",";
   body += "\"tradeAllowedOnTerminal\":" + (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "true" : "false") + ",";
   body += "\"accountBalance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   body += "\"accountEquity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   body += SafetyJson();
   body += "}";
   WriteTextFile("QuantGod_RuntimeHeartbeat.json", body);
}

void AppendTick(string symbol)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick)) return;
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point <= 0) point = 0.00001;
   double spreadPoints = MathAbs(tick.ask - tick.bid) / point;
   tick_sequence++;
   string body = "{";
   body += "\"schema\":\"quantgod.mt5.fast_lane.tick.v1\",";
   body += "\"generatedAt\":\"" + IsoNow() + "\",";
   body += "\"timeIso\":\"" + IsoNow() + "\",";
   body += "\"source\":\"mt5_runtime_fast_lane_ea\",";
   body += "\"sequence\":" + (string)tick_sequence + ",";
   body += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
   body += "\"bid\":" + DoubleToString(tick.bid, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ",";
   body += "\"ask\":" + DoubleToString(tick.ask, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ",";
   body += "\"last\":" + DoubleToString(tick.last, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)) + ",";
   body += "\"volume\":" + DoubleToString((double)tick.volume, 0) + ",";
   body += "\"point\":" + DoubleToString(point, 10) + ",";
   body += "\"spreadPoints\":" + DoubleToString(spreadPoints, 2) + ",";
   body += SafetyJson();
   body += "}";
   AppendTextFile("QuantGod_RuntimeTicks_" + symbol + ".jsonl", body);
}

void WriteIndicators(string symbol)
{
   double atrBuffer[], adxBuffer[], upperBuffer[], lowerBuffer[];
   int atrHandle = iATR(symbol, PERIOD_M15, QG_IndicatorPeriod);
   int adxHandle = iADX(symbol, PERIOD_M15, QG_IndicatorPeriod);
   int bandsHandle = iBands(symbol, PERIOD_M15, 20, 0, 2.0, PRICE_CLOSE);
   double atr = 0.0, adx = 0.0, bbWidth = 0.0;
   if(atrHandle != INVALID_HANDLE && CopyBuffer(atrHandle, 0, 0, 1, atrBuffer) > 0) atr = atrBuffer[0];
   if(adxHandle != INVALID_HANDLE && CopyBuffer(adxHandle, 0, 0, 1, adxBuffer) > 0) adx = adxBuffer[0];
   if(bandsHandle != INVALID_HANDLE && CopyBuffer(bandsHandle, 1, 0, 1, upperBuffer) > 0 && CopyBuffer(bandsHandle, 2, 0, 1, lowerBuffer) > 0) bbWidth = MathAbs(upperBuffer[0] - lowerBuffer[0]);
   if(atrHandle != INVALID_HANDLE) IndicatorRelease(atrHandle);
   if(adxHandle != INVALID_HANDLE) IndicatorRelease(adxHandle);
   if(bandsHandle != INVALID_HANDLE) IndicatorRelease(bandsHandle);
   datetime barOpen = iTime(symbol, PERIOD_M15, 0);
   double barProgress = 0.0;
   if(barOpen > 0) barProgress = MathMin(100.0, MathMax(0.0, 100.0 * (double)(TimeCurrent() - barOpen) / (15.0 * 60.0)));
   string body = "{";
   body += "\"schema\":\"quantgod.mt5.fast_lane.indicators.v1\",";
   body += "\"generatedAt\":\"" + IsoNow() + "\",";
   body += "\"source\":\"mt5_runtime_fast_lane_ea\",";
   body += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
   body += "\"timeframe\":\"M15\",";
   body += "\"atr\":" + DoubleToString(atr, 8) + ",";
   body += "\"adx\":" + DoubleToString(adx, 4) + ",";
   body += "\"bbWidth\":" + DoubleToString(bbWidth, 8) + ",";
   body += "\"barProgressPct\":" + DoubleToString(barProgress, 2) + ",";
   body += SafetyJson();
   body += "}";
   WriteTextFile("QuantGod_RuntimeIndicators_" + symbol + ".json", body);
}

void AppendDiagnostics(string symbol, string status)
{
   string body = "{";
   body += "\"schema\":\"quantgod.mt5.fast_lane.diagnostics.v1\",";
   body += "\"generatedAt\":\"" + IsoNow() + "\",";
   body += "\"source\":\"mt5_runtime_fast_lane_ea\",";
   body += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
   body += "\"status\":\"" + JsonEscape(status) + "\",";
   body += SafetyJson();
   body += "}";
   AppendTextFile("QuantGod_RuntimeStrategyDiagnostics.jsonl", body);
}

int OnInit()
{
   SplitSymbols();
   EventSetTimer(MathMax(1, QG_TimerSeconds));
   WriteHeartbeat();
   for(int i = 0; i < ArraySize(symbols); i++)
      AppendDiagnostics(symbols[i], "FAST_LANE_STARTED");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int i = 0; i < ArraySize(symbols); i++)
      AppendDiagnostics(symbols[i], "FAST_LANE_STOPPED");
}

void OnTick()
{
   on_tick_sequence++;
   int flushEvery = MathMax(1, QG_TickFlushEvery);
   if((on_tick_sequence % (ulong)flushEvery) != 0)
      return;
   for(int i = 0; i < ArraySize(symbols); i++)
      AppendTick(symbols[i]);
}

void OnTimer()
{
   WriteHeartbeat();
   for(int i = 0; i < ArraySize(symbols); i++)
   {
      AppendTick(symbols[i]);
      WriteIndicators(symbols[i]);
      AppendDiagnostics(symbols[i], "FAST_LANE_TIMER_OK");
   }
}

void OnTradeTransaction(const MqlTradeTransaction& trans, const MqlTradeRequest& request, const MqlTradeResult& result)
{
   string body = "{";
   body += "\"schema\":\"quantgod.mt5.fast_lane.trade_event.v1\",";
   body += "\"generatedAt\":\"" + IsoNow() + "\",";
   body += "\"source\":\"mt5_runtime_fast_lane_ea\",";
   body += "\"eventType\":" + (string)trans.type + ",";
   body += "\"symbol\":\"" + JsonEscape(trans.symbol) + "\",";
   body += "\"price\":" + DoubleToString(trans.price, 8) + ",";
   body += "\"volume\":" + DoubleToString(trans.volume, 2) + ",";
   body += "\"retcode\":" + (string)result.retcode + ",";
   body += SafetyJson();
   body += "}";
   AppendTextFile("QuantGod_RuntimeTradeEvents.jsonl", body);
}
