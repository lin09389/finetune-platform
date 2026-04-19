@echo off
chcp 65001 >nul
title Finetune Platform
if not defined SystemRoot set "SystemRoot=C:\Windows"
if not defined WINDIR set "WINDIR=C:\Windows"
if not defined SystemDrive set "SystemDrive=C:"

echo ========================================
echo   Finetune Platform 启动器
echo ========================================
echo.

cd /d "%~dp0"

REM 检查 Python
echo [1/4] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python 已安装

REM 检查 Node.js
echo [2/4] 检查 Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)
echo [OK] Node.js 已安装

REM 检查后端依赖
echo [3/4] 检查后端依赖...
cd /d "%~dp0server"
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo 正在安装后端依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if errorlevel 1 (
        echo [错误] 后端依赖安装失败
        pause
        exit /b 1
    )
)
echo [OK] 后端依赖已就绪

REM 检查前端依赖
echo [4/4] 检查前端依赖...
cd /d "%~dp0client"
if not exist node_modules (
    echo 正在安装前端依赖...
    call npm install --registry=https://registry.npmmirror.com
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败
        pause
        exit /b 1
    )
)
echo [OK] 前端依赖已就绪

echo.
echo ========================================
echo   启动服务...
echo ========================================
echo.

REM 启动后端
echo [后端] 启动中...
start "Finetune - 后端" cmd /k "cd /d "%~dp0server" && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

REM 等待后端启动
echo 等待后端启动 (5 秒)...
timeout /t 5 /nobreak >nul

REM 检查后端是否启动成功
powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 3 -ErrorAction Stop; Write-Host '[OK] 后端启动成功' -ForegroundColor Green } catch { Write-Host '[警告] 后端可能未启动成功' -ForegroundColor Yellow }"

echo.

REM 启动前端
echo [前端] 启动中...
start "Finetune - 前端" cmd /k "cd /d "%~dp0client" && npm run dev"

echo.
echo ========================================
echo   启动完成!
echo ========================================
echo.
echo   前端地址：http://localhost:5173
echo   后端地址：http://127.0.0.1:8000
echo   API 文档：http://127.0.0.1:8000/docs
echo.
echo   请打开浏览器访问：http://localhost:5173
echo.
echo ========================================
echo.
pause
