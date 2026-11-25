# ==============================================================================
# scripts/start_all.ps1 — Start Entire AlgoTrading Platform (Stocks & Crypto)
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RootPath = "D:\AlgoTrading"
$PythonExe = "$RootPath\.venv\Scripts\python.exe"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Starting AlgoTrading Platform Services (Production/DRY_RUN)...  " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Verify Docker Engine
Write-Host "`n[1/6] Verifying Docker Engine..." -ForegroundColor Yellow
$dockerReady = $false
try {
    $info = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { $dockerReady = $true }
} catch {}

if (-not $dockerReady) {
    Write-Host "[*] Docker not running. Starting Docker Desktop..." -ForegroundColor Yellow
    & "$RootPath\start_docker.ps1"
} else {
    Write-Host "[OK] Docker Engine is running." -ForegroundColor Green
}

# 2. Start Core Docker Infrastructure
Write-Host "`n[2/6] Starting Redpanda & Flink Containers..." -ForegroundColor Yellow
docker compose up -d redpanda-1 redpanda-2 jobmanager taskmanager price-producer news-producer
Start-Sleep -Seconds 3

# 3. Verify / Submit Flink Streaming Jobs
Write-Host "`n[3/6] Checking Flink Streaming Jobs..." -ForegroundColor Yellow
try {
    $overview = Invoke-RestMethod -Uri "http://localhost:8081/jobs/overview" -TimeoutSec 5
    $activeJobs = $overview.jobs | Where-Object { $_.state -eq "RUNNING" }
    
    $hasStocks = $activeJobs | Where-Object { $_.name -like "*trading_signals*" }
    if (-not $hasStocks) {
        Write-Host "[*] Submitting Stocks Flink Job..." -ForegroundColor Yellow
        & $PythonExe "$RootPath\submit_flink_job.py"
    } else {
        Write-Host "[OK] Stocks Flink Job is active." -ForegroundColor Green
    }
    
    $hasCrypto = $activeJobs | Where-Object { $_.name -like "*crypto_signals*" }
    if (-not $hasCrypto) {
        Write-Host "[*] Submitting Crypto Flink Job..." -ForegroundColor Yellow
        & $PythonExe "$RootPath\submit_crypto_flink_job.py"
    } else {
        Write-Host "[OK] Crypto Flink Job is active." -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Flink JobManager not ready yet: $_" -ForegroundColor Yellow
}

# 4. Start Signal Handlers (Host / Background)
Write-Host "`n[4/6] Verifying Signal Handlers (DRY_RUN Mode)..." -ForegroundColor Yellow
$shProc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    $cmd -like "*signal-handler.py*"
}
if (-not $shProc) {
    Write-Host "[*] Launching Stocks Signal Handler..." -ForegroundColor Yellow
    Start-Process -FilePath $PythonExe -ArgumentList "$RootPath\signal-handler.py" -WorkingDirectory $RootPath -WindowStyle Hidden
} else {
    Write-Host "[OK] Stocks Signal Handler already running." -ForegroundColor Green
}

$cshProc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    $cmd -like "*crypto_signal_handler.py*"
}
if (-not $cshProc) {
    Write-Host "[*] Launching Crypto Signal Handler..." -ForegroundColor Yellow
    Start-Process -FilePath $PythonExe -ArgumentList "$RootPath\crypto_signal_handler.py" -WorkingDirectory $RootPath -WindowStyle Hidden
} else {
    Write-Host "[OK] Crypto Signal Handler already running." -ForegroundColor Green
}

# 5. Start FastAPI Backend on Port 8005
Write-Host "`n[5/6] Verifying FastAPI Dashboard Backend..." -ForegroundColor Yellow
$backendConn = Get-NetTCPConnection -LocalPort 8005 -ErrorAction SilentlyContinue
if (-not $backendConn) {
    Write-Host "[*] Launching FastAPI backend on http://localhost:8005..." -ForegroundColor Yellow
    Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir `"$RootPath\trading-dashboard\backend`"" -WorkingDirectory $RootPath -WindowStyle Hidden
    Start-Sleep -Seconds 2
} else {
    Write-Host "[OK] FastAPI backend is running on http://localhost:8005" -ForegroundColor Green
}

# 6. Final Status Summary
Write-Host "`n[6/6] Platform Startup Complete!" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  - REST API & Health:   http://localhost:8005/api/health" -ForegroundColor White
Write-Host "  - Pipeline Telemetry:  http://localhost:8005/api/system/status" -ForegroundColor White
Write-Host "  - WebSocket Stream:    ws://localhost:8005/ws/live" -ForegroundColor White
Write-Host "  - Apache Flink WebUI:  http://localhost:8081" -ForegroundColor White
Write-Host "  - Redpanda Brokers:    localhost:9092, localhost:9093" -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Cyan

