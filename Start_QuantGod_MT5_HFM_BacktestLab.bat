@echo off
title QuantGod MT5 HFM Backtest Lab V1
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

echo ============================================
echo   QuantGod MT5 HFM Backtest Lab V1
echo ============================================
echo.
echo Preparing MA_Cross tester configs for EURUSDc / USDJPYc.
echo This default run does not interrupt the live HFM terminal.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\tools\run_mt5_backtest_lab.ps1"
echo.
echo If you intentionally want to launch MT5 Strategy Tester, run:
echo powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%\tools\run_mt5_backtest_lab.ps1" -RunTerminal
echo.
pause
