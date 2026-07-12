@echo off
chcp 65001 >nul
if not defined SystemRoot set "SystemRoot=C:\Windows"
if not defined WINDIR set "WINDIR=C:\Windows"
if not defined SystemDrive set "SystemDrive=C:"
echo 启动后端服务...
cd /d "%~dp0"
where uv >nul 2>&1
if not errorlevel 1 (
    uv sync --frozen --extra all
    if errorlevel 1 (
        echo [错误] uv 依赖同步失败
        pause
        exit /b 1
    )
    start "Finetune - 推理服务" /d "%~dp0" cmd /k uv run --extra all python -m server.inference_server
    start "Finetune - 训练 Worker" /d "%~dp0" cmd /k uv run --extra all python -m server.training_worker
    uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010 --log-level debug
) else (
    echo [警告] 未检测到 uv。Agent 依赖请优先安装 uv 后使用: uv sync --extra all
    cd /d "%~dp0server"
    if exist "%~dp0.venv\Scripts\python.exe" (
        echo [信息] 使用仓库 .venv 启动（推荐仍安装 uv）
        start "Finetune - 推理服务" /d "%~dp0server" cmd /k "%~dp0.venv\Scripts\python.exe" -m inference_server
        start "Finetune - 训练 Worker" /d "%~dp0server" cmd /k "%~dp0.venv\Scripts\python.exe" -m training_worker
        "%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level debug
    ) else (
        echo [警告] 使用系统 Python 启动。可能缺少 langchain-deepseek / deepagents 等 Agent 依赖。
        echo         请安装 uv 后执行: uv sync --extra all
        echo         推荐命令: uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
        start "Finetune - 推理服务" /d "%~dp0server" cmd /k python -m inference_server
        start "Finetune - 训练 Worker" /d "%~dp0server" cmd /k python -m training_worker
        python -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level debug
    )
)
pause
