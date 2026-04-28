@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%build_optimizer_v2_plan.py" %*
endlocal
