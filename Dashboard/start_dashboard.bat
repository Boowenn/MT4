@echo off
title QuantGod Dashboard Server
echo ============================================
echo   QuantGod Trading Dashboard Server
echo ============================================
echo.
echo Starting server at http://localhost:8080
echo Dashboard: http://localhost:8080/QuantGod_Dashboard.html
echo.
echo Press Ctrl+C to stop the server.
echo.
cd /d "C:\Program Files (x86)\MetaTrader 4\MQL4\Files"
for /f %%i in ('powershell -NoProfile -Command "[DateTimeOffset]::Now.ToUnixTimeSeconds()"') do set "QG_TS=%%i"
start "" "http://localhost:8080/QuantGod_Dashboard.html?ts=%QG_TS%"
node dashboard_server.js
