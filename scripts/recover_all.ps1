# ==============================================================================
# scripts/recover_all.ps1 — Automated Self-Healing & Disaster Recovery Script
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RootPath = "D:\AlgoTrading"
$PythonExe = "$RootPath\.venv\Scripts\python.exe"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  ALGOTRADING AUTOMATED PLATFORM SELF-HEALING & RECOVERY         " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$Report = @{
    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    actions_taken = @()
    status = "SUCCESS"
}

# 1. Recover Docker Containers
Write-Host "`n[1/5] Checking Docker Infrastructure Containers..." -ForegroundColor Yellow
$containers = docker compose ps --format json | ConvertFrom-Json
$required = @("redpanda-1", "redpanda-2", "jobmanager", "taskmanager", "price-producer", "news-producer")

foreach ($svc in $required) {
    $found = $containers | Where-Object { $_.Service -eq $svc -and $_.State -eq "running" }
    if (-not $found) {
        Write-Host "  [!] Container $svc is down or missing. Recovering..." -ForegroundColor Yellow
        docker compose up -d $svc
        $Report.actions_taken += "Restarted container: $svc"
    } else {
        Write-Host "  [OK] Container $svc is running." -ForegroundColor Green
    }
}

# 2. Recover Stale Locks
Write-Host "`n[2/5] Inspecting PID Lock Files..." -ForegroundColor Yellow
$lockFiles = Get-ChildItem -Path "$RootPath\data\locks\*.pid" -ErrorAction SilentlyContinue
foreach ($lf in $lockFiles) {
    try {
        $pidNum = [int](Get-Content $lf.FullName).Trim()
        $proc = Get-Process -Id $pidNum -ErrorAction SilentlyContinue
        if (-not $proc) {
            Write-Host "  [!] Stale lock detected for dead PID $pidNum ($($lf.Name)). Removing..." -ForegroundColor Yellow
            Remove-Item $lf.FullName -Force -ErrorAction SilentlyContinue
            $Report.actions_taken += "Removed stale lock: $($lf.Name) (dead PID $pidNum)"
        } else {
            Write-Host "  [OK] Active process lock verified: $($lf.Name) (PID $pidNum)" -ForegroundColor Green
        }
    } catch {
        Remove-Item $lf.FullName -Force -ErrorAction SilentlyContinue
    }
}

# 3. Recover Flink Streaming Jobs
Write-Host "`n[3/5] Verifying Flink Streaming Jobs & Checkpoint Continuity..." -ForegroundColor Yellow
try {
    $overview = Invoke-RestMethod -Uri "http://localhost:8081/jobs/overview" -TimeoutSec 5
    $activeJobs = $overview.jobs | Where-Object { $_.state -eq "RUNNING" }
    
    $hasStocks = $activeJobs | Where-Object { $_.name -like "*trading_signals*" }
    if (-not $hasStocks) {
        Write-Host "  [!] Stocks Flink Job missing. Resubmitting with checkpoint restore..." -ForegroundColor Yellow
        & $PythonExe "$RootPath\submit_flink_job.py"
        $Report.actions_taken += "Resubmitted Stocks Flink Job"
    } else {
        Write-Host "  [OK] Stocks Flink Job is healthy (JID: $($hasStocks.jid))." -ForegroundColor Green
    }
    
    $hasCrypto = $activeJobs | Where-Object { $_.name -like "*crypto_signals*" }
    if (-not $hasCrypto) {
        Write-Host "  [!] Crypto Flink Job missing. Resubmitting with checkpoint restore..." -ForegroundColor Yellow
        & $PythonExe "$RootPath\submit_crypto_flink_job.py"
        $Report.actions_taken += "Resubmitted Crypto Flink Job"
    } else {
        Write-Host "  [OK] Crypto Flink Job is healthy (JID: $($hasCrypto.jid))." -ForegroundColor Green
    }
} catch {
    Write-Host "  [!] Flink JobManager unreachable: $_" -ForegroundColor Red
    $Report.actions_taken += "Flink JobManager unreachable"
}

# 4. Recover FastAPI Dashboard Backend
Write-Host "`n[4/5] Checking FastAPI Dashboard Backend (Port 8005)..." -ForegroundColor Yellow
$backendConn = Get-NetTCPConnection -LocalPort 8005 -ErrorAction SilentlyContinue
if (-not $backendConn) {
    Write-Host "  [!] Backend port 8005 down. Relaunching..." -ForegroundColor Yellow
    Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir `"$RootPath\trading-dashboard\backend`"" -WorkingDirectory $RootPath -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $Report.actions_taken += "Relaunched FastAPI backend on port 8005"
    Write-Host "  [OK] Backend relaunched." -ForegroundColor Green
} else {
    Write-Host "  [OK] Backend port 8005 is active." -ForegroundColor Green
}

# 5. Persist Recovery Report
Write-Host "`n[5/5] Generating Recovery Audit Report..." -ForegroundColor Yellow
$statusDir = "$RootPath\data\status"
if (-not (Test-Path $statusDir)) { New-Item -ItemType Directory -Path $statusDir -Force }
$reportPath = "$statusDir\recovery_report.json"
$Report | ConvertTo-Json -Depth 5 | Set-Content -Path $reportPath -Encoding UTF8
Write-Host "  [OK] Recovery report saved: $reportPath" -ForegroundColor Green

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  RECOVERY EXECUTION COMPLETED. TOTAL ACTIONS: $($Report.actions_taken.Count)" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan

