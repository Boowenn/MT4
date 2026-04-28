@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"
set "POLYMARKET_ROOT=%~2"
if "%POLYMARKET_ROOT%"=="" set "POLYMARKET_ROOT=D:\polymarket"

python "%REPO_ROOT%\tools\build_polymarket_research_bridge.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard" --polymarket-root "%POLYMARKET_ROOT%"
endlocal
