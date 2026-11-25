# ==============================================================================
# Script: run-dashboard.ps1
# Description: Automated launcher for Live Trading Visualization Dashboard
# ==============================================================================

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Starting Real-Time Algo-Trading Dashboard System  " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$RootPath = "D:\AlgoTrading"
$BackendPath = "$RootPath\trading-dashboard\backend"
$FrontendPath = "$RootPath\trading-dashboard\frontend"
$PythonExe = "$RootPath\.venv\Scripts\python.exe"

# 1. Check Backend Port 8005
$BackendConn = Get-NetTCPConnection -LocalPort 8005 -ErrorAction SilentlyContinue
if ($BackendConn) {
    Write-Host "[OK] Backend already running on http://localhost:8005" -ForegroundColor Green
} else {
    Write-Host "[*] Launching FastAPI backend on http://localhost:8005..." -ForegroundColor Yellow
    Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir `"$BackendPath`"" -WorkingDirectory $RootPath -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "[OK] Backend started." -ForegroundColor Green
}

# 2. Check Frontend Port 5173
$FrontendConn = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue
if ($FrontendConn) {
    Write-Host "[OK] Frontend already running on http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "[*] Launching Vite frontend on http://localhost:5173..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev -- --host 0.0.0.0 --port 5173" -WorkingDirectory $FrontendPath -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "[OK] Frontend started." -ForegroundColor Green
}

# 3. Check Continuous Market Data Producers
Write-Host "[*] Checking Continuous Market Data Producers..." -ForegroundColor Yellow
& "$RootPath\run-producers.ps1" -Action start

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  DASHBOARD SERVICES READY:" -ForegroundColor Green
Write-Host "  - Trading Terminal UI:   http://localhost:5173" -ForegroundColor White
Write-Host "  - Backend REST API:      http://localhost:8005/docs" -ForegroundColor White
Write-Host "  - WebSocket Stream:      ws://localhost:8005/ws/live" -ForegroundColor White
Write-Host "  - Redpanda Console:      http://localhost:8080" -ForegroundColor White
Write-Host "  - Apache Flink Engine:   http://localhost:8081" -ForegroundColor White
Write-Host "  - Continuous Producers:  Active (Price & News)" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor Cyan
