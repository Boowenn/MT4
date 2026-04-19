//+------------------------------------------------------------------+
//|                                              AttachQuantGod.mq4  |
//|                          Helper script to guide EA attachment     |
//+------------------------------------------------------------------+
#property copyright "QuantGod"
#property link      "https://github.com/Boowenn/MT4"
#property version   "1.00"
#property strict
#property show_inputs

input string Info1 = "=== QuantGod Multi-Strategy EA ===";
input string Info2 = "请按以下步骤操作:";
input string Info3 = "1. 打开 导航器(Ctrl+N)";
input string Info4 = "2. 展开 Expert Advisors";
input string Info5 = "3. 将 QuantGod_MultiStrategy 拖到图表上";
input string Info6 = "4. 勾选 Allow live trading";
input string Info7 = "5. 点击 OK";

void OnStart()
{
   MessageBox(
      "QuantGod Multi-Strategy Engine v2.0\n\n"
      "EA已编译就绪!\n\n"
      "操作步骤:\n"
      "1. 按 Ctrl+N 打开导航器\n"
      "2. 展开 Expert Advisors 文件夹\n"
      "3. 找到 QuantGod_MultiStrategy\n"
      "4. 双击或拖到图表上\n"
      "5. 在弹出窗口中:\n"
      "   - 勾选 'Allow live trading'\n"
      "   - 调整策略参数(可选)\n"
      "   - 点击 OK\n\n"
      "6. 图表左上角出现笑脸图标即表示运行成功\n\n"
      "Dashboard面板:\n"
      "打开浏览器访问 http://localhost:8080/QuantGod_Dashboard.html\n"
      "或双击 MQL4\\Files\\start_dashboard.bat",
      "QuantGod Setup Guide",
      MB_OK | MB_ICONINFORMATION
   );
}
//+------------------------------------------------------------------+
