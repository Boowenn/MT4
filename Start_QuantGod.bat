@echo off
title QuantGod Launcher
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

echo ============================================
echo   QuantGod Launcher
echo ============================================
echo.
echo MT4/MQL4 has been retired from this repo.
echo Delegating to the MT5/HFM launcher.
echo.
call "%REPO_ROOT%\Start_QuantGod_MT5.bat"
