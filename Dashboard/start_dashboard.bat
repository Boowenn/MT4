@echo off
title QuantGod Dashboard Server
set "REPO_ROOT=%~dp0.."
echo ============================================
echo   QuantGod Trading Dashboard Server
echo ============================================
echo.
echo Starting server at http://localhost:8080
echo Vue workbench: http://localhost:8080/vue/
echo Legacy fallback: http://localhost:8080/QuantGod_Dashboard.html
echo.
echo Press Ctrl+C to stop the server.
echo.
cd /d "%~dp0"
for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
call "%REPO_ROOT%\tools\open_dashboard_chrome.bat" "http://localhost:8080/vue/?ts=%QG_TS%"
node dashboard_server.js
