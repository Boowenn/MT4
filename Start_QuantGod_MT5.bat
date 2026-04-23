@echo off
title QuantGod MT5 Launcher
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "QG_ROOT=C:\Program Files\MetaTrader 5"
set "QG_FILES=%QG_ROOT%\MQL5\Files"
set "QG_EXPERTS=%QG_ROOT%\MQL5\Experts"
set "QG_CONFIG=%REPO_ROOT%\MQL5\Config\QuantGod_MT5_Start.ini"

echo ============================================
echo   QuantGod MT5 Phase 1 Launcher
echo ============================================
echo.
echo 1. Syncing dashboard assets to MT5 Files...
copy /Y "%REPO_ROOT%\Dashboard\QuantGod_Dashboard.html" "%QG_FILES%\QuantGod_Dashboard.html" >nul
copy /Y "%REPO_ROOT%\Dashboard\dashboard_server.js" "%QG_FILES%\dashboard_server.js" >nul

echo 2. Syncing MT5 EA source...
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.mq5" "%QG_EXPERTS%\QuantGod_MultiStrategy.mq5" >nul
if exist "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" (
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" "%QG_EXPERTS%\QuantGod_MultiStrategy.ex5" >nul
)

echo 3. Starting MT5 terminal...
start "" "%QG_ROOT%\terminal64.exe" /config:"%QG_CONFIG%"

echo 4. Starting local dashboard server...
start "QuantGod MT5 Dashboard Server" cmd /k "cd /d ""%QG_FILES%"" && node dashboard_server.js"

for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
timeout /t 2 /nobreak >nul

echo 5. Opening dashboard...
start "" "http://localhost:8080/QuantGod_Dashboard.html?ts=%QG_TS%"

echo.
echo Note: compile QuantGod_MultiStrategy.mq5 in MetaEditor64 once so the launcher can sync the ex5.
echo This launcher uses the MT5 startup config to open EURUSD M1 and auto-load QuantGod_MultiStrategy.
echo MT5 phase 1 currently exports runtime JSON/CSV only. Strategy execution is not ported yet.
