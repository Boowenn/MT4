@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

python "%REPO_ROOT%\tools\run_param_lab.py" --runtime-dir "%RUNTIME_DIR%" %*

endlocal
