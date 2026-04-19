//+------------------------------------------------------------------+
//|                                                  QuantEngine.mqh |
//|                          QuantGod Multi-Strategy Trading Engine   |
//|                              https://github.com/Boowenn/MT4      |
//+------------------------------------------------------------------+
#property copyright "QuantGod Engine"
#property link      "https://github.com/Boowenn/MT4"
#property strict

//=== 策略枚举 ===
enum ENUM_STRATEGY
{
   STRAT_MA_CROSS    = 0,  // MA交叉策略
   STRAT_RSI_REVERSAL= 1,  // RSI均值回归
   STRAT_BB_TRIPLE   = 2,  // 布林带三重确认
   STRAT_MACD_DIV    = 3,  // MACD背离
   STRAT_SR_BREAKOUT = 4   // 支撑阻力突破
};

//=== 信号枚举 ===
enum ENUM_SIGNAL
{
   SIGNAL_NONE = 0,
   SIGNAL_BUY  = 1,
   SIGNAL_SELL = -1
};

//=== 交易信息结构 ===
struct TradeInfo
{
   int       ticket;
   string    symbol;
   int       type;
   double    lots;
   double    openPrice;
   double    sl;
   double    tp;
   double    profit;
   datetime  openTime;
   string    strategy;
   string    comment;
};

//=== 策略信号结构 ===
struct StrategySignal
{
   ENUM_SIGNAL signal;
   double      strength;    // 信号强度 0-100
   double      suggestedSL;
   double      suggestedTP;
   string      reason;
};

//+------------------------------------------------------------------+
//| 资金管理 - 计算手数                                                |
//+------------------------------------------------------------------+
double CalcLotSize(double riskPercent, double slPips, string symbol_name)
{
   double accountRisk = AccountBalance() * riskPercent / 100.0;
   double tickValue = MarketInfo(symbol_name, MODE_TICKVALUE);
   double tickSize = MarketInfo(symbol_name, MODE_TICKSIZE);
   double point = MarketInfo(symbol_name, MODE_POINT);

   if(tickValue == 0 || point == 0) return 0.01;

   double pipValue = tickValue * (0.0001 / tickSize);
   if(StringFind(symbol_name, "JPY") >= 0)
      pipValue = tickValue * (0.01 / tickSize);

   double lots = accountRisk / (slPips * pipValue);

   double minLot = MarketInfo(symbol_name, MODE_MINLOT);
   double maxLot = MarketInfo(symbol_name, MODE_MAXLOT);
   double lotStep = MarketInfo(symbol_name, MODE_LOTSTEP);

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
//| 获取点差 (pips)                                                    |
//+------------------------------------------------------------------+
double GetSpreadPips(string symbol_name)
{
   double spread = MarketInfo(symbol_name, MODE_SPREAD);
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   if(digits == 3 || digits == 5)
      spread /= 10.0;
   return spread;
}

//+------------------------------------------------------------------+
//| 点转价格                                                           |
//+------------------------------------------------------------------+
double PipsToPrice(double pips, string symbol_name)
{
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   if(digits == 3 || digits == 5)
      return pips * 10 * MarketInfo(symbol_name, MODE_POINT);
   else
      return pips * MarketInfo(symbol_name, MODE_POINT);
}

//+------------------------------------------------------------------+
//| 检查交易时段                                                       |
//+------------------------------------------------------------------+
bool IsTradeSession()
{
   int hour = TimeHour(TimeCurrent());
   // 伦敦 + 纽约时段 (GMT 7:00 - 21:00)
   if(hour >= 7 && hour <= 21) return true;
   return false;
}

//+------------------------------------------------------------------+
//| 检查是否已有该策略持仓                                              |
//+------------------------------------------------------------------+
bool HasOpenPosition(int magic, string symbol_name)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == magic && OrderSymbol() == symbol_name)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| 计算该策略持仓数量                                                  |
//+------------------------------------------------------------------+
int CountPositions(int magic, string symbol_name)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == magic && OrderSymbol() == symbol_name)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| 移动止损 (追踪止损)                                                 |
//+------------------------------------------------------------------+
void TrailingStop(int magic, double trailPips, string symbol_name)
{
   double trailPrice = PipsToPrice(trailPips, symbol_name);

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != magic || OrderSymbol() != symbol_name) continue;

      if(OrderType() == OP_BUY)
      {
         double newSL = MarketInfo(symbol_name, MODE_BID) - trailPrice;
         if(newSL > OrderStopLoss() + MarketInfo(symbol_name, MODE_POINT) &&
            newSL > OrderOpenPrice())
         {
            OrderModify(OrderTicket(), OrderOpenPrice(),
                       NormalizeDouble(newSL, (int)MarketInfo(symbol_name, MODE_DIGITS)),
                       OrderTakeProfit(), 0, clrGreen);
         }
      }
      else if(OrderType() == OP_SELL)
      {
         double newSL = MarketInfo(symbol_name, MODE_ASK) + trailPrice;
         if((newSL < OrderStopLoss() - MarketInfo(symbol_name, MODE_POINT) || OrderStopLoss() == 0) &&
            newSL < OrderOpenPrice())
         {
            OrderModify(OrderTicket(), OrderOpenPrice(),
                       NormalizeDouble(newSL, (int)MarketInfo(symbol_name, MODE_DIGITS)),
                       OrderTakeProfit(), 0, clrRed);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ATR止损计算                                                        |
//+------------------------------------------------------------------+
double GetATRStopLoss(string symbol_name, int timeframe, int period, double multiplier)
{
   double atr = iATR(symbol_name, timeframe, period, 1);
   int digits = (int)MarketInfo(symbol_name, MODE_DIGITS);
   double point = MarketInfo(symbol_name, MODE_POINT);

   double slPrice = atr * multiplier;
   return NormalizeDouble(slPrice / point / ((digits == 3 || digits == 5) ? 10.0 : 1.0), 1);
}

//+------------------------------------------------------------------+
//| 检查最大回撤                                                       |
//+------------------------------------------------------------------+
bool CheckMaxDrawdown(double maxDDPercent)
{
   double balance = AccountBalance();
   double equity = AccountEquity();
   if(balance == 0) return false;

   double dd = (balance - equity) / balance * 100.0;
   return dd < maxDDPercent;
}

//+------------------------------------------------------------------+
//| 关闭指定策略所有持仓                                                |
//+------------------------------------------------------------------+
void CloseAllByMagic(int magic, string symbol_name)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != magic || OrderSymbol() != symbol_name) continue;

      if(OrderType() == OP_BUY)
         OrderClose(OrderTicket(), OrderLots(), MarketInfo(symbol_name, MODE_BID), 3, clrRed);
      else if(OrderType() == OP_SELL)
         OrderClose(OrderTicket(), OrderLots(), MarketInfo(symbol_name, MODE_ASK), 3, clrBlue);
   }
}
