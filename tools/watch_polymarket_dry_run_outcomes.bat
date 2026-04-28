@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

python "%REPO_ROOT%\tools\watch_polymarket_dry_run_outcomes.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard"
endlocal
