@echo off
chcp 65001 >nul
title Finetune Platform - Training Worker
cd /d "%~dp0"

where uv >nul 2>&1
if not errorlevel 1 (
    uv run python -m server.training_worker
) else if exist "%~dp0.venv\Scripts\python.exe" (
    cd /d "%~dp0server"
    "%~dp0.venv\Scripts\python.exe" -m training_worker
) else (
    cd /d "%~dp0server"
    python -m training_worker
)
pause
