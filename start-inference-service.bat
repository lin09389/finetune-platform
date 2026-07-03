@echo off
chcp 65001 >nul
title Finetune Platform - Local Inference Service
cd /d "%~dp0"

where uv >nul 2>&1
if not errorlevel 1 (
    uv run python -m server.inference_server
) else if exist "%~dp0.venv\Scripts\python.exe" (
    cd /d "%~dp0server"
    "%~dp0.venv\Scripts\python.exe" -m inference_server
) else (
    cd /d "%~dp0server"
    python -m inference_server
)
pause
