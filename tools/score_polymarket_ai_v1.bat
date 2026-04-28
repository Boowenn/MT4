@echo off
setlocal
set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "RUNTIME_DIR=%~1"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"
set "LLM_MODE=%QG_POLYMARKET_AI_LLM_MODE%"
if "%LLM_MODE%"=="" set "LLM_MODE=auto"
set "LLM_ENV_FILE=%QG_POLYMARKET_AI_LLM_ENV_FILE%"
if "%LLM_ENV_FILE%"=="" set "LLM_ENV_FILE=D:\polymarket\.env"
set "LLM_MAX=%QG_POLYMARKET_AI_LLM_MAX_CANDIDATES%"
if "%LLM_MAX%"=="" set "LLM_MAX=8"

python "%REPO_ROOT%\tools\score_polymarket_ai_v1.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%REPO_ROOT%\Dashboard" --history-dir "%REPO_ROOT%\archive\polymarket\history" --db-path "%REPO_ROOT%\archive\polymarket\history\QuantGod_PolymarketHistory.sqlite" --llm-mode "%LLM_MODE%" --llm-env-file "%LLM_ENV_FILE%" --llm-max-candidates "%LLM_MAX%"
endlocal
