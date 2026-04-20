@echo off
setlocal

set "ROOT=C:\Program Files (x86)\MetaTrader 4"
set "FILES=%ROOT%\MQL4\Files"

echo ============================================
echo   QuantGod One-Click Launcher
echo ============================================
echo.
echo 1. Starting dashboard server if needed...
echo 2. Opening dashboard...
echo 3. Launching MT4 in portable mode...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = 'C:\Program Files (x86)\MetaTrader 4';" ^
  "$files = Join-Path $root 'MQL4\Files';" ^
  "$ts = [DateTimeOffset]::Now.ToUnixTimeSeconds();" ^
  "$dashUrl = ('http://localhost:8080/QuantGod_Dashboard.html?ts=' + $ts);" ^
  "try { $resp = Invoke-WebRequest 'http://localhost:8080/QuantGod_Dashboard.html' -UseBasicParsing -TimeoutSec 2; $serverUp = ($resp.StatusCode -eq 200) } catch { $serverUp = $false };" ^
  "if(-not $serverUp) { Start-Process python -ArgumentList '-m','http.server','8080' -WorkingDirectory $files -WindowStyle Minimized };" ^
  "Start-Sleep -Seconds 1;" ^
  "Start-Process $dashUrl;" ^
  "Start-Process (Join-Path $root 'terminal.exe') -ArgumentList '/portable'"

echo.
echo QuantGod launch completed.
echo Dashboard: http://localhost:8080/QuantGod_Dashboard.html
echo.
timeout /t 3 >nul
