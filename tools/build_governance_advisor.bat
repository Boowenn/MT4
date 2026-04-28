@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

python "%REPO_ROOT%\tools\build_governance_advisor.py" --runtime-dir "%RUNTIME_DIR%"
endlocal
