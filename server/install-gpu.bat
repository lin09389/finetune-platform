@echo off
chcp 65001 >nul
setlocal
title PyTorch GPU 安装器

echo ========================================
echo   PyTorch GPU 版本安装
echo ========================================
echo.
echo 目标版本：PyTorch 2.2.2 + CUDA 12.1
echo 依赖来源：pyproject.toml + uv.lock，GPU extra 安装 bitsandbytes
echo.

cd /d "%~dp0.."

echo [1/4] 检查 uv...
where uv >nul 2>&1
if errorlevel 1 (
    echo 未检测到 uv，正在安装 uv...
    python -m pip install uv
    if errorlevel 1 (
        echo [错误] uv 安装失败
        pause
        exit /b 1
    )
)

echo.
echo [2/4] 同步项目依赖（含 GPU extra）...
uv sync --frozen --extra gpu
if errorlevel 1 (
    echo [错误] uv sync --extra gpu 失败
    pause
    exit /b 1
)

echo.
echo [3/4] 安装 CUDA 12.1 PyTorch wheel...
uv pip install --reinstall torch==2.2.2 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (
    echo [错误] CUDA 12.1 PyTorch wheel 安装失败
    pause
    exit /b 1
)

echo.
echo [4/4] 验证安装...
uv run python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA 可用:', torch.cuda.is_available()); print('CUDA 版本:', torch.version.cuda); print('GPU 名称:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo.
echo ========================================
echo   安装完成
echo ========================================
pause
