@echo off
chcp 65001 >nul
title Finetune Platform - 快速验证

echo ========================================
echo   Finetune Platform - 服务验证
echo ========================================
echo.

REM 检查后端
echo 检查后端服务 (127.0.0.1:8000)...
powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 3 -ErrorAction Stop; Write-Host '[OK] 后端运行中' -ForegroundColor Green } catch { Write-Host '[FAIL] 后端未运行' -ForegroundColor Red }"

echo.

REM 检查前端
echo 检查前端服务 (localhost:5173)...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5173' -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop; Write-Host '[OK] 前端运行中' -ForegroundColor Green } catch { Write-Host '[FAIL] 前端未运行' -ForegroundColor Red }"

echo.

REM 检查 API 文档
echo 检查 API 文档...
powershell -Command "try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/docs' -TimeoutSec 3 -ErrorAction Stop; Write-Host '[OK] API 文档可访问' -ForegroundColor Green } catch { Write-Host '[WARN] API 文档访问失败' -ForegroundColor Yellow }"

echo.
echo ========================================
echo.
echo 提示：运行 start.bat 启动服务
echo.
pause
