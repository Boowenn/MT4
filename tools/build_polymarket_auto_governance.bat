@echo off
setlocal
cd /d "%~dp0\.."
python tools\build_polymarket_auto_governance.py %*
endlocal
