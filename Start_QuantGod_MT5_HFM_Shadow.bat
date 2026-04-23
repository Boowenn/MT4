@echo off
title QuantGod MT5 HFM Shadow Launcher
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "QG_ROOT=C:\Program Files\HFM Metatrader 5"
set "QG_FILES=%QG_ROOT%\MQL5\Files"
set "QG_EXPERTS=%QG_ROOT%\MQL5\Experts"
set "QG_PRESETS=%QG_ROOT%\MQL5\Presets"
set "QG_CONFIG=%REPO_ROOT%\MQL5\Config\QuantGod_MT5_HFM_Shadow.ini"

echo ============================================
echo   QuantGod MT5 HFM Shadow Launcher
echo ============================================
echo.
if not exist "%QG_ROOT%\terminal64.exe" (
echo HFM MT5 terminal not found: %QG_ROOT%
echo Please install the official HFM MT5 Windows client first.
exit /b 1
)

echo 1. Syncing dashboard assets to MT5 Files...
copy /Y "%REPO_ROOT%\Dashboard\QuantGod_Dashboard.html" "%QG_FILES%\QuantGod_Dashboard.html" >nul
copy /Y "%REPO_ROOT%\Dashboard\dashboard_server.js" "%QG_FILES%\dashboard_server.js" >nul

echo 2. Syncing MT5 EA source...
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.mq5" "%QG_EXPERTS%\QuantGod_MultiStrategy.mq5" >nul
if exist "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" (
copy /Y "%REPO_ROOT%\MQL5\Experts\QuantGod_MultiStrategy.ex5" "%QG_EXPERTS%\QuantGod_MultiStrategy.ex5" >nul
)

echo 3. Syncing MT5 preset...
if not exist "%QG_PRESETS%" mkdir "%QG_PRESETS%"
copy /Y "%REPO_ROOT%\MQL5\Presets\QuantGod_MT5_HFM_Shadow.set" "%QG_PRESETS%\QuantGod_MT5_HFM_Shadow.set" >nul

echo 4. Restarting MT5 in read-only shadow mode...
taskkill /IM terminal64.exe /F >nul 2>nul
timeout /t 2 /nobreak >nul
start "" "%QG_ROOT%\terminal64.exe" /config:"%QG_CONFIG%"

echo 5. Starting local dashboard server...
start "QuantGod MT5 Dashboard Server" cmd /k "cd /d ""%QG_FILES%"" && node dashboard_server.js"

for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
timeout /t 2 /nobreak >nul

echo 6. Opening dashboard...
start "" "http://localhost:8080/QuantGod_Dashboard.html?ts=%QG_TS%"

echo.
echo Read-only shadow mode is ON. HFM account connection is allowed, but live trading stays disabled.
echo This launcher targets the HFM MT5 client at "%QG_ROOT%".
echo It expects the HFM account credentials to have been saved in the local HFM terminal already.
