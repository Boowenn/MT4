@echo off
title QuantGod One-Click Launcher
set "QG_ROOT=C:\Program Files (x86)\MetaTrader 4"
set "QG_FILES=%QG_ROOT%\MQL4\Files"

echo ============================================
echo   QuantGod One-Click Launcher
echo ============================================
echo.
echo 1. Starting MT4 terminal...
start "" "%QG_ROOT%\terminal.exe"

echo 2. Starting dashboard server...
start "QuantGod Dashboard Server" cmd /k "cd /d ""%QG_FILES%"" && node dashboard_server.js"

if exist "%QG_FILES%\\quantgod_cloud_sync.json" (
echo 3. Starting cloud sync uploader...
start "QuantGod Cloud Sync" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%QG_FILES%\\cloud_sync_uploader.ps1"
)

for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
timeout /t 2 /nobreak >nul

echo 4. Opening dashboard...
start "" "http://localhost:8080/QuantGod_Dashboard.html?ts=%QG_TS%"

echo.
echo QuantGod is launching. You can close this window.
