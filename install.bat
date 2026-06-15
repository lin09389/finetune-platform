@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Finetune Platform 依赖安装
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   错误: 未找到 Python，请先安装 Python 3.11
    pause
    exit /b 1
)
echo   OK

echo [2/3] 安装前端依赖...
cd /d "%~dp0client"
if exist package.json (
    echo   使用镜像: registry.npmmirror.com
    call npm install --registry=https://registry.npmmirror.com
    if errorlevel 1 (
        echo   前端依赖安装失败
        pause
        exit /b 1
    )
    echo   前端依赖安装完成
) else (
    echo   错误: package.json 不存在
    pause
    exit /b 1
)

echo.
echo [3/3] 安装后端依赖...
cd /d "%~dp0"
where uv >nul 2>&1
if errorlevel 1 (
    echo   未检测到 uv，正在安装 uv...
    python -m pip install uv
    if errorlevel 1 (
        echo   uv 安装失败，回退到 pip 兼容安装...
        cd /d "%~dp0server"
        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
        if errorlevel 1 (
            echo   后端依赖安装失败
            pause
            exit /b 1
        )
        goto :backend_done
    )
)

cd /d "%~dp0"
echo   使用 uv sync --frozen --extra dev
uv sync --frozen --extra dev
if errorlevel 1 (
    echo   uv 安装失败，回退到 pip 兼容安装...
    cd /d "%~dp0server"
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if errorlevel 1 (
        echo   后端依赖安装失败
        pause
        exit /b 1
    )
)

:backend_done
if not exist "%~dp0server\requirements.txt" (
    echo   错误: server\requirements.txt 不存在
    pause
    exit /b 1
)
echo   后端依赖安装完成

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 启动方式:
echo   1. 双击运行 start.bat
echo   2. 或手动启动:
echo      cd server ^&^& uvicorn main:app --reload
echo      cd client ^&^& npm run dev
echo.
echo 提示: 后端依赖以 pyproject.toml + uv.lock 为准:
echo   uv sync --frozen --extra dev
echo.
pause
