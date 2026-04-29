@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "RUNTIME_DIR=%QG_MT5_FILES_DIR%"
if "%RUNTIME_DIR%"=="" set "RUNTIME_DIR=C:\Program Files\HFM Metatrader 5\MQL5\Files"
set "DASHBOARD_DIR=%SCRIPT_DIR%..\Dashboard"
set "CYCLES=%QG_POLYMARKET_RADAR_WORKER_CYCLES%"
if "%CYCLES%"=="" set "CYCLES=1"
set "INTERVAL=%QG_POLYMARKET_RADAR_WORKER_INTERVAL_SECONDS%"
if "%INTERVAL%"=="" set "INTERVAL=900"
set "QUEUE_MIN_SCORE=%QG_POLYMARKET_RADAR_QUEUE_MIN_SCORE%"
if "%QUEUE_MIN_SCORE%"=="" set "QUEUE_MIN_SCORE=45"
python "%SCRIPT_DIR%run_polymarket_radar_worker_v2.py" --runtime-dir "%RUNTIME_DIR%" --dashboard-dir "%DASHBOARD_DIR%" --cycles "%CYCLES%" --interval-seconds "%INTERVAL%" --queue-min-score "%QUEUE_MIN_SCORE%"
