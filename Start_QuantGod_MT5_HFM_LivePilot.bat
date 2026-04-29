@echo off
title QuantGod MT5 HFM Live Pilot Launcher
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "QG_ROOT=C:\Program Files\HFM Metatrader 5"
set "QG_FILES=%QG_ROOT%\MQL5\Files"
set "QG_EXPERTS=%QG_ROOT%\MQL5\Experts"
set "QG_PRESETS=%QG_ROOT%\MQL5\Presets"
set "QG_CONFIG=%REPO_ROOT%\MQL5\Config\QuantGod_MT5_HFM_LivePilot.ini"

echo ============================================
echo   QuantGod MT5 HFM Live Pilot Launcher
echo ============================================
echo.
if not exist "%QG_ROOT%\terminal64.exe" (
echo HFM MT5 terminal not found: %QG_ROOT%
echo Please install the official HFM MT5 Windows client first.
exit /b 1
)

echo 1. Syncing dashboard assets to MT5 Files...
if not exist "%QG_FILES%\vue-dist" mkdir "%QG_FILES%\vue-dist"
xcopy /E /I /Y "%REPO_ROOT%\Dashboard\vue-dist" "%QG_FILES%\vue-dist" >nul
copy /Y "%REPO_ROOT%\Dashboard\dashboard_server.js" "%QG_FILES%\dashboard_server.js" >nul
if exist "%REPO_ROOT%\archive\backtests\latest\QuantGod_BacktestSummary.json" (
copy /Y "%REPO_ROOT%\archive\backtests\latest\QuantGod_BacktestSummary.json" "%QG_FILES%\QuantGod_BacktestSummary.json" >nul
)

echo 1b. Refreshing governance advisor snapshot...
python "%REPO_ROOT%\tools\build_governance_advisor.py" --runtime-dir "%QG_FILES%" >nul 2>nul
if errorlevel 1 (
echo Governance advisor refresh skipped; dashboard will continue without it.
)

echo 2. Syncing MT5 EA source...
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.mq5" "%QG_EXPERTS%\QuantGod_MultiStrategy.mq5" >nul
if exist "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" (
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" "%QG_EXPERTS%\QuantGod_MultiStrategy.ex5" >nul
)

echo 3. Syncing MT5 live pilot preset...
if not exist "%QG_PRESETS%" mkdir "%QG_PRESETS%"
copy /Y "%REPO_ROOT%\MQL5\Presets\QuantGod_MT5_HFM_LivePilot.set" "%QG_PRESETS%\QuantGod_MT5_HFM_LivePilot.set" >nul

echo 4. Restarting MT5 in live pilot mode...
taskkill /IM terminal64.exe /F >nul 2>nul
timeout /t 2 /nobreak >nul
start "" "%QG_ROOT%\terminal64.exe" /config:"%QG_CONFIG%"

echo 5. Starting local dashboard server...
start "QuantGod MT5 Dashboard Server" cmd /k "cd /d ""%QG_FILES%"" && node dashboard_server.js"

for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
timeout /t 2 /nobreak >nul

echo 6. Opening dashboard...
call "%REPO_ROOT%\tools\open_dashboard_chrome.bat" "http://localhost:8080/vue/?ts=%QG_TS%"

echo.
echo Live pilot mode is ON with 0.01 lot cap and kill switches.
echo This launcher targets the HFM MT5 client at "%QG_ROOT%".
echo Manual positions stay protected, but they do not block same-symbol EA pilot evaluation.
echo Shadow Signal Ledger will append no-trade learning samples on each new M15 evaluation.
