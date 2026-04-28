@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"

python "%REPO_ROOT%\tools\build_param_optimization_plan.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\watch_param_lab_reports.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_governance_advisor.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_strategy_version_registry.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_optimizer_v2_plan.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_version_promotion_gate.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_param_lab_auto_scheduler.py" --runtime-dir "%RUNTIME_DIR%"
python "%REPO_ROOT%\tools\build_governance_advisor.py" --runtime-dir "%RUNTIME_DIR%"
endlocal
