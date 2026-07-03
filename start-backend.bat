@echo off
chcp 65001 >nul
if not defined SystemRoot set "SystemRoot=C:\Windows"
if not defined WINDIR set "WINDIR=C:\Windows"
if not defined SystemDrive set "SystemDrive=C:"
echo 启动后端服务...
cd /d "%~dp0"
where uv >nul 2>&1
if not errorlevel 1 (
    uv sync --frozen
    if errorlevel 1 (
        echo [错误] uv 依赖同步失败
        pause
        exit /b 1
    )
    start "Finetune - 推理服务" /d "%~dp0" cmd /k uv run python -m server.inference_server
    start "Finetune - 训练 Worker" /d "%~dp0" cmd /k uv run python -m server.training_worker
    uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010 --log-level debug
) else (
    cd /d "%~dp0server"
    if exist "%~dp0.venv\Scripts\python.exe" (
        start "Finetune - 推理服务" /d "%~dp0server" cmd /k "%~dp0.venv\Scripts\python.exe" -m inference_server
        start "Finetune - 训练 Worker" /d "%~dp0server" cmd /k "%~dp0.venv\Scripts\python.exe" -m training_worker
        "%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level debug
    ) else (
        start "Finetune - 推理服务" /d "%~dp0server" cmd /k python -m inference_server
        start "Finetune - 训练 Worker" /d "%~dp0server" cmd /k python -m training_worker
        python -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level debug
    )
)
pause
