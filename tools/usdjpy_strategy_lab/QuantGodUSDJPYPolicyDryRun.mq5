//+------------------------------------------------------------------+
//| QuantGod USDJPY Policy Dry Run Reader                            |
//| Read-only EA helper: reads QuantGod_USDJPYAutoExecutionPolicy.json |
//| and writes dry-run decision evidence. It never sends orders.       |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "QuantGod USDJPY-only policy dry-run reader. No trading actions."

input string QG_FocusSymbol = "USDJPYc";
input int    QG_TimerSeconds = 5;
input bool   QG_WriteLedger = true;

string QG_POLICY_FILE = "adaptive\\QuantGod_USDJPYAutoExecutionPolicy.json";
string QG_DECISION_FILE = "adaptive\\QuantGod_USDJPYEADryRunDecision.json";
string QG_LEDGER_FILE = "adaptive\\QuantGod_USDJPYEADryRunDecisionLedger.csv";

int OnInit()
{
   if(StringFind(_Symbol, "USDJPY") != 0)
   {
      Print("QuantGod USDJPY dry-run reader attached to non-focus symbol: ", _Symbol, ". It will stay read-only.");
   }
   EventSetTimer(MathMax(1, QG_TimerSeconds));
   WriteDecision("INIT", "阻断", "EA 已启动，仅干跑，不下单", 0.0, "UNKNOWN", "UNKNOWN");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   string text = ReadAllText(QG_POLICY_FILE);
   if(StringLen(text) <= 0)
   {
      WriteDecision("MISSING_POLICY", "阻断", "缺少 USDJPY 自动执行政策文件", 0.0, "UNKNOWN", "UNKNOWN");
      return;
   }
   if(StringFind(text, "\"symbol\": \"USDJPYc\"") < 0 && StringFind(text, "USDJPY") < 0)
   {
      WriteDecision("NON_FOCUS_POLICY", "阻断", "政策文件不是 USDJPY 专用，已忽略", 0.0, "UNKNOWN", "UNKNOWN");
      return;
   }

   string mode = ExtractValue(text, "entryMode");
   string strategy = ExtractValue(text, "strategy");
   string direction = ExtractValue(text, "direction");
   double lot = ExtractNumber(text, "recommendedLot");

   if(mode == "STANDARD_ENTRY")
   {
      WriteDecision(mode, "本应标准入场", "EA 干跑：标准入场候选，不执行真实订单", lot, strategy, direction);
      return;
   }
   if(mode == "OPPORTUNITY_ENTRY")
   {
      WriteDecision(mode, "本应机会入场", "EA 干跑：机会入场候选，只记录不下单", lot, strategy, direction);
      return;
   }
   WriteDecision(mode, "阻断", "EA 干跑：政策不允许入场", 0.0, strategy, direction);
}

string ReadAllText(string fileName)
{
   int handle = FileOpen(fileName, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return "";
   string result = "";
   while(!FileIsEnding(handle))
      result += FileReadString(handle) + "\n";
   FileClose(handle);
   return result;
}

string ExtractValue(string text, string key)
{
   string needle = "\"" + key + "\"";
   int pos = StringFind(text, needle);
   if(pos < 0) return "UNKNOWN";
   int colon = StringFind(text, ":", pos);
   if(colon < 0) return "UNKNOWN";
   int firstQuote = StringFind(text, "\"", colon + 1);
   if(firstQuote < 0) return "UNKNOWN";
   int secondQuote = StringFind(text, "\"", firstQuote + 1);
   if(secondQuote < 0) return "UNKNOWN";
   return StringSubstr(text, firstQuote + 1, secondQuote - firstQuote - 1);
}

double ExtractNumber(string text, string key)
{
   string needle = "\"" + key + "\"";
   int pos = StringFind(text, needle);
   if(pos < 0) return 0.0;
   int colon = StringFind(text, ":", pos);
   if(colon < 0) return 0.0;
   int end = colon + 1;
   while(end < StringLen(text))
   {
      ushort ch = StringGetCharacter(text, end);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-') end++;
      else if(ch == ' ' || ch == '\t') end++;
      else break;
   }
   string raw = StringSubstr(text, colon + 1, end - colon - 1);
   StringTrimLeft(raw);
   StringTrimRight(raw);
   return StringToDouble(raw);
}

void WriteDecision(string mode, string decision, string reason, double lot, string strategy, string direction)
{
   string now = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS);
   string escapedReason = EscapeJson(reason);
   string json = "{\n";
   json += "  \"schema\": \"quantgod.usdjpy_ea_dry_run_decision.v1\",\n";
   json += "  \"generatedAt\": \"" + now + "\",\n";
   json += "  \"symbol\": \"" + QG_FocusSymbol + "\",\n";
   json += "  \"entryMode\": \"" + mode + "\",\n";
   json += "  \"decision\": \"" + decision + "\",\n";
   json += "  \"strategy\": \"" + EscapeJson(strategy) + "\",\n";
   json += "  \"direction\": \"" + EscapeJson(direction) + "\",\n";
   json += "  \"recommendedLot\": " + DoubleToString(lot, 2) + ",\n";
   json += "  \"reason\": \"" + escapedReason + "\",\n";
   json += "  \"safety\": {\"dryRunOnly\": true, \"orderSendAllowed\": false, \"closeAllowed\": false, \"cancelAllowed\": false}\n";
   json += "}\n";

   int handle = FileOpen(QG_DECISION_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      FileWriteString(handle, json);
      FileClose(handle);
   }

   if(QG_WriteLedger)
   {
      bool exists = FileIsExist(QG_LEDGER_FILE);
      int ledger = FileOpen(QG_LEDGER_FILE, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(ledger != INVALID_HANDLE)
      {
         FileSeek(ledger, 0, SEEK_END);
         if(!exists)
            FileWrite(ledger, "generatedAt", "symbol", "entryMode", "decision", "strategy", "direction", "recommendedLot", "reason");
         FileWrite(ledger, now, QG_FocusSymbol, mode, decision, strategy, direction, DoubleToString(lot, 2), reason);
         FileClose(ledger);
      }
   }
}

string EscapeJson(string value)
{
   string result = value;
   StringReplace(result, "\\", "\\\\");
   StringReplace(result, "\"", "\\\"");
   StringReplace(result, "\r", " ");
   StringReplace(result, "\n", " ");
   return result;
}
