@echo off
title QuantGod One-Click Launcher
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
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

if exist "%QG_FILES%\\quantgod_cloud_sync.enabled.json" (
echo 3. Starting cloud sync uploader...
start "QuantGod Cloud Sync" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%QG_FILES%\\cloud_sync_uploader.ps1"
) else (
echo 3. Cloud sync disabled ^(local-first mode^)
)

for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
timeout /t 2 /nobreak >nul

echo 4. Opening dashboard...
call "%REPO_ROOT%\tools\open_dashboard_chrome.bat" "http://localhost:8080/QuantGod_Dashboard.html?ts=%QG_TS%"

echo.
echo QuantGod is launching. You can close this window.
