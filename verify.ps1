# Finetune Platform - Service Checker
$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Service Status Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Backend
Write-Host "Backend (127.0.0.1:8000)..." -ForegroundColor Yellow
try {
    $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  [OK] Running" -ForegroundColor Green
    Write-Host "  Version: $($r.version)" -ForegroundColor Gray
} catch {
    Write-Host "  [FAIL] Not running" -ForegroundColor Red
}

Write-Host ""
Write-Host "Frontend (localhost:5173)..." -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:5173' -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Host "  [OK] Running (Status: $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Not running" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
