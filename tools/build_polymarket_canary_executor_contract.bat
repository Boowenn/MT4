@echo off
setlocal
set "ROOT=%~dp0.."
set "RUNTIME=%~1"
if "%RUNTIME%"=="" set "RUNTIME=C:\Program Files\HFM Metatrader 5\MQL5\Files"
python "%ROOT%\tools\build_polymarket_canary_executor_contract.py" --runtime-dir "%RUNTIME%" --dashboard-dir "%ROOT%\Dashboard"
endlocal
