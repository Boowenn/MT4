@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

set "QUERY="
if "%~2"=="" goto run_analysis
shift
:collect_query
if "%~1"=="" goto run_analysis
if defined QUERY (
    set "QUERY=%QUERY% %~1"
) else (
    set "QUERY=%~1"
)
shift
goto collect_query

:run_analysis
if defined QUERY (
    python "%REPO_ROOT%\tools\analyze_polymarket_single_market.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard" --query "%QUERY%"
) else (
    python "%REPO_ROOT%\tools\analyze_polymarket_single_market.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard"
)
endlocal
