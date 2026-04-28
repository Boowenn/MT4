@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"
set "TESTER_ROOT=%REPO_ROOT%\runtime\HFM_MT5_Tester_Isolated"

python "%REPO_ROOT%\tools\run_param_lab_auto_tester_window.py" --runtime-dir "%RUNTIME_DIR%" --tester-root "%TESTER_ROOT%" --require-isolated-tester %*

endlocal
