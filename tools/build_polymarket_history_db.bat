@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

python "%REPO_ROOT%\tools\build_polymarket_history_db.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard" --history-dir "%REPO_ROOT%\archive\polymarket\history"
endlocal
