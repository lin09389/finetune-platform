# Finetune Platform 启动脚本 (PowerShell)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:SystemRoot) { $env:SystemRoot = "C:\Windows" }
if (-not $env:WINDIR) { $env:WINDIR = "C:\Windows" }
if (-not $env:SystemDrive) { $env:SystemDrive = "C:" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Finetune Platform 启动器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
Write-Host "[1/4] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [错误] 未找到 Python" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查 Node.js
Write-Host "[2/4] 检查 Node.js 环境..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "  Node.js $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  [错误] 未找到 Node.js" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查后端依赖
Write-Host "[3/4] 检查后端依赖..." -ForegroundColor Yellow
$serverDir = Join-Path $projectRoot "server"
$useUv = $false
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Push-Location $projectRoot
    try {
        Write-Host "  使用 uv sync --frozen" -ForegroundColor Yellow
        uv sync --frozen
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed"
        }
        $useUv = $true
        Write-Host "  [OK] 后端依赖已就绪" -ForegroundColor Green
    } catch {
        Write-Host "  [错误] uv 依赖同步失败：$_" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    } finally {
        Pop-Location
    }
} else {
    Push-Location $serverDir
    try {
        python -c "import fastapi" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  未检测到 uv，使用 pip 回退兼容路径..." -ForegroundColor Yellow
            pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
        }
        Write-Host "  [OK] 后端依赖已就绪" -ForegroundColor Green
    } catch {
        Write-Host "  [警告] 依赖检查失败" -ForegroundColor Yellow
    } finally {
        Pop-Location
    }
}

# 检查前端依赖
Write-Host "[4/4] 检查前端依赖..." -ForegroundColor Yellow
$clientDir = Join-Path $projectRoot "client"
Push-Location $clientDir
if (-not (Test-Path "node_modules")) {
    Write-Host "  正在安装前端依赖..." -ForegroundColor Yellow
    npm install --registry=https://registry.npmmirror.com
}
Write-Host "  [OK] 前端依赖已就绪" -ForegroundColor Green
Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动服务..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 启动推理服务
Write-Host "[推理服务] 启动中..." -ForegroundColor Yellow
$inferenceJob = Start-Job -ScriptBlock {
    param($dir, $useUv)
    if (-not $env:SystemRoot) { $env:SystemRoot = "C:\Windows" }
    if (-not $env:WINDIR) { $env:WINDIR = "C:\Windows" }
    if (-not $env:SystemDrive) { $env:SystemDrive = "C:" }
    Set-Location $dir
    if ($useUv) {
        uv run --extra all python -m server.inference_server
    } else {
        Set-Location (Join-Path $dir "server")
        python -m inference_server
    }
} -ArgumentList $projectRoot, $useUv

# 启动训练 Worker
Write-Host "[训练 Worker] 启动中..." -ForegroundColor Yellow
$workerJob = Start-Job -ScriptBlock {
    param($dir, $useUv)
    if (-not $env:SystemRoot) { $env:SystemRoot = "C:\Windows" }
    if (-not $env:WINDIR) { $env:WINDIR = "C:\Windows" }
    if (-not $env:SystemDrive) { $env:SystemDrive = "C:" }
    Set-Location $dir
    if ($useUv) {
        uv run --extra all python -m server.training_worker
    } else {
        Set-Location (Join-Path $dir "server")
        python -m training_worker
    }
} -ArgumentList $projectRoot, $useUv

# 启动后端
Write-Host "[后端] 启动中..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    param($dir, $useUv)
    if (-not $env:SystemRoot) { $env:SystemRoot = "C:\Windows" }
    if (-not $env:WINDIR) { $env:WINDIR = "C:\Windows" }
    if (-not $env:SystemDrive) { $env:SystemDrive = "C:" }
    Set-Location $dir
    if ($useUv) {
        uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
    } else {
        Set-Location (Join-Path $dir "server")
        python -m uvicorn main:app --host 127.0.0.1 --port 8010
    }
} -ArgumentList $projectRoot, $useUv

# 等待后端启动
Write-Host "  等待后端启动 (5 秒)..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# 检查后端是否启动成功
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8010/" -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  [OK] 后端启动成功：$($response.message)" -ForegroundColor Green
} catch {
    Write-Host "  [警告] 后端可能未启动成功，请检查新窗口中的错误信息" -ForegroundColor Yellow
}

# 启动前端
Write-Host "[前端] 启动中..." -ForegroundColor Yellow
$frontendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    npm run dev
} -ArgumentList $clientDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  启动完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  后端地址：http://127.0.0.1:8010" -ForegroundColor White
Write-Host "  前端地址：http://localhost:5173" -ForegroundColor White
Write-Host "  API 文档：http://127.0.0.1:8010/docs" -ForegroundColor White
Write-Host "  推理服务：http://127.0.0.1:8020（内部）" -ForegroundColor White
Write-Host ""
Write-Host "  提示：首次启动可能需要几分钟安装依赖" -ForegroundColor Gray
Write-Host ""
Write-Host "  按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

# 等待
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-Job -Job $inferenceJob -ErrorAction SilentlyContinue
    Stop-Job -Job $workerJob -ErrorAction SilentlyContinue
    Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
    Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $inferenceJob, $workerJob, $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
}
