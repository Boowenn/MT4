@echo off
setlocal
cd /d "%~dp0\.."
python tools\run_polymarket_canary_executor_v1.py %*
endlocal
